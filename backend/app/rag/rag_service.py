from app.schemas.contracts import RagContext


class RagService:
    def __init__(self, vectors, embeddings, files):
        self.vectors, self.embeddings, self.files = vectors, embeddings, files

    async def retrieve(self, scope, thread_id, query, file_ids=None):
        ids = file_ids or []
        sources = []
        for source_id in ids:
            source = await self.files.wait_for_index(source_id, scope, thread_id)
            sources.append({"id": source_id, "name": source["name"], "status": source["status"]})
        if not ids:
            return RagContext()
        embedding = await self.embeddings.embed_query(query)
        chunks = await self.vectors.search(scope, embedding, ids)
        names = {source["id"]: source["name"] for source in sources}
        return RagContext(chunks=[dict(chunk, name=names[chunk["source_id"]]) for chunk in chunks], sources=sources)
