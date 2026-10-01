# Chatbot Mode + Workspace Mode Harness

You are extending an existing AI harness application with two clearly separated user experiences:

```text
1. Chatbot Mode
2. Workspace Mode
```

The same core harness architecture can power both modes, but their permissions, context, tools, storage, and execution rules must be different.

Do not merge them into one unrestricted agent.

---

# 1. Product Goal

The application UI must expose two primary sections:

```text
Chatbot
Workspace
```

## Chatbot Mode

Designed for ordinary AI interaction.

Supported capabilities:

```text
chat
file upload
file analysis
RAG over uploaded files
web research
image/file generation
PDF/DOCX/XLSX generation
sandboxed code execution when required
conversation memory
artifact generation
```

Chatbot Mode must NOT automatically receive access to a local/project filesystem.

It only sees:

```text
current conversation
uploaded files
indexed sources
generated artifacts
allowed external tools
```

---

## Workspace Mode

Designed for project-level coding and file operations.

The user explicitly selects a workspace/folder.

Example:

```text
/projects/acme-website/
```

The harness can then work inside that selected workspace:

```text
read folders
read files
search files
create folders
create files
edit files
rename files
delete files with safeguards
run terminal commands
run tests
run build commands
inspect Git
generate code
repair errors
review project structure
```

Workspace Mode must operate only inside the selected workspace root.

---

# 2. Fundamental Security Boundary

The most important rule is:

```text
Selected workspace root = maximum filesystem boundary
```

If the workspace is:

```text
/home/user/projects/acme-site
```

then tools may access:

```text
/home/user/projects/acme-site/**
```

but must NOT access:

```text
/home/user/projects/other-project
/home/user/.ssh
/home/user/.aws
/etc
/
../outside-workspace
```

All paths must be normalized and verified before execution.

Reject:

```text
../../
../
absolute paths outside root
symlink escape outside workspace
```

Never allow a model-generated path to bypass this boundary.

---

# 3. UI Architecture

Frontend navigation:

```text
┌───────────────────────────┐
│ AI Harness                │
├───────────────────────────┤
│ Chatbot                   │
│ Workspace                 │
└───────────────────────────┘
```

Recommended route structure:

```text
/chat
/workspace
/workspace/:workspaceId
```

---

# 4. Chatbot UI

Chatbot section:

```text
Chatbot
├── Thread sidebar
├── Message area
├── File attachments
├── Composer
├── Research/tool status
└── Generated artifacts
```

Chatbot composer supports:

```text
message
file attachment
image attachment
research
generate file
```

Do not show project filesystem tools.

---

# 5. Workspace UI

Workspace screen initially shows:

```text
Select Workspace
```

User selects:

```text
Choose Folder
```

After selection:

```text
┌───────────────────────────────────────────┐
│ Workspace: Acme Website                   │
├─────────────┬─────────────────────────────┤
│ Files       │ Chat / Agent                │
│             │                             │
│ src/        │ User: Build business site   │
│ components/ │                             │
│ package.json│ Agent working...            │
│ README.md   │                             │
├─────────────┴─────────────────────────────┤
│ Activity / Terminal / Changes             │
└───────────────────────────────────────────┘
```

Recommended sections:

```text
Workspace file tree
Chat panel
Activity panel
Terminal/log panel
Changes/diff panel
Artifacts/preview panel
```

---

# 6. Workspace Selection

When a user selects a folder, create a workspace record.

MongoDB:

```json
{
  "_id": "workspace_123",
  "user_id": "user_123",

  "name": "Acme Website",

  "mode": "filesystem_workspace",

  "root": {
    "type": "local_folder",
    "display_name": "acme-website",
    "root_token": "secure_workspace_handle"
  },

  "status": "active",

  "created_at": "...",
  "updated_at": "..."
}
```

Do not trust a raw client-provided filesystem path as authority.

