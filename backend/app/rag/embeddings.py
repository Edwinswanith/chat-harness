import asyncio


class GeminiEmbeddings:
    def __init__(self, api_key, model):
        self.api_key, self.model, self._client = api_key, model, None

    def _client_or_raise(self):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for embeddings")
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def embed_documents(self, texts):
        return await asyncio.to_thread(self._embed, texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text):
        return (await asyncio.to_thread(self._embed, [text], "RETRIEVAL_QUERY"))[0]

    def _embed(self, texts, task_type):
        from google.genai import types
        vectors = []
        for text in texts:
            response = self._client_or_raise().models.embed_content(
                model=self.model, contents=text, config=types.EmbedContentConfig(task_type=task_type))
            vectors.append(list(response.embeddings[0].values))
        return vectors
