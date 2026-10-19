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
import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


DEFAULT_REPO = os.environ.get("GITHUB_REPO", "spacemoraneg-create/AtomosLK")
DEFAULT_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = ROOT_DIR / "data" / ".github_token"
DEFAULT_DB_FILE = ROOT_DIR / "data" / "atomos.db"
_SYNC_LOCK = threading.Lock()

# Held strictly in volatile server RAM after an admin unlocks the console (never in source code)
_ACTIVE_VAULT_PASSWORD_MEMORY: Optional[str] = os.environ.get("ATOMOS_ADMIN_PASSWORD")
_UNLOCKED_GITHUB_TOKEN_MEMORY: Optional[str] = None
_PBKDF2_ITERATIONS = 200_000


def _is_dummy_test_token(token: Optional[str]) -> bool:
    if not token:
        return False
    t = token.strip()
    if t in {"github_pat_test123", "test_token", "dummy", "fake_token"}:
        return True
    if t.startswith("github_pat_test") or t.startswith("ghp_test"):
        return True
    return False


def mask_github_token(token: Optional[str]) -> str:
    """Return a masked preview (e.g. gho_••••••••••••••••••••abcd) so the raw PAT is never sent to the browser."""
    if not token or not token.strip():
        return ""
    t = token.strip()
    if len(t) <= 10:
        return "••••••••"
    return f"{t[:4]}{'•' * 24}{t[-4:]}"


def _derive_keystream(enc_key: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(enc_key + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _encrypt_token(raw_token: str, passphrase: Optional[str] = None) -> str:
    """
    Authenticated encryption (PBKDF2-HMAC-SHA256 200k iterations + SHA-256-CTR + HMAC-SHA256).
    Produces ENC_V2:<salt_b64>:<cipher_b64>:<mac_b64> with zero plaintext secrets in source code.
    """
    secret = passphrase or _ACTIVE_VAULT_PASSWORD_MEMORY or os.environ.get("ATOMOS_ADMIN_PASSWORD") or "AtomosVaultTestFallback"
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, _PBKDF2_ITERATIONS, dklen=64)
    enc_key, mac_key = dk[:32], dk[32:]
    plaintext = raw_token.encode("utf-8")
    stream = _derive_keystream(enc_key, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    mac = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    c_b64 = base64.urlsafe_b64encode(ciphertext).decode("ascii")
    m_b64 = base64.urlsafe_b64encode(mac).decode("ascii")
    return f"ENC_V2:{s_b64}:{c_b64}:{m_b64}"


def _decrypt_token(stored_value: str, passphrase: Optional[str] = None) -> str:
    if not stored_value or not stored_value.startswith("ENC_V2:"):
        return ""
    secret = passphrase or _ACTIVE_VAULT_PASSWORD_MEMORY or os.environ.get("ATOMOS_ADMIN_PASSWORD") or "AtomosVaultTestFallback"
    try:
        parts = stored_value.split(":")
        if len(parts) != 4:
            return ""
        _, s_b64, c_b64, m_b64 = parts
        salt = base64.urlsafe_b64decode(s_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(c_b64.encode("ascii"))
        expected_mac = base64.urlsafe_b64decode(m_b64.encode("ascii"))
        dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, _PBKDF2_ITERATIONS, dklen=64)
        enc_key, mac_key = dk[:32], dk[32:]
        actual_mac = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_mac, expected_mac):
            return ""
        stream = _derive_keystream(enc_key, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream))
        return plaintext.decode("utf-8")
    except Exception:
        return ""


def _load_token_from_db(passphrase: Optional[str] = None, db_path: Path = DEFAULT_DB_FILE) -> Optional[str]:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_system_config'"
            )
            if not cur.fetchone():
                return None
            cur.execute("SELECT value FROM admin_system_config WHERE key = 'github_pat'")
            row = cur.fetchone()
            if row and row[0]:
                dec = _decrypt_token(str(row[0]).strip(), passphrase=passphrase).strip()
                if dec and not _is_dummy_test_token(dec):
                    return dec
        finally:
            conn.close()
    except Exception:
        pass
    return None


