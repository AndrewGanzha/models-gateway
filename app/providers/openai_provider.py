import openai
from openai import AsyncOpenAI

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


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        instructions = "\n\n".join(
            message.content
            for message in request.messages
            if message.role == MessageRole.SYSTEM
        )
        input_messages = [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in request.messages
            if message.role in {MessageRole.USER, MessageRole.ASSISTANT}
        ]

        parameters = {
            "model": request.model,
            "input": input_messages,
            "max_output_tokens": request.max_output_tokens,
        }
        if instructions:
            parameters["instructions"] = instructions

        try:
            response = await self._client.responses.create(**parameters)
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
        ) as error:
            raise ProviderAuthenticationError(self.name) from error
        except openai.RateLimitError as error:
            raise ProviderRateLimitError(self.name) from error
        except (
            openai.BadRequestError,
            openai.NotFoundError,
            openai.UnprocessableEntityError,
        ) as error:
            raise ProviderRequestError(self.name) from error
        except (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        ) as error:
            raise ProviderUnavailableError(self.name) from error

        try:
            if response.usage is None or not response.output_text:
                raise ValueError("В ответе нет текста или статистики")

            finish_reason = response.status or "unknown"
            if response.incomplete_details is not None:
                finish_reason = (
                    response.incomplete_details.reason or finish_reason
                )

            return GenerationResult(
                provider=self.name,
                model=response.model,
                text=response.output_text,
                usage=Usage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.total_tokens,
                ),
                finish_reason=finish_reason,
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidProviderResponseError(self.name) from error