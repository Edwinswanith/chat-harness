import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { api, workspaceImage } from '../../services/api'
import { WorkspacePreview } from './WorkspacePreview'
import { WorkspaceActivity } from './WorkspaceActivity'

type Entry = { path: string; name: string; type: 'directory' | 'file'; size_bytes: number }
type Change = { id: string; operation: string; path?: string; target_path?: string; before_sha256?: string; after_sha256?: string; diff?: string; tool_run_id?: string }
type FileData = { path: string; content: string; truncated?: boolean; next_offset_bytes?: number; size_bytes?: number; imageUrl?: string }
type Tab = 'files' | 'changes' | 'logs' | 'preview'

const statusMark = (change?: Change) => change?.operation === 'create' ? '＋' : change?.operation === 'delete' ? '−' : change ? '●' : ''

export function WorkspaceFiles({ workspaceId, runId, conversationId }: { workspaceId: string; runId?: string; conversationId?: string }) {
  const [nodes, setNodes] = useState<Record<string, Entry[]>>({}); const [expanded, setExpanded] = useState(new Set<string>(['.']))
  const [selected, setSelected] = useState<FileData | null>(null); const [changes, setChanges] = useState<Change[]>([])
  const [tab, setTab] = useState<Tab>('files'); const [query, setQuery] = useState(''); const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(true); const [error, setError] = useState('')
  const load = useCallback(async (path = '.') => {
    try { setError(''); setLoading(true); const tree = await api<{ entries: Entry[] }>(`/workspaces/${workspaceId}/tree?path=${encodeURIComponent(path)}`)
      setNodes(current => ({ ...current, [path]: tree.entries }))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Workspace files could not be loaded') }
    finally { setLoading(false) }
  }, [workspaceId])
  const loadActivity = useCallback(async () => {
    if (!runId) { setChanges([]); return }
    try {
      const nextChanges = await api<Change[]>(`/workspaces/${workspaceId}/changes?run_id=${runId}`)
      setChanges(nextChanges)
    } catch { /* Files remain usable when a historical run is unavailable. */ }
  }, [workspaceId, runId])
  useEffect(() => { setNodes({}); setExpanded(new Set(['.'])); void load('.') }, [workspaceId, load])
  useEffect(() => { void loadActivity(); const timer = window.setInterval(loadActivity, 1200); return () => window.clearInterval(timer) }, [loadActivity])
  useEffect(() => { const changed = () => { void load('.'); void loadActivity() }; addEventListener('workspace-files-changed', changed); return () => removeEventListener('workspace-files-changed', changed) }, [load, loadActivity])
  const byPath = useMemo(() => new Map(changes.flatMap(change => [[change.path, change], [change.target_path, change]]).filter(([path]) => Boolean(path)) as [string, Change][]), [changes])
  useEffect(() => () => { if (selected?.imageUrl) URL.revokeObjectURL(selected.imageUrl) }, [selected?.imageUrl])
  async function open(entry: Entry) {
    if (entry.type === 'directory') {
      setExpanded(current => { const next = new Set(current); next.has(entry.path) ? next.delete(entry.path) : next.add(entry.path); return next })
      if (!nodes[entry.path]) await load(entry.path)
      return
    }
    if (/\.(png|jpe?g|webp|gif)$/i.test(entry.path)) {
      try { setSelected({ path: entry.path, content: '', imageUrl: await workspaceImage(workspaceId, entry.path) }) }
      catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to preview image') }
      return
    }
    try { setSelected(await api<FileData>(`/workspaces/${workspaceId}/files?path=${encodeURIComponent(entry.path)}`)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to read file') }
  }
  function tree(path = '.', depth = 0): ReactNode[] {
    return (nodes[path] ?? []).filter(entry => !query || entry.path.toLowerCase().includes(query.toLowerCase())).flatMap(entry => {
      const isExpanded = expanded.has(entry.path); const change = byPath.get(entry.path)
      const row = <button className={`workspace-tree-row ${selected?.path === entry.path ? 'selected' : ''}`} style={{ paddingLeft: 12 + depth * 16 }} key={entry.path} onClick={() => void open(entry)} title={entry.path}>
        <span className="tree-chevron">{entry.type === 'directory' ? isExpanded ? '⌄' : '›' : '·'}</span><span className={`file-icon ${entry.type}`}>{entry.type === 'directory' ? '▸' : icon(entry.name)}</span><b>{entry.name}</b><em className={change ? `change-${change.operation}` : ''}>{statusMark(change)}</em>{entry.type === 'file' && <small>{entry.size_bytes} B</small>}</button>
      return entry.type === 'directory' && isExpanded ? [row, ...tree(entry.path, depth + 1)] : [row]
    })
  }
  const changesForRun = changes.filter(change => change.operation !== 'checkpoint' && change.operation !== 'revert')
  return <aside className={`workspace-files ide-drawer ${collapsed ? 'collapsed' : ''}`}><button className="workspace-files-toggle" onClick={() => setCollapsed(value => !value)} title={collapsed ? `Files · ${changesForRun.length} changes` : 'Collapse workspace panel'}>{collapsed ? `Files · ${changesForRun.length}` : '›'}</button>{!collapsed && <>
    <div className="workspace-files-head"><div><p className="eyebrow">WORKSPACE EXPLORER</p><b>◈ Project files</b></div><button title="Refresh project tree" onClick={() => void load('.')}>↻</button></div>
    <div className="workspace-tabs"><button className={tab === 'files' ? 'active' : ''} onClick={() => setTab('files')}>Files</button><button className={tab === 'changes' ? 'active' : ''} onClick={() => setTab('changes')}>Changes {changesForRun.length || ''}</button><button className={tab === 'logs' ? 'active' : ''} onClick={() => setTab('logs')}>Logs</button><button className={tab === 'preview' ? 'active' : ''} onClick={() => setTab('preview')}>Preview</button></div>
    {tab === 'files' && <><input className="workspace-search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search files…" />{error ? <p className="workspace-files-error">{error} <button onClick={() => void load('.')}>Retry</button></p> : loading && !nodes['.'] ? <p className="muted">Scanning workspace…</p> : <div className="workspace-file-list tree">{tree()}</div>}{!loading && nodes['.']?.length === 0 && <p className="muted">No project files yet. Ask the workspace agent to create or inspect this project.</p>}</>}
    {tab === 'changes' && <section className="workspace-change-list">{changesForRun.length ? changesForRun.map(change => <details key={change.id}><summary><em className={`change-${change.operation}`}>{statusMark(change)}</em> <code>{change.operation}</code> {change.path ?? change.target_path}</summary><pre>{JSON.stringify({ tool_run_id: change.tool_run_id, before_sha256: change.before_sha256, after_sha256: change.after_sha256 }, null, 2)}</pre>{change.diff && <pre>{change.diff}</pre>}</details>) : <p className="muted">No harness changes in this run.</p>}</section>}
    {tab === 'preview' && <WorkspacePreview workspaceId={workspaceId} runId={runId} />}
    {tab === 'logs' && <WorkspaceActivity embedded runId={runId} conversationId={conversationId} onReverted={() => { void load('.'); void loadActivity() }} />}
    {selected && <section className="workspace-preview"><div><b>{selected.path}</b><button onClick={() => setSelected(null)}>×</button></div>{selected.truncated && <p className="muted">Partial preview: first {selected.next_offset_bytes} of {selected.size_bytes} bytes. Ask the agent to read further pages.</p>}<>{selected.imageUrl ? <img src={selected.imageUrl} alt={selected.path} style={{ width: '100%', height: 'auto' }} /> : <pre>{selected.content}</pre>}</></section>}
  </>}</aside>
}
function icon(name: string) { const ext = name.split('.').pop()?.toLowerCase(); return ({ ts: 'TS', tsx: '⚛', js: 'JS', jsx: '⚛', css: '#', json: '{}', md: 'M', py: 'Py', html: '⌘' } as Record<string, string>)[ext ?? ''] ?? '·' }
