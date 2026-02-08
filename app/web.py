import os
import json
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any, List
from flask import Flask, request, jsonify, render_template, abort

from app.producer.producer_sdk import (
    new_action_attempt_id,
    build_refund_ccr,
    write_commit_artifacts,
)

from app.core.ep_au import compute_ep, compute_au
from app.core.hashing import sha256_hex
from app.core.rings import ringvector_hash
from app.core.v2 import build_v2
from app.core.evidence_pack import write_evidence_pack

from app.replay.replay import replay_attempt

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BASE_DIR / "out"
DATA_DIR = BASE_DIR / "nrb_knowledge" / "data"
CONTRACTS_DIR = BASE_DIR / "contracts"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def _read_csv_indexed(path: Path, key: str) -> Dict[str, Dict[str, str]]:
    import csv
    out: Dict[str, Dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if key in row and row[key]:
                out[row[key]] = row
    return out

def _is_dev_request(req) -> bool:
    token = req.headers.get("X-Manithy-Dev-Token", "")
    expected = os.environ.get("MANITHY_DEV_TOKEN", "")
    return bool(expected) and token == expected

def _attempt_dir_for(attempt_id: str) -> Optional[Path]:
    return next((x for x in OUT_DIR.glob(f"*__{attempt_id}") if x.is_dir()), None)

def _stable_ref(prefix: str, obj: Dict[str, Any]) -> str:
    b = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return prefix + sha256_hex(b)

def _llm_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())

def _redact(text: str) -> str:
    # NRB safety: avoid echoing "RB-" / hashes / evidence refs as conversational content.
    banned = ["RB-", "ccrh_", "eph_", "rcpt_", "EvidencePack", "ringvector", "hash"]
    lowered = text.lower()
    if any(b.lower() in lowered for b in banned):
        return "I can help with the refund form. Developer artifacts are available in the Developer sidebar after authorization."
    return text

def _call_openai_responses(user_message: str, state: Dict[str, Any]) -> str:
    """
    NRB-only assistant. It must not decide, must not mention RB artifacts, and must only guide
    the user to complete the form fields and press Submit.
    Uses the Responses API via HTTPS (no client-side key).
    """
    import urllib.request

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    # Minimal NRB context (no RB/V2/evidence)
    order_id = state.get("order_id")
    reason_code = state.get("reason_code")
    requested_resolution = state.get("requested_resolution")

    system = (
        "You are an NRB-only refund intake assistant for a product demo.\n"
        "You are NOT an authority and you do NOT decide outcomes.\n"
        "You must NEVER:\n"
        "- determine approval/denial\n"
        "- explain authority/policy logic\n"
        "- mention or reference RB artifacts, hashes, evidence packs, replay, rings\n"
        "- request or suggest override\n"
        "- output code, logs, or file paths\n\n"
        "Your ONLY job is to help the user complete these fields:\n"
        "1) order_id (format ORD-10001)\n"
        "2) reason (Damaged / Wrong item / Late delivery / Changed mind)\n"
        "3) requested_resolution (Refund / Exchange)\n\n"
        "When all fields are present, tell the user: \"Click Submit refund request\".\n"
        "Keep responses short, ChatGPT-style, and avoid repetition.\n"
    )

    developer = (
        "Return plain text only. No JSON. No HTML.\n"
        "If user asks for decision/explanation, answer that outcomes are determined only after Submit and shown in V2.\n"
        "If user asks about developer artifacts, say they are visible in Developer sidebar after authorization.\n"
        f"Current form state:\n"
        f"- order_id: {order_id or 'MISSING'}\n"
        f"- reason: {reason_code or 'MISSING'}\n"
        f"- resolution: {requested_resolution or 'MISSING'}\n"
    )

    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {"role": "system", "content": system},
            {"role": "developer", "content": developer},
            {"role": "user", "content": user_message[:2000]},
        ],
        "max_output_tokens": int(os.environ.get("OPENAI_MAX_TOKENS", "280")),
        "temperature": float(os.environ.get("OPENAI_TEMPERATURE", "0.2")),
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Pull the primary text output if present
    txt = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                txt += c.get("text", "")
    return txt.strip() or "Share your order number (e.g., ORD-10001) and I’ll guide the refund request."

# -----------------------------------------------------------------------------
# Load pinned contracts (repo-time)
# -----------------------------------------------------------------------------

RULES = _load_json(CONTRACTS_DIR / "coverage_rules_v1.json")
DOMAIN_REFUND = _load_json(CONTRACTS_DIR / "domain_refund_v1.json")

# -----------------------------------------------------------------------------
# Load NRB dataset (knowledge realism)
# -----------------------------------------------------------------------------

