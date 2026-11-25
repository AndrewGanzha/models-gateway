import asyncio
import json
import math
import platform
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import httpx2 as httpx

from app.evaluation.runner import EvaluationItem, evaluate_item


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = Path(__file__).resolve()
GATEWAY_URL = "http://127.0.0.1:8001"
PROMPT_PATH = PROJECT_ROOT / "prompts/support-classifier-v1.txt"
DATASET_PATH = (
    PROJECT_ROOT / "evals/support-classification-dev-v1.json"
)
PROFILES_PATH = PROJECT_ROOT / "evals/deployment-profiles-v1.json"
PRICING_PATH = (
    PROJECT_ROOT / "evals/pricing-proxyapi-2026-10-02.json"
)
REPORT_PATH = PROJECT_ROOT / "artifacts/deployment-comparison-v1.json"

TARGET_PROVIDERS = ("vllm", "ollama", "openai")
CONCURRENCY_LEVELS = (1, 4)
MAX_OUTPUT_TOKENS = 100
MINIMUM_ACCURACY = 0.875
CODE_VERSION = "model-gateway-module-2"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_deployment_profiles(
    deployment_profiles: dict[str, Any],
) -> None:
    profiles = deployment_profiles.get("profiles", {})
    missing = [
        provider for provider in TARGET_PROVIDERS
        if provider not in profiles
    ]
    if missing:
        raise RuntimeError(
            "В профилях размещения отсутствуют: " + ", ".join(missing)
        )

    unfinished = []
    for provider in TARGET_PROVIDERS:
        for field in ("hardware", "runtime"):
            value = str(profiles[provider].get(field, ""))
            if not value or value.startswith("Укажите"):
                unfinished.append(f"{provider}.{field}")

    if unfinished:
        raise RuntimeError(
            "Заполните сведения об окружении: " + ", ".join(unfinished)
        )


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def estimate_cost(
    observations: list[dict[str, Any]],
    *,
    model: str,
    pricing: dict[str, Any],
) -> float | None:
    rates = pricing["models"].get(model)
    if rates is None:
        return None

    input_tokens = sum(
        item["usage"]["input_tokens"] for item in observations
    )
    output_tokens = sum(
        item["usage"]["output_tokens"] for item in observations
    )
    cost = (
        input_tokens * rates["input_per_million"]
        + output_tokens * rates["output_per_million"]
    ) / 1_000_000
    return round(cost, 6)


def summarize(
    observations: list[dict[str, Any]],
    *,
    wall_seconds: float,
    concurrency: int,
    model: str,
    pricing: dict[str, Any],
) -> dict[str, Any]:
    latencies = [item["latency_ms"] for item in observations]
    correct = sum(item["correct"] for item in observations)

    return {
        "concurrency": concurrency,
        "total_items": len(observations),
        "correct_items": correct,
        "accuracy": round(correct / len(observations), 4),
        "wall_seconds": round(wall_seconds, 3),
        "requests_per_second": round(
            len(observations) / wall_seconds,
            3,
        ),
        "average_latency_ms": round(mean(latencies), 2),
        "p95_latency_ms": round(percentile_95(latencies), 2),
        "total_input_tokens": sum(
            item["usage"]["input_tokens"] for item in observations
        ),
        "total_output_tokens": sum(
            item["usage"]["output_tokens"] for item in observations
        ),
        "estimated_api_cost": estimate_cost(
            observations,
            model=model,
            pricing=pricing,
        ),
        "observations": observations,
    }