The backend/local workspace service must map a server-controlled workspace ID or handle to an approved root.

---

# 7. Local vs Web Deployment

Implement the workspace abstraction so filesystem access does not depend on one deployment style.

Define:

```python
class WorkspaceProvider:
    async def list_files(...): ...
    async def read_file(...): ...
    async def write_file(...): ...
    async def create_directory(...): ...
    async def delete_path(...): ...
    async def rename_path(...): ...
```

Possible implementations:

```text
LocalWorkspaceProvider
SyncedCloudWorkspaceProvider
FutureGitWorkspaceProvider
```

## Local/Desktop Deployment

The local backend/desktop agent can access the explicitly selected folder.

## Browser/Cloud Deployment

Do not assume a remote backend can magically access a user's local filesystem path.

Use one of:

```text
browser File System Access API + explicit syncing
workspace upload/sync
Git repository clone
desktop/local companion service
```

Keep these behind the same `WorkspaceProvider` interface.

---

# 8. Workspace Database Model

MongoDB collection:

```text
workspaces
```

Suggested record:

```json
{
  "_id": "workspace_123",

  "owner_user_id": "user_123",

  "name": "Business Portfolio Website",

  "provider": "local",

  "status": "active",

  "settings": {
    "allow_terminal": true,
    "allow_file_creation": true,
    "allow_file_deletion": false,
    "allow_git": true,
    "auto_index": true
  },

  "created_at": "...",
  "updated_at": "...",
  "last_opened_at": "..."
}
```

---

# 9. Workspace Session

Opening a workspace creates a workspace session.

Collection:

```text
workspace_sessions
```

Example:

```json
{
  "_id": "ws_session_123",

  "workspace_id": "workspace_123",
  "user_id": "user_123",

  "status": "active",

  "client_session_id": "browser_session_abc",

  "started_at": "...",
  "last_activity_at": "...",
  "closed_at": null
}
```

This is separate from authentication session.

---

# 10. Workspace File Index

Do not send the entire project to the LLM.

Create a lightweight workspace index.

Collection:

```text
workspace_files
```

Record:

```json
{
  "_id": "workspace_file_123",

  "workspace_id": "workspace_123",

  "relative_path": "src/components/Hero.tsx",

  "file_type": "typescript",

  "size_bytes": 4832,

  "sha256": "...",

  "language": "typescript",

  "indexed": true,

  "updated_at": "..."
}
```

Only store metadata in Mongo.

Source file bytes remain in the workspace filesystem.

---

# 11. Workspace Scan Flow

When workspace opens:

```text
User selects workspace
      ↓
WorkspaceProvider validates root
      ↓
Scan folder tree
      ↓
Ignore excluded paths
      ↓
Create/update workspace_file metadata
      ↓
Optional code/RAG indexing
      ↓
Display file tree
```

Ignore by default:

```text
.git/
node_modules/
dist/
build/
coverage/
.next/
.cache/
__pycache__/
.venv/
venv/
tmp/
.DS_Store
```

Also respect:

```text
.gitignore
.workspaceignore
```

---

# 12. Workspace Ignore File

Support:

```text
.workspaceignore
```

Example:

```text
node_modules/
.env
.env.*
secrets/
*.pem
*.key
dist/
build/
```

Never automatically read secrets just because they are inside the workspace.

---

# 13. Sensitive Files

Default deny or redact:

```text
.env
.env.*
*.pem
*.key
id_rsa
credentials.json
.aws/
.ssh/
```

If access is absolutely required, require explicit user permission.

Never inject secrets into LLM context.

---

# 14. Workspace Tool Registry

Workspace mode gets a different tool set than chatbot mode.

Example registry:

```text
workspace.list_directory
workspace.find_files
workspace.search_text
workspace.read_file

workspace.create_directory
workspace.create_file
workspace.write_file
workspace.patch_file
workspace.rename_path

workspace.delete_path

workspace.get_diff
workspace.get_file_metadata

terminal.run_command

git.status
git.diff
git.log

build.run
test.run
```