ORDERS = _read_csv_indexed(DATA_DIR / "orders.csv", "order_id")
CUSTOMERS = _read_csv_indexed(DATA_DIR / "customers.csv", "customer_id")
SHIP = _read_csv_indexed(DATA_DIR / "shipping_events.csv", "order_id")
POLICY = _read_csv_indexed(DATA_DIR / "returns_policy.csv", "rule_id")

# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

# -----------------------------------------------------------------------------
# Pages (Mode selector + two lenses)
# -----------------------------------------------------------------------------

@app.get("/")
def home():
    return render_template("home.html")

@app.get("/stakeholder")
def stakeholder():
    return render_template("app.html", mode="stakeholder")

@app.get("/developer")
def developer():
    return render_template("app.html", mode="developer")

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

@app.get("/api/config")
def api_config():
    # Do NOT disclose tokens; only capabilities.
    return jsonify({
        "dev_enabled": bool(os.environ.get("MANITHY_DEV_TOKEN", "")),
        "llm_enabled": _llm_enabled(),
        "llm_model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini") if _llm_enabled() else None
    })

@app.post("/api/chat")
def api_chat():
    """
    NRB-only deterministic assistant (no LLM).
    Must NOT start RB pipeline.
    """
    data = request.get_json(force=True) or {}
    msg = (data.get("message") or "").strip()
    state = data.get("state") or {}

    lower = msg.lower()
    next_state = dict(state)
    reply = ""

    # Minimal intent parsing (NRB UX only)
    if "ord-" in lower:
        import re
        m = re.search(r"(ord-\d+)", lower, re.I)
        if not m:
            return jsonify({"reply_markdown": "Please share your order number (e.g., **ORD-10001**).", "state": next_state})

        oid = m.group(1).upper()
        if oid not in ORDERS:
            reply = "I couldn't find that order number in the demo dataset. Try **ORD-10001**, **ORD-10002**, or **ORD-10003**."
            return jsonify({"reply_markdown": reply, "state": next_state})

        next_state["order_id"] = oid
        o = ORDERS[oid]
        ship_events = SHIP.get(oid, {}).get("events", "")
        pol = POLICY.get("R1", {})

        pay = o.get("payment_method") or o.get("payment") or o.get("payment_type") or o.get("payment_provider") or "—"

        reply = (
            f"<div class=\"nrbCards\">"
            f"<div class=\"nrbCard\"><div class=\"nrbTitle\">Order summary</div>"
            f"<div class=\"nrbRow\"><span>Order</span><strong>{oid}</strong></div>"
            f"<div class=\"nrbRow\"><span>Total</span><strong>{int(o['total_minor'])/100:.2f} {o['currency']}</strong></div>"
            f"<div class=\"nrbRow\"><span>Ordered</span><strong>{o['order_date']}</strong></div>"
            f"<div class=\"nrbRow\"><span>Delivered</span><strong>{o['delivery_date']}</strong></div>"
            f"<div class=\"nrbRow\"><span>Payment</span><strong>{pay}</strong></div>"
            f"</div>"
            f"<div class=\"nrbCard\"><div class=\"nrbTitle\">Shipping timeline</div>"
            f"<div class=\"nrbBody\">{ship_events.replace('>', ' → ')}</div></div>"
            f"<div class=\"nrbCard\"><div class=\"nrbTitle\">Policy (NRB)</div>"
            f"<div class=\"nrbBody\">{pol.get('conditions', 'Refund policy available.')}</div>"
            f"<div class=\"nrbSmall\">Exceptions: {pol.get('exceptions', '—')}</div></div>"
            f"</div>"
            f"<div style=\"margin-top:10px\">What’s the reason for the refund? (Damaged / Wrong item / Late delivery / Changed mind)</div>"
        )
        return jsonify({"reply_markdown": reply, "state": next_state})

    if "damaged" in lower:
        next_state["reason_code"] = "DAMAGED"
        reply = "Got it — marked as **Damaged**. Do you want a **refund** or an **exchange**?"
    elif "wrong" in lower:
        next_state["reason_code"] = "WRONG_ITEM"
        reply = "Okay — marked as **Wrong item**. Do you want a **refund** or an **exchange**?"
    elif "late" in lower or "delay" in lower:
        next_state["reason_code"] = "LATE_DELIVERY"
        reply = "Understood — marked as **Late delivery**. Do you want a **refund** or an **exchange**?"
    elif "changed" in lower or "mind" in lower:
        next_state["reason_code"] = "CHANGED_MIND"
        reply = "Noted — marked as **Changed mind**. Do you want a **refund** or an **exchange**?"
    elif "refund" in lower:
        next_state["requested_resolution"] = "REFUND"
        reply = "Thanks. Please confirm: **Submit refund request** for this order?"
    elif "exchange" in lower:
        next_state["requested_resolution"] = "EXCHANGE"
        reply = "Thanks. Please confirm: **Submit refund request** for this order?"
    elif "submit" in lower and "refund" in lower:
        reply = "Click the **Submit refund request** button below to formally submit the request."
    else:
        reply = "Share your **order number** (e.g., ORD-10001) and I’ll guide the refund request."

    return jsonify({"reply_markdown": reply, "state": next_state})

