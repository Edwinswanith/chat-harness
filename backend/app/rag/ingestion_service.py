import io

from app.rag.chunker import chunk_text


class IngestionService:
    def __init__(self, repo, storage, vectors, embeddings, document_extractor=None):
        self.repo, self.storage, self.vectors, self.embeddings = repo, storage, vectors, embeddings
        self.document_extractor = document_extractor

    async def ingest(self, scope, source_id):
        source = await self.repo.get("file", source_id, scope)
        raw = await self.storage.read(source["key"])
        text = await self._extract_text(source["name"], raw)
        markdown = f"# {source['name']}\n\n{text}" if source["name"].endswith(".csv") else text
        derived_key = source.get("derived_key")
        if not derived_key:
            from app.storage.paths import file_key
            derived_key = file_key(source_id, derived=True)
        await self.storage.write(derived_key, markdown.encode())
        chunks = chunk_text(markdown)
        vectors = await self.embeddings.embed_documents(chunks)
        await self.vectors.replace_source(scope, source_id, source["thread_id"], zip(chunks, vectors))
        await self.repo.patch("file", source_id, scope, status="indexed", derived_key=derived_key, chunk_count=len(chunks))

    async def _extract_text(self, name, raw):
        if name.lower().endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if text or self.document_extractor is None:
                return text
            return await self.document_extractor.extract_pdf(raw, name)
        return raw.decode("utf-8")
