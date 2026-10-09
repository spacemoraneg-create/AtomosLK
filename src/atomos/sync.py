"""
Atomos GitHub Synchronization Service

Enables committing and syncing updated database (atomos.db) and static exports
directly back to the GitHub repository from the running application instance.
Supports both:
1. Local Git CLI push (with Git Credential Manager or token-authenticated remote)
2. GitHub Git Data (Blobs / Trees / Commits) REST API for single-commit atomic cloud sync
   supporting files > 1 MB (up to 100 MB).
"""

import base64
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


DEFAULT_REPO = os.environ.get("GITHUB_REPO", "spacemoraneg-create/AtomosLK")
DEFAULT_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / "data" / ".github_token"
_SYNC_LOCK = threading.Lock()


def load_persisted_github_token() -> Optional[str]:
    """Load persisted GitHub token from data/.github_token or .env if present."""
    env_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_tok and env_tok.strip():
        return env_tok.strip()
    try:
        if TOKEN_FILE.exists():
            val = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except Exception:
        pass
    return None


def save_persisted_github_token(token: Optional[str]) -> None:
    """Persist or clear GitHub token in data/.github_token."""
    try:
        if token and token.strip():
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(token.strip(), encoding="utf-8")
            os.environ["GITHUB_TOKEN"] = token.strip()
        else:
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            os.environ.pop("GITHUB_TOKEN", None)
    except Exception:
        pass


