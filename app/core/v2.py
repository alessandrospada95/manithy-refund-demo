def build_v2(action_attempt_id: str, policy_bundle_id: str,
             ep_status: str, au_status: str,
             final_disposition: str,
             facts: dict | None,
             override_present: bool,
             evidence_pack_ref: str,
             capture_receipt_ref: str) -> dict:
    return {
        "v2_version": "manithy.v2.facts_envelope.v1",
        "action_attempt_id": action_attempt_id,
        "action_type": "REFUND_REQUEST",
        "ep_status": ep_status,
        "au_status": au_status,
        "final_disposition": final_disposition,
        "facts": facts if facts is not None else None,
        "override_present": override_present,
        "pins": {"policy_bundle_id": policy_bundle_id},
        "evidence_pack_ref": evidence_pack_ref,
        "capture_receipt_ref": capture_receipt_ref,
        "authority": {
            "override_allowed": (final_disposition != "APPROVED"),
            "override_required": (final_disposition != "APPROVED"),
            "override_applied": override_present
        }
    }
