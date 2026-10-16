import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
let activeWrites = 0

async function boundedBody(request: NextRequest, limit: number): Promise<ArrayBuffer> {
  const reader = request.body?.getReader()
  if (!reader) return new ArrayBuffer(0)
  const chunks: Uint8Array[] = []
  let total = 0
  let timeout: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => { void reader.cancel(); reject(new Error('body_timeout')) }, 15000)
  })
  try {
    while (true) {
      const { done, value } = await Promise.race([reader.read(), deadline])
      if (done) break
      total += value.byteLength
      // Let the 413 response flush before closing the connection; canceling the
      // incoming Node stream here destroys the socket before clients see it.
      if (total > limit) throw new Error('body_too_large')
      chunks.push(value)
    }
    const body = new Uint8Array(total)
    let offset = 0
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength }
    return body.buffer
  } finally { if (timeout) clearTimeout(timeout); reader.releaseLock() }
}
// Backend address is server-only. No provider credentials enter browser bundles.
async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (request.method === 'POST') {
    const origin = request.headers.get('origin')
    let invalidOrigin = false
    if (origin) {
      try {
        const parsed = new URL(origin)
        invalidOrigin = !['http:', 'https:'].includes(parsed.protocol) || parsed.host !== request.headers.get('host') || !!parsed.username || !!parsed.password || parsed.origin !== origin
      } catch { invalidOrigin = true }
    }
    if (request.headers.get('sec-fetch-site') === 'cross-site' || invalidOrigin) {
      return NextResponse.json({ detail: 'Cross-origin actions are not allowed' }, { status: 403 })
    }
    const limit = request.headers.get('content-type')?.toLowerCase().startsWith('multipart/form-data') ? 11 * 1024 * 1024 : 256 * 1024
    const length = request.headers.get('content-length') || '0'
    if (!/^\d+$/.test(length)) return NextResponse.json({ detail: 'Invalid request length' }, { status: 400 })
    if (Number(length) > limit) {
      return NextResponse.json({ detail: 'Request is too large' }, { status: 413 })
    }
    if (activeWrites >= 8) return NextResponse.json({ detail: 'Too many active requests. Retry shortly.' }, { status: 429 })
  }
  const { path } = await context.params
  if (path.some(part => part === '..' || part.includes('/') || part.includes('\\'))) {
    return NextResponse.json({ detail: 'Invalid path' }, { status: 400 })
  }
  const base = process.env.INFRACLAIM_API_INTERNAL_URL || 'http://127.0.0.1:8000'
  const target = `${base}/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`
  if (request.method === 'POST') activeWrites++
  try {
    const response = await fetch(target, {
      method: request.method,
      headers: {
        ...(request.headers.has('content-type') ? { 'content-type': request.headers.get('content-type')! } : {}),
        ...(request.headers.has('cookie') ? { cookie: request.headers.get('cookie')! } : {}),
      },
      body: request.method === 'POST' ? await boundedBody(request, request.headers.get('content-type')?.toLowerCase().startsWith('multipart/form-data') ? 11 * 1024 * 1024 : 256 * 1024) : undefined,
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(125000),
    })
    const headers = new Headers({ 'Content-Type': response.headers.get('content-type') || 'application/json',
      'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff' })
    if (response.headers.get('content-disposition') && ['application/pdf', 'application/octet-stream'].includes(response.headers.get('content-type') || '')) {
      headers.set('Content-Disposition', response.headers.get('content-disposition')!)
    }
    if (response.headers.get('set-cookie')) headers.set('Set-Cookie', response.headers.get('set-cookie')!)
    if (response.headers.get('retry-after')) headers.set('Retry-After', response.headers.get('retry-after')!)
    return new NextResponse(response.body, { status: response.status, headers })
  } catch (error) {
    if (error instanceof Error && error.message === 'body_too_large') return NextResponse.json({ detail: 'Request is too large' }, { status: 413, headers: { Connection: 'close' } })
    if (error instanceof Error && error.message === 'body_timeout') return NextResponse.json({ detail: 'Request body timed out' }, { status: 408 })
    return NextResponse.json({ detail: 'Backend unavailable or timed out. Refresh the saved case before retrying.' }, { status: 502 })
  } finally { if (request.method === 'POST') activeWrites-- }
}
export { forward as GET, forward as POST }
