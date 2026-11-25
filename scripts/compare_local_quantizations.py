import asyncio
import json
import platform
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from typing import Any

import httpx2 as httpx

from app.evaluation.ollama_benchmark import (
    LocalObservation,
    generate_observation,
    read_runtime_profile,
    unload_model,
)


OLLAMA_URL = "http://127.0.0.1:11434"
CANDIDATES = (
    "qwen3:0.6b-q4_K_M",
    "qwen3:0.6b-fp16",
)
CODE_VERSION = "model-gateway-module-2"
PROMPT_VERSION = "support-classifier-v1"
PROMPT_PATH = Path("prompts/support-classifier-v1.txt")
DATASET_PATH = Path("evals/support-classification-dev-v1.json")
REPORT_PATH = Path("artifacts/local-quantization-comparison-v1.json")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def summarize(
    observations: list[LocalObservation],
) -> dict[str, int | float]:
    return {
        "total_items": len(observations),
        "correct_items": sum(item.correct is True for item in observations),
        "accuracy": round(
            sum(item.correct is True for item in observations)
            / len(observations),
            4,
        ),
        "average_client_latency_ms": round(
            mean(item.client_latency_ms for item in observations),
            2,
        ),
        "average_tokens_per_second": round(
            mean(item.tokens_per_second for item in observations),
            2,
        ),
    }


async def main() -> None:
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    dataset = load_json(DATASET_PATH)
    probe = dataset["items"][0]

    async with httpx.AsyncClient(
        base_url=OLLAMA_URL,
        timeout=180.0,
    ) as client:
        version_response = await client.get("/api/version")
        version_response.raise_for_status()
        ollama_version = version_response.json()["version"]

        tags_response = await client.get("/api/tags")
        tags_response.raise_for_status()
        local_models = {
            item["name"]: item
            for item in tags_response.json().get("models", [])
        }
        missing = [model for model in CANDIDATES if model not in local_models]
        if missing:
            raise RuntimeError(
                "Сначала загрузите модели: " + ", ".join(missing)
            )

        runs = []
        for model in CANDIDATES:
            for candidate in CANDIDATES:
                await unload_model(client, candidate)

            cold = await generate_observation(
                client,
                model=model,
                system_prompt=prompt,
                input_text=probe["text"],
                phase="cold",
                expected=probe["expected"],
            )
            runtime = await read_runtime_profile(client, model)
            warm = await generate_observation(
                client,
                model=model,
                system_prompt=prompt,
                input_text=probe["text"],
                phase="warm",
                expected=probe["expected"],
            )

            observations = []
            for item in dataset["items"]:
                observations.append(
                    await generate_observation(
                        client,
                        model=model,
                        system_prompt=prompt,
                        input_text=item["text"],
                        phase="evaluation",
                        expected=item["expected"],
                    )
                )

            catalog_item = local_models[model]
            runs.append(
                {
                    "model": model,
                    "digest": catalog_item.get("digest"),
                    "disk_size_bytes": catalog_item.get("size"),
                    "details": catalog_item.get("details"),
                    "runtime": runtime,
                    "cold_run": cold.to_dict(),
                    "warm_run": warm.to_dict(),
                    "metrics": summarize(observations),
                    "observations": [
                        item.to_dict() for item in observations
                    ],
                }
            )
            await unload_model(client, model)

    report = {
        "experiment": {
            "started_at": datetime.now(UTC).isoformat(),
            "code_version": CODE_VERSION,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": file_hash(PROMPT_PATH),
            "dataset_version": dataset["version"],
            "dataset_sha256": file_hash(DATASET_PATH),
            "models": list(CANDIDATES),
            "parameters": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": 2048,
                "num_predict": 16,
                "think": False,
            },
            "environment": {
                "python": platform.python_version(),
                "system": platform.system(),
                "machine": platform.machine(),
                "ollama": ollama_version,
                "httpx2": version("httpx2"),
            },
        },
        "runs": runs,
    }

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for run in runs:
        metrics = run["metrics"]
        print(
            f'{run["model"]}: '
            f'accuracy={metrics["accuracy"]:.2%}, '
            f'cold={run["cold_run"]["client_latency_ms"]:.2f} ms, '
            f'warm={run["warm_run"]["client_latency_ms"]:.2f} ms, '
            f'tokens/s={metrics["average_tokens_per_second"]:.2f}'
        )
    print(f"Полный отчёт сохранён в {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())