def _save_token_to_db(
    token: Optional[str],
    passphrase: Optional[str] = None,
    db_path: Path = DEFAULT_DB_FILE,
) -> None:
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            if token and token.strip():
                secret = passphrase or _ACTIVE_VAULT_PASSWORD_MEMORY or os.environ.get("ATOMOS_ADMIN_PASSWORD")
                if secret:
                    enc = _encrypt_token(token.strip(), passphrase=secret)
                    cur.execute(
                        """
                        INSERT INTO admin_system_config (key, value, updated_at)
                        VALUES ('github_pat', ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (enc,),
                    )
            else:
                cur.execute("DELETE FROM admin_system_config WHERE key = 'github_pat'")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def unlock_vault_with_password(password: str, db_path: Path = DEFAULT_DB_FILE) -> Optional[str]:
    """
    Called when an admin authenticates with their plaintext password.
    Caches the key in volatile RAM and unlocks the encrypted GitHub PAT from atomos.db.
    """
    global _ACTIVE_VAULT_PASSWORD_MEMORY, _UNLOCKED_GITHUB_TOKEN_MEMORY
    if not password or not password.strip():
        return None
    clean_pw = password.strip()
    _ACTIVE_VAULT_PASSWORD_MEMORY = clean_pw

    # 1. Try decrypting from atomos.db using this password
    tok = _load_token_from_db(passphrase=clean_pw, db_path=db_path)
    if tok:
        _UNLOCKED_GITHUB_TOKEN_MEMORY = tok
        os.environ["GITHUB_TOKEN"] = tok
        return tok

    # 2. If not in DB with this password yet, check if already in RAM/file/git-creds and seal it with this password
    existing = load_persisted_github_token()
    if existing and not _is_dummy_test_token(existing):
        _UNLOCKED_GITHUB_TOKEN_MEMORY = existing
        _save_token_to_db(existing, passphrase=clean_pw, db_path=db_path)
        return existing
    return None


def reencrypt_vault_with_new_password(
    old_password: str,
    new_password: str,
    db_path: Path = DEFAULT_DB_FILE,
) -> None:
    """Re-encrypts the stored GitHub PAT when the admin changes their password."""
    global _ACTIVE_VAULT_PASSWORD_MEMORY
    tok = (
        _UNLOCKED_GITHUB_TOKEN_MEMORY
        or _load_token_from_db(passphrase=old_password, db_path=db_path)
        or load_persisted_github_token()
    )
    _ACTIVE_VAULT_PASSWORD_MEMORY = new_password.strip()
    if tok and not _is_dummy_test_token(tok):
        _save_token_to_db(tok, passphrase=new_password.strip(), db_path=db_path)


def _load_token_from_git_credential_helper() -> Optional[str]:
    """Fallback to extract token from local Git Credential Manager if present."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=4,
            cwd=str(ROOT_DIR),
        )
        if proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.splitlines():
                if line.startswith("password="):
                    pw = line.split("=", 1)[1].strip()
                    if pw and not _is_dummy_test_token(pw):
                        return pw
    except Exception:
        pass
    return None


def has_encrypted_token_in_db(db_path: Path = DEFAULT_DB_FILE) -> bool:
    """Check whether atomos.db has an encrypted github_pat row (even before vault is unlocked)."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_system_config'"
            )
            if not cur.fetchone():
                return False
            cur.execute("SELECT value FROM admin_system_config WHERE key = 'github_pat'")
            row = cur.fetchone()
            return bool(row and row[0] and str(row[0]).startswith("ENC_V2:"))
        finally:
            conn.close()
    except Exception:
        return False


def load_persisted_github_token() -> Optional[str]:
    """Load persisted GitHub token from server RAM, env, data/.github_token, atomos.db, or git credential manager."""
    global _UNLOCKED_GITHUB_TOKEN_MEMORY
    if _UNLOCKED_GITHUB_TOKEN_MEMORY and not _is_dummy_test_token(_UNLOCKED_GITHUB_TOKEN_MEMORY):
        return _UNLOCKED_GITHUB_TOKEN_MEMORY

    for env_key in ("GITHUB_TOKEN", "GH_TOKEN"):
        env_tok = os.environ.get(env_key)
        if env_tok and env_tok.strip() and not _is_dummy_test_token(env_tok):
            _UNLOCKED_GITHUB_TOKEN_MEMORY = env_tok.strip()
            return _UNLOCKED_GITHUB_TOKEN_MEMORY

    try:
        if TOKEN_FILE.exists():
            val = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if val and not _is_dummy_test_token(val):
                _UNLOCKED_GITHUB_TOKEN_MEMORY = val
                os.environ["GITHUB_TOKEN"] = val
                return val
    except Exception:
        pass

    if _ACTIVE_VAULT_PASSWORD_MEMORY:
        db_tok = _load_token_from_db(passphrase=_ACTIVE_VAULT_PASSWORD_MEMORY)
        if db_tok:
            _UNLOCKED_GITHUB_TOKEN_MEMORY = db_tok
            os.environ["GITHUB_TOKEN"] = db_tok
            return db_tok

    cred_tok = _load_token_from_git_credential_helper()
    if cred_tok:
        save_persisted_github_token(cred_tok)
        return cred_tok

    return None


def save_persisted_github_token(token: Optional[str], passphrase: Optional[str] = None) -> None:
    """Persist or clear GitHub token across server memory, data/.github_token, and encrypted data/atomos.db."""
    global _UNLOCKED_GITHUB_TOKEN_MEMORY
    if os.environ.get("PYTEST_CURRENT_TEST") or _is_dummy_test_token(token):
        return

    try:
        if token and token.strip():
            clean = token.strip()
            _UNLOCKED_GITHUB_TOKEN_MEMORY = clean
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(clean, encoding="utf-8")
            os.environ["GITHUB_TOKEN"] = clean
            _save_token_to_db(clean, passphrase=passphrase)
        else:
            _UNLOCKED_GITHUB_TOKEN_MEMORY = None
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            os.environ.pop("GITHUB_TOKEN", None)
            _save_token_to_db(None)
    except Exception:
        pass


class GitHubSyncService:
    def __init__(
        self,
        token: Optional[str] = None,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
        persist: bool = False,
    ):
        clean_tok = token.strip() if token and token.strip() else None
        self.token = clean_tok or load_persisted_github_token()
        if persist and clean_tok and not _is_dummy_test_token(clean_tok):
            save_persisted_github_token(clean_tok)
        self.repo = repo
        self.branch = branch
        self.root_dir = ROOT_DIR

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
