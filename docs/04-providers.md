# 4. Поставщики и адаптеры

## Контракт адаптера

```python
class LLMProvider(Protocol):
    name: str

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        ...
```

[app/providers/base.py](../app/providers/base.py)

Три строки — и это всё, что нужно знать ядру. `Protocol` вместо абстрактного класса выбран
сознательно: адаптер не обязан наследоваться, достаточно структурного совпадения, а типизация
проверяется статически. Цена — нет общей реализации, каждый адаптер дублирует шапку.

У контракта два негласных обязательства, без которых шлюз ломается:

- **вернуть `GenerationResult` или бросить `GatewayError`** — ничего третьего;
- **не выполнять повторов и не переключать поставщика** — это работа `ModelRouter`
  ([docs/06-routing.md](06-routing.md)).

## Четыре адаптера

### OpenAI — Responses API

[app/providers/openai_provider.py](../app/providers/openai_provider.py)

Самый «непохожий» на остальных: это не чат-API, а API ответов. Разделение сообщений делается
вручную — системные собираются в одну строку и уходят в `instructions`, остальные в `input`
([#L29-L52](../app/providers/openai_provider.py#L29-L52)).

Тонкость в признаке завершения:

```python
finish_reason = response.status or "unknown"
if response.incomplete_details is not None:
    finish_reason = response.incomplete_details.reason or finish_reason
```

[#L77-L81](../app/providers/openai_provider.py#L77-L81)

Это поведение подтверждено живым запросом: при лимите в 20 токенов вернулось
`"finish_reason": "max_output_tokens"` — из `incomplete_details.reason`, а не из `status`.
Без этой ветки клиент получил бы `status` (что-то вроде `incomplete`) и не смог бы отличить
«не хватило лимита» от «сработал фильтр».

### Anthropic — Messages API

[app/providers/anthropic_provider.py](../app/providers/anthropic_provider.py)

Системная инструкция уходит отдельным полем `system` ([#L29-L50](../app/providers/anthropic_provider.py#L29-L50)),
ответ приходит списком блоков, из которого склеиваются только текстовые
([#L74-L80](../app/providers/anthropic_provider.py#L74-L80)). Особенность, которую легко пропустить:
`total_tokens` API не отдаёт, адаптер складывает сам
([#L82-L93](../app/providers/anthropic_provider.py#L82-L93)).

### Ollama — свой HTTP-протокол

[app/providers/ollama_provider.py](../app/providers/ollama_provider.py)

Единственный адаптер без SDK: обычный `POST /api/chat` через `httpx2`
([#L44-L55](../app/providers/ollama_provider.py#L44-L55)). Здесь нет типизированных исключений,
поэтому ошибки различаются по коду ответа: `>= 500` — поставщик недоступен, `>= 400` — отвергнут
запрос. Правило «5xx — временно, 4xx — навсегда» — простейшая эвристика, и она неточна:
у Ollama `429` тоже не бывает, а вот `400` из-за слишком длинного контекста вполне.

В теле запроса видны специфичные параметры, которых нет в общем контракте:
`stream: false`, `think: false`, `keep_alive: "5m"`, `options.num_predict`
([#L27-L42](../app/providers/ollama_provider.py#L27-L42)). Это иллюстрация «низшего общего
знаменателя»: шлюз держит модель загруженной 5 минут, потому что так дешевле, — и это знание
живёт только здесь.

### vLLM — OpenAI-совместимый

[app/providers/vllm_provider.py](../app/providers/vllm_provider.py)

Тот же SDK, но `chat.completions` вместо Responses API и с `extra_body` для отключения
«размышлений» ([#L28-L45](../app/providers/vllm_provider.py#L28-L45)). Два адаптера на одном SDK —
хороший пример того, что «совместимый с OpenAI» не означает «такой же»: разные эндпоинты, разные
структуры ответа, разные поля статистики (`prompt_tokens` против `input_tokens`).

Клиент vLLM создаётся с `max_retries=0`
([app/api/routes/generation.py](../app/api/routes/generation.py#L69-L79)) — иначе SDK незаметно
повторял бы запросы, и учёт попыток в маршрутизаторе перестал бы соответствовать реальности.

## Сравнение: что адаптер скрывает

| Что | OpenAI | Anthropic | Ollama | vLLM |
|---|---|---|---|---|
| Системная инструкция | склейка → `instructions` | склейка → `system` | в списке сообщений | в списке сообщений |
| Лимит вывода | `max_output_tokens` | `max_tokens` | `options.num_predict` | `max_tokens` |
| Входные токены | `usage.input_tokens` | `usage.input_tokens` | `prompt_eval_count` | `usage.prompt_tokens` |
| Всего токенов | готовое поле | сложение вручную | сложение вручную | готовое поле |
| Завершение | `status` + `incomplete_details` | `stop_reason` | `done_reason` | `finish_reason` |
| Текст ответа | `output_text` | склейка блоков `type == "text"` | `message.content` | `choices[0].message.content` |

Одна строка этой таблицы — одна ветка в коде. Всё это исчезает из приложения.

## Ошибки: перевод один раз

Каждый адаптер сводит свои исключения к пяти типам (`ProviderAuthenticationError`,
`ProviderRequestError`, `ProviderRateLimitError`, `ProviderUnavailableError`,
`InvalidProviderResponseError`). Пример для OpenAI
([#L53-L71](../app/providers/openai_provider.py#L53-L71)):

| Исключение SDK | Тип шлюза | `retryable` |
|---|---|---|
| `AuthenticationError`, `PermissionDeniedError` | `ProviderAuthenticationError` | нет |
| `RateLimitError` | `ProviderRateLimitError` | да |
| `BadRequestError`, `NotFoundError`, `UnprocessableEntityError` | `ProviderRequestError` | нет |
| `APIConnectionError`, `APITimeoutError`, `InternalServerError` | `ProviderUnavailableError` | да |

Порядок `except` важен: `APITimeoutError` наследуется от `APIConnectionError`, поэтому оба
перечислены явно, чтобы читателю не приходилось помнить иерархию SDK.

Второй блок обработки — про ответ, а не про запрос
([#L73-L95](../app/providers/openai_provider.py#L73-L95)). Пустой текст, отсутствующий `usage`,
неожидаемая структура — `InvalidProviderResponseError`. Это важное отличие: **поставщик ответил
200, но нарушил обещание**. Такое не лечится повтором, и повторять не нужно.

## Параметры, которых нет в контракте

В `GenerationRequest` есть только `model`, `messages`, `max_output_tokens`
([app/domain/models.py](../app/domain/models.py#L19-L24)). Следствия:

- нельзя задать температуру — vLLM жёстко ставит `temperature=0`
  ([#L39](../app/providers/vllm_provider.py#L39)), Ollama оставляет серверный дефолт;
- поведение невоспроизводимо между поставщиками: один и тот же запрос не означает одинаковое
  сэмплирование;
- зато оценка качества из [docs/08-evaluation.md](08-evaluation.md) сравнивает модели, а не настройки.

Осознанно ли это? Для учебного проекта — да: узкий контракт проще. В реальном шлюзе `temperature`
и `seed` почти наверняка нужны, и тогда стоит подумать не о «добавить поле», а о
типизированном наборе параметров с возможностью отбрасывать неподдерживаемые.

## Вопросы для самопроверки

1. Почему Ollama-адаптер не различает ошибку авторизации?
   <sub>Локальная Ollama не требует ключа: аутентифицироваться нечем, поэтому
   `ProviderAuthenticationError` некуда возникнуть. Отсюда и отсутствие этого типа в импортах
   файла.</sub>
2. адаптер vLLM вернул `200`, но `choices` пуст. Что произойдёт?
   <sub>`IndexError` в шаге разбора перехватывается и превращается в
   `InvalidProviderResponseError` ([#L66-L86](../app/providers/vllm_provider.py#L66-L86)) → `502`.</sub>
3. Клиент получил `503` от `/generate?provider=openai`. Стоит ли повторять запрос?
   <sub>`retryable: true` в теле ответа — да, имеет смысл, но только клиенту и с задержкой.
   Внутри шлюза повторов нет: `ModelGateway` ничего не повторяет.</sub>
4. Зачем в ответе `model`, если клиент сам её запросил?
   <sub>Потому что поставщик может вернуть другое имя (алиас, версия, дата). Оценка фиксирует
   `actual_model` отдельно от `requested_model` — см. [app/evaluation/runner.py](../app/evaluation/runner.py#L45-L61).
   Так ловится незаметная подмена модели.</sub>
