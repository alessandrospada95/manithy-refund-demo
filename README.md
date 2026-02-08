# MANITHY — Refund Product Demo (Stakeholders + Developers)

A **stakeholders-ready** ChatGPT-style refund experience with **two lenses**:

- **Stakeholder lens**: chat + NRB cards + **V2-only** envelope.
- **Developer lens (gated)**: inline previews of **RB_INTERNAL / RB_PROOF** artifacts (no downloads), **Replay**, and **Override** (only when AU requires it).

This demo is intentionally **deterministic** for decisions: the LLM (optional) is **NRB-only** and can only help fill the request (never decide).

---

## Quick start (macOS / Linux)

```bash
cd MANITHY_REFUND_PRODUCT_FINAL

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

chmod +x run_web.sh

# (optional) enable Developer lens
export MANITHY_DEV_TOKEN="dev-secret"

# (optional) enable NRB-only LLM assistant
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4.1-mini"     # optional
export OPENAI_MAX_TOKENS="280"         # optional
export OPENAI_TEMPERATURE="0.2"        # optional

PORT=5050 ./run_web.sh
```

Open: http://localhost:5050

---

## What files get generated?

Each **Submit refund request** creates a unique directory:

```
out/<scenario>__<action_attempt_id>/
```

Inside you will find:

- `RB-01_CommitBoundaryEvent.json` *(RB_INTERNAL)*
- `RB-02_CommitCaptureRecord.json` *(RB_INTERNAL preview-only)*
- `RB-02_CommitCaptureRecord.bytes` *(RB_PROOF — never shown raw)*
- `RB-03_CommitCaptureRecord.hash.json` *(RB_PROOF)*
- `RB-05_EP_Verdict.json` *(RB_INTERNAL)*
- `RB-08_RingVector.json` *(RB_INTERNAL preview-only)*
- `RB-08_RingVector.bytes` *(RB_PROOF — never shown raw)*
- `RB-08_RingVector.hash.json` *(RB_PROOF)*
- `RB-10_AU_Verdict.json` *(RB_INTERNAL)*
- `RB-12_CaptureReceipt.json` *(RB_INTERNAL)*
- `EvidencePack.manifest.json` *(RB_PROOF)*
- `EvidencePack.bin` *(RB_PROOF — never shown raw)*
- `NRB_V2_Facts.json` *(V2 ONLY — the only servable surface)*
- `NRB_V2_Facts.hash` *(helper for demo)*

Replay / Override will also generate:

- `REPLAY-01_request.json`, `REPLAY-02_result.json`
- `RB-07_override_act.json`, `RB-08_override.hash.json` (when override is committed)

---

## Dev lens: how to see the artifacts

1. Run with `MANITHY_DEV_TOKEN` set
2. Open `/developer`
3. Paste the token into the sidebar field and click **Save**
4. Submit a refund request → artifacts appear under **Artifacts (inline)**

Binaries are shown as **size + sha256** only.

---

## Notes

- The LLM (if enabled) is **NRB-only** and cannot access RB artifacts or decide outcomes.
- Decision is computed deterministically at Submit time (EP/AU logic), and surfaced only via `NRB_V2_Facts.json`.
