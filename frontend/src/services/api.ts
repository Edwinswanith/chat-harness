const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'
const token = import.meta.env.VITE_AUTH_TOKEN ?? 'local-demo-token'

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, ...(init.headers ?? {}) } })
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? response.statusText)
  return response.json() as Promise<T>
}

export async function stream(path: string, onEvent: (event: string, data: unknown, seq?: number) => void) {
  const response = await fetch(`${baseUrl}${path}`, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok || !response.body) throw new Error('Unable to open event stream')
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
  while (true) {
    const result = await reader.read(); if (result.done) break
    buffer += decoder.decode(result.value, { stream: true })
    const frames = buffer.split('\n\n'); buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1]; const data = frame.match(/^data: (.+)$/m)?.[1]
      if (event && data) onEvent(event, JSON.parse(data), Number(frame.match(/^id: (\d+)$/m)?.[1]) || undefined)
    }
  }
}

export function artifactUrl(id: string) { return `${baseUrl}/artifacts/${id}/download` }
export function authHeader() { return { Authorization: `Bearer ${token}` } }

export async function previewImage(workspaceId: string, runId: string, viewport: 'desktop' | 'mobile') {
  const response = await fetch(`${baseUrl}/workspaces/${workspaceId}/runs/${runId}/preview/${viewport}`, { headers: authHeader() })
  if (!response.ok) throw new Error('No screenshot available yet. The run must reach browser validation first.')
  return URL.createObjectURL(await response.blob())
}

export async function workspaceImage(workspaceId: string, path: string) {
  const response = await fetch(`${baseUrl}/workspaces/${workspaceId}/image?path=${encodeURIComponent(path)}`, { headers: authHeader() })
  if (!response.ok) throw new Error('Workspace image could not be loaded')
  return URL.createObjectURL(await response.blob())
}
