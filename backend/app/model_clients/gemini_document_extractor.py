import asyncio


class GeminiDocumentExtractor:
    def __init__(self, api_key, model):
        self.api_key, self.model, self._client = api_key, model, None

    def _client_or_raise(self):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required to extract scanned PDFs")
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def extract_pdf(self, data, name):
        return await asyncio.to_thread(self._extract_sync, data, name)

    def _extract_sync(self, data, name):
        from google.genai import types
        response = self._client_or_raise().models.generate_content(
            model=self.model,
            contents=[types.Part.from_bytes(data=data, mime_type="application/pdf"),
                      f"Extract all readable text from {name}. Preserve headings, lists, and table values as Markdown."],
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("PDF contains no extractable text")
        return text