Do not expose raw unrestricted shell as the primary interface.

---

# 15. Read Tools

## list_directory

```python
list_directory(
    relative_path="src"
)
```

Returns:

```json
{
  "entries": [
    {
      "name": "components",
      "type": "directory"
    }
  ]
}
```

---

## read_file

```python
read_file(
    relative_path="src/App.tsx"
)
```

Must validate:

```text
resolved path remains inside workspace root
file exists
size within limit
file is allowed
```

---

## search_text

```python
search_text(
    query="Hero",
    paths=["src"]
)
```

Use efficient search such as ripgrep internally.

Return structured matches.

---

# 16. Write Tools

Prefer patch-based modifications.

Tools:

```text
create_file
write_file
patch_file
create_directory
rename_path
```

`patch_file` should be preferred for existing files.

Example:

```json
{
  "relative_path": "src/App.tsx",
  "patch": "..."
}
```

Do not rewrite a 1000-line file just to change three lines.

---

# 17. Delete Tool

Deletion is higher risk.

Default:

```text
allow_file_deletion = false
```

If deletion is enabled:

```text
model requests delete
      ↓
permission service checks
      ↓
high-risk operation?
      ↓
user confirmation when required
      ↓
delete
```

Consider soft deletion or backup before destructive operations.

---

# 18. Terminal Tool

Do not expose:

```text
bash(command)
```

without policy.

Implement:

```python
run_command(
    command: str,
    cwd_relative: str = ".",
    timeout_seconds: int = 60
)
```

Execution environment must force:

```text
cwd = workspace root / cwd_relative
```

Do not permit `cwd` outside root.

---

# 19. Terminal Command Policy

Allow common project commands:

```text
npm install
npm run build
npm test
npm run lint

pnpm install
pnpm build

yarn install

pytest
python -m pytest

pip install -r requirements.txt

git status
git diff
```

Dangerous commands require rejection or explicit confirmation:

```text
rm -rf /
sudo
shutdown
reboot
mkfs
dd
curl | bash
wget | sh
chmod -R 777 /
```

Also inspect chained commands.

---

# 20. Workspace Execution Environment

Strong recommendation:

Run terminal/build commands inside an isolated workspace execution environment.

Architecture:

```text
Selected Workspace
      ↓
Workspace Agent
      ↓
Command request
      ↓
Workspace Execution Worker
      ↓
Isolated container
      ↓
Workspace mounted at:
      /workspace
```

Unlike ordinary artifact sandbox, workspace execution needs controlled write access to selected workspace.

Mount:

```text
selected workspace → /workspace
```

Never mount:

```text
/
$HOME
Docker socket
SSH directory
AWS directory
```

---

# 21. Workspace Command Container

Recommended:

```text
/workspace = selected project root
```

Set:

```text
working directory = /workspace
non-root user
CPU limit
RAM limit
timeout
```

Network:

```text
off by default
```

But package installation may require network.

If enabled:

```text
explicit execution mode
limited duration
logged
optional domain allowlist
```

---

# 22. Workspace Harness Context

When user asks:

```text
Build a professional business website
```

do NOT send all files to model.

First build workspace context:

```text
workspace name
project type
directory tree summary
package manifest
framework detection
important config files
relevant source files
recent Git status
user request
```

Example:

```text
Workspace:
acme-site

Detected stack:
React + Vite + TypeScript

Important files:
package.json
vite.config.ts
src/App.tsx
src/main.tsx

User request:
Build a professional business portfolio website.
```

---

# 23. Workspace Task Classification

The orchestrator should classify:

```json
{
  "mode": "workspace",
  "task_type": "website_build",

  "requires_workspace_scan": true,
  "requires_planning": true,

  "requires_tools": true,

  "tools": [
    "workspace.read_file",
    "workspace.patch_file",
    "workspace.create_file",
    "terminal.run_command"
  ],

  "requires_validation": true
}
```

