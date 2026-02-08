import uuid
from datetime import datetime, date
from pathlib import Path
import json

from app.core.canonical import canonical_json_bytes
from app.core.hashing import sha256_hex
from app.core.buckets import bucket_amount_minor, bucket_age_days

def new_action_attempt_id() -> str:
    return "att_" + uuid.uuid4().hex[:12]

def build_refund_ccr(action_attempt_id: str, policy_bundle_id: str, order_ref: str, customer_ref: str,
                     total_minor: int, currency: str, order_age_days: int,
                     delivery_status: str, reason_code: str, requested_resolution: str, claim_flags: list[str]) -> dict:
    return {
        "ccr_version": "ccr.refund.v1",
        "action_type": "REFUND_REQUEST",
        "action_attempt_id": action_attempt_id,
        "policy_bundle_id": policy_bundle_id,
        "customer_ref": customer_ref,
        "order_ref": order_ref,
        "order_amount_bucket": bucket_amount_minor(total_minor),
        "order_age_days_bucket": bucket_age_days(order_age_days),
        "delivery_status": delivery_status,
        "refund_reason_code": reason_code,
        "requested_resolution": requested_resolution,
        "claim_flags": sorted(list(set(claim_flags))),
    }

def write_commit_artifacts(out_dir: Path, ccr: dict) -> tuple[bytes, str]:
    # RB-02 CCR canonical bytes
    canon = canonical_json_bytes(ccr)
    (out_dir / "RB-02_CommitCaptureRecord.bytes").write_bytes(canon)

    # RB-03 CCR hash
    ccr_hash = sha256_hex(canon)
    (out_dir / "RB-03_CommitCaptureRecord.hash.json").write_text(json.dumps({"algo":"sha256","ccr_hash":"ccrh_"+ccr_hash}, indent=2))

    # RB-02b view (demo-only)
    (out_dir / "RB-02_CommitCaptureRecord.json").write_text(json.dumps(ccr, indent=2, sort_keys=True))
    return canon, "ccrh_" + ccr_hash
