from pathlib import Path

import pytest

from app.services.auth import Auth
from app.services.backup import create_backup, restore_copy, verify_backup
from app.services.store import Store


def test_consistent_backup_and_restore_copy(tmp_path):
    source = tmp_path / 'live.db'
    auth = Auth(Store(str(source)))
    auth.create_user('operator1', 'Pilot Operator', 'operator', 'operator-password-12345')
    backup = tmp_path / 'backup.db'
    manifest = create_backup(source, backup)
    assert manifest['counts']['users'] == 1
    assert verify_backup(backup) == manifest
    restored = tmp_path / 'restored.db'
    assert restore_copy(backup, restored) == manifest
    assert restored.read_bytes() == backup.read_bytes()
    with pytest.raises(FileExistsError):
        restore_copy(backup, restored)
    with backup.open('r+b') as target:
        target.seek(100)
        target.write(b'tamper')
    with pytest.raises(ValueError, match='checksum'):
        verify_backup(backup)
