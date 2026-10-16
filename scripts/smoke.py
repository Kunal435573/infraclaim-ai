"""Smoke test an already-running local backend and production dashboard."""
import json
import time
import urllib.request


def api(path, method='GET'):
    request = urllib.request.Request('http://127.0.0.1:8000' + path, method=method)
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


with urllib.request.urlopen('http://127.0.0.1:3000', timeout=30) as response:
    html = response.read().decode()
    assert response.status == 200 and 'InfraClaim' in html
    assert 'RECOVERY VERIFIED' in html
hero = api('/demo/investigate/inc_cooling_001', 'POST')
assert hero['amount_usd'] == 40000
api(f"/cases/{hero['id']}/run-loop", 'POST')
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    case = api(f"/cases/{hero['id']}")
    if case['state'] in {'verified', 'human_review'}:
        break
    time.sleep(0.5)
assert case['state'] == 'verified', case['state']
assert case['reconciliation']['memo']['amount_cents'] == 4000000
ambiguous = api('/demo/investigate/inc_cooling_ambiguous', 'POST')
assert ambiguous['state'] == 'human_review'
assert api('/recovery-summary')['verified_amount_usd'] == 40000
print(json.dumps({'frontend': 'HTTP 200 / production HTML', 'hero_state': case['state'],
                  'hero_amount_usd': case['amount_usd'], 'memo_matched': case['reconciliation']['matched'],
                  'ambiguous_state': ambiguous['state'], 'recovery': api('/recovery-summary')}, indent=2))
