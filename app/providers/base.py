from typing import Protocol

from app.domain.models import GenerationRequest, GenerationResult


class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        ...