---

# 24. End-to-End Workspace Request Flow

User opens:

```text
Workspace → Acme Website
```

Then enters:

```text
Build a professional business website
```

Flow:

```text
Frontend
  ↓
POST workspace message
  ↓
Backend
  ↓
validate user + workspace ownership
  ↓
create message
  ↓
create assistant run
  ↓
Orchestrator
  ↓
load workspace context
  ↓
inspect project
  ↓
create implementation plan
  ↓
select tools/sub-agents
  ↓
execute modifications
  ↓
run build/tests
  ↓
validate
  ↓
repair if needed
  ↓
compute diff
  ↓
final response
```

---

# 25. Detailed Website Build Flow

## Step 1

User:

```text
Build a professional business website
```

---

## Step 2

Orchestrator requests workspace inspection.

Tools:

```text
list_directory(".")
read_file("package.json")
read_file("src/App.tsx")
read_file("src/main.tsx")
git.status()
```

---

## Step 3

Detect environment:

```json
{
  "framework": "React",
  "language": "TypeScript",
  "build_tool": "Vite",
  "styling": "Tailwind",
  "package_manager": "npm"
}
```

---

## Step 4

Planning agent creates:

```json
{
  "steps": [
    "analyze current design",
    "create component structure",
    "build hero section",
    "build services section",
    "build portfolio section",
    "build testimonials",
    "build contact CTA",
    "update styling",
    "run build",
    "fix errors"
  ]
}
```

---

# 26. Design Sub-Agent

Optional design agent receives:

```text
user goal
current project structure
brand files
existing style
relevant memory
```

Returns:

```json
{
  "layout": [...],
  "sections": [...],
  "components": [...],
  "design_direction": "premium professional business"
}
```

It does not write files unless explicitly granted tools.

---

# 27. Code Agent

Code agent receives:

```text
approved plan
design plan
selected source files
framework rules
```

It returns structured file operations:

```json
{
  "operations": [
    {
      "type": "create",
      "path": "src/components/Hero.tsx",
      "content": "..."
    },
    {
      "type": "patch",
      "path": "src/App.tsx",
      "patch": "..."
    }
  ]
}
```

---

# 28. File Operation Validation

Before writing:

```text
normalize every path
ensure path inside workspace
ensure file not denied
check file size
check write permission
```

Then apply operations.

---

# 29. Snapshot / Change Safety

Before first modification, create a change checkpoint.

Options:

```text
Git commit/checkpoint
temporary patch snapshot
file hash snapshot
```

Store:

```json
{
  "workspace_run_id": "run_123",
  "base_git_commit": "...",
  "modified_files": []
}
```

This allows revert.

---

# 30. Apply Changes

Tool orchestrator applies:

```text
create directories
create files
patch existing files
rename files if required
```

Track every operation.

Collection:

```text
workspace_changes
```

Example:

```json
{
  "run_id": "run_123",
  "workspace_id": "workspace_123",

  "operation": "patch",

  "path": "src/App.tsx",

  "before_sha256": "...",
  "after_sha256": "...",

  "created_at": "..."
}
```

---

# 31. Build Validation

After changes:

```text
terminal.run_command("npm run build")
```

Collect:

```text
stdout
stderr
exit code
duration
```

If:

```text
exit code = 0
```

continue.

If not:

```text
feedback loop
```

---

# 32. Feedback / Repair Loop

Example error:

```text
Cannot find module './components/Hero'
```

Validation service creates:

```json
{
  "passed": false,

  "error_type": "build_error",

  "feedback": "Hero component is imported but missing.",

  "retryable": true
}
```

Repair agent receives:

```text
original request
plan
changed files
build error
relevant source files
```

Returns patch.

Apply patch.

Run build again.

Limit:

```text
max repair attempts = 3
```

