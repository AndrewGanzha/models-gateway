import asyncio
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from typing import Any

import httpx2 as httpx

from app.evaluation.runner import EvaluationItem, evaluate_item


GATEWAY_URL = "http://127.0.0.1:8001"
CODE_VERSION = "model-gateway-module-1"
PROMPT_VERSION = "support-classifier-v1"
PROMPT_PATH = Path("prompts/support-classifier-v1.txt")
DATASET_PATH = Path("evals/support-classification-dev-v1.json")
PRICING_PATH = Path("evals/pricing-proxyapi-2026-10-02.json")
REPORT_PATH = Path("artifacts/model-comparison-v1.json")
MAX_OUTPUT_TOKENS = 100


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def calculate_metrics(
    observations: list[dict[str, Any]],
    rates: dict[str, float],
) -> dict[str, int | float]:
    correct = sum(item["correct"] for item in observations)
    input_tokens = sum(
        item["usage"]["input_tokens"] for item in observations
    )
    output_tokens = sum(
        item["usage"]["output_tokens"] for item in observations
    )
    estimated_cost = (
        input_tokens * rates["input_per_million"]
        + output_tokens * rates["output_per_million"]
    ) / 1_000_000

    return {
        "total_items": len(observations),
        "correct_items": correct,
        "accuracy": round(correct / len(observations), 4),
        "average_latency_ms": round(
            mean(item["latency_ms"] for item in observations),
            2,
        ),
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "estimated_cost": round(estimated_cost, 6),
    }


async def main() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    dataset = load_json(DATASET_PATH)
    pricing = load_json(PRICING_PATH)
    started_at = datetime.now(UTC).isoformat()

    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        timeout=120.0,
    ) as client:
        models_response = await client.get("/models")
        models_response.raise_for_status()

        candidates = [
            {
                "provider": profile["provider"],
                "model": profile["model"],
            }
            for profile in models_response.json()
            if profile["text_generation"]["verified"] == "supported"
        ]

        if not candidates:
            raise RuntimeError(
                "В реестре нет моделей с проверенной генерацией текста"
            )

        missing_prices = [
            candidate["model"]
            for candidate in candidates
            if candidate["model"] not in pricing["models"]
        ]
        if missing_prices:
            raise RuntimeError(
                "В снимке тарифов нет моделей: "
                + ", ".join(missing_prices)
            )

        runs = []
        for candidate in candidates:
            observations = []
            for raw_item in dataset["items"]:
                item = EvaluationItem(
                    item_id=raw_item["id"],
                    text=raw_item["text"],
                    expected=raw_item["expected"],
                )
                observations.append(
                    await evaluate_item(
                        client,
                        provider=candidate["provider"],
                        model=candidate["model"],
                        prompt=prompt,
                        item=item,
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                    )
                )

            runs.append(
                {
                    "requested_provider": candidate["provider"],
                    "requested_model": candidate["model"],
                    "actual_models": sorted(
                        {
                            item["actual_model"]
                            for item in observations
                        }
                    ),
                    "metrics": calculate_metrics(
                        observations,
                        pricing["models"][candidate["model"]],
                    ),
                    "observations": observations,
                }
            )

    report = {
        "experiment": {
            "started_at": started_at,
            "code_version": CODE_VERSION,
            "prompt_version": PROMPT_VERSION,
            "dataset_version": dataset["version"],
            "dataset_split": dataset["split"],
            "pricing_version": pricing["version"],
            "parameters": {
                "max_output_tokens": MAX_OUTPUT_TOKENS
            },
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "httpx2": version("httpx2"),
                "gateway_url": GATEWAY_URL,
            },
        },
        "currency": pricing["currency"],
        "runs": runs,
    }

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for run in runs:
        metrics = run["metrics"]
        print(
            f"{run['requested_provider']} | "
            f"{run['requested_model']} | "
            f"точность={metrics['accuracy']:.2%} | "
            f"задержка={metrics['average_latency_ms']:.2f} мс | "
            f"стоимость≈{metrics['estimated_cost']:.6f} "
            f"{pricing['currency']}"
        )

    print(f"Полный отчёт сохранён в {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())