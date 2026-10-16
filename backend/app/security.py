"""Single-process pilot controls. Put a trusted rate-limiting gateway in front of a public host."""
import asyncio
from collections import OrderedDict
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from starlette.responses import JSONResponse


PUBLIC = {'/health', '/ready', '/auth/login', '/auth/signup', '/auth/signup-status'}
WRITE_ROLES = {
    '/auth/logout': {'admin', 'operator', 'reviewer'},
    '/contracts/demo/ingest': {'admin', 'operator'},
    '/contracts/ingest': {'admin', 'operator'},
    '/contracts': {'admin', 'operator'},
    '/cases/intake': {'admin', 'operator'},
    '/cases/{case_id}/amend': {'admin', 'operator'},
    '/cases/{case_id}/sources': {'admin', 'operator'},
    '/cases/{case_id}/sources/pilot-fixtures': {'admin', 'operator'},
    '/cases/{case_id}/review': {'admin', 'reviewer'},
}


def authorize(request, enabled=True):
    if not enabled or request.url.path in PUBLIC:
        return
    role = request.state.identity['role']
    # Match the resolved route, never an attacker-selected suffix or URL alias.
    template = request.scope['route'].path
    permitted = {'admin'} if template.startswith('/admin/') else None
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        permitted = WRITE_ROLES.get(template, {'admin'})
    if permitted is not None and role not in permitted:
        raise HTTPException(403, 'Your account cannot perform this action.')


def origin_allowed(request, origins):
    origin = request.headers.get('origin')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return False
    if origin is None:
        return True  # Non-browser API clients still require a valid session.
    try:
        value = urlsplit(origin)
        if value.scheme not in {'http', 'https'} or not value.netloc or value.username or value.password:
            return False
        if value.path or value.query or value.fragment:
            return False
        return origin in origins
    except ValueError:
        return False


class RateLimits:
    """Bounded token buckets; keys come from the actual peer/session, not forwarded headers."""
    def __init__(self):
        self.buckets = OrderedDict()
        self.clock = time.monotonic

    def allow(self, key, capacity, seconds):
        now = self.clock()
        tokens, then = self.buckets.pop(key, (float(capacity), now))
        tokens = min(capacity, tokens + (now - then) * capacity / seconds)
        allowed = tokens >= 1
        self.buckets[key] = (tokens - 1 if allowed else tokens, now)
        while len(self.buckets) > 4096:
            self.buckets.popitem(last=False)
        return allowed


class BoundedBodyMiddleware:
    """Cap actual received bytes before JSON/multipart parsing, even for chunked bodies."""
    def __init__(self, app, max_upload_bytes=11 * 1024 * 1024, max_json_bytes=256 * 1024):
        self.app = app
        self.max_upload_bytes, self.max_json_bytes = max_upload_bytes, max_json_bytes
        self.slots = asyncio.Semaphore(8)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in {'GET', 'HEAD', 'OPTIONS'}:
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        limit = self.max_upload_bytes if headers.get(b'content-type', b'').lower().startswith(b'multipart/form-data') else self.max_json_bytes
        async def reject(status, message):
            await JSONResponse({'detail': message}, status_code=status)(scope, receive, send)
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0: raise ValueError()
        except ValueError:
            return await reject(400, 'Invalid request length.')
        if length > limit:
            return await reject(413, 'Request is too large.')
        if self.slots.locked():
            return await reject(429, 'Too many active requests. Retry shortly.')
        async with self.slots:
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect': return
                        chunk = message.get('body', b'')
                        if len(body) + len(chunk) > limit:
                            return await reject(413, 'Request is too large.')
                        body.extend(chunk)
                        if not message.get('more_body', False): break
            except TimeoutError:
                return await reject(408, 'Request body timed out.')
            delivered = False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()
            await self.app(scope, replay, send)
