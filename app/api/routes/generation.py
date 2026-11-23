from typing import Literal

from anthropic import AsyncAnthropic
from fastapi import APIRouter, HTTPException, Query
from openai import AsyncOpenAI

from app.config import load_settings
from app.domain.capabilities import ModelCapabilities
from app.domain.errors import (
    GatewayError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
from app.domain.models import GenerationRequest, GenerationResult
from app.gateway.model_registry import build_model_registry
from app.gateway.service import ModelGateway
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.openai_provider import OpenAIProvider


ProviderName = Literal["openai", "anthropic"]

settings = load_settings()
model_registry = build_model_registry(
    openai_model=settings.openai_model,
    anthropic_model=settings.anthropic_model,
)

gateways: dict[ProviderName, ModelGateway] = {
    "openai": ModelGateway(
        OpenAIProvider(
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        ),
        capabilities=model_registry["openai"],
    ),
    "anthropic": ModelGateway(
        AnthropicProvider(
            AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
            )
        ),
        capabilities=model_registry["anthropic"],
    ),
}

router = APIRouter(tags=["generation"])


def provider_http_error(
    error: GatewayError,
    status_code: int,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "message": str(error),
            "retryable": error.retryable,
        },
    )


@router.get("/models", response_model=list[ModelCapabilities])
async def models() -> list[ModelCapabilities]:
    return [gateway.capabilities for gateway in gateways.values()]


@router.post("/generate", response_model=GenerationResult)
async def generate(
    request: GenerationRequest,
    provider: ProviderName = Query(...),
) -> GenerationResult:
    try:
        return await gateways[provider].generate(request)
    except UnsupportedModelError as error:
        raise provider_http_error(error, 400) from error
    except ProviderRequestError as error:
        raise provider_http_error(error, 400) from error
    except (
        ProviderRateLimitError,
        ProviderUnavailableError,
    ) as error:
        raise provider_http_error(error, 503) from error
    except GatewayError as error:
        raise provider_http_error(error, 502) from error