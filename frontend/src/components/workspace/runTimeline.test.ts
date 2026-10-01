import { describe, expect, it } from 'vitest'
import type { ExecutionEvent } from '../../types/chat'
import { mergeEvents, runTimeline } from './runTimeline'

function event(seq: number, type: string, details: Record<string, unknown>, status = 'success', component = 'tool'): ExecutionEvent {
  return { seq, event: type, data: { event_id: `evt-${seq}`, timestamp: `2026-10-01T06:00:${String(seq).padStart(2, '0')}Z`, component, component_name: details.name as string ?? component, status, details } }
}

describe('workspace execution transcript', () => {
  it('labels failed creates and identical retries accurately', () => {
    const blocks = runTimeline([
      event(1, 'tool', { tool_call_id: 'conflict', name: 'workspace_create_file', data: { path: 'globals.css', code: 'file_exists' }, error: 'File already exists' }, 'failed'),
      event(2, 'tool', { tool_call_id: 'noop', name: 'workspace_create_file', data: { path: 'tokens.css', operation: 'unchanged', created: false } }),
    ], 'completed')
    const group = blocks[0]
    if (group.kind !== 'group') throw new Error('Expected action group')
    expect(group.actions).toHaveLength(1)
    expect(group.actions[0].label).toBe('Already present tokens.css')
  })
  it('updates running tools in place and preserves commentary order', () => {
    const events = [event(1, 'commentary', { text: 'Inspecting the workspace.' }, 'success', 'orchestrator'),
      event(2, 'tool.started', { tool_call_id: 'read', name: 'workspace_read_file', arguments: { relative_path: 'README.md' } }, 'started'),
      event(3, 'tool', { tool_call_id: 'read', name: 'workspace_read_file', data: { content: '[redacted]' } }),
      event(4, 'commentary', { text: 'I’ll run the tests now.' }, 'success', 'orchestrator'),
      event(5, 'tool.started', { tool_call_id: 'shell', name: 'terminal_run_command', arguments: { command: 'npm test' } }, 'started', 'terminal'),
      event(6, 'tool', { tool_call_id: 'shell', name: 'terminal_run_command', data: { stdout: '2 passed', exit_code: 0 } }, 'success', 'terminal')]
    const blocks = runTimeline(events, 'completed')
    expect(blocks.map(block => block.kind)).toEqual(['comment', 'group', 'comment', 'group'])
    const group = blocks[3]; expect(group.kind).toBe('group')
    if (group.kind === 'group') { expect(group.actions).toHaveLength(1); expect(group.actions[0].label).toBe('Ran npm test'); expect(group.actions[0].result.stdout).toBe('2 passed') }
    const readGroup = blocks[1]
    if (readGroup.kind === 'group') expect(readGroup.actions[0].label).toBe('Read README.md')
  })
  it('deduplicates SSE replay against persisted history without losing sequence', () => {
    const persisted = event(1, 'tool', { tool_call_id: 'read' })
    const replay = { ...persisted, seq: undefined }
    expect(mergeEvents([persisted], [replay])).toEqual([persisted])
  })
  it('keeps terminal failures in raw events for Logs', () => {
    const events = [event(1, 'tool', { tool_call_id: 'shell', name: 'workspace_run_build', data: { exit_code: 1, stderr: 'Missing import' }, error: 'Build failed' }, 'failed')]
    expect(runTimeline(events, 'failed')).toEqual([])
    expect(events[0].data.details?.error).toBe('Build failed')
  })
  it('pairs automatic build lifecycle events and does not duplicate file notifications', () => {
    const blocks = runTimeline([event(1, 'terminal.started', { command: 'npm run build' }, 'started', 'terminal'), event(2, 'terminal.success', { command: 'npm run build', exit_code: 0 }, 'success', 'terminal'), event(3, 'workspace.file.created', { path: 'App.jsx' }, 'success', 'workspace')])
    const group = blocks[0]
    if (group.kind !== 'group') throw new Error('Expected action group')
    expect(group.actions).toHaveLength(1); expect(group.actions[0].status).toBe('success')
  })
  it('never leaves an interrupted tool looking active after cancellation', () => {
    const blocks = runTimeline([event(1, 'tool.started', { tool_call_id: 'shell', name: 'terminal_run_command', arguments: { command: 'npm test' } }, 'started')], 'cancelled')
    const group = blocks[0]
    if (group.kind !== 'group') throw new Error('Expected action group')
    expect(group.actions[0].status).toBe('cancelled')
  })
})


describe('recoverable failures stay in Logs', () => {
  it('suppresses historical feedback commentary and failed tool output', () => {
    const events = [event(1, 'commentary', { text: 'An action failed. I am retrying.' }, 'retrying', 'feedback'),
      event(2, 'tool', { name: 'workspace_patch_file', error: 'Patch text was not found' }, 'failed'),
      event(3, 'commentary', { text: 'Editing the navigation.' }, 'success', 'orchestrator')]
    expect(runTimeline(events)).toEqual([{ kind: 'comment', id: 'evt-3', text: 'Editing the navigation.' }])
    expect(events).toHaveLength(3)
  })
})
