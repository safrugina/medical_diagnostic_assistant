"""Anamnesis collection logic and stages."""

from enum import Enum
from typing import Dict, Any, Optional


class AnamnesisStage(Enum):
    START = 0
    CHIEF_COMPLAINTS = 1
    COMPLAINT_DETAILS = 2
    ASSOCIATED_SYMPTOMS = 3
    HPI = 4
    PAST_MEDICAL_HISTORY = 5
    MEDICATIONS = 6
    LIFESTYLE = 7
    REVIEW = 8
    COMPLETE = 9             # Anamnesis done → offer document analysis
    DOCUMENT_ANALYSIS = 10   # Scanning and analyzing documents
    FINISHED = 11            # Data collection done → auto-advance to diagnosis
    DIFFERENTIAL_DIAGNOSIS = 12  # Interactive differential diagnosis phase
    TEST_PRIORITIZATION = 13     # Prioritized investigation plan
    AWAITING_RESULTS = 14        # Waiting for new documents (no diagnosis ≥ 90%)
    FINAL_DIAGNOSIS = 15         # Final diagnosis reached (≥ 90%)


class AnamnesisManager:
    """Manages anamnesis collection process."""

    STAGE_DESCRIPTIONS = {
        AnamnesisStage.START: "Starting consultation",
        AnamnesisStage.CHIEF_COMPLAINTS: "Collecting chief complaints",
        AnamnesisStage.COMPLAINT_DETAILS: "Detailing chief complaints",
        AnamnesisStage.ASSOCIATED_SYMPTOMS: "Collecting associated symptoms",
        AnamnesisStage.HPI: "History of present illness",
        AnamnesisStage.PAST_MEDICAL_HISTORY: "Past medical history",
        AnamnesisStage.MEDICATIONS: "Current medications",
        AnamnesisStage.LIFESTYLE: "Lifestyle and habits",
        AnamnesisStage.REVIEW: "Review and clarification",
        AnamnesisStage.COMPLETE: "Anamnesis complete",
        AnamnesisStage.DOCUMENT_ANALYSIS: "Analyzing documents",
        AnamnesisStage.FINISHED: "Ready for diagnosis",
        AnamnesisStage.DIFFERENTIAL_DIAGNOSIS: "Differential diagnosis",
        AnamnesisStage.TEST_PRIORITIZATION: "Investigation plan",
        AnamnesisStage.AWAITING_RESULTS: "Awaiting new results",
        AnamnesisStage.FINAL_DIAGNOSIS: "Final diagnosis",
    }

    def __init__(self):
        self.current_stage = AnamnesisStage.START
        self.patient_data: Dict[str, Any] = {}

    def get_current_stage(self) -> AnamnesisStage:
        return self.current_stage

    def advance_stage(self) -> None:
        if self.current_stage.value < AnamnesisStage.FINAL_DIAGNOSIS.value:
            self.current_stage = AnamnesisStage(self.current_stage.value + 1)

    def set_stage(self, stage: AnamnesisStage) -> None:
        self.current_stage = stage

    def reset_anamnesis(self) -> None:
        self.current_stage = AnamnesisStage.START
        self.patient_data = {}

    def get_stage_description(self) -> str:
        return self.STAGE_DESCRIPTIONS.get(self.current_stage, "Unknown stage")

    def get_progress(self) -> float:
        """Progress 0–100% based on anamnesis stages only (up to COMPLETE)."""
        anamnesis_end = AnamnesisStage.COMPLETE.value
        current = min(self.current_stage.value, anamnesis_end)
        return (current / anamnesis_end) * 100

    def get_stage_number(self) -> int:
        return self.current_stage.value

    def is_anamnesis_complete(self) -> bool:
        return self.current_stage.value >= AnamnesisStage.COMPLETE.value

    def is_finished(self) -> bool:
        return self.current_stage == AnamnesisStage.FINISHED
