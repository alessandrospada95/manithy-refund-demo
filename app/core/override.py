from dataclasses import dataclass

@dataclass(frozen=True)
class OverrideAct:
    operator_id: str
    decision: str  # APPROVE | DENY
    reason_code: str  # CLOSED SET (demo)
