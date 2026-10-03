import type { Brief, Candidate, Example, ExportFormat, GenerateResponse, RoomTypeInfo, Units } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

const UNREACHABLE = 'Cannot reach the Parti API. Is the backend running on port 8000?'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit & { json?: unknown }, signal?: AbortSignal): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      signal,
      headers: init?.json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(UNREACHABLE, 0)
  }
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    throw new ApiError(UNREACHABLE, res.status)
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = body.detail[0].msg.replace(/^Value error, /, '')
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status)
  }
  return res as Response & { json(): Promise<T> }
}

export async function getExamples(): Promise<Example[]> {
  return (await request<Example[]>('/api/examples')).json()
}

export async function getRoomTypes(): Promise<RoomTypeInfo[]> {
  return (await request<RoomTypeInfo[]>('/api/room-types')).json()
}

export async function interpret(prompt: string, signal?: AbortSignal): Promise<Brief> {
  return (await request<Brief>('/api/interpret', { method: 'POST', json: { prompt } }, signal)).json()
}

export async function generate(input: { prompt?: string; brief?: Brief }, signal?: AbortSignal): Promise<GenerateResponse> {
  return (await request<GenerateResponse>('/api/generate', { method: 'POST', json: { ...input, count: 6 } }, signal)).json()
}

export async function exportPlan(candidate: Candidate, format: ExportFormat, units: Units): Promise<Blob> {
  const res = await request('/api/export/' + format, { method: 'POST', json: { candidate, units } })
  return res.blob()
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
