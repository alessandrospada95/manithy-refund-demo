import json
from pathlib import Path
from app.core.hashing import sha256_hex
from app.core.evidence_pack import _read_bytes

MISMATCH = {
    "OK": "OK",
    "MISSING_FILE": "MISSING_FILE",
    "HASH_MISMATCH": "HASH_MISMATCH",
    "MANIFEST_HASH_MISMATCH": "MANIFEST_HASH_MISMATCH",
    "PACK_HASH_MISMATCH": "PACK_HASH_MISMATCH",
}

def replay_attempt(out_dir: Path) -> dict:
    # Deterministic replay: verify manifest hashes, then verify pack hash matches.
    mpath = out_dir / "EvidencePack.manifest.json"
    ppath = out_dir / "EvidencePack.bin"
    if not mpath.exists() or not ppath.exists():
        return {"status":"FAIL", "code":MISMATCH["MISSING_FILE"]}

    manifest_bytes = _read_bytes(mpath)
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    manifest_hash = sha256_hex(manifest_bytes)

    # verify file hashes
    for f in manifest.get("files", []):
        fp = out_dir / f["name"]
        if not fp.exists():
            return {"status":"FAIL", "code":MISMATCH["MISSING_FILE"], "file": f["name"]}
        got = sha256_hex(_read_bytes(fp))
        if got != f["sha256"]:
            return {"status":"FAIL", "code":MISMATCH["HASH_MISMATCH"], "file": f["name"]}

    # verify pack hash (recompute exactly as writer does)
    header = b"MANITHY_EP_V4\0"
    blob = header + manifest_hash.encode("utf-8") + b"\n"
    for f in manifest.get("files", []):
        blob += (f["name"] + ":" + f["sha256"] + "\n").encode("utf-8")
    expected_pack_hash = sha256_hex(blob)

    pack_bytes = _read_bytes(ppath)
    got_pack_hash = sha256_hex(pack_bytes)
    if got_pack_hash != expected_pack_hash:
        return {"status":"FAIL", "code":MISMATCH["PACK_HASH_MISMATCH"]}

    return {"status":"PASS", "code":MISMATCH["OK"], "manifest_hash":"mh_"+manifest_hash, "evidence_pack_hash":"eph_"+got_pack_hash}
