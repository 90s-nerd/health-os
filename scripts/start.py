"""Start Health OS with migrations and a persistent session key."""

import os
import secrets
import subprocess
from pathlib import Path


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


configure_session_secret()
subprocess.run(["alembic", "upgrade", "head"], check=True)
os.execvp(
    "uvicorn",
    ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"],
)
