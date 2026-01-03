import logging
from typing import List
from openai import AsyncOpenAI
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OpenAIEmbedder:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "text-embedding-3-small"
        self.dimensions = 1536

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.model,
                dimensions=self.dimensions
            )
            return [data.embedding for data in response.data]

        except Exception as e:
            logger.error(f" OpenAI Embedding Error: {e}")
            raise e