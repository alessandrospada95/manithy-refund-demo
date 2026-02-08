import json, os
from pathlib import Path
from .hashing import sha256_hex

def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()

def build_manifest(out_dir: Path, policy_bundle_id: str, entries: list[tuple[str,str]]) -> dict:
    # entries: (filename, sha256hex)
    return {
        "manifest_version": "manithy.evidence_pack.manifest.v1",
        "policy_bundle_id": policy_bundle_id,
        "files": [{"name": n, "sha256": h} for (n,h) in entries],
    }

def write_evidence_pack(out_dir: Path, policy_bundle_id: str, file_names: list[str]) -> tuple[str,str]:
    # Build a compact binary evidence pack (demo): header + file hashes.
    entries = []
    for fn in file_names:
        p = out_dir / fn
        h = sha256_hex(_read_bytes(p))
        entries.append((fn, h))

    manifest = build_manifest(out_dir, policy_bundle_id, entries)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",",":")).encode("utf-8")
    manifest_hash = sha256_hex(manifest_bytes)

    # Binary pack: fixed header + manifest_hash + per-file hashes (write-once)
    header = b"MANITHY_EP_V4\0"
    blob = header + manifest_hash.encode("utf-8") + b"\n"
    for fn, h in entries:
        blob += (fn + ":" + h + "\n").encode("utf-8")

    ep_hash = sha256_hex(blob)

    (out_dir / "EvidencePack.bin").write_bytes(blob)
    (out_dir / "EvidencePack.manifest.json").write_bytes(manifest_bytes)
    return "eph_" + ep_hash, "mh_" + manifest_hash
