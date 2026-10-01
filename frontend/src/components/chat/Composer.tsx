import { useRef, useState } from 'react'
import type { Source } from '../../types/chat'

export function Composer({ disabled, attachments, onRemove, onSend, onUpload, placeholder }: { disabled: boolean; attachments: Source[]; onRemove: (id: string) => void; onSend: (text: string) => void; onUpload: (file: File) => Promise<void>; placeholder?: string }) {
  const [text, setText] = useState(''); const input = useRef<HTMLInputElement>(null)
  function submit() { if (text.trim() && !disabled) { onSend(text); setText('') } }
  return <div className="composer-wrap">{attachments.length > 0 && <div className="attachment-tray">{attachments.map(file => <span key={file.id}>⌁ {file.name}<em>{file.status}</em><button type="button" onClick={() => onRemove(file.id)}>×</button></span>)}</div>}
  <form className="composer" onSubmit={event => { event.preventDefault(); submit() }}>
    <input ref={input} type="file" accept=".txt,.md,.csv,.pdf,application/pdf" hidden onChange={async event => { const file = event.target.files?.[0]; if (file) await onUpload(file); event.target.value = '' }} />
    <button className="attach" type="button" onClick={() => input.current?.click()} disabled={disabled} title="Attach PDF, Markdown, text, or CSV">＋ <span>Attach</span></button>
    <textarea value={text} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }} placeholder={placeholder ?? 'Ask, research, generate an image, or create a report…'} disabled={disabled} />
    <button className="send" disabled={disabled || !text.trim()}>Send <span>↗</span></button>
  </form></div>
}
