# End-to-end test cases

The automated suite in `backend/tests/test_end_to_end_harness.py` uses a deterministic model, embedding service, and sandbox double. It tests real persistence, worker dispatch, orchestration, tools, memory, RAG, finalization, and scope checks without Gemini credentials or Docker.

| ID | User request / setup | Expected result | Automated |
| --- | --- | --- | --- |
| E2E-01 | `Build a website brief` | Model calls `create_artifact`; job executes; validated `website.md` is persisted and attached to the final message. | Yes |
| E2E-02 | Upload `orbit.md`, then `Research orbital mission` with its file ID. | Ingestion stores derived Markdown and vectors; retrieval supplies the source; final message contains a source card. | Yes |
| E2E-03 | Alice uploads a source; Bob attempts to read it. | Lookup fails before RAG or tool access. | Yes |
| E2E-04 | Send `Remember my green garden`, then `Review this plan`. | The second model context contains prior conversation; reviewer runs once with limited feedback and no tools; final response succeeds. | Yes |
| E2E-05 | Repeat the same message submission with one idempotency key. | One run and one user message are persisted; duplicate execution is rejected. | Yes (`test_core.py`) |
| E2E-06 | Invalid Bearer token or no token. | API returns 401; a different valid user receives 404 for another user’s thread. | Yes |
| E2E-07 | `calculate 8 * (4 + 1)`. | Calculator validates bounded AST input, records a tool run, and returns a final response. | Unit coverage exists; add to live Gemini smoke run. |
| E2E-08 | Sandbox exits nonzero or returns an unexpected file. | Job fails; artifact metadata is never created; run returns a clear error. | Run with sandbox integration environment. |
| E2E-09 | Live Gemini: research, website artifact, and reviewer requests. | Gemini emits function calls only for registered tools, embeds sources, and finalizes streamed output. | Manual: requires `GEMINI_API_KEY`. |

## Commands

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm test
python scripts/check_source_size.py
```

For live sandbox verification, start `./scripts/start-sandbox.sh`, then run the backend with `GEMINI_API_KEY` configured. Submit E2E-01 and E2E-02 through the UI and confirm the SSE state sequence: `created → planning → context_building → model_running → tool_running → validating → completed`.
