"""Bounded Token Factory requests. Failure yields review, never a mock fallback."""
import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any
import httpx
from app.config import get_settings
from app.schemas import ModelAssessment, ReasoningAssessment


def output_schema():
    schema = ModelAssessment.model_json_schema()
    schema['required'] = list(schema['properties'])
    return {'type': 'json_schema', 'json_schema': {'name': 'infraclaim_assessment', 'strict': True, 'schema': schema}}


class InferenceOutput(dict):
    def __init__(self, value, trace):
        super().__init__(value)
        self.trace = trace


class InferenceError(RuntimeError):
    def __init__(self, code, trace):
        super().__init__(code)
        self.trace = dict(trace, status='failed', error_code=code)


class NebiusClient:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport
        self._slots = asyncio.Semaphore(2)

    @property
    def live(self):
        return self.settings.infraclaim_llm_mode == 'live'

    def _key(self):
        key = self.settings.nebius_api_key
        return key.get_secret_value().strip() if hasattr(key, 'get_secret_value') else str(key or '').strip()

    def runtime(self):
        return {'mode': self.settings.infraclaim_llm_mode, 'provider': 'Nebius Token Factory',
                'configured': bool(self._key()) if self.live else True,
                'routine_model': self.settings.nebius_lightning_model,
                'complex_model': self.settings.nebius_super_model,
                'vendor_mode': 'simulated', 'structured_output': 'json_schema',
                'live_verification': 'See per-case provenance and separate live evaluation reports.',
                'principle': 'Model interpretation; deterministic financial and action authority.'}

    async def preflight(self):
        """Catalog access is not an inference success. Never return provider error bodies."""
        if not self.live or not self._key():
            return {'status': 'blocked', 'reason': 'Live mode and NEBIUS_API_KEY are required', 'inference_verified': False}
        try:
            async with httpx.AsyncClient(timeout=self.settings.nebius_timeout_seconds, transport=self.transport,
                                         follow_redirects=False) as client:
                response = await client.get(self.settings.nebius_base_url + '/models',
                                            headers={'Authorization': f'Bearer {self._key()}'})
                response.raise_for_status()
                ids = {m['id'] for m in response.json()['data']}
            required = {self.settings.nebius_lightning_model, self.settings.nebius_super_model}
            missing = sorted(required - ids)
            return {'status': 'blocked' if missing else 'ready', 'missing_models': missing,
                    'available_nemotron_models': sorted(x for x in ids if 'nemotron' in x.lower()),
                    'inference_verified': False, 'execution': 'test_transport' if self.transport else 'live'}
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return {'status': 'blocked', 'reason': type(exc).__name__, 'inference_verified': False}

    async def reason_json(self, *, system: str, prompt: str, complex_case: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        model = self.settings.nebius_super_model if complex_case else self.settings.nebius_lightning_model
        trace = {'requested_mode': self.settings.infraclaim_llm_mode,
                 'execution': ('test_transport' if self.transport else 'live') if self.live else 'mock',
                 'model': model if self.live else None, 'status': 'pending', 'attempts': 0,
                 'recorded_at': datetime.now(timezone.utc).isoformat(),
                 'prompt_sha256': hashlib.sha256((system + '\n' + prompt).encode()).hexdigest(),
                 'schema_sha256': hashlib.sha256(json.dumps(output_schema(), sort_keys=True).encode()).hexdigest()}
        if not self.live:
            citations = ['sla.cooling.7.4', 'ev_ticket', 'ev_ack', 'ev_telemetry', 'ev_maintenance_0']
            decision = 'supported'
            contradictions = []
            try:
                source = json.loads(prompt)
                citations = [source['contract']['sla']['id'], *source['evidence_ids']]
                contradictions = source.get('deterministic_contradictions', [])
                if not source.get('entitlement', {}).get('eligible', True):
                    decision = 'not_supported'
                elif contradictions:
                    decision = 'needs_review'
            except (ValueError, KeyError, TypeError):
                pass
            value = {'decision': decision, 'confidence': 0.82 if decision == 'needs_review' else 0.97,
                     'summary': 'Mock assessment of the supplied evidence; no model was called.',
                     'citations': citations, 'contradictions': contradictions,
                     'exclusion_analysis': ['Mock fixture; deterministic policy checks maintenance overlap.']}
            return InferenceOutput(value, dict(trace, status='succeeded', elapsed_ms=round((time.perf_counter()-started)*1000, 2)))
        if not self._key():
            raise InferenceError('missing_credentials', trace)
        if len(prompt) > 100000:
            raise InferenceError('input_too_large', trace)
        payload = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
                   'temperature': 0, 'max_tokens': self.settings.nebius_max_tokens, 'response_format': output_schema()}
        if self._slots.locked():
            raise InferenceError('provider_busy', trace)
        async with self._slots:
            async with httpx.AsyncClient(timeout=self.settings.nebius_timeout_seconds, transport=self.transport,
                                         follow_redirects=False) as client:
                for attempt in range(1, self.settings.nebius_max_attempts + 1):
                    trace['attempts'] = attempt
                    try:
                        async with asyncio.timeout(self.settings.nebius_timeout_seconds):
                            response = await client.post(self.settings.nebius_base_url + '/chat/completions',
                                                         headers={'Authorization': f'Bearer {self._key()}'}, json=payload)
                        trace['http_status'] = response.status_code
                        if response.status_code in {429, 502, 503, 504} and attempt < self.settings.nebius_max_attempts:
                            await asyncio.sleep(min(attempt * 0.25, 1))
                            continue
                        if response.status_code != 200:
                            raise InferenceError(f'http_{response.status_code}', trace)
                        if len(response.content) > 1000000:
                            raise InferenceError('response_too_large', trace)
                        data = response.json()
                        choice = data['choices'][0]
                        message = choice['message']
                        if message.get('refusal'):
                            raise InferenceError('model_refusal', trace)
                        if choice.get('finish_reason') != 'stop':
                            raise InferenceError('incomplete_output', trace)
                        raw = json.loads(message['content'])
                        if set(raw) != set(ModelAssessment.model_fields):
                            raise InferenceError('invalid_schema', trace)
                        validated = ModelAssessment.model_validate(raw, strict=True)
                        trace.update(status='succeeded', response_id=str(data.get('id', ''))[:160],
                                     response_model=str(data.get('model', ''))[:160],
                                     elapsed_ms=round((time.perf_counter()-started)*1000, 2))
                        trace['usage'] = {k: v for k, v in (data.get('usage') or {}).items()
                                          if k in {'prompt_tokens', 'completion_tokens', 'total_tokens'}
                                          and type(v) is int and v >= 0}
                        return InferenceOutput(validated.model_dump(), trace)
                    except (httpx.RequestError, TimeoutError):
                        if attempt < self.settings.nebius_max_attempts:
                            await asyncio.sleep(min(attempt * 0.25, 1))
                            continue
                        raise InferenceError('transport_error', trace) from None
                    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                        raise InferenceError('invalid_schema', trace) from None
        raise InferenceError('request_failed', trace)


async def assess(client, *, system, prompt, complex_case=True):
    """Fail closed without logging credentials, source payloads or provider bodies."""
    trace = None
    try:
        raw = await client.reason_json(system=system, prompt=prompt, complex_case=complex_case)
        trace = raw.trace if isinstance(raw, InferenceOutput) else None
        assessment = ModelAssessment.model_validate(dict(raw), strict=True)
        return ReasoningAssessment(**assessment.model_dump(), inference=trace)
    except (ValueError, TypeError, KeyError, IndexError, RuntimeError, httpx.HTTPError) as exc:
        trace = exc.trace if isinstance(exc, InferenceError) else trace
        return ReasoningAssessment(decision='needs_review', confidence=0,
            summary='Model assessment unavailable or invalid; human review is required.',
            contradictions=['Model assessment could not be validated.'], inference=trace)
