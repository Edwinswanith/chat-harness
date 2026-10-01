export type Block = { type: string; id: string; name: string; media_type?: string }
export type Message = { id?: string; role: 'user' | 'assistant'; text: string; run_id?: string; blocks?: Block[] }
export type Source = { id: string; name: string; status: string }
export type Run = { id: string; status: string; assistant_message_id?: string; request?: { text: string; file_ids?: string[] } }
export type Conversation = { id: string; conversation_id: string; title: string; preview: string; mode: string; project_workspace_id?: string; status: string; updated_at: number; last_message_at: number; message_count: number }
export type MessagePage = { items: Message[]; next_cursor: string | null }
export type ExecutionEvent = { seq?: number; event: string; data: { event_id?: string; timestamp?: string; run_id?: string; component?: string; component_name?: string; event_type?: string; summary?: string; status?: string; duration_ms?: number; details?: Record<string, unknown> } }