---

# 33. Optional Test/Lint

If project provides scripts:

```text
npm test
npm run lint
```

Do not assume scripts exist.

Inspect `package.json`.

---

# 34. QA Agent

QA agent can review:

```text
changed file list
Git diff
build results
test results
design requirements
```

Returns:

```json
{
  "approved": true,
  "issues": [],
  "warnings": []
}
```

Or:

```json
{
  "approved": false,
  "issues": [...]
}
```

---

# 35. Final Workspace Validation

Before completion:

```text
build passes
critical tests pass
no path escapes occurred
no denied file modified
no secret exposed
expected files exist
diff recorded
```

Only then mark run completed.

---

# 36. Final Response

Frontend displays:

```text
Website updated successfully.

Changed:
- src/App.tsx
- src/components/Hero.tsx
- src/components/Services.tsx
- src/components/Portfolio.tsx
- src/styles.css

Validation:
✓ npm run build
✓ lint

You can review the changes in the Changes panel.
```

---

# 37. Changes Panel

Frontend should show:

```text
5 files changed
+340 additions
-72 deletions
```

Tabs:

```text
Files
Diff
Commands
Validation
```

---

# 38. Workspace Conversation Persistence

Workspace chats should still be normal chat threads, but scoped to a workspace.

`chat_threads`:

```json
{
  "_id": "thread_123",

  "mode": "workspace",

  "workspace_id": "workspace_123",

  "title": "Build business website"
}
```

Chatbot-mode threads:

```json
{
  "_id": "thread_456",

  "mode": "chatbot",

  "workspace_id": null
}
```

---

# 39. Tool Availability by Mode

Implement mode-based tool policies.

Chatbot:

```text
search_documents
web_search
analyze_file
create_artifact
generate_image
```

Workspace:

```text
workspace.read_file
workspace.search_text
workspace.create_file
workspace.patch_file
workspace.create_directory
workspace.rename_path

terminal.run_command

git.status
git.diff

plus optional:
web_search
RAG search
```

Never expose workspace filesystem tools to ordinary chatbot mode.

---

# 40. Harness Context by Mode

Chatbot context:

```text
system instructions
conversation
uploaded files
RAG context
general tools
```

Workspace context:

```text
system instructions
conversation
workspace metadata
project tree
selected/relevant files
Git status
workspace memory
workspace tools
```

---

# 41. Workspace RAG

Optionally index project files.

Pipeline:

```text
workspace file
  ↓
code/text chunking
  ↓
embeddings
  ↓
workspace vector index
```

When user asks:

```text
Where is authentication implemented?
```

RAG can retrieve relevant source files.

However:

```text
filesystem remains source of truth
```

Vector index is only a search accelerator.

---

# 42. Workspace Change Detection

Workspace may change outside the agent.

Implement:

```text
file watcher
or
periodic hash scan
```

If file changes:

```text
update workspace_files metadata
invalidate relevant RAG chunks
reindex changed file
```

Do not reindex entire project every time.

---

# 43. Concurrent Browser/Agent Safety

Multiple sessions may open same workspace.

Prevent write collisions.

Use:

```text
workspace_run lock
file version/hash checks
optimistic concurrency
```

Before patch:

```text
expected_sha256 == current_sha256
```

If not:

```text
conflict
```

Do not silently overwrite changes made after the model read the file.

---

# 44. Optimistic File Editing

Read:

```json
{
  "path": "src/App.tsx",
  "sha256": "abc..."
}
```

Patch request:

```json
{
  "path": "src/App.tsx",
  "expected_sha256": "abc...",
  "patch": "..."
}
```

If current hash differs:

```text
reject patch
re-read file
replan
```

This is important.

---

# 45. Git Integration

If workspace is a Git repository, expose:

```text
git.status
git.diff
git.log
```

Optional:

```text
git.create_branch
git.commit
```

Do not automatically commit unless configured/user requested.

