from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2 as httpx


@dataclass(frozen=True, slots=True)
class EvaluationItem:
    item_id: str
    text: str
    expected: str


async def evaluate_item(
    client: httpx.AsyncClient,
    *,
    provider: str,
    model: str,
    prompt: str,
    item: EvaluationItem,
    max_output_tokens: int,
) -> dict[str, Any]:
    started = perf_counter()
    response = await client.post(
        "/generate",
        params={"provider": provider},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": item.text},
            ],
            "max_output_tokens": max_output_tokens,
        },
    )
    latency_ms = round((perf_counter() - started) * 1000, 2)

    if response.is_error:
        raise RuntimeError(
            f"Оценка {item.item_id} через {provider} завершилась "
            f"с кодом {response.status_code}: {response.text}"
        )

    result = response.json()
    prediction = result["text"].strip().lower()

    return {
        "id": item.item_id,
        "input": item.text,
        "expected": item.expected,
        "prediction": prediction,
        "correct": prediction == item.expected,
        "latency_ms": latency_ms,
        "requested_provider": provider,
        "actual_provider": result["provider"],
        "requested_model": model,
        "actual_model": result["model"],
        "usage": result["usage"],
        "finish_reason": result["finish_reason"],
    }