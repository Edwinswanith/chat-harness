import { useState } from 'react'
import { api } from '../../services/api'

export function WorkspacePanel({ onWorkspaceOpened }: { onWorkspaceOpened: (workspaceId: string) => Promise<void> }) {
  const [folderPath, setFolderPath] = useState(''); const [error, setError] = useState(''); const [opening, setOpening] = useState(false)
  async function choose() {
    const path = folderPath.trim(); if (!path) return setError('Enter the local folder path to open.')
    try { setError(''); setOpening(true); const workspace = await api<{ id: string }>('/workspaces', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) }); await onWorkspaceOpened(workspace.id) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to open workspace') }
    finally { setOpening(false) }
  }
  return <main className="workspace-panel"><header><div><p className="eyebrow">WORKSPACE MODE</p><h1>Open a workspace</h1></div></header>{error && <p className="error">{error}</p>}
    <section className="workspace-picker"><h2>Choose Folder</h2><p>Enter a local folder path. It opens as an IDE workspace with a file explorer and workspace chat.</p><div className="folder-input"><input value={folderPath} onChange={event => setFolderPath(event.target.value)} onKeyDown={event => event.key === 'Enter' && void choose()} placeholder="/home/you/projects/my-project" /><button disabled={opening} onClick={() => void choose()}>{opening ? 'Opening…' : 'Open folder'}</button></div></section>
  </main>
}