Never automatically push remote changes by default.

---

# 46. Undo/Revert

Support workspace run rollback.

For each run maintain:

```text
changed files
original hashes
patches
base commit/checkpoint
```

Provide:

```text
Revert run changes
```

Do not delete user changes unrelated to the run.

---

# 47. MongoDB Collections

Add:

```text
workspaces
workspace_sessions
workspace_files
workspace_runs
workspace_changes
```

Existing:

```text
chat_threads
chat_messages
assistant_runs
tool_runs
```

Workspace run:

```json
{
  "_id": "workspace_run_123",

  "workspace_id": "workspace_123",
  "assistant_run_id": "run_123",

  "status": "running",

  "base_revision": "...",

  "changed_paths": [
    "src/App.tsx"
  ],

  "commands": [
    {
      "command": "npm run build",
      "exit_code": 0
    }
  ],

  "created_at": "...",
  "completed_at": null
}
```

---

# 48. S3 Usage in Workspace Mode

Do NOT copy every workspace source file into S3 automatically unless needed.

Use S3 for:

```text
workspace snapshots
generated artifacts
large logs
optional backup/checkpoints
preview builds
```

The selected workspace filesystem remains the active project state.

---

# 49. Preview Output

For website workflows:

```text
npm run build
```

If successful:

```text
dist/
```

Optionally package preview into artifact:

```text
website-preview.zip
```

or run temporary preview server in an isolated environment.

Do not expose arbitrary dev servers publicly without access control.

---

# 50. Workspace API Endpoints

Suggested APIs:

```text
POST /api/workspaces/select
GET  /api/workspaces
GET  /api/workspaces/{workspace_id}

GET  /api/workspaces/{workspace_id}/tree
GET  /api/workspaces/{workspace_id}/files

POST /api/workspaces/{workspace_id}/messages

GET  /api/workspaces/{workspace_id}/runs/{run_id}
POST /api/workspaces/{workspace_id}/runs/{run_id}/cancel

GET /api/workspaces/{workspace_id}/changes
GET /api/workspaces/{workspace_id}/diff

POST /api/workspaces/{workspace_id}/revert/{run_id}
```

Do not expose generic:

```text
POST /filesystem/read-any-path
```

---

# 51. Workspace Events

Stream events:

```text
workspace.scan.started
workspace.scan.completed

run.planning
run.reading_files

tool.started
tool.completed

file.created
file.modified
file.deleted

command.started
command.completed

validation.started
validation.failed
validation.passed

repair.started

run.completed
run.failed
```

Frontend uses these for activity display.

---

# 52. Example Complete Flow

User:

```text
Workspace
→ Select `/projects/acme`
→ "Build a professional business portfolio website"
```

Flow:

```text
1. Frontend sends request + workspace ID.

2. Backend validates:
   user owns/has access to workspace.

3. Save chat message.

4. Create assistant run.

5. Orchestrator loads workspace context.

6. Workspace tools inspect:
   tree
   package.json
   src/App.tsx
   config files

7. Memory/RAG retrieves:
   workspace rules
   brand files
   previous decisions

8. Planner creates implementation plan.

9. Optional Design Agent creates layout.

10. Code Agent creates structured operations.

11. Tool Orchestrator validates every path.

12. Create checkpoint.

13. Apply file operations.

14. Run:
    npm run build

15. Validator checks result.

16. If build fails:
    feedback → Repair Agent → patch → rebuild.

17. Run lint/tests when appropriate.

18. QA Agent reviews final diff.

19. Validate no forbidden resources changed.

20. Save run/change metadata.

21. Optionally store preview artifact in S3.

22. Mark assistant run completed.

23. Frontend shows:
    summary
    changed files
    diff
    commands
    validation results
    preview.
```

---

# 53. Non-Negotiable Safety Rules

Never allow Workspace Mode to:

