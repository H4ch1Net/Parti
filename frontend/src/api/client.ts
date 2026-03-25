import type { Candidate, GenerateResponse } from '../types/planner'

const API = 'http://localhost:8000/api'

export async function generatePlan(prompt: string): Promise<GenerateResponse> {
  const res = await fetch(`${API}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) throw new Error('Failed to generate plan')
  return await res.json()
}

export async function getExamples(): Promise<string[]> {
  const res = await fetch(`${API}/examples`)
  if (!res.ok) throw new Error('Failed to load examples')
  return await res.json()
}

export async function parsePlan(file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API}/parse`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to parse file')
  return await res.json()
}

export async function exportInlineSvg(candidate: Candidate): Promise<string> {
  const res = await fetch(`${API}/export/svg-inline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate }),
  })
  if (!res.ok) throw new Error('Failed to render svg')
  return await res.text()
}

export async function downloadExport(candidate: Candidate, kind: 'svg' | 'pdf' | 'dxf' | 'png'): Promise<void> {
  const res = await fetch(`${API}/export/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate }),
  })
  if (!res.ok) throw new Error(`Failed to export ${kind}`)
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${candidate.id}.${kind}`
  a.click()
  window.URL.revokeObjectURL(url)
}
