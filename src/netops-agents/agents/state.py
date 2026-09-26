"""Shared LangGraph state for the investigation graph, and the structured diagnosis the LLM must return."""
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    root_cause: Literal["rf_impairment", "dhcp_storm", "interface_flap", "unknown"]
    action: Literal["escalate_field_tech", "dhcp_discard_clear", "interface_reset", "none"]
    evidence: list[str] = Field(description="Facts from the evidence, with their numbers, that support the root cause.")


class InvestigationState(TypedDict, total=False):
    anomaly_event: dict  # from detect/anomaly_detector.py
    evidence: dict  # from tools.gather_evidence
    diagnosis: dict  # Diagnosis.model_dump(), kept plain so checkpoints serialize cleanly
    action_result: str  # audit line, or why nothing ran
