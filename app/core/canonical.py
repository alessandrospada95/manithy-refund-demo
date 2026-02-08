import json

def canonical_json_bytes(obj: dict) -> bytes:
    # UTF-8, sorted keys, no whitespace: deterministic canonical bytes
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
