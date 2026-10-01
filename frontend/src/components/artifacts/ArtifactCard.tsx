import { useEffect, useState } from 'react'
import { artifactUrl, authHeader } from '../../services/api'
import type { Block } from '../../types/chat'

export function ArtifactCard({ artifact }: { artifact: Block }) {
  const [preview, setPreview] = useState('')
  const image = artifact.media_type?.startsWith('image/')
  useEffect(() => {
    if (!image) return
    let url = ''
    fetch(artifactUrl(artifact.id), { headers: authHeader() }).then(response => response.blob()).then(blob => {
      url = URL.createObjectURL(blob); setPreview(url)
    })
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [artifact.id, image])
  async function download() {
    const response = await fetch(artifactUrl(artifact.id), { headers: authHeader() })
    const url = URL.createObjectURL(await response.blob()); const link = document.createElement('a')
    link.href = url; link.download = artifact.name; link.click(); URL.revokeObjectURL(url)
  }
  return <section className="artifact-card">{image && preview && <img src={preview} alt={artifact.name} />}
    <button className="artifact" onClick={download}>{image ? 'Save image' : 'Download'} · {artifact.name}</button></section>
}
