import { useEffect, useRef } from 'react'
import type { Message, Source, ExecutionEvent, Run } from '../../types/chat'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { RunTimeline } from '../workspace/RunTimeline'
import { ArtifactCard } from '../artifacts/ArtifactCard'

function uniqueBlocks(message: Message, type: string) {
  const seen = new Set<string>()
  return (message.blocks ?? []).filter(block => block.type === type && !seen.has(block.id) && Boolean(seen.add(block.id)))
}

export function ChatWindow({ messages, sources, workspace = false, activities = {}, run, activityError }: { messages: Message[]; sources: Source[]; workspace?: boolean; activities?: Record<string, ExecutionEvent[]>; run?: Run | null; activityError?: string }) {
  const transcript = useRef<HTMLElement>(null)
  const followLatest = useRef(true)
  const activityCount = Object.values(activities).reduce((count, events) => count + events.length, 0)
  useEffect(() => {
    if (workspace && transcript.current && followLatest.current) transcript.current.scrollTop = transcript.current.scrollHeight
  }, [workspace, activityCount, messages, run?.status])
  function statusFor(message: Message) {
    if (run && run.id === message.run_id) return run.status
    const state = [...(activities[message.run_id ?? ''] ?? [])].reverse().find(event => event.event === 'state')
    const status = state?.data.details?.status
    return typeof status === 'string' ? status : message.text ? 'completed' : 'running'
  }
  return <main ref={transcript} onScroll={() => { const node = transcript.current; if (node) followLatest.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80 }} className={`chat ${workspace ? 'workspace-transcript' : ''}`}>{sources.length > 0 && <section className="sources"><strong>Attached knowledge</strong>{sources.map(source => <span key={source.id} className={`source-chip ${source.status}`}>{source.name}<em>{source.status}</em></span>)}</section>}
    {messages.map((message, index) => <article className={`message ${message.role}`} key={message.id ?? index}>
      {!workspace && <span className="avatar">{message.role === 'user' ? 'Y' : '✦'}</span>}<div className="message-content">{!workspace && <strong>{message.role === 'user' ? 'You' : 'Harness'}</strong>}{workspace && message.role === 'assistant' && message.run_id && <RunTimeline events={activities[message.run_id] ?? []} status={statusFor(message)} error={run?.id === message.run_id ? activityError : undefined} />}{message.role === 'assistant' ? <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text || (workspace ? '' : 'Thinking…')}</ReactMarkdown></div> : <p>{message.text || 'Thinking…'}</p>}
      {uniqueBlocks(message, 'source').map(block => <span className="message-source" key={`source-${block.id}`}>⌁ {block.name}</span>)}
      {uniqueBlocks(message, 'artifact').map(block => <ArtifactCard key={`artifact-${block.id}`} artifact={block} />)}
      </div></article>)}
  </main>
}
