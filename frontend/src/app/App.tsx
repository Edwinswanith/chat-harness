import { AgentStatus } from '../components/workspace/AgentStatus'
import { ChatWindow } from '../components/chat/ChatWindow'
import { Composer } from '../components/chat/Composer'
import { WorkspaceFiles } from '../components/workspace/WorkspaceFiles'
import { WorkspacePanel } from '../components/workspace/WorkspacePanel'
import { useChat } from '../hooks/useChat'
import { api } from '../services/api'
import { useEffect, useState } from 'react'
import '../styles.css'

type View = 'chatbot' | 'workspace' | 'workspace-chat'
type Workspace = { id: string; name: string }

export function App() {
  const routeView = (): View => /^\/workspace\/[^/]+\/chat\//.test(location.pathname) ? 'workspace-chat' : location.pathname.startsWith('/workspace') ? 'workspace' : 'chatbot'
  const chat = useChat(); const [view, setView] = useState<View>(routeView); const active = chat.active
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const workspaceId = decodeURIComponent(location.pathname.match(/^\/workspace\/([^/]+)\/chat\//)?.[1] ?? '')
  useEffect(() => { const change = () => setView(routeView()); addEventListener('popstate', change); return () => removeEventListener('popstate', change) }, [])
  const refreshWorkspaces = async () => setWorkspaces(await api<Workspace[]>('/workspaces'))
  useEffect(() => { if (view !== 'chatbot') void refreshWorkspaces() }, [view])
  const switchView = (next: 'chatbot' | 'workspace') => { history.pushState({}, '', next === 'workspace' ? '/workspace' : `/chat/${chat.conversationId}`); setView(next) }
  const openWorkspaceChat = (id: string, idForWorkspace: string) => { history.pushState({}, '', `/workspace/${idForWorkspace}/chat/${id}`); window.dispatchEvent(new PopStateEvent('popstate')); void chat.refreshConversations(); setView('workspace-chat') }
  const newWorkspaceConversation = async () => { if (!workspaceId) return; const conversation = await api<{ id: string }>(`/workspaces/${workspaceId}/conversations`, { method: 'POST' }); openWorkspaceChat(conversation.id, workspaceId) }
  const openWorkspace = async (selectedWorkspaceId: string) => {
    const conversations = await api<{ id: string }[]>(`/workspaces/${encodeURIComponent(selectedWorkspaceId)}/conversations`)
    if (conversations[0]) openWorkspaceChat(conversations[0].id, selectedWorkspaceId)
    else { const conversation = await api<{ id: string }>(`/workspaces/${selectedWorkspaceId}/conversations`, { method: 'POST' }); openWorkspaceChat(conversation.id, selectedWorkspaceId) }
  }
  const removeWorkspace = async (selectedWorkspaceId: string, name: string) => {
    if (!confirm(`Remove ${name} from Harness? The folder and its files will not be deleted.`)) return
    await api(`/workspaces/${encodeURIComponent(selectedWorkspaceId)}`, { method: 'DELETE' }); await refreshWorkspaces(); await chat.refreshConversations()
  }
  const prompt = (text: string) => chat.send(text)
  const workspaceConversations = chat.conversations.filter(conversation => conversation.mode === 'workspace' && conversation.project_workspace_id === workspaceId)
  const workspaceRunId = chat.run?.id ?? [...chat.messages].reverse().find(message => message.run_id)?.run_id
  return <div className={`app-shell ${view === 'workspace-chat' ? 'workspace-execution-app' : ''}`}><aside className="sidebar"><div className="brand"><span>✦</span><div><b>Harness</b><small>Gemini workspace</small></div></div>
    <div className="mode-switch"><button className={view === 'chatbot' ? 'selected' : ''} onClick={() => switchView('chatbot')}>Chatbot</button><button className={view !== 'chatbot' ? 'selected' : ''} onClick={() => switchView('workspace')}>Workspace</button></div>
    {view === 'workspace' ? <><button className="new-chat" onClick={() => void refreshWorkspaces()}>↻ Refresh workspaces</button><nav className="conversation-list" aria-label="Recent workspaces">{workspaces.map(workspace => <div key={workspace.id} className="conversation-item"><button onClick={() => void openWorkspace(workspace.id)}><b>{workspace.name}</b><small>Open workspace IDE</small></button><span><button title="Remove workspace" onClick={() => void removeWorkspace(workspace.id, workspace.name)}>×</button></span></div>)}</nav><div className="privacy"><span>⌁</span><p><b>Workspace boundary</b><br />Only the selected folder is accessible.</p></div></> : view === 'workspace-chat' ? <>
      <button className="new-chat" onClick={() => void newWorkspaceConversation()}>＋ New workspace chat</button>
      <nav className="conversation-list" aria-label="Workspace conversations">{workspaceConversations.map(conversation => <div key={conversation.id} className={`conversation-item ${conversation.id === chat.conversationId ? 'selected' : ''}`}><button onClick={() => openWorkspaceChat(conversation.id, workspaceId)}><b>{conversation.title}</b><small>{conversation.preview || 'Empty workspace chat'}</small></button></div>)}</nav>
      <div className="privacy"><span>⌁</span><p><b>Workspace agent</b><br />Changes stay in this selected folder.</p></div>
    </> : <>
      <button className="new-chat" onClick={() => void chat.newConversation()}>＋ New conversation</button>
      <nav className="conversation-list" aria-label="Conversations">{chat.conversations.filter(conversation => conversation.mode !== 'workspace').map(conversation => <div key={conversation.id} className={`conversation-item ${conversation.id === chat.conversationId ? 'selected' : ''}`}><button onClick={() => void chat.load(conversation.id, true)}><b>{conversation.title}</b><small>{conversation.preview || 'Empty conversation'}</small></button><span><button title="Rename" onClick={() => void chat.rename(conversation.id)}>✎</button><button title="Archive" onClick={() => void chat.archive(conversation.id)}>⌄</button><button title="Delete" onClick={() => void chat.remove(conversation.id)}>×</button></span></div>)}</nav>
      <div className="privacy"><span>⌁</span><p><b>Scoped workspace</b><br />Files stay inside this chat.</p></div>
    </>}</aside>
    <div className={`shell ${view === 'workspace-chat' ? 'workspace-chat-shell' : ''}`}>{view === 'workspace' ? <WorkspacePanel onWorkspaceOpened={openWorkspace} /> : <>
      {view === 'workspace-chat' && <WorkspaceFiles conversationId={chat.conversationId} workspaceId={workspaceId} runId={workspaceRunId} />}
      <div className="chat-content"><header><div><p className="eyebrow">{view === 'workspace-chat' ? 'WORKSPACE MODE' : 'CHATBOT MODE'}</p><h1>{view === 'workspace-chat' ? 'Workspace agent' : 'Gemini Harness'}</h1></div><div className="run-status">{view === 'workspace-chat' && <AgentStatus events={chat.activities[chat.run?.id ?? ''] ?? []} status={chat.run?.status} />}<i className={active ? 'pulse' : ''}></i><span>{view === 'workspace-chat' ? ({ model_running: 'Working', tool_running: 'Executing action', context_building: 'Preparing context', inspecting_workspace: 'Inspecting workspace', subagent_running: 'Specialist working', visual_validating: 'Checking design', final_review: 'Final checks' } as Record<string, string>)[chat.run?.status ?? ''] ?? chat.run?.status?.replaceAll('_', ' ') ?? 'Ready' : chat.run?.status ?? 'Ready'}</span>{active && <button onClick={chat.cancel}>Cancel run</button>}</div></header>
        {chat.error && <div className="error"><span>{chat.error}</span>{chat.run?.status === 'failed' && <button onClick={() => void chat.retry()}>Retry request</button>}</div>}<ChatWindow messages={chat.messages} sources={chat.sources} workspace={view === 'workspace-chat'} activities={chat.activities} run={chat.run} activityError={chat.activityError} />
        <div className="suggestions">{view === 'workspace-chat' ? <><button onClick={() => prompt('Inspect this workspace and explain its structure.')}>Inspect project</button><button onClick={() => prompt('Find the main application entry point.')}>Find entry point</button><button onClick={() => prompt('Create a README.md that explains this project.')}>Create README</button></> : <><button onClick={() => prompt('Summarize my attached PDF.')}>Summarize PDF</button><button onClick={() => prompt('Generate an image of a calm futuristic workspace.')}>Create image</button><button onClick={() => prompt('Create a report from my attached files.')}>Create report</button></>}</div>
        <Composer disabled={!chat.ready || active} attachments={chat.attachments} onRemove={chat.removeAttachment} onSend={chat.send} onUpload={chat.upload} placeholder={view === 'workspace-chat' ? 'Ask or edit workspace files…' : undefined} />
      </div>
    </>}</div>
  </div>
}
