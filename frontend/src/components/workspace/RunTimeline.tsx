import { useEffect, useState } from 'react'
import { BookOpen, TerminalWindow, Folder, FolderPlus, PencilSimple, FilePlus, Code, Check, CircleNotch, CaretRight, WarningCircle, XCircle } from '@phosphor-icons/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ExecutionEvent } from '../../types/chat'
import { pending, runTimeline, type RunAction } from './runTimeline'

function ActionRow({ action, now }: { action: RunAction; now: number }) {
  const running = pending(action.status)
  const duration = running && action.timestamp ? Math.max(0, now - Date.parse(action.timestamp)) : action.durationMs
  const Icon = action.command ? TerminalWindow : action.name.includes('read') ? BookOpen : action.name.includes('directory') ? action.name.includes('create') ? FolderPlus : Folder : action.name.includes('create') ? FilePlus : action.name.includes('patch') || action.name.includes('write') ? PencilSimple : Code
  const output = typeof action.result.stdout === 'string' ? action.result.stdout : ''
  const stderr = typeof action.result.stderr === 'string' ? action.result.stderr : typeof action.result.stderr_tail === 'string' ? action.result.stderr_tail : ''
  const diff = typeof action.result.diff === 'string' ? action.result.diff : ''
  const entries = Array.isArray(action.result.entries) ? action.result.entries : []
  const statusLabel = running ? 'Running' : action.status === 'success' ? 'Success' : action.status === 'cancelled' ? 'Cancelled' : action.status === 'interrupted' ? 'Interrupted' : 'Failed'
  const StatusIcon = running ? CircleNotch : action.status === 'success' ? Check : action.status === 'cancelled' ? XCircle : WarningCircle
  return <details className={`run-action ${action.status}`} data-action-id={action.id}>
    <summary><Icon size={15} aria-hidden="true" /><span className="run-action-label" title={action.label}>{action.label}</span>{duration > 0 && <span className="run-action-duration">{running ? 'for' : 'in'} {duration < 1000 ? `${duration}ms` : `${(duration / 1000).toFixed(1)}s`}</span>}<CaretRight className="disclosure-caret" size={12} aria-hidden="true" />{running && <CircleNotch className="spinning" size={13} aria-label="Running" />}</summary>
    <div className="run-action-panel">
      <div className="run-action-panel-heading"><span>{action.command ? 'Shell' : diff ? 'File changes' : action.name.includes('directory') ? 'Workspace' : 'Tool result'}</span><span>{action.target}</span></div>
      {action.command && <pre className="command-line">$ {action.command}</pre>}
      {output && <pre aria-label="Command output">{output}</pre>}
      {stderr && <pre className="command-stderr" aria-label="Command errors">{stderr}</pre>}
      {action.error && action.error !== stderr && <pre className="command-stderr">{action.error}</pre>}
      {diff && <pre className="file-diff" aria-label="File diff">{diff.split('\n').map((line, index) => <span key={index} className={line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-remove' : ''}>{line}{'\n'}</span>)}</pre>}
      {entries.length > 0 && <pre>{entries.map(item => { const entry = item as { path?: string; type?: string }; return `${entry.type === 'directory' ? 'folder' : 'file'}  ${entry.path}` }).join('\n')}</pre>}
      {!output && !stderr && !diff && !entries.length && !action.error && <p>{running ? 'Waiting for the execution result…' : action.result.content === '[redacted]' ? 'File read completed. Source content is omitted from execution logs.' : 'Execution result recorded.'}</p>}
      <details className="run-action-metadata"><summary>Execution details</summary><pre>{JSON.stringify({ tool: action.name, tool_call_id: action.id, ...action.details }, null, 2)}</pre></details>
      <div className={`run-action-status ${action.status}`}><span>{action.result.exit_code !== undefined ? `Exit code: ${String(action.result.exit_code)}` : ''}</span><span><StatusIcon size={14} className={running ? 'spinning' : ''} aria-hidden="true" />{statusLabel}</span></div>
    </div>
  </details>
}

export function RunTimeline({ events, status, error }: { events: ExecutionEvent[]; status?: string; error?: string }) {
  const blocks = runTimeline(events, status)
  const first = events[0]?.data.timestamp
  const last = events.at(-1)?.data.timestamp
  const active = !status || !['completed', 'failed', 'cancelled'].includes(status)
  const [now, setNow] = useState(Date.now())
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [active])
  const seconds = first ? Math.max(0, Math.round(((active ? now : last ? Date.parse(last) : now) - Date.parse(first)) / 1000)) : 0
  const elapsed = seconds >= 60 ? `${Math.floor(seconds / 60)}m ${seconds % 60}s` : `${seconds}s`
  return <section className="run-timeline" aria-label="Step-by-step workspace execution">
    <div className="run-working-status" role="status">{active ? <><CircleNotch className="spinning" size={14} />Working{first && ` for ${elapsed}`}</> : `${status === 'completed' ? 'Worked' : status === 'cancelled' ? 'Cancelled' : 'Stopped'}${first ? ` after ${elapsed}` : ''}`}</div>
    {blocks.map((block, index) => block.kind === 'comment' ? <div className="run-commentary markdown" key={block.id}><ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown></div> : <details className="run-action-group" key={block.id} open={active && index === blocks.length - 1}>
      <summary>{block.actions.some(action => action.command) ? <TerminalWindow size={15} aria-hidden="true" /> : <BookOpen size={15} aria-hidden="true" />}<span>{block.label}</span><CaretRight className="disclosure-caret" size={13} aria-hidden="true" /><span className="run-action-count">{block.actions.length}</span></summary>
      <div className="run-action-list">{block.actions.map(action => <ActionRow action={action} now={now} key={action.id} />)}</div>
    </details>)}
    {active && !blocks.length && <p className="run-waiting">Preparing workspace execution…</p>}
    {error && <p className="run-timeline-error" role="alert">{error}</p>}
  </section>
}
