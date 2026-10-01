# RAG Skill

## Purpose
Ingest documents/artifacts into searchable semantic context and retrieve only relevant chunks.

## Ingestion
```text
source file
→ extracted.md
→ chunk
→ embed
→ vector store
```

## Retrieval
```text
query
→ embed
→ vector search
→ metadata filter
→ rank/dedupe
→ RagContext
```

## Rules
- DB/storage are source of truth
- vector DB is disposable index
- scope filters mandatory
- no cross-workspace retrieval
- automatic RAG only after standalone retrieval is tested
