import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, generate, getExamples, getRoomTypes, interpret } from './api'
import { BriefPanel, type RecentBrief } from './components/BriefPanel'
import { Segmented, Spinner } from './components/controls'
import { DetailsPanel, type DetailTab } from './components/DetailsPanel'
import { Icon } from './components/Icon'
import { type CanvasController, PlanCanvas } from './components/PlanCanvas'
import { RoomInspector } from './components/RoomInspector'
import { ShortcutsDialog } from './components/ShortcutsDialog'
import { type ThemePref, TopBar } from './components/TopBar'
import { VariantStrip } from './components/VariantStrip'
import { useHotkeys } from './hooks/useHotkeys'
import { usePersistentState } from './hooks/usePersistentState'
import { briefFromHash, encodeBrief } from './lib/share'
import type { Brief, Example, GenerateResponse, RoomTypeInfo, Units } from './types'

const DEFAULT_PROMPT = '2 bedroom apartment, 800 sqft, open kitchen and good daylight'
type Layers = { furniture: boolean; labels: boolean; dims: boolean }

export default function App() {
  const [units, setUnits] = usePersistentState<Units>('parti.units', 'metric')
  const [theme, setTheme] = usePersistentState<ThemePref>('parti.theme', 'system')
  const [layers, setLayers] = usePersistentState<Layers>('parti.layers', { furniture: true, labels: true, dims: true })
  const [recent, setRecent] = usePersistentState<RecentBrief[]>('parti.recent', [])

  const shared = useMemo(() => briefFromHash(window.location.hash), [])
  const [prompt, setPrompt] = useState(() => shared?.raw_prompt ?? recent[0]?.prompt ?? DEFAULT_PROMPT)
  const [brief, setBrief] = useState<Brief | null>(shared)
  const [briefEdited, setBriefEdited] = useState(false)
  const [interpreting, setInterpreting] = useState(false)
  const [interpretError, setInterpretError] = useState<string | null>(null)

  const [result, setResult] = useState<GenerateResponse | null>(null)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [floor, setFloor] = useState(1)
  const [selectedRoom, setSelectedRoom] = useState<string | null>(null)
  const [hoverRoom, setHoverRoom] = useState<string | null>(null)
  const [tab, setTab] = useState<DetailTab>('score')
  const [examples, setExamples] = useState<Example[]>([])
  const [roomTypes, setRoomTypes] = useState<RoomTypeInfo[]>([])
  const [help, setHelp] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const [rereadToken, setRereadToken] = useState(0)

  const canvas = useRef<CanvasController>(null)
  const genAbort = useRef<AbortController | null>(null)
  const skipInterpret = useRef(!!shared)
  const autoRun = useRef(true)

  // Theme.
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') delete root.dataset.theme
    else root.dataset.theme = theme
  }, [theme])

  // Static data.
  useEffect(() => {
    getExamples().then(setExamples).catch(() => undefined)
    getRoomTypes().then(setRoomTypes).catch(() => undefined)
  }, [])

  const runGenerate = useCallback(
    async (input?: Brief | null) => {
      const b = input ?? brief
      if (!b && !prompt.trim()) return
      genAbort.current?.abort()
      const ac = new AbortController()
      genAbort.current = ac
      setGenerating(true)
      setGenError(null)
      try {
        const res = await generate(b ? { brief: b } : { prompt }, ac.signal)
        setResult(res)
        // The server may adjust the brief (e.g. raise an infeasible area); show what was used.
        setBrief(res.brief)
        setInterpretError(null)
        setSelectedId(res.best_candidate_id)
        setFloor(1)
        setSelectedRoom(null)
        const token = encodeBrief(res.brief)
        window.history.replaceState(null, '', `#b=${token}`)
        setRecent((prev) => {
          const entry: RecentBrief = { prompt: res.brief.raw_prompt, brief: res.brief, at: Date.now() }
          return [entry, ...prev.filter((r) => encodeBrief(r.brief) !== token)].slice(0, 6)
        })
        const valid = res.candidates.filter((c) => c.validation.valid).length
        setAnnouncement(`Generated ${res.candidates.length} variants in ${(res.elapsed_ms / 1000).toFixed(1)} seconds, ${valid} pass all checks.`)
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        setGenError(e instanceof ApiError || e instanceof Error ? e.message : 'Generation failed')
      } finally {
        if (genAbort.current === ac) setGenerating(false)
      }
    },
    [brief, prompt, setRecent],
  )

  // Read the brief as the user types; the first successful read on load
  // also generates, so a first visit lands on a finished plan.
  useEffect(() => {
    if (skipInterpret.current) {
      skipInterpret.current = false
      if (shared && autoRun.current) {
        autoRun.current = false
        runGenerate(shared)
      }
      return
    }
    const text = prompt.trim()
    if (!text) {
      setBrief(null)
      return
    }
    const ac = new AbortController()
    const t = setTimeout(async () => {
      setInterpreting(true)
      try {
        const b = await interpret(text, ac.signal)
        setBrief(b)
        setBriefEdited(false)
        setInterpretError(null)
        if (autoRun.current) {
          autoRun.current = false
          runGenerate(b)
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setInterpretError((e as Error).message)
          if (autoRun.current) {
            autoRun.current = false
            setGenError((e as Error).message)
          }
        }
      } finally {
        if (!ac.signal.aborted) setInterpreting(false)
      }
    }, 350)
    return () => {
      clearTimeout(t)
      ac.abort()
    }
  }, [prompt, rereadToken])

  const candidates = result?.candidates ?? []
  const candidate = candidates.find((c) => c.id === selectedId) ?? null
  const levels = candidate?.floors ?? 1
  const svg = candidate ? (result?.drawings[candidate.id]?.[Math.min(floor, levels) - 1] ?? '') : ''
  const flagged = useMemo(
    () => (candidate ? candidate.validation.issues.filter((i) => i.severity === 'error').flatMap((i) => i.room_ids) : []),
    [candidate],
  )

  const selectRoom = useCallback(
    (id: string | null) => {
      setSelectedRoom(id)
      const room = candidate?.rooms.find((r) => r.id === id)
      if (room && room.floor !== floor) setFloor(room.floor)
    },
    [candidate, floor],
  )

  const stepVariant = (dir: number) => {
    if (!candidates.length) return
    const i = candidates.findIndex((c) => c.id === selectedId)
    const next = candidates[(i + dir + candidates.length) % candidates.length]
    setSelectedId(next.id)
    setSelectedRoom(null)
  }

  useHotkeys({
    'mod+Enter': () => runGenerate(),
    ArrowLeft: () => stepVariant(-1),
    ArrowRight: () => stepVariant(1),
    '1': () => setFloor(1),
    '2': () => levels >= 2 && setFloor(2),
    '3': () => levels >= 3 && setFloor(3),
    '+': () => canvas.current?.zoomBy(1.3),
    '=': () => canvas.current?.zoomBy(1.3),
    '-': () => canvas.current?.zoomBy(1 / 1.3),
    '0': () => canvas.current?.fit(),
    f: () => setLayers((l) => ({ ...l, furniture: !l.furniture })),
    l: () => setLayers((l) => ({ ...l, labels: !l.labels })),
    d: () => setLayers((l) => ({ ...l, dims: !l.dims })),
    u: () => setUnits((u) => (u === 'metric' ? 'imperial' : 'metric')),
    Escape: () => (help ? setHelp(false) : setSelectedRoom(null)),
    '?': () => setHelp(true),
  })

  const shareUrl = result ? `${window.location.origin}${window.location.pathname}#b=${encodeBrief(result.brief)}` : ''
  const layerClass = `${layers.furniture ? '' : 'hide-furniture'} ${layers.labels ? '' : 'hide-labels'} ${layers.dims ? '' : 'hide-dims'}`
  const planLabel = candidate
    ? `${candidate.label}: ${candidate.strategy}, ${candidate.rooms.length} rooms, score ${Math.round(candidate.score.total)}. Use the Rooms tab for a list.`
    : 'Floor plan'

  return (
    <div className={`app units-${units}`}>
      <a className="skip-link" href="#plan-stage">
        Skip to plan
      </a>
      <TopBar units={units} theme={theme} onUnits={setUnits} onTheme={setTheme} onHelp={() => setHelp(true)} />

      <main className="workspace">
        <BriefPanel
          prompt={prompt}
          brief={brief}
          briefEdited={briefEdited}
          interpreting={interpreting}
          interpretError={interpretError}
          generating={generating}
          examples={examples}
          recent={recent}
          roomTypes={roomTypes}
          units={units}
          onPromptChange={setPrompt}
          onBriefChange={(b) => {
            // Interpreter notes describe the text, not a hand-edited program.
            setBrief({ ...b, notes: [] })
            setBriefEdited(true)
          }}
          onResetBrief={() => setRereadToken((n) => n + 1)}
          onGenerate={() => runGenerate()}
          onPickRecent={(r) => {
            skipInterpret.current = true
            setPrompt(r.prompt)
            setBrief(r.brief)
            setBriefEdited(false)
            runGenerate(r.brief)
          }}
          onClearRecent={() => setRecent([])}
        />

        <section className="stage" id="plan-stage" aria-label="Plan">
          <div className={`canvas-frame ${layerClass}`}>
            {candidate && (
              <div className="canvas-toolbar" role="toolbar" aria-label="Plan view">
                <div className="toolbar-group">
                  {levels > 1 && (
                    <Segmented
                      label="Level"
                      size="sm"
                      value={Math.min(floor, levels)}
                      options={Array.from({ length: levels }, (_, i) => ({ value: i + 1, label: `Level ${i + 1}` }))}
                      onChange={(f) => {
                        setFloor(f)
                        setSelectedRoom(null)
                      }}
                    />
                  )}
                </div>
                <div className="toolbar-group">
                  {(
                    [
                      ['furniture', 'Furniture', 'F'],
                      ['labels', 'Labels', 'L'],
                      ['dims', 'Dimensions', 'D'],
                    ] as const
                  ).map(([key, label, k]) => (
                    <button
                      key={key}
                      type="button"
                      className={`toggle ${layers[key] ? 'is-on' : ''}`}
                      aria-pressed={layers[key]}
                      title={`${label} (${k})`}
                      onClick={() => setLayers({ ...layers, [key]: !layers[key] })}
                    >
                      {label}
                    </button>
                  ))}
                  <span className="toolbar-sep" />
                  <button type="button" className="icon-btn" onClick={() => canvas.current?.zoomBy(1 / 1.3)} aria-label="Zoom out" title="Zoom out (−)">
                    <Icon name="minus" />
                  </button>
                  <button type="button" className="icon-btn" onClick={() => canvas.current?.fit()} aria-label="Fit to view" title="Fit (0)">
                    <Icon name="fit" />
                  </button>
                  <button type="button" className="icon-btn" onClick={() => canvas.current?.zoomBy(1.3)} aria-label="Zoom in" title="Zoom in (+)">
                    <Icon name="plus" />
                  </button>
                </div>
              </div>
            )}

            {svg ? (
              <PlanCanvas
                svg={svg}
                selectedRoom={selectedRoom}
                hoverRoom={hoverRoom}
                flaggedRooms={flagged}
                label={planLabel}
                onHoverRoom={setHoverRoom}
                onSelectRoom={selectRoom}
                controllerRef={canvas}
              />
            ) : (
              <EmptyStage generating={generating} error={genError} onRetry={() => runGenerate()} />
            )}

            {generating && candidate && (
              <div className="canvas-busy" role="status">
                <Spinner /> Exploring layouts…
              </div>
            )}
            {genError && candidate && (
              <div className="canvas-alert" role="alert">
                <Icon name="alert" />
                <span>{genError}</span>
                <button type="button" className="link-btn" onClick={() => runGenerate()}>
                  Retry
                </button>
              </div>
            )}

            {candidate && !selectedRoom && (
              <ul className="legend" aria-label="Zone colours">
                {(['public', 'private', 'service', 'circulation'] as const).map((z) => (
                  <li key={z}>
                    <span className={`zone-dot zone-${z}`} aria-hidden="true" />
                    {z.charAt(0).toUpperCase() + z.slice(1)}
                  </li>
                ))}
              </ul>
            )}

            {candidate && selectedRoom && (
              <RoomInspector candidate={candidate} roomId={selectedRoom} units={units} onClose={() => setSelectedRoom(null)} onSelectRoom={selectRoom} />
            )}
          </div>

          {result && candidates.length > 0 && (
            <div className="variants-wrap">
              <div className="variants-head">
                <h2>Variants</h2>
                <span className="muted small">
                  {candidates.length} plans · {(result.elapsed_ms / 1000).toFixed(1)} s · <span className="kbd-hint">← → to browse</span>
                </span>
              </div>
              <VariantStrip
                candidates={candidates}
                drawings={result.drawings}
                selectedId={selectedId}
                units={units}
                onSelect={(id) => {
                  setSelectedId(id)
                  setSelectedRoom(null)
                }}
              />
            </div>
          )}
        </section>

        {candidate && result ? (
          <DetailsPanel
            candidate={candidate}
            targetArea={result.brief.target_area_sqm}
            units={units}
            tab={tab}
            onTab={setTab}
            selectedRoom={selectedRoom}
            hoverRoom={hoverRoom}
            onSelectRoom={selectRoom}
            onHoverRoom={setHoverRoom}
            shareUrl={shareUrl}
            briefPrompt={result.brief.raw_prompt}
          />
        ) : (
          <aside className="panel details details-empty" aria-hidden="true">
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-line" />
            <div className="skeleton skeleton-block" />
          </aside>
        )}
      </main>

      <ShortcutsDialog open={help} onClose={() => setHelp(false)} />
      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>
    </div>
  )
}

function EmptyStage({ generating, error, onRetry }: { generating: boolean; error: string | null; onRetry: () => void }) {
  if (error) {
    return (
      <div className="stage-message" role="alert">
        <Icon name="alert" size={22} />
        <h3>Could not generate a plan</h3>
        <p>{error}</p>
        <p className="fine">
          Start the API with <code>uvicorn app.main:app --reload</code> in <code>backend/</code>, then retry.
        </p>
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
      </div>
    )
  }
  if (generating) {
    return (
      <div className="stage-message" role="status">
        <div className="drafting" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <h3>Exploring layouts…</h3>
        <p className="muted">Testing room arrangements, doors, daylight and furniture.</p>
      </div>
    )
  }
  return (
    <div className="stage-message">
      <Icon name="sparkle" size={22} />
      <h3>Describe a building to begin</h3>
      <p className="muted">Write a brief on the left or pick an example, then generate.</p>
    </div>
  )
}
