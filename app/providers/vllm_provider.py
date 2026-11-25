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
    Usage,
)


class VLLMProvider:
    name = "vllm"

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult:
        try:
            response = await self._client.chat.completions.create(
                model=request.model,
                messages=[
                    {
                        "role": message.role.value,
                        "content": message.content,
                    }
                    for message in request.messages
                ],
                max_tokens=request.max_output_tokens,
                temperature=0,
                extra_body={
                    "chat_template_kwargs": {
                        "enable_thinking": False,
                    }
                },
            )
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
            choice = response.choices[0]
            text = choice.message.content
            usage = response.usage

            if not text or usage is None:
                raise ValueError("В ответе vLLM нет текста или статистики")

            return GenerationResult(
                provider=self.name,
                model=response.model,
                text=text,
                usage=Usage(
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                ),
                finish_reason=choice.finish_reason or "unknown",
            )
        except (IndexError, AttributeError, TypeError, ValueError) as error:
            raise InvalidProviderResponseError(self.name) from error