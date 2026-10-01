# Local Gemini AI Harness

This repository provides a local chat harness with Gemini function calling, scoped source retrieval, an isolated artifact sandbox, and a React chat UI.

## Run locally

1. Build and start the sandbox: `SANDBOX_TOKEN=local-sandbox-token ./scripts/start-sandbox.sh`.
2. Copy `backend/.env.example` to your local environment, set `GEMINI_API_KEY`, then run `cd backend && python -m uvicorn app.main:app --reload --port 8000`.
3. Copy `frontend/.env.example` to `frontend/.env`, then run `cd frontend && npm install && npm run dev`.

Open `http://localhost:5173`. The UI sends `local-demo-token` by default; change `AUTH_TOKENS` and `VITE_AUTH_TOKEN` together for another local scope.

## Request path

`React UI → FastAPI API → RunOrchestrator → Gemini/tools → worker → sandbox → validation → SSE final event`

Uploads accept UTF-8 `.txt`, `.md`, `.csv`, and `.pdf`. PDFs are text-extracted before scoped Gemini embedding. Ask for an image to use the registered Gemini image tool; generated PNG/JPEG artifacts are previewed in chat and can be downloaded.

## Durable conversations

Each sidebar entry is a durable `chat_threads` conversation. The browser route is `/chat/{conversation_id}`; refreshing it reloads messages, files, memory context, and any active run from the API. `POST /api/conversations`, `GET /api/conversations`, `GET /api/conversations/{id}/messages`, and conversation rename/archive/delete endpoints are all bearer-scoped. User messages and an assistant placeholder are saved before generation; streamed deltas update that placeholder record, so a reload cannot lose a response already generated.

## Chatbot and workspace modes

Chatbot mode is limited to conversation sources, RAG, artifacts, and its registered general tools. Workspace mode exposes a local folder-path picker and workspace chat route. The user explicitly selects a folder on the machine running the backend; the backend registers an opaque workspace token and never lets operations leave that selected folder.

Workspace paths are resolved on the server and must remain under the selected root. Path traversal, symlink escapes, sensitive files such as `.env`, PEM/key files, and `.ssh`/`.aws` directories are denied. Workspace tools include bounded directory listing, file read/search, protected create/write operations, and an opt-in allowlisted terminal runner. Terminal access is controlled by each workspace’s settings.

Repeated file creates with identical content succeed without changing the file or adding a change record. Different content produces a recoverable `file_exists` result with instructions to read the existing file and edit using its current hash. Failures feed the shared repair loop; unresolved mutations cannot finalize successfully. The transcript distinguishes failed creates from files already present.

Workspace file tools accept `path` as an alias for the canonical `relative_path` field. Conflicting values are rejected and unknown fields remain forbidden. Invalid tool arguments return concise repair guidance without echoing input values; the agent corrects them in the shared feedback loop. Successful calls are logged with canonical arguments, and unresolved argument errors cannot finalize successfully.

Missing-file and directory-read errors give recoverable guidance to inspect the actual path or create a required file. Text reads return at most 200 KB; large files return `truncated` and `next_offset_bytes` for additional pages, plus a hash of the whole file. Patching assembles the full file within the 500 KB write limit so unread tails are preserved.

Workspace tool failures (including failed commands), invalid final answers, model request errors, and failed website checks feed back into the ongoing run. Technical workspace repairs keep using the feedback loop. Screenshot visual quality repairs have a separate maximum of three attempts; a result that still fails cannot be delivered as successful. Stale hashes and missing patch matches trigger a fresh logged file read; edits must still use current hash protection. Pending mutations and commands reject premature final answers and ask for another repair. Reaching `WORKSPACE_MAX_STEPS` starts another processing batch in the same run, compacts model context, and resets the batch tool budget. The default `WORKSPACE_MAX_BATCHES=0` keeps continuing until validated completion or Cancel; an explicit positive batch cap is available for bounded deployments and tests. Model request retries wait briefly, and workspace restrictions remain enforced on every call.

After a failed or cancelled workspace run, send **continue** in the same chat to resume the original goal in a new linked run. The harness carries forward bounded action/failure evidence, the original website plan and design brief, and inspects the existing files. It does not automatically replay tool calls. Fresh completion validation is required; the previous run and its logs remain available. Completed tasks and runs from another workspace are not selected for failure continuation.

## Sandbox compatibility

The disposable artifact runner remains non-root, network-disabled, read-only, capability-dropped, PID/CPU/memory limited, and mounts only temporary output. Some local Docker/AppArmor configurations reject every process execution when `no-new-privileges` is also enabled. It is therefore disabled by default for this local runner; set `SANDBOX_NO_NEW_PRIVILEGES=true` only on hosts where the sandbox image passes an execution smoke test.

## Production persistence

The default host runtime automatically uses MongoDB for structured state and Cloudflare R2 for source and artifact bytes when the corresponding variables in `backend/.env` are configured. MongoDB keeps threads, messages, runs, jobs, memory, files, artifacts, durable events, and scoped RAG chunk metadata. R2 holds the original upload, derived Markdown, and generated artifact bytes under tenant-scoped object keys.

Set `PERSISTENCE_MODE=local` to force SQLite and the local filesystem, or `PERSISTENCE_MODE=mongo` to require the remote services. The test suite uses a temporary data directory and remains local. Never put database or R2 credentials in frontend variables or commit `backend/.env`.

## Verification

Run `cd backend && python -m pytest -q`, `cd frontend && npm run build`, and `python scripts/check_source_size.py`.


## Website completion and execution logs

