import asyncio
from uuid import uuid4


class GeminiImageClient:
    def __init__(self, api_key, model):
        self.api_key, self.model, self._client = api_key, model, None

    def _client_or_raise(self):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for image generation")
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate(self, prompt):
        return await asyncio.to_thread(self._generate_sync, prompt)

    def _generate_sync(self, prompt):
        from google.genai import types
        response = self._client_or_raise().models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]))
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    mime = inline.mime_type or "image/png"
                    extension = ".png" if mime == "image/png" else ".jpg"
                    data = inline.data if isinstance(inline.data, bytes) else bytes(inline.data)
                    return f"generated-{uuid4().hex[:8]}{extension}", data
        raise RuntimeError("Gemini did not return an image")
