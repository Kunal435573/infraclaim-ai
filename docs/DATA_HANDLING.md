# Internal pilot data handling

Use synthetic records only. The local SQLite database stores case details, uploaded contracts and incident source files, reviewer notes, account password hashes, and simulated credit entries. Source uploads are retained with SHA-256 checksums; the application does not parse them into model evidence or authenticate their origin. Approval requires a different reviewer to select ticket, telemetry, and maintenance files and record how they were compared with the entered incident. This is a human attestation, not independent system verification.

Browser sessions expire after 12 hours and are removed on application startup and login. Unlinked contract PDFs older than 24 hours are removed on startup or the next upload/save. Linked contracts, source files, cases, and audit events are **not automatically deleted**; no customer-data retention schedule has been approved. Do not place real customer data in this pilot.

Create a consistent backup with the backend virtual environment:

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.backup_data --create D:\InfraClaimPilotBackups\pilot-YYYY-MM-DD.sqlite3
.venv\Scripts\python.exe -m scripts.backup_data --verify D:\InfraClaimPilotBackups\pilot-YYYY-MM-DD.sqlite3
.venv\Scripts\python.exe -m scripts.backup_data --restore-copy D:\InfraClaimPilotBackups\pilot-YYYY-MM-DD.sqlite3 D:\InfraClaimPilotBackups\restore-check.sqlite3
```

The backup uses SQLite's online backup API and includes a checksum manifest and integrity check. Restore always writes to a new path and refuses to overwrite an existing file. These local backups are **not encrypted**. Keep them private, off the system drive when possible, and out of the release ZIP. A real customer pilot needs an approved retention/deletion schedule, encrypted offsite backups, key management, and a tested full service recovery procedure.
