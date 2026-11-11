"""Run once: python -m studio.bootstrap. Credentials are written only to ignored data/."""
import os
from pathlib import Path
import secrets

from .auth import AuthStore
from .workspace import WorkspaceStore

MEMBERS = [
    ("peng_ao", "PENG Ao", "admin"),
    ("lyu_xingzhi", "LYU Xingzhi", "member"),
    ("xu_xiaodong", "XU Xiaodong", "member"),
    ("wang_sikai", "WANG sikai", "member"),
    ("zhao_zhe", "ZHAO Zhe", "member"),
]


def main():
    path = Path(os.getenv("STUDIO_DB_PATH", str(Path(__file__).resolve().parent.parent / "data/projects.db")))
    path.parent.mkdir(parents=True, exist_ok=True)
    WorkspaceStore(path)
    auth = AuthStore(path)
    with auth.connect() as c:
        existing = {r[0] for r in c.execute("SELECT username FROM users")}
    pending = [m for m in MEMBERS if m[0] not in existing]
    if not pending:
        print("All five accounts already exist. No passwords changed.")
        return
    destination = path.parent / ("initial-credentials-" + secrets.token_hex(4) + ".txt")
    with destination.open("x", encoding="utf-8") as f:
        os.chmod(destination, 0o600)
        f.write("Private initial credentials. Distribute each account separately. Do not commit or share this file.\n")
        for username, name, role in pending:
            password = secrets.token_urlsafe(18)
            auth.add_user(username, name, password, role)
            f.write(f"{name}\t{username}\t{password}\n")
    print(f"Created {len(pending)} accounts. Private credentials file: {destination}")


if __name__ == "__main__":
    main()
