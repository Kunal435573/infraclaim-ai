"""SQLite unit of work: case, vendor, memo and recovery writes commit together."""
import json
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from app.schemas import ClaimCase


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, incident_id TEXT UNIQUE NOT NULL,
                    version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vendor_claims (
                    id TEXT PRIMARY KEY, case_id TEXT UNIQUE NOT NULL REFERENCES cases(id),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS credit_memos (
                    id TEXT PRIMARY KEY, claim_id TEXT UNIQUE NOT NULL REFERENCES vendor_claims(id),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS recoveries (
                    memo_id TEXT PRIMARY KEY REFERENCES credit_memos(id),
                    case_id TEXT UNIQUE NOT NULL REFERENCES cases(id),
                    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), currency TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contracts (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contract_documents (
                    id TEXT PRIMARY KEY,
                    contract_id TEXT UNIQUE REFERENCES contracts(id),
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    uploaded_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS incident_documents (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    category TEXT NOT NULL CHECK(category IN ('ticket','telemetry','maintenance')),
                    filename TEXT NOT NULL, sha256 TEXT NOT NULL,
                    payload BLOB NOT NULL, uploaded_at TEXT NOT NULL, uploader TEXT NOT NULL);
                PRAGMA user_version = 3;
            ''')
        self.purge_staged_documents()

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, case_id, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.get(case_id, conn)
        row = db.execute('SELECT payload FROM cases WHERE id=?', (case_id,)).fetchone()
        if row is None:
            raise KeyError('case not found')
        return ClaimCase.model_validate_json(row['payload'])

    def list(self, limit=None, offset=0):
        with self.transaction() as db:
            return [ClaimCase.model_validate_json(r[0]) for r in db.execute(
                'SELECT payload FROM cases ORDER BY rowid DESC LIMIT ? OFFSET ?',
                (-1 if limit is None else limit, offset))]

    def list_contracts(self, limit=None, offset=0):
        from app.schemas import VendorContract
        with self.transaction() as db:
            return [VendorContract.model_validate_json(row[0]) for row in db.execute(
                'SELECT payload FROM contracts ORDER BY rowid DESC LIMIT ? OFFSET ?',
                (-1 if limit is None else limit, offset))]

    def get_contract(self, contract_id):
        from app.schemas import VendorContract
        with self.transaction() as db:
            row = db.execute('SELECT payload FROM contracts WHERE id=?', (contract_id,)).fetchone()
            if row is None:
                raise KeyError('contract not found')
            return VendorContract.model_validate_json(row[0])

    def create_contract(self, contract):
        from app.schemas import VendorContract
        # Validate the exact serialized representation before committing any row.
        serialized = contract.model_dump_json()
        VendorContract.model_validate_json(serialized)
        self.purge_staged_documents()
        with self.transaction() as db:
            if db.execute('SELECT count(*) FROM contracts').fetchone()[0] >= 1000:
                raise Conflict('Pilot contract limit reached; archive data before adding more.')
            try:
                db.execute('INSERT INTO contracts VALUES (?,?)', (contract.id, serialized))
            except sqlite3.IntegrityError as exc:
                raise Conflict('Contract ID already exists; use a new ID for a revised contract.') from exc
            if contract.source_document_id:
                linked = db.execute(
                    'UPDATE contract_documents SET contract_id=? WHERE id=? AND contract_id IS NULL AND sha256=?',
                    (contract.id, contract.source_document_id, contract.source_file_sha256))
                if linked.rowcount != 1:
                    raise Conflict('Uploaded PDF is missing, changed, or already linked to another contract.')
        return contract

    def stage_contract_document(self, payload: bytes, filename: str):
        self.purge_staged_documents()
        document_id = 'doc_' + uuid4().hex
        digest = hashlib.sha256(payload).hexdigest()
        safe_name = Path(filename).name[:160] or 'contract.pdf'
        with self.transaction() as db:
            self._document_budget(db, len(payload))
            db.execute('INSERT INTO contract_documents VALUES (?,?,?,?,?,?)',
                       (document_id, None, safe_name, digest, payload,
                        datetime.now(timezone.utc).isoformat()))
        return {'id': document_id, 'sha256': digest, 'filename': safe_name}

    def purge_staged_documents(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with self.transaction() as db:
            db.execute('DELETE FROM contract_documents WHERE contract_id IS NULL AND uploaded_at < ?',
                       (cutoff,))

    def contract_document(self, contract_id: str):
        with self.transaction() as db:
            row = db.execute(
                'SELECT filename, sha256, payload FROM contract_documents WHERE contract_id=?',
                (contract_id,)).fetchone()
            if row is None:
                raise KeyError('contract source PDF not found')
            return {'filename': row['filename'], 'sha256': row['sha256'], 'payload': row['payload']}

    def add_incident_document(self, case_id, category, filename, payload, uploader):
        if category not in {'ticket', 'telemetry', 'maintenance'}:
            raise ValueError('Choose ticket, telemetry, or maintenance source.')
        from app.schemas import CaseState, CaseEvent
        with self.transaction() as db:
            case = self.get(case_id, db)
            from app.services.source_checks import check_source
            analysis = check_source({'payload': payload, 'filename': filename, 'category': category}, case.incident_snapshot)
            if analysis.get('invalid'):
                raise ValueError('Malformed source data; provide a valid export.')
            if case.source != 'manual' or case.state != CaseState.HUMAN_REVIEW:
                raise Conflict('Sources can only be added to an operator-entered case in review.')
            if db.execute('SELECT count(*) FROM incident_documents WHERE case_id=?', (case_id,)).fetchone()[0] >= 10:
                raise Conflict('Maximum 10 source files per case.')
            self._document_budget(db, len(payload))
            document_id = 'src_' + uuid4().hex
            uploaded_at = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO incident_documents VALUES(?,?,?,?,?,?,?,?)',
                       (document_id, case_id, category, Path(filename).name[:160] or 'source',
                        hashlib.sha256(payload).hexdigest(), payload, uploaded_at, uploader))
            case.timeline.append(CaseEvent(at=datetime.now(timezone.utc), state=case.state,
                                           message=f'{uploader} attached {category} source {document_id}.'))
            case.review_approved = False
            self.save(case, db)
            return {'case': case, 'document': self._source_meta(db.execute(
                'SELECT * FROM incident_documents WHERE id=?', (document_id,)).fetchone())}

    @staticmethod
    def _source_meta(row):
        return {key: row[key] for key in ('id', 'case_id', 'category', 'filename', 'sha256', 'uploaded_at', 'uploader')}

    def list_incident_documents(self, case_id, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.list_incident_documents(case_id, conn)
        self.get(case_id, db)
        return [self._source_meta(row) for row in db.execute(
            'SELECT * FROM incident_documents WHERE case_id=? ORDER BY uploaded_at,id', (case_id,))]

    def incident_document(self, case_id, document_id, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.incident_document(case_id, document_id, conn)
        row = db.execute('SELECT * FROM incident_documents WHERE case_id=? AND id=?',
                         (case_id, document_id)).fetchone()
        if not row:
            raise KeyError('Incident source not found')
        return dict(row)

    def for_incident(self, incident_id):
        with self.transaction() as db:
            row = db.execute('SELECT payload FROM cases WHERE incident_id=?', (incident_id,)).fetchone()
            return ClaimCase.model_validate_json(row[0]) if row else None

    def create(self, case):
        with self.transaction() as db:
            if db.execute('SELECT count(*) FROM cases').fetchone()[0] >= 1000 and not db.execute('SELECT 1 FROM cases WHERE incident_id=?', (case.incident_id,)).fetchone():
                raise Conflict('Pilot case limit reached; archive data before adding more.')
            db.execute('INSERT OR IGNORE INTO cases VALUES (?,?,?,?)',
                       (case.id, case.incident_id, case.version, case.model_dump_json()))
            row = db.execute('SELECT payload FROM cases WHERE incident_id=?', (case.incident_id,)).fetchone()
            return ClaimCase.model_validate_json(row[0])

    @staticmethod
    def _document_budget(db, incoming):
        contract_bytes = db.execute('SELECT COALESCE(SUM(length(payload)),0) FROM contract_documents').fetchone()[0]
        source_bytes = db.execute('SELECT COALESCE(SUM(length(payload)),0) FROM incident_documents').fetchone()[0]
        if contract_bytes + source_bytes + incoming > 256 * 1024 * 1024:
            raise Conflict('Pilot document storage limit reached; contact the administrator.')

    def save(self, case, db):
        previous = case.version
        case.version += 1
        updated = db.execute('UPDATE cases SET version=?, payload=? WHERE id=? AND version=?',
                            (case.version, case.model_dump_json(), case.id, previous))
        if updated.rowcount != 1:
            raise Conflict('Case changed during investigation; reload and retry.')
        return case

    def vendor(self, claim_id, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.vendor(claim_id, conn)
        row = db.execute('SELECT payload FROM vendor_claims WHERE id=?', (claim_id,)).fetchone()
        if row is None:
            raise KeyError('vendor claim not found')
        return json.loads(row[0])

    def put_vendor(self, vendor, db):
        db.execute('INSERT INTO vendor_claims VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (vendor['id'], vendor['case_id'], json.dumps(vendor)))

    def memo(self, claim_id, db=None):
        if db is None:
            with self.transaction() as conn:
                return self.memo(claim_id, conn)
        row = db.execute('SELECT payload FROM credit_memos WHERE claim_id=?', (claim_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def summary(self):
        with self.transaction() as db:
            total, count = db.execute('SELECT COALESCE(SUM(amount_cents),0), COUNT(*) FROM recoveries').fetchone()
            return {'verified_amount_usd': total / 100, 'verified_cases': count, 'currency': 'USD'}
