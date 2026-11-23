from app.domain.capabilities import (
    CapabilityInfo,
    CapabilityState,
    ModelCapabilities,
)


def build_model_registry(
    openai_model: str,
    anthropic_model: str,
) -> dict[str, ModelCapabilities]:
    verified_text_generation = CapabilityInfo(
        declared=True,
        verified=CapabilityState.SUPPORTED,
        note="Проверено настоящим запросом в разделе 1.3",
    )
    declared_but_not_verified = CapabilityInfo(
        declared=True,
        verified=CapabilityState.UNKNOWN,
        note=(
            "Возможность описана поставщиком, но ещё не проверена "
            "для выбранной модели через текущий адрес API"
        ),
    )

    return {
        "openai": ModelCapabilities(
            provider="openai",
            model=openai_model,
            text_generation=verified_text_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
        "anthropic": ModelCapabilities(
            provider="anthropic",
            model=anthropic_model,
            text_generation=verified_text_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
    }