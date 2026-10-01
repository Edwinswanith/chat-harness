import type { ExecutionEvent } from '../../types/chat'

export function agentActivity(events: ExecutionEvent[], runStatus?: string) {
  const ended = ['completed', 'failed', 'cancelled'].includes(runStatus ?? '')
  const agents = new Map<string, { id: string; name: string; status: string }>()
  if (runStatus) agents.set('main', { id: 'main', name: 'Workspace agent', status: ended ? runStatus! : 'running' })
  for (const event of events) {
    if (!event.event.startsWith('agent.')) continue
    const details = event.data.details ?? {}; const id = details.agent_id
    if (typeof id !== 'string') continue
    const status = event.data.status === 'started' ? 'running' : event.data.status ?? 'running'
    agents.set(id, { id, name: String(details.agent_name ?? event.data.component_name ?? 'Specialist'), status })
  }
  const items = [...agents.values()].map(agent => ended && agent.status === 'running' ? { ...agent, status: runStatus === 'cancelled' ? 'cancelled' : 'interrupted' } : agent)
  return { items, total: items.length, running: items.filter(agent => agent.status === 'running').length }
}
