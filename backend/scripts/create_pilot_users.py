"""Create three local synthetic-pilot accounts; keep credentials outside the release ZIP."""
import os
import secrets
import sys
from pathlib import Path

from app.config import get_settings
from app.services.auth import Auth
from app.services.store import Store


def main():
    target = Path(sys.argv[1]).resolve()
    if target.exists():
        raise SystemExit('Credential file already exists; refusing to replace it.')
    auth = Auth(Store(get_settings().database_path))
    accounts = [('pilot-admin', 'Pilot Administrator', 'admin'),
                ('pilot-operator', 'Pilot Operator', 'operator'),
                ('pilot-reviewer', 'Pilot Reviewer', 'reviewer')]
    records = [(username, role, secrets.token_urlsafe(24)) for username, _, role in accounts]
    with auth.store.transaction() as db:
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            raise SystemExit('Accounts already exist; refusing to create duplicates.')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write('InfraClaim internal pilot accounts — local synthetic data only\n')
            output.write('Use these passwords to sign in at http://127.0.0.1:3016/login\n\n')
            for username, role, password in records:
                output.write(f'{username} ({role}): {password}\n')
        for (username, display_name, role), (_, _, password) in zip(accounts, records):
            auth.create_user(username, display_name, role, password)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    print(f'Created {len(accounts)} accounts. Credentials: {target}')


if __name__ == '__main__':
    main()
