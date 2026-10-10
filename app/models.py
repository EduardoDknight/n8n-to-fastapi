from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["hot", "warm", "cold"]


class Lead(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    company: str | None = Field(default=None, max_length=160)
    budget: float | None = Field(default=None, ge=0)
    message: str = Field(default="", max_length=5000)


class EnrichedLead(Lead):
    domain: str
    company_size: str


class Classification(BaseModel):
    tier: Tier
    reason: str
    source: Literal["llm", "rules"]


class LeadResult(BaseModel):
    lead_id: str
    tier: Tier
    classifier: str
    routed_to: list[str]
    duplicate: bool = False
