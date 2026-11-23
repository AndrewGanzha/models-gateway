from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import GenerationResult, Message


class RoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    candidates: tuple[str, ...] = Field(min_length=1)
    max_attempts: int = Field(gt=0)


class RoutingState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output_started: bool = False
    external_action_completed: bool = False

    @property
    def can_switch(self) -> bool:
        return not (
            self.output_started
            or self.external_action_completed
        )


class RoutedGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[Message] = Field(min_length=1)
    max_output_tokens: int = Field(default=512, gt=0)


class RoutingAttempt(BaseModel):
    provider: str
    status: Literal["completed", "failed"]
    error: str | None = None


class RoutedGenerationResult(BaseModel):
    route_version: str
    selected_provider: str
    attempts: list[RoutingAttempt]
    result: GenerationResult