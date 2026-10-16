"""Consistent SQLite backups with integrity and checksum verification."""
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


TABLES = ('cases', 'contracts', 'contract_documents', 'incident_documents', 'vendor_claims', 'credit_memos',
          'recoveries', 'users', 'auth_events')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(path: Path) -> dict:
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed.')
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'cases', 'contracts', 'users'}.issubset(names):
            raise ValueError('Backup is missing required InfraClaim tables.')
        return {'schema_version': db.execute('PRAGMA user_version').fetchone()[0],
                'counts': {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                           for table in TABLES if table in names}}


def create_backup(database: Path, target: Path) -> dict:
    database, target = database.resolve(), target.resolve()
    if not database.is_file() or target == database:
        raise ValueError('Source database must exist and backup must have a different path.')
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(str(target) + '.manifest.json')
    if manifest_path.exists():
        raise FileExistsError('Backup manifest already exists.')
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True) as source, sqlite3.connect(target) as backup:
            source.backup(backup)
        details = inspect(target)
        manifest = {'format': 'infraclaim-sqlite-backup-v1',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'file': target.name, 'sha256': sha256(target), **details}
        with manifest_path.open('x', encoding='utf-8') as output:
            json.dump(manifest, output, indent=2)
        return manifest
    except BaseException:
        target.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise


def verify_backup(target: Path) -> dict:
    target = target.resolve()
    manifest_path = Path(str(target) + '.manifest.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'infraclaim-sqlite-backup-v1' or manifest.get('file') != target.name:
        raise ValueError('Backup manifest does not match the file.')
    if sha256(target) != manifest.get('sha256'):
        raise ValueError('Backup checksum does not match the manifest.')
    details = inspect(target)
    if details != {key: manifest[key] for key in ('schema_version', 'counts')}:
        raise ValueError('Backup contents do not match the manifest.')
    return manifest


def restore_copy(source: Path, destination: Path) -> dict:
    manifest = verify_backup(source)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open('rb') as input_file:
            with destination.open('xb') as output_file:
                created = True
                shutil.copyfileobj(input_file, output_file)
        if sha256(destination) != manifest['sha256'] or inspect(destination) != {
            key: manifest[key] for key in ('schema_version', 'counts')}:
            raise ValueError('Restored copy failed verification.')
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return manifest
