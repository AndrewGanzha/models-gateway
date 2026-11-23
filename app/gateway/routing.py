import json
from pathlib import Path

from pydantic import ValidationError

from app.domain.capabilities import CapabilityState
from app.domain.errors import GatewayError, RoutingConfigurationError
from app.domain.models import GenerationRequest
from app.domain.routing import (
    RoutedGenerationRequest,
    RoutedGenerationResult,
    RoutingAttempt,
    RoutingPolicy,
    RoutingState,
)
from app.gateway.service import ModelGateway


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "policies" / "routing-v1.json"


def load_routing_policy() -> RoutingPolicy:
    try:
        raw_policy = json.loads(
            POLICY_PATH.read_text(encoding="utf-8")
        )
        return RoutingPolicy.model_validate(raw_policy)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise RoutingConfigurationError(
            f"Не удалось загрузить политику {POLICY_PATH}"
        ) from error


class ModelRouter:
    def __init__(
        self,
        gateways: dict[str, ModelGateway],
        policy: RoutingPolicy,
    ) -> None:
        self._gateways = gateways
        self._policy = policy
        self._candidates = policy.candidates[
            : policy.max_attempts
        ]

        if len(set(self._candidates)) != len(self._candidates):
            raise RoutingConfigurationError(
                "Политика содержит повторяющихся кандидатов"
            )

        for provider_name in self._candidates:
            self._get_gateway(provider_name)

    async def generate(
        self,
        request: RoutedGenerationRequest,
        state: RoutingState | None = None,
    ) -> RoutedGenerationResult:
        current_state = state or RoutingState()
        attempts: list[RoutingAttempt] = []

        for position, provider_name in enumerate(self._candidates):
            gateway = self._get_gateway(provider_name)
            generation_request = GenerationRequest(
                model=gateway.capabilities.model,
                messages=request.messages,
                max_output_tokens=request.max_output_tokens,
            )

            try:
                result = await gateway.generate(generation_request)
            except GatewayError as error:
                attempts.append(
                    RoutingAttempt(
                        provider=provider_name,
                        status="failed",
                        error=str(error),
                    )
                )
                has_next_candidate = (
                    position + 1 < len(self._candidates)
                )
                can_use_fallback = (
                    error.retryable
                    and has_next_candidate
                    and current_state.can_switch
                )
                if can_use_fallback:
                    continue
                raise

            attempts.append(
                RoutingAttempt(
                    provider=provider_name,
                    status="completed",
                )
            )
            return RoutedGenerationResult(
                route_version=self._policy.version,
                selected_provider=provider_name,
                attempts=attempts,
                result=result,
            )

        raise RoutingConfigurationError(
            "Политика не содержит доступных попыток"
        )

    def _get_gateway(self, provider_name: str) -> ModelGateway:
        gateway = self._gateways.get(provider_name)
        if gateway is None:
            raise RoutingConfigurationError(
                f"Поставщик {provider_name} отсутствует в Model Gateway"
            )

        verified = (
            gateway.capabilities.text_generation.verified
        )
        if verified != CapabilityState.SUPPORTED:
            raise RoutingConfigurationError(
                f"Генерация текста не подтверждена для {provider_name}"
            )

        return gateway