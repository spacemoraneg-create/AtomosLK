"""
Atomos GitHub Synchronization Service

Enables committing and syncing updated database (atomos.db) and static exports
directly back to the GitHub repository from the running application instance.
"""

import base64
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


DEFAULT_REPO = os.environ.get("GITHUB_REPO", "spacemoraneg-create/AtomosLK")
DEFAULT_BRANCH = os.environ.get("GITHUB_BRANCH", "main")


class GitHubSyncService:
    def __init__(
        self,
        token: Optional[str] = None,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
    ):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.repo = repo
        self.branch = branch

    def is_configured(self) -> bool:
        return bool(self.token)

    def sync_database_and_export(
        self,
        db_path: Path,
        export_dir: Path,
        commit_message: str = "chore(data): auto-sync atomos.db and web export after admin update",
    ) -> Dict[str, Any]:
        """
        Synchronizes atomos.db and key web export files to GitHub.
        Tries local git push first if git credentials exist; falls back to GitHub REST API.
        """
        if not self.is_configured():
            # Try git cli push if possible
            cli_res = self._try_git_cli_push(commit_message)
            if cli_res.get("success"):
                return cli_res
            return {
                "success": False,
                "error": "GITHUB_TOKEN not configured. Configure GITHUB_TOKEN in environment variables or enter it in Admin Console to enable automatic cloud commits.",
            }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Atomos-Cloud-Sync",
        }

        # Verify token access
        try:
            user_res = requests.get("https://api.github.com/user", headers=headers, timeout=10)
            if user_res.status_code == 401:
                return {"success": False, "error": "Invalid GITHUB_TOKEN: Authentication failed (401)."}
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to GitHub API: {str(e)}"}

        synced_files: List[str] = []

        # 1. Sync data/atomos.db
        if db_path.exists():
            db_res = self._sync_file_via_api(
                file_path=db_path,
                repo_path="data/atomos.db",
                commit_message=commit_message,
                headers=headers,
            )
            if db_res.get("success"):
                synced_files.append("data/atomos.db")
            else:
                return db_res

        # 2. Sync critical web export files
        key_export_files = [
            "v2_speakers_tab.json",
            "v2_speakers_general.json",
            "v2_teams_tab.json",
            "v2_teams_general.json",
            "v2_adjudicators.json",
            "v2_tournaments.json",
            "circuit_summary.json",
        ]
        for fname in key_export_files:
            fpath = export_dir / fname
            if fpath.exists():
                f_res = self._sync_file_via_api(
                    file_path=fpath,
                    repo_path=f"data/web_export/{fname}",
                    commit_message=f"{commit_message} [{fname}]",
                    headers=headers,
                )
                if f_res.get("success"):
                    synced_files.append(f"data/web_export/{fname}")

        return {
            "success": True,
            "message": f"Successfully synchronized {len(synced_files)} file(s) to GitHub ({self.repo} @ {self.branch}).",
            "synced_files": synced_files,
            "repo": self.repo,
            "branch": self.branch,
        }

    def _sync_file_via_api(
        self,
        file_path: Path,
        repo_path: str,
        commit_message: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Uploads or updates a file using GitHub Contents API."""
        try:
            content_bytes = file_path.read_bytes()
            content_b64 = base64.b64encode(content_bytes).decode("utf-8")

            url = f"https://api.github.com/repos/{self.repo}/contents/{repo_path}"
            # Check existing file SHA
            get_res = requests.get(f"{url}?ref={self.branch}", headers=headers, timeout=15)
            sha = None
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")

            payload = {
                "message": commit_message,
                "content": content_b64,
                "branch": self.branch,
            }
            if sha:
                payload["sha"] = sha

            put_res = requests.put(url, headers=headers, json=payload, timeout=30)
            if put_res.status_code in (200, 201):
                return {"success": True}
            else:
                err_detail = put_res.text[:200]
                return {
                    "success": False,
                    "error": f"GitHub API error updating {repo_path} ({put_res.status_code}): {err_detail}",
                }
        except Exception as e:
            return {"success": False, "error": f"Failed uploading {repo_path}: {str(e)}"}

    def _try_git_cli_push(self, commit_message: str) -> Dict[str, Any]:
        """Attempts to commit and push via git CLI if available."""
        try:
            root_dir = Path(__file__).resolve().parent.parent.parent
            # Check if dirty
            status = subprocess.run(
                ["git", "status", "--porcelain", "data/"],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if not status.stdout.strip():
                return {"success": True, "message": "No data modifications to commit."}

            subprocess.run(["git", "add", "data/"], cwd=str(root_dir), check=True, timeout=10)
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=str(root_dir),
                check=True,
                timeout=10,
            )
            push = subprocess.run(
                ["git", "push", "origin", self.branch],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                timeout=20,
            )
            if push.returncode == 0:
                return {"success": True, "message": "Successfully committed and pushed via git CLI."}
            return {"success": False, "error": f"git push failed: {push.stderr.strip()[:150]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
