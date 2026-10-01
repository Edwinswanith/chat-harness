import { useEffect, useRef, useState } from 'react'
import { api } from '../../services/api'

type Event = { seq: number; event: string; data: { timestamp?: string; component?: string; component_name?: string; event_type?: string; status?: string; summary?: string; duration_ms?: number; details?: Record<string, unknown> } }
type Change = { id: string; operation: string; path?: string; target_path?: string; before_sha256?: string; after_sha256?: string; tool_run_id?: string }
type Run = { id: string; status: string; attempts?: number; created_at?: number; website_validation?: { passed: boolean }; request?: { text: string } }
const tabs = ['All', 'Tools', 'Agents', 'Memory', 'RAG', 'Files', 'Terminal', 'Validation', 'Errors', 'Changes']
const categories: Record<string, string[]> = { Tools: ['tool'], Agents: ['subagent'], Memory: ['memory'], RAG: ['rag'], Files: ['workspace'], Terminal: ['terminal', 'sandbox', 'worker'], Validation: ['validation', 'visual_qa', 'preview'] }

export function WorkspaceActivity({ runId, conversationId, onReverted, embedded = false }: { runId?: string; conversationId?: string; onReverted: () => void; embedded?: boolean }) {
  const [collapsed, setCollapsed] = useState(false)
  const [events, setEvents] = useState<Event[]>([]); const [changes, setChanges] = useState<Change[]>([])
  const [runs, setRuns] = useState<Run[]>([]); const [selected, setSelected] = useState(runId ?? ''); const [run, setRun] = useState<Run>()
  const [error, setError] = useState(''); const [tab, setTab] = useState('All'); const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true); const [errorsOnly, setErrorsOnly] = useState(false)
  const [statusFilter, setStatusFilter] = useState(''); const [expanded, setExpanded] = useState(false); const end = useRef<HTMLDivElement>(null)
  useEffect(() => { setSelected(runId ?? '') }, [runId, conversationId])
  useEffect(() => {
    if (!conversationId) { setRuns([]); return }
    let alive = true
    const refresh = () => void api<Run[]>(`/conversations/${conversationId}/runs`).then(items => {
      if (!alive) return
      setRuns(items); setSelected(current => current || items.at(-1)?.id || '')
    }).catch(reason => { if (alive) setError(String(reason)) })
    refresh(); const timer = window.setInterval(refresh, 2500)
    return () => { alive = false; window.clearInterval(timer) }
  }, [conversationId])
  useEffect(() => {
    setEvents([]); setChanges([]); setRun(undefined); setError('')
    if (!selected) return
    let alive = true
    const refresh = () => void Promise.all([api<Event[]>(`/runs/${selected}/activity`), api<Change[]>(`/runs/${selected}/changes`), api<Run>(`/runs/${selected}`)]).then(([activity, nextChanges, nextRun]) => {
      if (alive) { setEvents(activity); setChanges(nextChanges); setRun(nextRun); setError('') }
    }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : 'Unable to load activity') })
    refresh(); const timer = window.setInterval(refresh, 1200)
    return () => { alive = false; window.clearInterval(timer) }
  }, [selected])
  useEffect(() => { if (autoScroll && !collapsed) end.current?.scrollIntoView({ block: 'nearest' }) }, [events.length, autoScroll, collapsed, tab])
  async function revert() {
    if (!selected || !confirm('Revert safe changes made by this run? Files changed after the run will be left untouched.')) return
    try { await api(`/runs/${selected}/revert`, { method: 'POST' }); onReverted(); setChanges([]) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to revert this run') }
  }
  const activity = events.filter(item => !['delta', 'final'].includes(item.event))
  const visible = activity.filter(({ data }) => {
    const failed = data.status === 'failed'
    return (!(errorsOnly || tab === 'Errors') || failed) && (!statusFilter || data.status === statusFilter) &&
      (!categories[tab] || categories[tab].includes(data.component ?? '')) &&
      (!search || JSON.stringify(data).toLowerCase().includes(search.toLowerCase()))
  })
  const first = events[0]?.data.timestamp
  const last = events.at(-1)?.data.timestamp
  const elapsed = first ? Math.max(0, Math.floor(((run && ['completed', 'failed', 'cancelled'].includes(run.status) && last ? Date.parse(last) : Date.now()) - Date.parse(first)) / 1000)) : 0
  const files = new Set(changes.filter(item => ['create', 'write', 'patch', 'rename', 'delete'].includes(item.operation)).map(item => item.path))
  const tools = activity.filter(item => item.event === 'tool').length
  const agents = activity.filter(item => item.data.component === 'subagent' && item.data.status === 'started').length
  const metrics = { Status: run?.status ?? 'Idle', Stage: activity.filter(item => item.event === 'state').at(-1)?.data.details?.status ?? 'Pending', Elapsed: `${elapsed}s`, Tools: tools, 'Files Changed': files.size, Agents: agents, Retries: run?.attempts ?? 0, Validation: run?.website_validation ? run.website_validation.passed ? 'Passed' : 'Failed' : 'Pending' }
  return <aside className={`${embedded ? 'workspace-log-panel' : 'workspace-activity'} ${collapsed ? 'collapsed' : ''}`}>
    {!embedded && <button className="workspace-activity-toggle" onClick={() => setCollapsed(value => !value)} title={collapsed ? 'Show workspace activity' : 'Hide workspace activity'}>{collapsed ? '‹' : '›'}</button>}
    {!collapsed && <><div className="workspace-activity-head"><p className="eyebrow">RUN ACTIVITY</p><b>Workspace logs</b></div>
      <label className="run-selector">Run<select aria-label="Select run" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Select a run</option>{runs.map(item => <option key={item.id} value={item.id}>{item.request?.text.slice(0, 40) ?? item.id} · {item.status}</option>)}{selected && !runs.some(item => item.id === selected) && <option value={selected}>{selected}</option>}</select></label>
      <dl className="run-metrics">{Object.entries(metrics).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}</dl>
      {error && <p role="alert" className="workspace-files-error">{error}</p>}
      <div className="log-tabs" role="tablist" aria-label="Log categories">{tabs.map(name => <button key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name}</button>)}</div>
      <div className="log-controls"><input aria-label="Search logs" placeholder="Search logs…" value={search} onChange={event => setSearch(event.target.value)} />
        <select aria-label="Filter log status" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="">All statuses</option>{['started', 'running', 'success', 'warning', 'failed', 'retrying', 'cancelled', 'skipped'].map(status => <option key={status}>{status}</option>)}</select>
        <label><input type="checkbox" checked={autoScroll} onChange={event => setAutoScroll(event.target.checked)} />Auto-scroll</label>
        <label><input type="checkbox" checked={errorsOnly} onChange={event => setErrorsOnly(event.target.checked)} />Errors only</label>
        <button onClick={() => setExpanded(value => !value)}>{expanded ? 'Collapse' : 'Expand'} details</button>
      </div>
      <section className="execution-log" aria-label={tab === 'Changes' ? 'Workspace changes' : 'Execution events'}>
        {tab === 'Changes' ? <>{changes.map(change => <details key={change.id} open={expanded}><summary>{change.operation} {change.path ?? 'Checkpoint'}{change.target_path && ` → ${change.target_path}`}</summary><pre>{JSON.stringify(change, null, 2)}</pre></details>)}{!changes.length && <p className="muted">No tracked changes yet.</p>}{changes.length > 0 && <button className="workspace-revert" onClick={() => void revert()}>Revert this run</button>}</> : <>{visible.map(item => <details key={item.seq} className={`execution-event ${item.data.status}`} open={expanded}><summary><span className="event-meta"><time>{item.data.timestamp ? new Date(item.data.timestamp).toLocaleTimeString() : ''}</time><b>{item.data.component_name ?? item.data.component}</b><span>{item.data.status}</span><span>{item.data.duration_ms ?? 0}ms</span></span><span>{item.data.summary ?? item.event}</span></summary><pre>{JSON.stringify(item.data.details ?? item.data, null, 2)}</pre></details>)}{!visible.length && <p className="muted">No matching events.</p>}</>}
        <div ref={end} />
      </section>
    </>}
  </aside>
}
