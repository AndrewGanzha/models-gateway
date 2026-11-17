from app.domain.models import GenerationRequest, GenerationResult
from app.providers.base import LLMProvider


class ModelGateway:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        return await self._provider.generate(request)