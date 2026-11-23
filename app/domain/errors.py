class GatewayError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderAuthenticationError(GatewayError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Поставщик {provider} отклонил ключ или запретил доступ",
            retryable=False,
        )


class ProviderRequestError(GatewayError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Поставщик {provider} отклонил параметры запроса",
            retryable=False,
        )


class ProviderRateLimitError(GatewayError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Поставщик {provider} ограничил частоту запросов",
            retryable=True,
        )


class ProviderUnavailableError(GatewayError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Поставщик {provider} временно недоступен",
            retryable=True,
        )


class InvalidProviderResponseError(GatewayError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Поставщик {provider} вернул неожиданный ответ",
            retryable=False,
        )
        

class UnsupportedModelError(GatewayError):
    def __init__(
        self,
        provider: str,
        requested_model: str,
        expected_model: str,
    ) -> None:
        super().__init__(
            (
                f"Модель {requested_model} не настроена для поставщика "
                f"{provider}. Ожидается {expected_model}"
            ),
            retryable=False,
        )


class RoutingConfigurationError(GatewayError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)