@app.post("/api/nrb/llm_chat")
def api_llm_chat():
    """
    NRB-only LLM assistant. Must not start RB pipeline; must not access RB artifacts.
    """
    if not _llm_enabled():
        return jsonify({"error": "LLM_DISABLED"}), 400

    data = request.get_json(force=True) or {}
    msg = (data.get("message") or "").strip()
    state = data.get("state") or {}

    # Very small deterministic state updates (keep LLM out of parsing)
    lower = msg.lower()
    import re
    m = re.search(r"(ord-\d+)", lower, re.I)
    next_state = dict(state)
    if m:
        next_state["order_id"] = m.group(1).upper()
    if "damaged" in lower:
        next_state["reason_code"] = "DAMAGED"
    elif "wrong" in lower:
        next_state["reason_code"] = "WRONG_ITEM"
    elif "late" in lower or "delay" in lower:
        next_state["reason_code"] = "LATE_DELIVERY"
    elif "changed" in lower or "mind" in lower:
        next_state["reason_code"] = "CHANGED_MIND"
    if "refund" in lower:
        next_state["requested_resolution"] = "REFUND"
    elif "exchange" in lower:
        next_state["requested_resolution"] = "EXCHANGE"

    try:
        txt = _call_openai_responses(msg, next_state)
    except Exception:
        # Fail-closed: do not guess; fall back to deterministic helper.
        txt = "Share your order number (e.g., ORD-10001) and I’ll guide the refund request."

    txt = _redact(txt)
    return jsonify({"reply_markdown": txt, "state": next_state})