Workspace website-generation requests receive a persisted implementation plan and design brief. React/Vite plans cover the manifest, HTML entry, Vite config, application entry, section components, reusable UI components, token/global/layout/animation styles, portfolio/services/testimonials data, meaningful local hero/project assets and README, while reusing detected filenames in existing projects. The default workspace processing batch is 80 model actions (`WORKSPACE_MAX_STEPS`); workspace execution continues across batches automatically.

Delivery requires planned files and imports, dependency installation when needed, a successful production build, generated HTML and bundled assets, desktop (1440px) and mobile (390px) preview loads, no browser/resource errors, responsive DOM checks and Gemini screenshot review. Failed checks feed automatic repair attempts throughout processing. Missing browser or model review capability fails validation and cannot produce a successful delivery.

Install backend dependencies and provision Chromium with `python -m playwright install chromium`, or set `HARNESS_CHROME_PATH` to a local browser executable. System Chrome/Chromium is also detected. Screenshots are kept under the selected project’s `.harness-preview` folder, excluded from source indexing.

The workspace Logs tab shows searchable, filtered action events, run selection, metrics, detail expansion, error filtering and pausable auto-scroll. Events include identity, component, status, timestamps, duration and sanitized results. File change records include paths, tool/run IDs and before/after hashes; source bodies and secrets are excluded from execution logs.

The portfolio integration regression uses scripted model output and screenshot review, but runs a real Vite build and real desktop/mobile browser capture. It reuses `frontend/node_modules`, so install frontend dependencies before running the backend suite. It also verifies incomplete output is rejected and cannot finalize after reaching an explicitly configured batch cap.


## Workspace execution transcript

Successful production builds and repeated unchanged actions also trigger project completion checks, so alternating build/listing loops receive concrete missing-file or visual repair feedback even when the model never requests a final answer. Completion is delivered only after the entire contract passes.

Workspace assistant turns now show their execution history directly in the conversation: progress messages, collapsible action groups, file reads/edits/creation, directory operations and command execution. Expand a command row to see its Shell panel with command text, stdout/stderr, exit code, duration and success/failure status. File edits expose sanitized diffs. The detailed Logs panel remains available for diagnostics.

Progress notes are public commentary events; hidden model thoughts are excluded. Live SSE updates replace running actions in place, and reloading a conversation loads its persisted event history without duplicate action rows. The composer stays visible while the transcript scrolls; following the newest events pauses when the user scrolls back. Command output appears when the controlled command returns.

Website quality is evaluated separately from build correctness. Before coding, DesignAgent persists a typed DesignBrief with section specifications, color/type/spacing/layout tokens, asset dimensions and mood, motion, responsive behavior, and placeholder prohibitions. When image generation is configured, `generate_image` can create a PNG/JPEG directly inside the selected project with `relative_path`; deliberate local SVG artwork remains the fallback.

The controlled browser captures full-page desktop and mobile screenshots and checks actual assets, hero imagery, visual project cards, tonal surfaces, typography, navigation, testimonials, footer, overflow, hover, keyboard focus and reduced-motion behavior. VisualQAAgent separately reviews the actual screenshots against twelve scored dimensions; every score must be at least 4/5, both viewport reviews must pass, and no high-severity issue may remain.

RepairAgent receives the original request, persisted brief, actual screenshots, structured issues, current file list, bounded workspace diffs, approved Git file diffs when available, and build output. It makes targeted file operations before rebuilding, recapturing and reviewing. The final report persists the complete technical and visual completion contract. After three unsuccessful visual repair attempts, the run preserves its work and reports failure without emitting a successful final answer. Send **continue** to resume with fresh validation.

The workspace explorer includes **Preview**, with authenticated desktop/mobile screenshots and an option to open the full image. **Changes** provides diffs and file hashes; **Logs** provides DesignAgent, CodeAgent, build, preview, visual QA and RepairAgent evidence. Preview images are isolated to the authenticated run and workspace and are not live deployments.

Repeated inspection recovery uses file versions and read offsets, so changed files and new pages count as fresh evidence. An unchanged inspection cycle triggers one recovery event: the harness refreshes relevant edit hashes, checks current website files/imports, and temporarily offers implementation and check tools instead of another read/list/search cycle. Successful edits restore normal inspection tools. The run preserves its original request, completed changes and pending failures across processing batches; duplicate inspections cannot emit a successful project delivery.

Invalid tool arguments are tracked by tool capability rather than an invented root-file mutation. Rejected commands return `command_not_allowed` and can be replaced with approved checks; command restrictions still apply. Failed production builds share a canonical command identity across `workspace_run_build` and `terminal_run_command`, so a successful retry through either wrapper resolves the same failure. Final delivery still requires the completion contract and resolution of pending actions.

In Workspace Mode, image and company-logo requests use Gemini image generation and always save into the selected project, even when no destination is supplied. React projects default to `src/assets/generated/`; static projects use `assets/generated/`. Paths are unique and explicit destinations remain create-only. The agent then imports/renders the returned path in the relevant website component. Finalization rejects unreferenced imagery and images confined to unused components, and runs the existing build script for standalone image-integration changes. Generated asset requirements carry forward on **continue**. Raster assets open as authenticated image previews in the file explorer.

Recoverable failure details, patch errors and retry diagnostics appear only in **Logs**. They continue feeding the model's repair loop; the chat transcript hides failed action rows and historical feedback commentary. Terminal run failures remain visible as the overall run status.

The workspace top bar shows running and total agents, including the main workspace agent, with an expandable name/status list. Specialist lifecycle events have unique agent-run IDs, so concurrent agents sharing a role count separately. Success, failure and cancellation update the running count; finished or interrupted runs cannot leave agents showing as running. This reports actual specialists when used, without automatically adding parallel work to every request.
