"""Create a timestamped SQLite backup and enforce retention."""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

source = Path(os.getenv("DATABASE_URL", "sqlite:///./health-os.db").split(":///", 1)[1])
target_dir = Path(os.getenv("BACKUP_DIR", "./backups"))
target_dir.mkdir(parents=True, exist_ok=True)
target = target_dir / f"health-os-{datetime.now():%Y%m%d-%H%M%S}.db"
shutil.copy2(source, target)
cutoff = datetime.now() - timedelta(days=int(os.getenv("BACKUP_RETENTION_DAYS", "14")))
for path in target_dir.glob("health-os-*.db"):
    if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
        path.unlink()
print(target)