```text
access filesystem outside selected root
follow symlinks outside root
read secret files by default
run sudo
mount Docker socket inside agent environment
send workspace files externally without permission
push Git changes automatically
delete arbitrary files without policy
```

Every write/command must be attributable to:

```text
user
workspace
run
tool call
timestamp
```

---

# 54. Required Components

Backend:

```text
WorkspaceService
WorkspaceProvider
WorkspaceToolRegistry
WorkspacePermissionService
WorkspaceRunService
WorkspaceChangeService
WorkspaceExecutionService
WorkspaceIndexer
```

Harness:

```text
RunOrchestrator
WorkspaceContextBuilder
Planner
SubAgentManager
ToolOrchestrator
ValidationService
FeedbackLoop
```

Frontend:

```text
WorkspaceSelector
WorkspaceFileTree
WorkspaceChat
ActivityPanel
TerminalPanel
DiffViewer
ValidationPanel
PreviewPanel
```

---

# 55. Suggested Folder Structure

```text
backend/app/
├── workspace/
│   ├── service.py
│   ├── provider.py
│   ├── local_provider.py
│   ├── scanner.py
│   ├── watcher.py
│   ├── paths.py
│   ├── permissions.py
│   ├── changes.py
│   └── models.py
│
├── tools/workspace/
│   ├── list_directory.py
│   ├── read_file.py
│   ├── search_text.py
│   ├── create_file.py
│   ├── patch_file.py
│   ├── rename_path.py
│   └── delete_path.py
│
├── tools/terminal/
│   └── run_command.py
│
├── tools/git/
│   ├── status.py
│   ├── diff.py
│   └── log.py
│
└── workers/
    └── workspace_execution_worker.py
```

Frontend:

```text
frontend/src/
├── pages/
│   ├── ChatbotPage.tsx
│   └── WorkspacePage.tsx
│
└── components/workspace/
    ├── WorkspaceSelector.tsx
    ├── FileTree.tsx
    ├── WorkspaceChat.tsx
    ├── ActivityPanel.tsx
    ├── TerminalPanel.tsx
    ├── DiffViewer.tsx
    ├── ChangesPanel.tsx
    └── PreviewPanel.tsx
```

---

# 56. Acceptance Criteria

Implementation is complete only when:

1. Chatbot and Workspace are separate UI modes.
2. Chatbot mode cannot use workspace filesystem tools.
3. User explicitly selects workspace root.
4. Workspace tools cannot escape selected root.
5. Workspace tree is visible in UI.
6. Agent can read files.
7. Agent can create folders/files.
8. Agent can patch existing files.
9. Agent can run allowed terminal commands.
10. Build/test commands produce streamed status.
11. File changes are tracked per run.
12. Optimistic hash checks prevent accidental overwrite.
13. Validation happens before success.
14. Feedback/repair loop works.
15. Diff is available to user.
16. Workspace run can be cancelled.
17. Workspace changes can be reverted safely.
18. Sensitive files are protected.
19. Git remote push does not happen automatically.
20. Workspace source does not get copied wholesale to S3 unnecessarily.
21. MongoDB stores workspace/run/change metadata.
22. S3 stores optional snapshots/artifacts/logs.
23. Workspace RAG is scoped to selected workspace.
24. Multiple users/workspaces cannot access each other.
25. Existing Chatbot Mode still works independently.

---

# 57. Final Architectural Rule

Always preserve this distinction:

```text
Chatbot Mode:
"Work with the information I give you."

Workspace Mode:
"Work inside this explicitly selected project."
```

And:

```text
The model does not receive unrestricted filesystem access.

The harness exposes narrow workspace tools.

The Tool Orchestrator validates every operation.

The Workspace Provider enforces the root boundary.

The Validator checks the resulting project.

The Feedback Loop repairs failures.

The user remains in control of the workspace.
```

Build Workspace Mode as a **controlled project environment**, not as an unrestricted shell attached to an LLM.