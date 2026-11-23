from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CapabilityState(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    LIMITED = "limited"
    UNKNOWN = "unknown"


class CapabilityInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    declared: bool | None = None
    verified: CapabilityState = CapabilityState.UNKNOWN
    note: str | None = None


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    text_generation: CapabilityInfo
    structured_output: CapabilityInfo = Field(
        default_factory=CapabilityInfo
    )
    tools: CapabilityInfo = Field(default_factory=CapabilityInfo)
    streaming: CapabilityInfo = Field(default_factory=CapabilityInfo)