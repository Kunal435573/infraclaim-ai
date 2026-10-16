"""Explicit mock/live evaluations; this command never falls back between modes."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.services.case_engine import CaseEngine
from app.services.evaluation import run_evaluation
from app.services.nebius import NebiusClient
from app.services.repository import load_contract


def source_hash():
    hasher = hashlib.sha256()
    for path in sorted((ROOT / 'backend/app').rglob('*.py')):
        hasher.update(path.relative_to(ROOT).as_posix().encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['mock', 'live'])
    parser.add_argument('--count', type=int, default=50)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 5 <= args.count <= 200:
        parser.error('count must be 5..200')
    settings = Settings(infraclaim_llm_mode=args.mode, watcher_enabled=False)
    client = NebiusClient(settings)
    preflight = await client.preflight() if args.mode == 'live' else None
    if preflight and preflight['status'] != 'ready':
        report = {'suite': 'infraclaim_phase6_v1', 'mode': 'live', 'status': 'blocked',
                  'generated_at': datetime.now(timezone.utc).isoformat(), 'scenario_count': 0,
                  'requested_scenario_count': args.count, 'real_model_successes': 0,
                  'metrics': None, 'model_metrics': None, 'publishable_live_model_metrics': False}
    else:
        report = await run_evaluation(load_contract(), CaseEngine(client, settings), args.count)
    report.update(preflight=preflight, source_sha256=source_hash(), python_version=platform.python_version())
    output = args.output or ROOT / 'reports' / f"evaluation-{args.mode}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'mode': args.mode,
                      'scenarios': report['scenario_count'], 'real_model_successes': report['real_model_successes'],
                      'metrics': report['metrics'], 'report': str(output)}, indent=2))
    if report['status'] != 'completed' or (args.mode == 'live' and not report['publishable_live_model_metrics']):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
