import os
from typing import Dict, Any, Optional

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


SYSTEM_NRBL_ONLY = """You are an NRB-only UX assistant for a refund demo.

NON-NEGOTIABLE RULES:
- You do NOT decide refunds. You do NOT approve/deny/manual-review. You do NOT predict eligibility.
- You do NOT mention RB artifacts, hashes, evidence packs, rings, AU/EP logic, or internal pipeline details.
- You ONLY help the user navigate the flow: collect order id, reason, resolution, and explain next steps.
- You may restate ONLY NRB-visible fields that the UI shows (order summary, shipping timeline, policy snippet).
- If asked to decide, respond: "I can guide you through submitting the request. The decision is computed deterministically on Submit."
Return concise plain text (or simple HTML snippets compatible with the UI).
"""


def nrb_llm_reply(
    user_message: str,
    state: Dict[str, Any],
    nrb_context: Dict[str, Any],
    model: Optional[str] = None,
) -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or OpenAI is None:
        return None

    client = OpenAI(api_key=api_key)
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    order = nrb_context.get("order") or {}
    policy = nrb_context.get("policy") or {}
    shipping = nrb_context.get("shipping") or ""

    # NRB-only context (no RB, no hashes, no files, no out/)
    context_text = (
        "NRB context (user-visible only):\n"
        f"- order_id: {order.get('order_id','')}\n"
        f"- currency: {order.get('currency','')}\n"
        f"- total_minor: {order.get('total_minor','')}\n"
        f"- order_date: {order.get('order_date','')}\n"
        f"- delivery_date: {order.get('delivery_date','')}\n"
        f"- shipping_timeline: {shipping}\n"
        f"- policy_snippet: {policy.get('conditions','')}\n"
        f"- policy_exceptions: {policy.get('exceptions','')}\n"
        f"- current_state_keys: {list(state.keys())}\n"
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_NRBL_ONLY},
            {"role": "user", "content": context_text},
            {"role": "user", "content": user_message},
        ],
    )

    txt = (resp.output_text or "").strip()
    return txt or None
