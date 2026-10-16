"""Rehearse the persistent synthetic workflow through the real ASGI API, with an isolated DB."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['mock', 'live'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = {'mode': args.mode, 'vendor_mode': 'simulated', 'real_money_recovered': False,
              'started_at': datetime.now(timezone.utc).isoformat(), 'steps': [], 'status': 'failed'}
    try:
        with TemporaryDirectory(prefix='infraclaim-rehearsal-') as temp:
            settings = Settings(infraclaim_llm_mode=args.mode, database_path=str(Path(temp) / 'rehearsal.db'),
                                watcher_enabled=False, credit_delay_seconds=0)
            def call(client, path, method='POST'):
                response = client.request(method, path)
                assert response.status_code == 200, f'{path}: HTTP {response.status_code}'
                return response.json()
            with TestClient(create_app(settings)) as client:
                runtime = call(client, '/ai/runtime', 'GET')
                assert runtime['configured'], 'Live credentials are missing'
                contract = call(client, '/contracts/demo/ingest')
                assert contract['pages'] == 3 and contract['contract']['sla']['source_page'] == 2
                report['steps'].append('Three-page PDF ingested; Section 7.4 on page 2')
                hero = call(client, '/demo/investigate/inc_cooling_001')
                assert hero['state'] == 'claim_ready' and hero['amount_usd'] == 40000, f"Hero routed to {hero['state']}"
                cid = hero['id']
                report['investigation_inference'] = hero['reasoning']['inference']
                call(client, f'/cases/{cid}/run-loop')
                for expected in ['submitted', 'disputed', 'defended', 'accepted']:
                    call(client, '/watcher/tick')
                    hero = call(client, f'/cases/{cid}', 'GET')
                    assert hero['state'] == expected, f"Expected {expected}, got {hero['state']}"
                    report['steps'].append(expected)
                assert call(client, '/recovery-summary', 'GET')['verified_amount_usd'] == 0
                report['counter_inference'] = hero['counter_investigation']['inference']
            with TestClient(create_app(settings)) as client:
                hero = call(client, f'/cases/{cid}/reconcile')
                assert hero['state'] == 'verified' and hero['reconciliation']['matched']
                assert hero['reconciliation']['memo']['amount_cents'] == 4000000
                call(client, f'/cases/{cid}/reconcile')
                assert call(client, '/recovery-summary', 'GET')['verified_amount_usd'] == 40000
                assert call(client, '/recovery-summary', 'GET')['verified_cases'] == 1
                report['steps'].append('Restarted API; matched posted $40,000 simulated memo; duplicate reconciliation booked once')
                ambiguous = call(client, '/demo/investigate/inc_cooling_ambiguous')
                assert ambiguous['state'] == 'human_review'
                assert client.post(f"/cases/{ambiguous['id']}/submit").status_code == 409
                report['ambiguous_inference'] = ambiguous['reasoning']['inference']
                report['steps'].append('Ambiguous incident held for review; submission blocked')
                report['simulated_verified_amount_usd'] = 40000
                if args.mode == 'live':
                    assert all(report[name]['execution'] == 'live' and report[name]['status'] == 'succeeded'
                               for name in ['investigation_inference', 'counter_inference', 'ambiguous_inference'])
                report['status'] = 'passed'
    except AssertionError as exc:
        report['failure'] = str(exc)
    except Exception as exc:
        report['failure'] = type(exc).__name__  # No provider bodies or secrets.
    output = args.output or ROOT / 'reports' / f"rehearsal-{args.mode}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    sys.exit(main())
