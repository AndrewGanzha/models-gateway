import anthropic
from anthropic import AsyncAnthropic

from app.domain.errors import (
    InvalidProviderResponseError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from app.domain.models import (
    GenerationRequest,
    GenerationResult,
    MessageRole,
    Usage,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        system = "\n\n".join(
            message.content
            for message in request.messages
            if message.role == MessageRole.SYSTEM
        )
        messages = [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in request.messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        ]

        parameters = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
        }
        if system:
            parameters["system"] = system

        try:
            response = await self._client.messages.create(**parameters)
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
        ) as error:
            raise ProviderAuthenticationError(self.name) from error
        except anthropic.RateLimitError as error:
            raise ProviderRateLimitError(self.name) from error
        except (
            anthropic.BadRequestError,
            anthropic.NotFoundError,
            anthropic.UnprocessableEntityError,
        ) as error:
            raise ProviderRequestError(self.name) from error
        except (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        ) as error:
            raise ProviderUnavailableError(self.name) from error

        try:
            text = "".join(
                block.text
                for block in response.content
                if block.type == "text"
            )
            if not text:
                raise ValueError("В ответе нет текста")

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            return GenerationResult(
                provider=self.name,
                model=response.model,
                text=text,
                usage=Usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                ),
                finish_reason=response.stop_reason or "unknown",
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidProviderResponseError(self.name) from error