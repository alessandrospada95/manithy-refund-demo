def bucket_amount_minor(total_minor: int) -> str:
    if total_minor < 5000: return "B0_0_50"
    if total_minor < 20000: return "B1_50_200"
    if total_minor < 100000: return "B2_200_1000"
    return "B3_1000_PLUS"

def bucket_age_days(age_days: int) -> str:
    if age_days <= 7: return "D0_0_7"
    if age_days <= 30: return "D1_8_30"
    if age_days <= 90: return "D2_31_90"
    return "D3_90_PLUS"

def bucket_eta_days(days: int | None) -> str:
    if days is None: return "UNKNOWN"
    if days <= 2: return "D0_0_2"
    if days <= 7: return "D1_3_7"
    if days <= 14: return "D2_8_14"
    return "D3_15_PLUS"
