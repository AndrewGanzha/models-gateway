from typing import Literal

import httpx2 as httpx
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
    RoutingConfigurationError,
    UnsupportedModelError,
)
from app.domain.models import GenerationRequest, GenerationResult
from app.domain.routing import (
    RoutedGenerationRequest,
    RoutedGenerationResult,
)
from app.gateway.model_registry import build_model_registry
from app.gateway.routing import ModelRouter, load_routing_policy
from app.gateway.service import ModelGateway
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.vllm_provider import VLLMProvider

ProviderName = Literal["openai", "anthropic", "ollama", "vllm"]

settings = load_settings()
model_registry = build_model_registry(
    openai_model=settings.openai_model,
    anthropic_model=settings.anthropic_model,
    ollama_model=settings.ollama_model,
    vllm_model=settings.vllm_model,
)

gateways: dict[str, ModelGateway] = {
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
    "ollama": ModelGateway(
        OllamaProvider(
            httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=120.0,
            )
        ),
        capabilities=model_registry["ollama"],
    ),
    "vllm": ModelGateway(
        VLLMProvider(
            AsyncOpenAI(
                api_key=settings.vllm_api_key,
                base_url=settings.vllm_base_url,
                timeout=120.0,
                max_retries=0,
            )
        ),
        capabilities=model_registry["vllm"],
    ),
}

model_router = ModelRouter(
    gateways=gateways,
    policy=load_routing_policy(),
)

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


@router.post(
    "/generate/auto",
    response_model=RoutedGenerationResult,
)
async def generate_automatically(
    request: RoutedGenerationRequest,
) -> RoutedGenerationResult:
    try:
        return await model_router.generate(request)
    except RoutingConfigurationError as error:
        raise provider_http_error(error, 500) from error
    except ProviderRequestError as error:
        raise provider_http_error(error, 400) from error
    except (
        ProviderRateLimitError,
        ProviderUnavailableError,
    ) as error:
        raise provider_http_error(error, 503) from error
    except GatewayError as error:
        raise provider_http_error(error, 502) from error