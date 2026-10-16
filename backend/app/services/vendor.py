"""Deterministic, local-only Vendor Claims API simulator. No real vendor calls."""
import json
from datetime import datetime, timedelta, timezone
from app.services.policy import cents
from app.services.store import Conflict


def now():
    return datetime.now(timezone.utc)


class VendorSimulator:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def submit(self, case, db):
        vendor = {
            'id': f'vendor_{case.id}', 'case_id': case.id, 'status': 'submitted',
            'contract_id': case.contract_id, 'incident_id': case.incident_id,
            'vendor': case.contract_snapshot.vendor, 'customer': case.contract_snapshot.customer,
            'amount_cents': cents(case.amount_usd), 'currency': 'USD',
            'submitted_at': now().isoformat(), 'dispute': None, 'defense': None,
            'accepted_at': None, 'memo_due_at': None,
        }
        self.store.put_vendor(vendor, db)
        return vendor

    def dispute(self, vendor, db):
        if vendor['status'] != 'submitted':
            raise Conflict('Vendor claim must be submitted before a dispute.')
        vendor['status'] = 'disputed'
        vendor['dispute'] = {'code': 'PLANNED_MAINTENANCE',
                             'reason': 'Vendor alleges planned maintenance excludes this cooling incident.',
                             'at': now().isoformat()}
        self.store.put_vendor(vendor, db)

    def defend(self, vendor, assessment, db):
        if vendor['status'] != 'disputed':
            raise Conflict('Vendor claim must be disputed before a defense.')
        vendor['status'] = 'defended'
        vendor['defense'] = assessment.model_dump(mode='json')
        self.store.put_vendor(vendor, db)

    def accept(self, vendor, db):
        if vendor['status'] not in {'submitted', 'defended'}:
            raise Conflict('An unresolved vendor dispute cannot be accepted.')
        timestamp = now()
        vendor.update(status='accepted', accepted_at=timestamp.isoformat(),
                      memo_due_at=(timestamp + timedelta(seconds=self.settings.credit_delay_seconds)).isoformat())
        self.store.put_vendor(vendor, db)

    def poll_memo(self, vendor, db):
        memo = self.store.memo(vendor['id'], db)
        if memo:
            return memo
        if vendor['status'] != 'accepted' or now() < datetime.fromisoformat(vendor['memo_due_at']):
            return None
        memo = {
            'id': f"memo_{vendor['id']}", 'claim_id': vendor['id'], 'case_id': vendor['case_id'],
            'contract_id': vendor['contract_id'], 'incident_id': vendor['incident_id'],
            'vendor': vendor['vendor'], 'customer': vendor['customer'],
            'currency': vendor['currency'], 'amount_cents': vendor['amount_cents'],
            'status': 'posted', 'issued_at': now().isoformat(),
        }
        db.execute('INSERT INTO credit_memos VALUES (?,?,?)',
                   (memo['id'], vendor['id'], json.dumps(memo)))
        return memo
