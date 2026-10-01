import { useEffect, useRef, useState } from 'react'
import { api, stream } from '../services/api'
import { mergeEvents } from '../components/workspace/runTimeline'
import type { Conversation, Message, MessagePage, Run, Source, ExecutionEvent } from '../types/chat'

const terminal = ['completed', 'failed', 'cancelled']
const routeId = () => decodeURIComponent(location.pathname.match(/^(?:\/chat\/|\/workspace\/[^/]+\/chat\/)([^/]+)$/)?.[1] ?? '')
const workspaceRoute = () => location.pathname.startsWith('/workspace')
const routeWorkspaceId = () => decodeURIComponent(location.pathname.match(/^\/workspace\/([^/]+)\/chat\//)?.[1] ?? '')
const uniqueMessages = (items: Message[]) => [...new Map(items.map((item, index) => [item.id ?? `transient-${index}`, item])).values()]

export function useChat() {
  const [conversationId, setConversationId] = useState(routeId()); const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<Message[]>([]); const [sources, setSources] = useState<Source[]>([])
  const [attachments, setAttachments] = useState<Source[]>([]); const [run, setRun] = useState<Run | null>(null); const [error, setError] = useState('')
  const [activities, setActivities] = useState<Record<string, ExecutionEvent[]>>({})
  const [activityError, setActivityError] = useState('')
  const initialized = useRef(false)
  const watching = useRef(new Set<string>())
  const loadVersion = useRef(0)
  const refreshConversations = async () => setConversations(await api<Conversation[]>('/conversations'))
  const refreshSources = async (id = conversationId) => { if (id) setSources(await api<Source[]>(`/files?thread_id=${id}`)) }

  function applyEvent(event: string, raw: unknown, runId: string, seq?: number) {
    const execution = raw as ExecutionEvent['data']
    if (execution.event_id) setActivities(current => ({ ...current, [runId]: mergeEvents(current[runId] ?? [], [{ event, data: execution, seq }]) }))
    const wrapped = raw as { details?: unknown }
    const data = (wrapped.details ?? raw) as { text?: string; full_text?: string; message_id?: string; message?: Message; status?: string; error?: string; name?: string }
    if (event === 'delta' && data.message_id) setMessages(current => current.map(item => item.id === data.message_id ? { ...item, text: data.full_text ?? `${item.text}${data.text ?? ''}` } : item))
    if (event === 'final' && data.message) { setMessages(current => current.map(item => item.id === data.message?.id ? data.message! : item)); setRun(current => current ? { ...current, status: 'completed' } : current); void refreshConversations() }
    if (event === 'state' && data.status) {
      setRun(current => current ? { ...current, status: data.status! } : current)
      if (data.status === 'failed') {
        const message = data.error ?? 'The run failed. You can retry the request.'
        setError(message)
        const guidance = workspaceRoute() ? '\n\nSend “continue” to resume this task from the existing files.' : ''
        setMessages(current => current.map(item => item.role === 'assistant' && item.run_id === runId && !item.text ? { ...item, text: `Run failed: ${message}${guidance}` } : item))
      }
    }
    if (event === 'tool' && data.name?.startsWith('workspace_')) window.dispatchEvent(new Event('workspace-files-changed'))
  }
  async function watch(active: Run) {
    const version = loadVersion.current
    const watchKey = `${active.id}:${version}`
    if (watching.current.has(watchKey)) return
    watching.current.add(watchKey)
    try {
      await stream(`/runs/${active.id}/events`, (event, raw, seq) => { if (version === loadVersion.current) applyEvent(event, raw, active.id, seq) })
      if (version === loadVersion.current) { await refreshSources(); await refreshConversations() }
    } catch (reason) { if (version === loadVersion.current) setActivityError(reason instanceof Error ? reason.message : 'Execution stream interrupted') }
    finally { watching.current.delete(watchKey) }
  }
  async function load(id: string, navigate = false) {
    const version = ++loadVersion.current
    setError(''); setActivityError(''); setActivities({}); setAttachments([]); setConversationId(id); if (navigate && routeId() !== id) history.pushState({}, '', `/chat/${encodeURIComponent(id)}`)
    try {
      const conversation = await api<Conversation>(`/conversations/${id}`)
      const expectedWorkspaceId = routeWorkspaceId()
      if (expectedWorkspaceId && (conversation.mode !== 'workspace' || conversation.project_workspace_id !== expectedWorkspaceId)) throw new Error('This chat does not belong to the selected workspace.')
      const [page, listedSources, active] = await Promise.all([api<MessagePage>(`/conversations/${id}/messages`), api<Source[]>(`/files?thread_id=${id}`), api<Run | null>(`/conversations/${id}/active-run`)])
      if (version !== loadVersion.current) return
      setMessages(uniqueMessages(page.items)); setSources(listedSources); setRun(active)
      const runIds = [...new Set([...page.items.map(message => message.run_id).filter((value): value is string => Boolean(value)), ...(active ? [active.id] : [])])]
      if (conversation.mode === 'workspace') {
        void Promise.allSettled(runIds.map(async runId => ({ runId, events: await api<ExecutionEvent[]>(`/runs/${runId}/activity`) }))).then(results => {
          if (version !== loadVersion.current) return
          setActivities(current => {
            const next = { ...current }
            for (const result of results) if (result.status === 'fulfilled') next[result.value.runId] = mergeEvents(next[result.value.runId] ?? [], result.value.events)
            return next
          })
          if (results.some(result => result.status === 'rejected')) setActivityError('Some execution history could not be loaded. Reload this conversation to retry.')
        })
      }
      if (active) void watch(active)
    } catch (err) {
      if (version === loadVersion.current) { setMessages([]); setSources([]); setRun(null); setError(err instanceof Error ? err.message : 'Unable to load this conversation') }
    }
  }
  async function newConversation() { const created = await api<Conversation>('/conversations', { method: 'POST' }); await refreshConversations(); await load(created.id, true) }
  useEffect(() => {
    if (initialized.current) return; initialized.current = true
    void refreshConversations().then(() => routeId() ? load(routeId()) : workspaceRoute() ? undefined : newConversation()).catch(err => setError(err.message))
    const pop = () => { const id = routeId(); if (id) void load(id) }; addEventListener('popstate', pop); return () => removeEventListener('popstate', pop)
  }, [])
  async function upload(file: File) { if (!conversationId) return; const body = new FormData(); body.set('thread_id', conversationId); body.set('file', file); const source = await api<Source>('/files', { method: 'POST', body }); setAttachments(current => [...current, source]); await refreshSources() }
  async function submit(text: string, fileIds: string[]) {
    if (!conversationId) return; setError('')
    const request = { thread_id: conversationId, text, idempotency_key: crypto.randomUUID(), file_ids: fileIds }
    try {
      const started = await api<Run>('/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })
      setAttachments([]); setRun(started); const page = await api<MessagePage>(`/conversations/${conversationId}/messages`); setMessages(uniqueMessages(page.items)); await refreshConversations(); void watch(started)
    } catch (err) { setError(err instanceof Error ? err.message : 'Request failed') }
  }
  async function send(text: string) { await submit(text, attachments.map(file => file.id)) }
  async function retry() { if (run?.request?.text) await submit(run.request.text, run.request.file_ids ?? []) }
  async function rename(id: string) { const title = prompt('Conversation title'); if (!title) return; await api(`/conversations/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) }); await refreshConversations() }
  async function archive(id: string) { await api(`/conversations/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'archived' }) }); await refreshConversations(); if (id === conversationId) await newConversation() }
  async function remove(id: string) { if (!confirm('Delete this conversation?')) return; await api(`/conversations/${id}`, { method: 'DELETE' }); await refreshConversations(); if (id === conversationId) await newConversation() }
  async function cancel() { if (run) { await api(`/runs/${run.id}/cancel`, { method: 'POST' }); setRun({ ...run, status: 'cancelled' }) } }
  return { activities, activityError, conversationId, conversations, messages, sources, attachments, run, error, send, retry, upload, load, newConversation, rename, archive, remove, refreshConversations, removeAttachment: (id: string) => setAttachments(current => current.filter(file => file.id !== id)), cancel, ready: Boolean(conversationId), active: Boolean(run && !terminal.includes(run.status)) }
}
