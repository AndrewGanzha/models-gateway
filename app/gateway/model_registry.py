from app.domain.capabilities import (
    CapabilityInfo,
    CapabilityState,
    ModelCapabilities,
)


def build_model_registry(
    openai_model: str,
    anthropic_model: str,
    ollama_model: str,
    vllm_model: str,
) -> dict[str, ModelCapabilities]:
    verified_external_generation = CapabilityInfo(
        declared=True,
        verified=CapabilityState.SUPPORTED,
        note="Проверено настоящими запросами в разделе 1.3",
    )
    verified_ollama_generation = CapabilityInfo(
        declared=True,
        verified=CapabilityState.SUPPORTED,
        note="Проверено через локальный API Ollama в разделе 2.2",
    )
    verified_vllm_generation = CapabilityInfo(
        declared=True,
        verified=CapabilityState.SUPPORTED,
        note="Проверено через vLLM в Google Colab в разделе 2.4",
    )
    declared_but_not_verified = CapabilityInfo(
        declared=True,
        verified=CapabilityState.UNKNOWN,
        note="Возможность описана, но ещё не проверена в текущей конфигурации",
    )

    return {
        "openai": ModelCapabilities(
            provider="openai",
            model=openai_model,
            text_generation=verified_external_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
        "anthropic": ModelCapabilities(
            provider="anthropic",
            model=anthropic_model,
            text_generation=verified_external_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
        "ollama": ModelCapabilities(
            provider="ollama",
            model=ollama_model,
            text_generation=verified_ollama_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
        "vllm": ModelCapabilities(
            provider="vllm",
            model=vllm_model,
            text_generation=verified_vllm_generation,
            structured_output=declared_but_not_verified,
            tools=declared_but_not_verified,
            streaming=declared_but_not_verified,
        ),
    }