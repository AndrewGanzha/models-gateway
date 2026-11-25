from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

import httpx2 as httpx


@dataclass(frozen=True, slots=True)
class LocalObservation:
    model: str
    phase: str
    input_text: str
    expected: str | None
    prediction: str
    correct: bool | None
    client_latency_ms: float
    ollama_total_ms: float
    load_ms: float
    prompt_eval_ms: float
    generation_ms: float
    input_tokens: int
    output_tokens: int
    tokens_per_second: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def nanoseconds_to_milliseconds(value: int) -> float:
    return round(value / 1_000_000, 2)


async def unload_model(
    client: httpx.AsyncClient,
    model: str,
) -> None:
    response = await client.post(
        "/api/generate",
        json={"model": model, "keep_alive": 0},
    )
    if response.is_error:
        raise RuntimeError(
            f"Не удалось выгрузить {model}: "
            f"{response.status_code} {response.text}"
        )


async def generate_observation(
    client: httpx.AsyncClient,
    *,
    model: str,
    system_prompt: str,
    input_text: str,
    phase: str,
    expected: str | None = None,
) -> LocalObservation:
    started = perf_counter()
    response = await client.post(
        "/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
            "stream": False,
            "think": False,
            "keep_alive": -1,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": 2048,
                "num_predict": 16,
            },
        },
    )
    client_latency_ms = round((perf_counter() - started) * 1000, 2)

    if response.is_error:
        raise RuntimeError(
            f"Запрос к {model} завершился с кодом "
            f"{response.status_code}: {response.text}"
        )

    try:
        data = response.json()
        prediction = str(data["message"]["content"]).strip().lower()
        input_tokens = int(data["prompt_eval_count"])
        output_tokens = int(data["eval_count"])
        eval_duration = int(data["eval_duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Ollama вернула неожиданный ответ для {model}"
        ) from error

    tokens_per_second = (
        round(output_tokens / (eval_duration / 1_000_000_000), 2)
        if eval_duration > 0
        else 0.0
    )

    return LocalObservation(
        model=str(data.get("model") or model),
        phase=phase,
        input_text=input_text,
        expected=expected,
        prediction=prediction,
        correct=prediction == expected if expected is not None else None,
        client_latency_ms=client_latency_ms,
        ollama_total_ms=nanoseconds_to_milliseconds(
            int(data.get("total_duration") or 0)
        ),
        load_ms=nanoseconds_to_milliseconds(
            int(data.get("load_duration") or 0)
        ),
        prompt_eval_ms=nanoseconds_to_milliseconds(
            int(data.get("prompt_eval_duration") or 0)
        ),
        generation_ms=nanoseconds_to_milliseconds(eval_duration),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tokens_per_second=tokens_per_second,
    )


async def read_runtime_profile(
    client: httpx.AsyncClient,
    model: str,
) -> dict[str, Any]:
    response = await client.get("/api/ps")
    if response.is_error:
        raise RuntimeError(
            f"Не удалось получить /api/ps: "
            f"{response.status_code} {response.text}"
        )

    for item in response.json().get("models", []):
        if model in {item.get("name"), item.get("model")}:
            details = item.get("details") or {}
            return {
                "name": item.get("name"),
                "digest": item.get("digest"),
                "loaded_size_bytes": item.get("size"),
                "vram_size_bytes": item.get("size_vram"),
                "context_length": item.get("context_length"),
                "format": details.get("format"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
            }

    raise RuntimeError(
        f"Модель {model} не найдена среди загруженных моделей"
    )