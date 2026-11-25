from typing import Any

import httpx2 as httpx

from app.domain.errors import (
    InvalidProviderResponseError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from app.domain.models import (
    GenerationRequest,
    GenerationResult,
    Usage,
)


class OllamaProvider:
    name = "ollama"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                }
                for message in request.messages
            ],
            "stream": False,
            "think": False,
            "keep_alive": "5m",
            "options": {
                "num_predict": request.max_output_tokens,
            },
        }

        try:
            response = await self._client.post(
                "/api/chat",
                json=payload,
            )
        except httpx.RequestError as error:
            raise ProviderUnavailableError(self.name) from error

        if response.status_code >= 500:
            raise ProviderUnavailableError(self.name)
        if response.status_code >= 400:
            raise ProviderRequestError(self.name)

        try:
            data = response.json()
            message = data["message"]
            text = message["content"]
            input_tokens = int(data["prompt_eval_count"])
            output_tokens = int(data["eval_count"])

            if not isinstance(text, str) or not text.strip():
                raise ValueError("В ответе Ollama нет текста")

            return GenerationResult(
                provider=self.name,
                model=str(data["model"]),
                text=text,
                usage=Usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
                finish_reason=str(data.get("done_reason") or "unknown"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidProviderResponseError(self.name) from error