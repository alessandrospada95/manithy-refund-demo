from .hashing import sha256_hex

def ringvector_hash(ccr_hash_hex: str, policy_bundle_id: str) -> str:
    # Deterministic, in-memory ringvector represented ONLY by its hash.
    return sha256_hex((ccr_hash_hex + "|" + policy_bundle_id).encode("utf-8"))
