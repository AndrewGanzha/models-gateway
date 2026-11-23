from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = Field(min_length=1)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)
    max_output_tokens: int = Field(default=512, gt=0)


class Usage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class GenerationResult(BaseModel):
    provider: str
    model: str
    text: str
    usage: Usage
    finish_reason: str