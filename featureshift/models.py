"""Validated, explicit contracts at user and execution boundaries."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_order: bool = True
    row_order: bool = True
    compare_index: bool = True
    compare_dtypes: bool = True
    nulls: Literal["strict", "equivalent"] = "strict"
    rtol: float = Field(default=1e-7, ge=0, le=1)
    atol: float = Field(default=1e-9, ge=0, le=1)
    expected_columns: list[str] | None = None
    expected_row_count: int | None = Field(default=None, ge=0)
    expected_dtypes: dict[str, str] = Field(default_factory=dict)
    non_null: list[str] = Field(default_factory=list)
    intentional: list[str] = Field(default_factory=list)
    rationale: str | None = None


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    repeats: int = Field(default=2, ge=2, le=5)
    timeout_s: float = Field(default=8, ge=0.05, le=30)
    contract: Contract | None = None


class AcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    description: str
    category: str
    source: str
    fixture: str
    entrypoint: str = "transform"
    contract: Contract = Field(default_factory=Contract)
    expected: str
    family: str
    split: Literal["demo", "development", "evaluation"]
    provenance: dict
    evidence_query: str | None = None
    evidence_versions: tuple[str, str] | None = None
    cutoff: str | None = None
    fault: Literal["environment", "probe_timeout", "probe_syntax"] | None = None

