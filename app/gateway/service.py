from app.domain.capabilities import ModelCapabilities
from app.domain.errors import UnsupportedModelError
from app.domain.models import GenerationRequest, GenerationResult
from app.providers.base import LLMProvider


class ModelGateway:
    def __init__(
        self,
        provider: LLMProvider,
        capabilities: ModelCapabilities,
    ) -> None:
        self._provider = provider
        self._capabilities = capabilities

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        if request.model != self._capabilities.model:
            raise UnsupportedModelError(
                provider=self._capabilities.provider,
                requested_model=request.model,
                expected_model=self._capabilities.model,
            )
        return await self._provider.generate(request)