async def run_profile(
    client: httpx.AsyncClient,
    *,
    provider: str,
    model: str,
    prompt: str,
    items: list[EvaluationItem],
    concurrency: int,
    pricing: dict[str, Any],
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run_item(item: EvaluationItem) -> dict[str, Any]:
        async with semaphore:
            return await evaluate_item(
                client,
                provider=provider,
                model=model,
                prompt=prompt,
                item=item,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )

    started = perf_counter()
    observations = list(await asyncio.gather(*(run_item(item) for item in items)))
    wall_seconds = perf_counter() - started

    return summarize(
        observations,
        wall_seconds=wall_seconds,
        concurrency=concurrency,
        model=model,
        pricing=pricing,
    )


async def preflight(
    client: httpx.AsyncClient,
    *,
    registry: dict[str, dict[str, Any]],
    prompt: str,
    probe: EvaluationItem,
) -> dict[str, str]:
    models = {}
    for provider in TARGET_PROVIDERS:
        profile = registry[provider]
        if profile["text_generation"]["verified"] != "supported":
            raise RuntimeError(
                f"Генерация текста не подтверждена для {provider}"
            )

        model = profile["model"]
        print(f"Проверяем доступность {provider}...")
        await evaluate_item(
            client,
            provider=provider,
            model=model,
            prompt=prompt,
            item=probe,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        models[provider] = model

    print("Все три варианта доступны. Начинаем измерения.\n")
    return models



async def main() -> None:
    started_at = datetime.now(UTC).isoformat()
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    dataset = load_json(DATASET_PATH)
    deployment_profiles = load_json(PROFILES_PATH)
    pricing = load_json(PRICING_PATH)
    validate_deployment_profiles(deployment_profiles)
    items = [
        EvaluationItem(
            item_id=item["id"],
            text=item["text"],
            expected=item["expected"],
        )
        for item in dataset["items"]
    ]

    async with httpx.AsyncClient(
        base_url=GATEWAY_URL,
        timeout=180.0,
    ) as client:
        models_response = await client.get("/models")
        models_response.raise_for_status()
        registry = {
            item["provider"]: item
            for item in models_response.json()
        }

        missing = [
            provider
            for provider in TARGET_PROVIDERS
            if provider not in registry
        ]
        if missing:
            raise RuntimeError(
                "В реестре отсутствуют поставщики: "
                + ", ".join(missing)
            )

        models = await preflight(
            client,
            registry=registry,
            prompt=prompt,
            probe=items[0],
        )

        runs = []
        for provider in TARGET_PROVIDERS:
            model = models[provider]
            measured_profiles = []
            for concurrency in CONCURRENCY_LEVELS:
                print(
                    f"{provider}: запускаем серию "
                    f"с concurrency={concurrency}..."
                )
                measured_profiles.append(
                    await run_profile(
                        client,
                        provider=provider,
                        model=model,
                        prompt=prompt,
                        items=items,
                        concurrency=concurrency,
                        pricing=pricing,
                    )
                )

            runs.append(
                {
                    "provider": provider,
                    "requested_model": model,
                    "actual_models": sorted(
                        {
                            observation["actual_model"]
                            for measured in measured_profiles
                            for observation in measured["observations"]
                        }
                    ),
                    "placement": deployment_profiles["profiles"][
                        provider
                    ],
                    "eligible_by_quality": all(
                        measured["accuracy"] >= MINIMUM_ACCURACY
                        for measured in measured_profiles
                    ),
                    "profiles": measured_profiles,
                }
            )

    report = {
        "experiment": {
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "code_version": CODE_VERSION,
            "code_sha256": file_hash(SCRIPT_PATH),
            "prompt_version": "support-classifier-v1",
            "prompt_sha256": file_hash(PROMPT_PATH),
            "dataset_version": dataset["version"],
            "dataset_split": dataset["split"],
            "dataset_sha256": file_hash(DATASET_PATH),
            "deployment_profile_version": deployment_profiles["version"],
            "deployment_profile_sha256": file_hash(PROFILES_PATH),
            "pricing_version": pricing["version"],
            "providers": list(TARGET_PROVIDERS),
            "parameters": {
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "concurrency_levels": list(CONCURRENCY_LEVELS),
                "minimum_accuracy": MINIMUM_ACCURACY,
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
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for run in runs:
        for measured in run["profiles"]:
            cost = measured["estimated_api_cost"]
            cost_text = (
                f"{cost:.6f} {pricing['currency']}"
                if cost is not None
                else "не рассчитывается по токенам"
            )
            print(
                f'{run["provider"]} | '
                f'concurrency={measured["concurrency"]} | '
                f'accuracy={measured["accuracy"]:.2%} | '
                f'wall={measured["wall_seconds"]:.3f} с | '
                f'requests/s={measured["requests_per_second"]:.3f} | '
                f'avg={measured["average_latency_ms"]:.2f} мс | '
                f'cost={cost_text}'
            )
        print(
            "Допускается по качеству:",
            "да" if run["eligible_by_quality"] else "нет",
        )

    print(f"Полный отчёт сохранён в {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())