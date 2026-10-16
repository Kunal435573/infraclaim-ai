"""Local pilot identities and opaque, revocable browser sessions."""
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone


def digest_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


_DUMMY_SALT = secrets.token_bytes(16)
_DUMMY_HASH = digest_password(secrets.token_urlsafe(32), _DUMMY_SALT)


class Auth:
    def __init__(self, store):
        self.store = store
        with store.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','operator','reviewer')),
                    salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_events (
                    id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, subject TEXT NOT NULL);
            ''')
        self.purge_expired_sessions()

    def purge_expired_sessions(self):
        with self.store.transaction() as db:
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (datetime.now(timezone.utc).isoformat(),))

    def create_user(self, username: str, display_name: str, role: str, password: str, actor='system', disabled=False):
        username = username.strip().lower()
        if not (3 <= len(username) <= 64 and username.replace('_', '').replace('-', '').isalnum()):
            raise ValueError('Username must be 3–64 letters, numbers, dashes, or underscores.')
        if not (2 <= len(display_name.strip()) <= 100) or role not in {'admin', 'operator', 'reviewer'}:
            raise ValueError('Choose a display name and valid role.')
        if not 14 <= len(password) <= 1024:
            raise ValueError('Password must have at least 14 characters.')
        salt = secrets.token_bytes(16)
        password_hash = digest_password(password, salt)
        with self.store.transaction() as db:
            if db.execute('SELECT count(*) FROM users').fetchone()[0] >= 200:
                raise ValueError('Pilot account limit reached. Contact the administrator.')
            db.execute('INSERT INTO users(username,display_name,role,salt,password_hash,disabled) VALUES(?,?,?,?,?,?)',
                       (username, display_name.strip(), role, salt, password_hash, int(disabled)))
            self._event(db, actor, 'signup_requested' if disabled and actor == 'self_signup' else 'created', username)

    def list_users(self):
        with self.store.transaction() as db:
            return [{'username': row['username'], 'display_name': row['display_name'],
                     'role': row['role'], 'disabled': bool(row['disabled'])}
                    for row in db.execute('SELECT * FROM users ORDER BY username')]

    def set_disabled(self, username: str, disabled: bool, actor: str):
        with self.store.transaction() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username.lower(),)).fetchone()
            if not row:
                raise KeyError('Account not found')
            if disabled and row['role'] == 'admin' and not row['disabled']:
                other = db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0 AND id<>?",
                                   (row['id'],)).fetchone()[0]
                if not other:
                    raise ValueError('The last active administrator cannot be disabled.')
            db.execute('UPDATE users SET disabled=? WHERE id=?', (int(disabled), row['id']))
            if disabled:
                db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            self._event(db, actor, 'disabled' if disabled else 'enabled', row['username'])

    def reset_password(self, username: str, password: str, actor: str):
        if not 14 <= len(password) <= 1024:
            raise ValueError('Password must have at least 14 characters.')
        salt = secrets.token_bytes(16)
        with self.store.transaction() as db:
            row = db.execute('SELECT id,username FROM users WHERE username=?', (username.lower(),)).fetchone()
            if not row:
                raise KeyError('Account not found')
            db.execute('UPDATE users SET salt=?, password_hash=?, failed_attempts=0, locked_until=NULL WHERE id=?',
                       (salt, digest_password(password, salt), row['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            self._event(db, actor, 'password_reset', row['username'])

    def events(self):
        with self.store.transaction() as db:
            return [dict(row) for row in db.execute(
                'SELECT at,actor,action,subject FROM auth_events ORDER BY id DESC LIMIT 100')]

    def login(self, username: str, password: str):
        now = datetime.now(timezone.utc)
        # Hash outside the database lock; unknown accounts receive equivalent work.
        with self.store.transaction() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username.strip().lower(),)).fetchone()
        correct = hmac.compare_digest(digest_password(password, row['salt'] if row else _DUMMY_SALT),
                                      row['password_hash'] if row else _DUMMY_HASH)
        with self.store.transaction() as db:
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (now.isoformat(),))
            current = db.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone() if row else None
            if (not current or current['disabled'] or not correct
                    or current['password_hash'] != row['password_hash']):
                # Per-peer/global throttles guard guessing without letting five
                # unauthenticated failures lock the victim out of their account.
                self._event(db, 'anonymous', 'login_failed', row['username'] if row else 'unknown')
                return None
            db.execute('UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=?', (row['id'],))
            db.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires_at DESC LIMIT -1 OFFSET 4)', (row['id'],))
            token = secrets.token_urlsafe(32)
            expires = (now + timedelta(hours=12)).isoformat()
            db.execute('INSERT INTO sessions VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), row['id'], expires))
            self._event(db, row['username'], 'login_succeeded', row['username'])
            return token, self._public(current)

    def user(self, token: str | None):
        if not token:
            return None
        with self.store.transaction() as db:
            row = db.execute('''SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0''',
                (hashlib.sha256(token.encode()).hexdigest(), datetime.now(timezone.utc).isoformat())).fetchone()
            return self._public(row) if row else None

    def logout(self, token: str | None):
        if token:
            with self.store.transaction() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))

    @staticmethod
    def _event(db, actor, action, subject):
        db.execute('INSERT INTO auth_events(at,actor,action,subject) VALUES(?,?,?,?)',
                   (datetime.now(timezone.utc).isoformat(), actor, action, subject))
        db.execute('DELETE FROM auth_events WHERE id NOT IN (SELECT id FROM auth_events ORDER BY id DESC LIMIT 10000)')

    @staticmethod
    def _public(row):
        return {'username': row['username'], 'display_name': row['display_name'], 'role': row['role']}