class GitHubSyncService:
    def __init__(
        self,
        token: Optional[str] = None,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
    ):
        self.token = (token.strip() if token and token.strip() else None) or load_persisted_github_token()
        if token and token.strip():
            save_persisted_github_token(token.strip())
        self.repo = repo
        self.branch = branch
        self.root_dir = Path(__file__).resolve().parent.parent.parent

    def has_git_cli_remote(self) -> bool:
        """Check whether the local directory is a git repository with an origin remote."""
        try:
            git_dir = self.root_dir / ".git"
            if not git_dir.exists():
                return False
            res = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False

    def get_head_commit_sha(self) -> Optional[str]:
        """Return current local HEAD commit SHA (short) if available."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def get_auth_mode(self) -> str:
        if self.token:
            return "token"
        if self.has_git_cli_remote():
            return "git_cli"
        return "unconfigured"

    def is_configured(self) -> bool:
        return bool(self.token) or self.has_git_cli_remote()

    def sync_database_and_export(
        self,
        db_path: Path,
        export_dir: Path,
        commit_message: str = "chore(data): auto-sync atomos.db and web export after admin update",
    ) -> Dict[str, Any]:
        """
        Synchronizes atomos.db and all web_export/*.json files to GitHub.
        1. Tries local git CLI commit & push first (keeps local git history & remote in sync).
        2. Falls back to GitHub Git Data (Blobs/Trees/Commits) API if git CLI push is unavailable.
        """
        with _SYNC_LOCK:
            # Collect all target files to sync
            files_to_sync: List[tuple[Path, str]] = []
            if db_path.exists():
                files_to_sync.append((db_path, "data/atomos.db"))

            if export_dir.exists():
                for jf in sorted(export_dir.glob("*.json")):
                    files_to_sync.append((jf, f"data/web_export/{jf.name}"))
                brackets_dir = export_dir / "brackets"
                if brackets_dir.exists():
                    for bf in sorted(brackets_dir.glob("*.json")):
                        files_to_sync.append((bf, f"data/web_export/brackets/{bf.name}"))

            synced_rel_paths = [rel for _, rel in files_to_sync]

            # Strategy 1: Local Git CLI commit + push
            if self.has_git_cli_remote():
                cli_res = self._try_git_cli_push(commit_message, synced_rel_paths)
                if cli_res.get("success"):
                    return cli_res
                # If CLI failed and we have a token, fall through to GitHub Git Data API
                if not self.token:
                    return cli_res

            # Strategy 2: GitHub Git Data (Blobs/Trees/Commits) API
            if self.token:
                return self._sync_via_git_trees_api(files_to_sync, commit_message)

            return {
                "success": False,
                "error": "Neither GITHUB_TOKEN nor local git push credentials are configured.",
            }

    def _try_git_cli_push(self, commit_message: str, synced_rel_paths: List[str]) -> Dict[str, Any]:
        """Commits and pushes data/atomos.db and data/web_export/ via git CLI."""
        try:
            lock_file = self.root_dir / ".git" / "index.lock"
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass
            subprocess.run(
                ["git", "add", "data/atomos.db", "data/web_export/"],
                cwd=str(self.root_dir),
                check=False,
                timeout=15,
            )

            status = subprocess.run(
                ["git", "status", "--porcelain", "data/atomos.db", "data/web_export/"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if status.stdout.strip():
                commit_proc = subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if commit_proc.returncode != 0 and "nothing to commit" not in (commit_proc.stdout + commit_proc.stderr).lower():
                    return {
                        "success": False,
                        "error": f"git commit failed: {(commit_proc.stderr or commit_proc.stdout).strip()[:200]}",
                    }

            # Push to origin
            push = subprocess.run(
                ["git", "push", "origin", self.branch],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=45,
            )
            if push.returncode != 0 and self.token:
                # Retry push using token-authenticated URL
                auth_url = f"https://x-access-token:{self.token}@github.com/{self.repo}.git"
                push = subprocess.run(
                    ["git", "push", auth_url, f"HEAD:{self.branch}"],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    timeout=45,
                )

            if push.returncode == 0:
                sha = self.get_head_commit_sha()
                return {
                    "success": True,
                    "message": f"Synchronized {len(synced_rel_paths)} files to GitHub ({self.repo} @ {self.branch}, commit {sha or 'HEAD'}).",
                    "synced_files": synced_rel_paths,
                    "commit_sha": sha,
                    "repo": self.repo,
                    "branch": self.branch,
                }

            return {
                "success": False,
                "error": f"git push failed: {(push.stderr or push.stdout).strip()[:200]}",
            }
        except Exception as e:
            return {"success": False, "error": f"Git CLI sync error: {str(e)}"}

    def _sync_via_git_trees_api(
        self,
        files_to_sync: List[tuple[Path, str]],
        commit_message: str,
    ) -> Dict[str, Any]:
        """
        Atomically commits all files in a single GitHub commit using the Git Data API
        (Blobs + Trees + Commits + Refs). Supports files > 1 MB (up to 100 MB).
        """
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Atomos-Cloud-Sync",
        }
        base_url = f"https://api.github.com/repos/{self.repo}"

        try:
            # 1. Get current branch reference SHA
            ref_res = requests.get(f"{base_url}/git/ref/heads/{self.branch}", headers=headers, timeout=15)
            if ref_res.status_code == 401:
                return {"success": False, "error": "Invalid GITHUB_TOKEN: Authentication failed (401)."}
            if ref_res.status_code != 200:
                return {"success": False, "error": f"Failed to read branch ref '{self.branch}' ({ref_res.status_code}): {ref_res.text[:180]}"}

            latest_commit_sha = ref_res.json()["object"]["sha"]

            # 2. Get base tree SHA of latest commit
            commit_res = requests.get(f"{base_url}/git/commits/{latest_commit_sha}", headers=headers, timeout=15)
            if commit_res.status_code != 200:
                return {"success": False, "error": f"Failed to fetch commit '{latest_commit_sha}' ({commit_res.status_code})."}
            base_tree_sha = commit_res.json()["tree"]["sha"]

            # 3. Create blobs for all files
            tree_items = []
            synced_files = []
            for local_path, repo_path in files_to_sync:
                if not local_path.exists():
                    continue
                content_b64 = base64.b64encode(local_path.read_bytes()).decode("utf-8")
                blob_res = requests.post(
                    f"{base_url}/git/blobs",
                    headers=headers,
                    json={"content": content_b64, "encoding": "base64"},
                    timeout=60,
                )
                if blob_res.status_code != 201:
                    return {
                        "success": False,
                        "error": f"Failed creating blob for {repo_path} ({blob_res.status_code}): {blob_res.text[:180]}",
                    }
                blob_sha = blob_res.json()["sha"]
                tree_items.append({
                    "path": repo_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                })
                synced_files.append(repo_path)

            if not tree_items:
                return {"success": True, "message": "No files to sync.", "synced_files": []}

            # 4. Create new tree
            tree_res = requests.post(
                f"{base_url}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_items},
                timeout=30,
            )
            if tree_res.status_code != 201:
                return {"success": False, "error": f"Failed creating git tree ({tree_res.status_code}): {tree_res.text[:180]}"}
            new_tree_sha = tree_res.json()["sha"]

            # If tree SHA is identical to base_tree_sha, no content changed
            if new_tree_sha == base_tree_sha:
                return {
                    "success": True,
                    "message": f"GitHub repository ({self.repo} @ {self.branch}) is already up to date with latest data.",
                    "synced_files": synced_files,
                    "commit_sha": latest_commit_sha[:7],
                    "repo": self.repo,
                    "branch": self.branch,
                }

            # 5. Create commit
            new_commit_res = requests.post(
                f"{base_url}/git/commits",
                headers=headers,
                json={
                    "message": commit_message,
                    "tree": new_tree_sha,
                    "parents": [latest_commit_sha],
                },
                timeout=20,
            )
            if new_commit_res.status_code != 201:
                return {"success": False, "error": f"Failed creating commit ({new_commit_res.status_code}): {new_commit_res.text[:180]}"}
            new_commit_sha = new_commit_res.json()["sha"]

            # 6. Update branch ref
            patch_res = requests.patch(
                f"{base_url}/git/refs/heads/{self.branch}",
                headers=headers,
                json={"sha": new_commit_sha, "force": False},
                timeout=20,
            )
            if patch_res.status_code != 200:
                return {"success": False, "error": f"Failed updating branch ref ({patch_res.status_code}): {patch_res.text[:180]}"}

            return {
                "success": True,
                "message": f"Successfully synchronized {len(synced_files)} files to GitHub ({self.repo} @ {self.branch}, commit {new_commit_sha[:7]}).",
                "synced_files": synced_files,
                "commit_sha": new_commit_sha[:7],
                "repo": self.repo,
                "branch": self.branch,
            }
        except Exception as e:
            return {"success": False, "error": f"GitHub Git Data API sync failed: {str(e)}"}
