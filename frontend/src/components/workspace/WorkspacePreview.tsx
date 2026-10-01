import { useEffect, useState } from 'react'
import { previewImage } from '../../services/api'

export function WorkspacePreview({ workspaceId, runId }: { workspaceId: string; runId?: string }) {
  const [viewport, setViewport] = useState<'desktop' | 'mobile'>('desktop')
  const [url, setUrl] = useState(''); const [error, setError] = useState(''); const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false; let imageUrl = ''
    setUrl(''); setError('')
    if (!runId) return
    void previewImage(workspaceId, runId, viewport).then(value => {
      imageUrl = value
      if (disposed) URL.revokeObjectURL(value); else setUrl(value)
    }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : 'Preview unavailable') })
    return () => { disposed = true; if (imageUrl) URL.revokeObjectURL(imageUrl) }
  }, [workspaceId, runId, viewport, revision])
  return <section className="workspace-screenshot-preview"><div className="workspace-tabs">
    <button className={viewport === 'desktop' ? 'active' : ''} onClick={() => setViewport('desktop')}>Desktop · 1440</button>
    <button className={viewport === 'mobile' ? 'active' : ''} onClick={() => setViewport('mobile')}>Mobile · 390</button>
    <button onClick={() => setRevision(value => value + 1)} aria-label="Refresh screenshots">↻</button></div>
    {!runId && <p className="muted">Run a website task to capture previews.</p>}
    {error && <p className="muted">{error}</p>}
    {url && <><a href={url} target="_blank" rel="noreferrer">Open full screenshot</a><img src={url} alt={`${viewport} website preview`} style={{ width: '100%', height: 'auto', marginTop: 12 }} /></>}
  </section>
}
