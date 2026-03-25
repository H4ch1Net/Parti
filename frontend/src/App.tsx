import { useEffect, useMemo, useState } from 'react'
import { CandidateList } from './components/CandidateList'
import { ScheduleTable } from './components/ScheduleTable'
import { ScorePanel } from './components/ScorePanel'
import { SvgViewer } from './components/SvgViewer'
import { downloadExport, exportInlineSvg, generatePlan, getExamples, parsePlan } from './api/client'
import type { Candidate, GenerateResponse } from './types/planner'

export default function App() {
  const [prompt, setPrompt] = useState('Make a floor plan for 2 bedrooms, kitchen, bathroom. 800 sqft')
  const [examples, setExamples] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GenerateResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [svg, setSvg] = useState('')
  const [parseInfo, setParseInfo] = useState<any>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getExamples().then(setExamples).catch(() => undefined)
  }, [])

  const selected: Candidate | null = useMemo(() => {
    if (!result) return null
    const id = selectedId ?? result.best_candidate_id
    return result.candidates.find((c) => c.id === id) ?? null
  }, [result, selectedId])

  useEffect(() => {
    if (!selected) return
    exportInlineSvg(selected)
      .then(setSvg)
      .catch((e: Error) => setError(e.message))
  }, [selected])

  async function onGenerate() {
    setLoading(true)
    setError('')
    try {
      const data = await generatePlan(prompt)
      setResult(data)
      setSelectedId(data.best_candidate_id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function onUpload(file: File) {
    try {
      const parsed = await parsePlan(file)
      setParseInfo(parsed)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <h1>Architect Planner</h1>
        <p>Natural-language to architect-quality schematic floor plans</p>
      </header>

      <section className="controls panel">
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} />
        <div className="row">
          <button onClick={onGenerate} disabled={loading}>{loading ? 'Generating...' : 'Generate Plans'}</button>
          <label className="upload">
            Upload Plan
            <input type="file" accept=".png,.jpg,.jpeg,.pdf" onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
          </label>
        </div>
        <div className="examples">
          {examples.map((e, idx) => (
            <button key={idx} onClick={() => setPrompt(e)}>{e}</button>
          ))}
        </div>
      </section>

      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <CandidateList items={result.candidates} selectedId={selectedId} onSelect={setSelectedId} />

          <section className="content-grid">
            <div className="panel">
              <h3>Drafted Plan (SVG)</h3>
              {svg ? <SvgViewer svg={svg} /> : <p>Loading SVG...</p>}
              {selected && (
                <div className="row">
                  <button onClick={() => downloadExport(selected, 'svg')}>Download SVG</button>
                  <button onClick={() => downloadExport(selected, 'pdf')}>Download PDF</button>
                  <button onClick={() => downloadExport(selected, 'dxf')}>Download DXF</button>
                  <button onClick={() => downloadExport(selected, 'png')}>Download PNG</button>
                </div>
              )}
            </div>

            <ScorePanel candidate={selected} />
            <ScheduleTable candidate={selected} />
            <div className="panel">
              <h3>Validation</h3>
              {selected && (
                <>
                  <p>Status: {selected.validation.valid ? 'Valid' : 'Invalid'}</p>
                  <p>Errors: {selected.validation.errors.length ? selected.validation.errors.join('; ') : 'None'}</p>
                  <p>Warnings: {selected.validation.warnings.length ? selected.validation.warnings.join('; ') : 'None'}</p>
                </>
              )}
            </div>
            <div className="panel">
              <h3>Parser Output</h3>
              {parseInfo ? <pre>{JSON.stringify(parseInfo, null, 2)}</pre> : <p>Upload an image/PDF to parse.</p>}
            </div>
          </section>
        </>
      )}
    </main>
  )
}
