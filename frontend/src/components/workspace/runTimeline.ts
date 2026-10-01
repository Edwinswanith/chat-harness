import type { ExecutionEvent } from '../../types/chat'

export type RunAction = { kind: 'action'; id: string; name: string; label: string; status: string; timestamp?: string; durationMs: number; target: string; command: string; details: Record<string, unknown>; result: Record<string, unknown>; error?: string }
export type RunComment = { kind: 'comment'; id: string; text: string }
export type TimelineItem = RunAction | RunComment
export type TimelineBlock = RunComment | { kind: 'group'; id: string; actions: RunAction[]; label: string }
const commands: Record<string, string> = { workspace_run_build: 'npm run build', workspace_run_tests: 'npm test', workspace_run_lint: 'npm run lint' }
const labels: Record<string, [string, string]> = {
  workspace_list_directory: ['Listing files', 'Listed files'], workspace_read_file: ['Reading', 'Read'],
  workspace_search_text: ['Searching files', 'Searched files'], workspace_create_file: ['Creating', 'Created'],
  workspace_write_file: ['Editing', 'Edited'], workspace_patch_file: ['Editing', 'Edited'],
  workspace_create_directory: ['Creating folder', 'Created folder'], workspace_rename_path: ['Renaming', 'Renamed'],
  workspace_delete_path: ['Deleting', 'Deleted'],
}
const object = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const string = (value: unknown) => typeof value === 'string' ? value : ''
export const pending = (status: string) => ['started', 'running', 'queued', 'retrying'].includes(status)

export function mergeEvents(previous: ExecutionEvent[], incoming: ExecutionEvent[]) {
  const key = (event: ExecutionEvent) => event.data.event_id ?? `${event.seq}:${event.event}`
  const merged = new Map(previous.map(event => [key(event), event]))
  incoming.forEach(event => merged.set(key(event), { ...event, seq: event.seq ?? merged.get(key(event))?.seq }))
  return [...merged.values()].sort((a, b) => a.seq !== undefined && b.seq !== undefined ? a.seq - b.seq : Date.parse(a.data.timestamp ?? '') - Date.parse(b.data.timestamp ?? ''))
}

export function runTimeline(events: ExecutionEvent[], runStatus?: string): TimelineBlock[] {
  const items: TimelineItem[] = []; const actions = new Map<string, RunAction>()
  for (const [index, event] of events.entries()) {
    const data = event.data; const details = object(data.details ?? data)
    const id = data.event_id ?? `${event.seq ?? index}:${event.event}`
    if (event.event === 'commentary') {
      if (data.component === 'feedback' || details.visibility === 'logs_only') continue
      const text = string(details.text) || data.summary || ''
      if (text) items.push({ kind: 'comment', id, text })
      continue
    }
    if (event.event.startsWith('agent.')) continue
    const isTool = ['tool.started', 'tool', 'tool.cancelled'].includes(event.event)
    const isTerminal = data.component === 'terminal' && details.command
    const isOther = ['subagent', 'sandbox'].includes(data.component ?? '') && !event.event.startsWith('state')
    if (!isTool && !isTerminal && !isOther) continue
    // Build-stage announcements have no executable command; only actual actions are rows.
    const name = string(data.component_name) || string(details.name) || data.component || 'tool'
    const args = object(details.arguments); const result = isTerminal && !isTool ? details : object(details.data)
    let command = string(args.command) || string(details.command) || string(result.command) || commands[name] || ''
    let target = string(args.relative_path) || string(details.target) || string(result.path) || string(details.target_path) || '.'
    const status = data.status || string(details.status) || 'running'
    let key = string(details.tool_call_id)
    if (!key) {
      const matching = [...actions.values()].reverse().find(action => action.name === name && (!command || action.command === command) && pending(action.status))
      key = matching && !pending(status) ? matching.id : id
    }
    const previous = actions.get(key)
    command ||= previous?.command ?? ''
    if (target === '.' && previous) target = previous.target
    const action: RunAction = previous ?? { kind: 'action', id: key, name, label: '', status, timestamp: data.timestamp, durationMs: 0, target, command, details: {}, result: {} }
    action.status = status; action.durationMs = data.duration_ms ?? 0
    action.details = { ...action.details, ...details }; action.result = { ...action.result, ...result }
    action.error = string(details.error) || undefined
    const verbs = labels[name]
    const suffix = target !== '.' ? ` ${target}` : ''
    action.label = command ? `${pending(status) ? 'Running' : status === 'cancelled' ? 'Cancelled command' : 'Ran'} ${command}` : verbs ? `${verbs[pending(status) ? 0 : 1]}${suffix}` : (data.summary || name.replaceAll('_', ' '))
    if (name === 'workspace_write_file' && !pending(status) && action.result.created === true) action.label = `Created ${target}`
    if (action.result.operation === 'unchanged') action.label = `Already present ${target}`
    if (status === 'failed') {
      const failedVerbs: Record<string, string> = { workspace_create_file: 'create', workspace_create_directory: 'create folder', workspace_write_file: 'edit', workspace_patch_file: 'edit', workspace_read_file: 'read', workspace_rename_path: 'rename', workspace_delete_path: 'delete' }
      action.label = failedVerbs[name] ? `Failed to ${failedVerbs[name]}${suffix}` : action.label + ' · Failed'
    }
    if (!previous) { items.push(action); actions.set(key, action) }
  }
  if (runStatus && ['failed', 'cancelled', 'completed'].includes(runStatus)) {
    for (const action of actions.values()) if (pending(action.status)) {
      action.status = runStatus === 'cancelled' ? 'cancelled' : 'interrupted'
      action.label = action.label.replace(/^Running /, 'Interrupted command ').replace(/^Reading /, 'Interrupted read ') + (runStatus === 'cancelled' ? ' · Cancelled' : ' · Interrupted')
    }
  }
  const visibleItems = items.filter(item => item.kind === 'comment' || !['failed', 'error'].includes(item.status))
  const blocks: TimelineBlock[] = []
  for (const item of visibleItems) {
    if (item.kind === 'comment') { blocks.push(item); continue }
    const last = blocks.at(-1)
    if (last?.kind === 'group') last.actions.push(item)
    else blocks.push({ kind: 'group', id: item.id, actions: [item], label: '' })
  }
  for (const block of blocks) if (block.kind === 'group') {
    const hasCommands = block.actions.some(action => action.command)
    const hasFiles = block.actions.some(action => action.name.startsWith('workspace_') && !action.command)
    block.label = hasFiles && hasCommands ? 'Read files, ran commands' : hasCommands ? 'Ran commands' : hasFiles ? block.actions.some(action => /create|write|patch|rename|delete/.test(action.name)) ? 'Edited files and folders' : 'Read files' : 'Executed tools'
  }
  return blocks
}
