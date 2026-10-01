import type { ExecutionEvent } from '../../types/chat'
import { agentActivity } from './agentActivity'

export function AgentStatus({ events, status }: { events: ExecutionEvent[]; status?: string }) {
  const agents = agentActivity(events, status)
  if (!agents.total) return null
  return <details className="agent-status"><summary aria-label="Agent activity">Agents · {agents.running} running / {agents.total} total</summary>
    <ul>{agents.items.map(agent => <li key={agent.id}><span>{agent.name}</span> <small>{agent.status}</small></li>)}</ul>
  </details>
}
