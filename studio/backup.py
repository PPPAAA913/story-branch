"""SQLite-consistent snapshot, usable while the single-instance app is running."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist.")
    if source == destination or destination.exists():
        raise ValueError("Destination must be a new file, different from source.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents replacing a previous backup.
    with destination.open("xb"):
        pass
    os.chmod(destination, 0o600)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as target:
                src.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed.")
                tables = {r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"w_projects", "w_versions", "w_branches"}.issubset(tables):
                    raise ValueError("Not a Story Branch workspace database.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    default = Path(__file__).resolve().parent.parent / "data/projects.db"
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv("STUDIO_DB_PATH", str(default)))
    parser.add_argument("--output", help="New file path; existing files are never overwritten.")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = args.output or str(Path(args.source).parent / "backups" / (stamp + ".db"))
    print("Verified backup: " + str(backup(args.source, target)))


if __name__ == "__main__":
    main()
