import { expect, it } from 'vitest'
import { agentActivity } from './agentActivity'
import type { ExecutionEvent } from '../../types/chat'
const event = (id: string, status: string): ExecutionEvent => ({ event: `agent.${status}`, data: { status, component_name: 'reviewer', details: { agent_id: id, agent_name: 'reviewer' } } })
it('counts overlapping agents with the same role separately and deduplicates replay', () => {
  const events = [event('a', 'started'), event('b', 'started'), event('a', 'started')]
  expect(agentActivity(events, 'subagent_running')).toMatchObject({ running: 3, total: 3 })
  expect(agentActivity([...events, event('a', 'success')], 'model_running')).toMatchObject({ running: 2, total: 3 })
  expect(agentActivity(events, 'cancelled')).toMatchObject({ running: 0, total: 3 })
})
