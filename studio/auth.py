"""Small-team authentication. Passwords and session tokens are never stored in plaintext."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager

COOKIE = "story_session"


class AuthStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL, password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL, role TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS project_members(
                    project_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    PRIMARY KEY(project_id,user_id));
                CREATE TABLE IF NOT EXISTS login_attempts(
                    bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

    def add_user(self, username, name, password, role="member"):
        if not 12 <= len(password) <= 128 or role not in {"member", "admin"}:
            raise ValueError("Password must have 12–128 characters; role must be member/admin.")
        user_id, salt = secrets.token_hex(16), secrets.token_hex(16)
        digest = self.password_hash(password, salt)
        with self.connect() as c:
            c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", (user_id, username, name, digest, salt, role))
            # This release contains exactly one shared course team.
            c.execute("INSERT OR IGNORE INTO project_members SELECT id,? FROM w_projects", (user_id,))
        return user_id

    def login(self, username, password, address):
        instant = time.time()
        buckets = ["ip:" + address, "user:" + username]
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM login_attempts WHERE until < ?", (instant,))
            for bucket in buckets:
                row = c.execute("SELECT count FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
                if row and row["count"] >= 20:
                    return None, "limited"
            for bucket in buckets:
                c.execute("INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, instant + 900))
            user = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        digest = self.password_hash(password, user["salt"] if user else "00" * 16)
        if not user or not hmac.compare_digest(digest, user["password_hash"]):
            return None, "invalid"
        token = secrets.token_urlsafe(32)
        with self.connect() as c:
            c.execute("DELETE FROM sessions WHERE expires < ?", (instant,))
            c.execute("DELETE FROM login_attempts WHERE bucket=?", ("user:" + username,))
            c.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user["id"], instant + 43200))
        return token, None

    def user(self, token):
        if not token or len(token) > 128:
            return None
        with self.connect() as c:
            row = c.execute("SELECT u.id,u.username,u.name,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires>?", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
            return dict(row) if row else None

    def logout(self, token):
        with self.connect() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def member(self, project_id, user_id):
        with self.connect() as c:
            return bool(c.execute("SELECT 1 FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id)).fetchone())
