"""Start Health OS with migrations and a persistent session key."""

import os
import secrets
import subprocess
from pathlib import Path

HEALTHOS_UID = int(os.getenv("HEALTHOS_UID", "10001"))
HEALTHOS_GID = int(os.getenv("HEALTHOS_GID", "10001"))


def chown_tree(path: Path, uid: int, gid: int) -> None:
    """Give the application ownership of a managed storage tree."""
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid, follow_symlinks=False)
    for root, directories, files in os.walk(path, followlinks=False):
        os.chown(root, uid, gid, follow_symlinks=False)
        for name in [*directories, *files]:
            os.chown(Path(root) / name, uid, gid, follow_symlinks=False)


def prepare_managed_storage() -> None:
    """Initialize mounted storage as root, then permanently drop privileges."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return

    storage_paths = {Path("/data"), Path(os.getenv("BACKUP_DIR", "/backups"))}
    for path in storage_paths:
        chown_tree(path, HEALTHOS_UID, HEALTHOS_GID)

    os.setgroups([])
    os.setgid(HEALTHOS_GID)
    os.setuid(HEALTHOS_UID)


def configure_session_secret() -> None:
    if os.getenv("SESSION_SECRET"):
        return
    if os.getenv("DEPLOYMENT_MODE", "standalone") != "home_assistant":
        raise SystemExit("SESSION_SECRET is required for standalone deployment")
    secret_file = Path("/data/session-secret")
    if secret_file.exists():
        secret = secret_file.read_text(encoding="utf-8").strip()
    else:
        secret = secrets.token_urlsafe(48)
        secret_file.write_text(secret, encoding="utf-8")
        secret_file.chmod(0o600)
    os.environ["SESSION_SECRET"] = secret


prepare_managed_storage()
configure_session_secret()
subprocess.run(["alembic", "upgrade", "head"], check=True)
os.execvp(
    "uvicorn",
    ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"],
)