@app.post("/api/refund/submit")
def submit_refund():
    """
    Explicit COMMIT boundary trigger.
    Generates RB artifacts + EvidencePack + V2 ONLY.
    """
    data = request.get_json(force=True) or {}

    order_id = (data.get("order_id") or "").strip().upper()
    reason_code = (data.get("reason_code") or "").strip().upper()
    requested_resolution = (data.get("requested_resolution") or "REFUND").strip().upper()
    claim_flags = data.get("claim_flags") or []
    scenario = (data.get("scenario") or "refund").strip().lower()

    if order_id not in ORDERS:
        return jsonify({"error": "UNKNOWN_ORDER"}), 400
    if reason_code not in DOMAIN_REFUND.get("reason_codes", []):
        return jsonify({"error": "INVALID_REASON"}), 400
    if requested_resolution not in ["REFUND", "EXCHANGE"]:
        return jsonify({"error": "INVALID_RESOLUTION"}), 400

    order = ORDERS[order_id]
    customer_id = order["customer_id"]
    currency = order["currency"]
    total_minor = int(order["total_minor"])
    order_date = date.fromisoformat(order["order_date"])
    age_days = (date.today() - order_date).days

    ship_events = SHIP.get(order_id, {}).get("events", "")
    delivery_status = "DELIVERED" if "DELIVERED" in ship_events.upper() else "UNKNOWN"

    policy_bundle_id = RULES["policy_bundle_id"]

    attempt_id = new_action_attempt_id()
    attempt_dir = OUT_DIR / f"{scenario}__{attempt_id}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    # RB-01 CommitBoundaryEvent (RB_INTERNAL)
    (attempt_dir / "RB-01_CommitBoundaryEvent.json").write_text(
        json.dumps(
            {
                "action_attempt_id": attempt_id,
                "commit_point_id": "refund_submit_v1",
                "action_type": "REFUND_REQUEST",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # CCR build (minimal, bucketed)
    ccr = build_refund_ccr(
        action_attempt_id=attempt_id,
        policy_bundle_id=policy_bundle_id,
        order_ref=order_id,
        customer_ref=customer_id,
        total_minor=total_minor,
        currency=currency,
        order_age_days=age_days,
        delivery_status=delivery_status,
        reason_code=reason_code,
        requested_resolution=requested_resolution,
        claim_flags=claim_flags,
    )

    # RB-02 bytes + RB-03 hash + RB-02 preview JSON (writer decides; must be preview-only)
    _ccr_canon_bytes, ccr_hash = write_commit_artifacts(attempt_dir, ccr)

    # EP + AU (deterministic)
    ep = compute_ep(reason_code, RULES)
    within_window = age_days <= ep.refund_window_days
    au = compute_au(ep, within_window)

    (attempt_dir / "RB-05_EP_Verdict.json").write_text(
        json.dumps(
            {
                "ep_status": ep.status,
                "reasons": getattr(ep, "reasons", []),
                "refund_window_days": ep.refund_window_days,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (attempt_dir / "RB-10_AU_Verdict.json").write_text(
        json.dumps(
            {
                "au_status": au.status,
                "reasons": getattr(au, "reasons", []),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Rings (RB_PROOF): deterministic bytes + hashes; never served raw
    ring_h = ringvector_hash(ccr_hash.replace("ccrh_", ""), policy_bundle_id)

    ring_bytes = (f"rh_input:{ccr_hash}|{policy_bundle_id}".encode("utf-8"))
    (attempt_dir / "RB-08_RingVector.bytes").write_bytes(ring_bytes)

    ring_bytes_hash = "rh_" + sha256_hex(ring_bytes)
    (attempt_dir / "RB-08_RingVector.hash.json").write_text(
        json.dumps(
            {"algo": "sha256", "ring_hash": "rh_" + ring_h, "ring_bytes_hash": ring_bytes_hash},
            indent=2,
        ),
        encoding="utf-8",
    )

    # Preview-only view (RB_INTERNAL)
    (attempt_dir / "RB-08_RingVector.json").write_text(
        json.dumps({"ringvector": "<demo-preview-only>", "ring_hash": "rh_" + ring_h}, indent=2),
        encoding="utf-8",
    )

    # RB-12 CaptureReceipt (RB_INTERNAL, minimal)
    receipt = {
        "attempt_id": attempt_id,
        "commit_point_id": "refund_submit_v1",
        "ccr_hash": ccr_hash,
        "ep_status": ep.status,
        "au_status": au.status,
    }
    (attempt_dir / "RB-12_CaptureReceipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    capture_receipt_ref = _stable_ref("rcpt_", receipt)

    # Evidence Pack V4 (RB_PROOF) — always present
    eph, mh = write_evidence_pack(
        attempt_dir,
        policy_bundle_id,
        [
            "RB-02_CommitCaptureRecord.bytes",
            "RB-03_CommitCaptureRecord.hash.json",
            "RB-08_RingVector.bytes",
            "RB-08_RingVector.hash.json",
            "RB-05_EP_Verdict.json",
            "RB-10_AU_Verdict.json",
        ],
    )

    # V2 ONLY (servable surface)
    facts = None
    if ep.status == "COVERED":
        facts = {
            "order_ref": order_id,
            "amount_minor": total_minor,
            "currency": currency,
            "order_age_days": age_days,
        }

    if au.status == "PERMIT":
        final_disposition = "APPROVED"
    elif au.status == "BLOCK":
        final_disposition = "DENIED"
    else:
        final_disposition = "MANUAL_REVIEW"

    v2 = build_v2(
        action_attempt_id=attempt_id,
        policy_bundle_id=policy_bundle_id,
        ep_status=ep.status,
        au_status=au.status,
        final_disposition=final_disposition,
        facts=facts,
        override_present=False,
        evidence_pack_ref=eph,
        capture_receipt_ref=capture_receipt_ref,
    )

    (attempt_dir / "NRB_V2_Facts.json").write_text(json.dumps(v2, indent=2), encoding="utf-8")
    v2_bytes = json.dumps(v2, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (attempt_dir / "NRB_V2_Facts.hash").write_text("v2h_" + sha256_hex(v2_bytes), encoding="utf-8")

    return jsonify({"action_attempt_id": attempt_id})

@app.get("/api/v2/<attempt_id>")
def get_v2(attempt_id: str):
    d = _attempt_dir_for(attempt_id)
    if d is None:
        abort(404)
    p = d / "NRB_V2_Facts.json"
    if not p.exists():
        abort(404)
    return jsonify(json.loads(p.read_text(encoding="utf-8")))

# -----------------------------------------------------------------------------
# Dev API (gated, lens-only, no downloads)
# -----------------------------------------------------------------------------

@app.get("/api/dev/artifacts/<attempt_id>")
def dev_artifacts(attempt_id: str):
    if not _is_dev_request(request):
        abort(404)

    d = _attempt_dir_for(attempt_id)
    if d is None:
        abort(404)

    allowed_json = [
        "RB-01_CommitBoundaryEvent.json",
        "RB-02_CommitCaptureRecord.json",
        "RB-03_CommitCaptureRecord.hash.json",
        "RB-05_EP_Verdict.json",
        "RB-08_RingVector.json",
        "RB-08_RingVector.hash.json",
        "RB-10_AU_Verdict.json",
        "RB-12_CaptureReceipt.json",
        "EvidencePack.manifest.json",
        "REPLAY-01_request.json",
        "REPLAY-02_result.json",
        "RB-07_override_act.json",
        "RB-08_override.hash.json",
        "NRB_V2_Facts.hash",
    ]

    binary_meta = [
        "RB-02_CommitCaptureRecord.bytes",
        "RB-08_RingVector.bytes",
        "EvidencePack.bin",
    ]

    out: List[Dict[str, Any]] = []

    for fn in allowed_json:
        p = d / fn
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > 8000:
                content = content[:8000] + "\n...<truncated>..."
            out.append({"name": fn, "kind": "json", "content": content})

    for fn in binary_meta:
        p = d / fn
        if p.exists():
            b = p.read_bytes()
            out.append({"name": fn, "kind": "bin_meta", "size_bytes": len(b), "sha256": "h_" + sha256_hex(b)})

    return jsonify({"attempt_id": attempt_id, "artifacts": out})

@app.post("/api/dev/replay/<attempt_id>")
def dev_replay(attempt_id: str):
    if not _is_dev_request(request):
        abort(404)

    d = _attempt_dir_for(attempt_id)
    if d is None:
        abort(404)

    res = replay_attempt(d)
    (d / "REPLAY-01_request.json").write_text(json.dumps({"attempt_id": attempt_id}, indent=2), encoding="utf-8")
    (d / "REPLAY-02_result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return jsonify(res)

@app.post("/api/dev/override/<attempt_id>")
def dev_override(attempt_id: str):
    if not _is_dev_request(request):
        abort(404)

    d = _attempt_dir_for(attempt_id)
    if d is None:
        abort(404)

    v2_path = d / "NRB_V2_Facts.json"
    if not v2_path.exists():
        abort(400)

    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    override_required = bool(v2.get("authority", {}).get("override_required", False))
    if not override_required:
        return jsonify({"error": "OVERRIDE_NOT_REQUIRED"}), 400

    data = request.get_json(force=True) or {}
    operator_id = (data.get("operator_id") or "").strip()
    decision = (data.get("decision") or "").strip().upper()
    reason_code = (data.get("reason_code") or "").strip().upper()

    if not operator_id or decision not in ["APPROVE", "DENY"] or reason_code not in ["POLICY_EXCEPTION", "CUSTOMER_CARE", "FRAUD_REVIEW", "OTHER"]:
        return jsonify({"error": "INVALID_OVERRIDE"}), 400

    override_act = {"operator_id": operator_id, "decision": decision, "reason_code": reason_code}

    act_bytes = json.dumps(override_act, sort_keys=True, separators=(",", ":")).encode("utf-8")
    oh = "oh_" + sha256_hex(act_bytes)

    (d / "RB-07_override_act.json").write_text(json.dumps(override_act, indent=2), encoding="utf-8")
    (d / "RB-08_override.hash.json").write_text(json.dumps({"algo": "sha256", "override_hash": oh}, indent=2), encoding="utf-8")

    policy_bundle_id = RULES["policy_bundle_id"]
    eph, _mh = write_evidence_pack(
        d,
        policy_bundle_id,
        [
            "RB-02_CommitCaptureRecord.bytes",
            "RB-03_CommitCaptureRecord.hash.json",
            "RB-08_RingVector.bytes",
            "RB-08_RingVector.hash.json",
            "RB-05_EP_Verdict.json",
            "RB-10_AU_Verdict.json",
            "RB-07_override_act.json",
            "RB-08_override.hash.json",
        ],
    )

    # Update V2 (servable-only, minimal)
    v2["final_disposition"] = "APPROVED" if decision == "APPROVE" else "DENIED"
    v2["override_present"] = True
    v2.setdefault("authority", {})
    v2["authority"]["override_applied"] = True
    v2["evidence_pack_ref"] = eph

    v2_path.write_text(json.dumps(v2, indent=2), encoding="utf-8")
    v2_bytes = json.dumps(v2, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (d / "NRB_V2_Facts.hash").write_text("v2h_" + sha256_hex(v2_bytes), encoding="utf-8")

    return jsonify({"status": "OK", "action_attempt_id": attempt_id})

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5050")))
    args = parser.parse_args()
    app.run(host="0.0.0.0", port=args.port, debug=False)

if __name__ == "__main__":
    main()
