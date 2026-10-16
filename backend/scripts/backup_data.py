"""Backup, verify, or restore to a NEW path. Never overwrites a database."""
import argparse
from pathlib import Path

from app.config import get_settings
from app.services.backup import create_backup, verify_backup, restore_copy


def main():
    parser = argparse.ArgumentParser(description='InfraClaim local SQLite backup')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--create', type=Path, help='Create a new backup at this path')
    modes.add_argument('--verify', type=Path, help='Verify backup and manifest')
    modes.add_argument('--restore-copy', nargs=2, type=Path, metavar=('BACKUP', 'NEW_PATH'))
    args = parser.parse_args()
    if args.create:
        result = create_backup(Path(get_settings().database_path), args.create)
    elif args.verify:
        result = verify_backup(args.verify)
    else:
        result = restore_copy(*args.restore_copy)
    print(f"Verified {result['file']}: SHA-256 {result['sha256']}; counts {result['counts']}")


if __name__ == '__main__':
    main()
