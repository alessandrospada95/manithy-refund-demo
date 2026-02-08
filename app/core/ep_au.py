from dataclasses import dataclass
from .buckets import bucket_eta_days

@dataclass(frozen=True)
class EPVerdict:
    status: str  # COVERED | UNCOVERED
    refund_window_days: int

@dataclass(frozen=True)
class AUVerdict:
    status: str  # PERMIT | BLOCK | REQUIRE_OVERRIDE

def compute_ep(reason_code: str, rules: dict) -> EPVerdict:
    if reason_code in rules["covered_reasons"]:
        return EPVerdict(status="COVERED", refund_window_days=int(rules["refund_window_days"]))
    return EPVerdict(status="UNCOVERED", refund_window_days=int(rules["refund_window_days"]))

def compute_au(ep: EPVerdict, within_window: bool) -> AUVerdict:
    if ep.status == "UNCOVERED":
        return AUVerdict(status="REQUIRE_OVERRIDE")
    return AUVerdict(status="PERMIT" if within_window else "BLOCK")

def v2_timeline_eta(au: AUVerdict) -> str:
    # Demo-only: deterministic, business-friendly buckets
    if au.status == "PERMIT":
        return bucket_eta_days(5)
    if au.status == "REQUIRE_OVERRIDE":
        return bucket_eta_days(10)
    return "UNKNOWN"
