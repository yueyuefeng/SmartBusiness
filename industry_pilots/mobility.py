"""目标工况筛选与组合证据检查，不作道路合法性自动判定。"""
from .shared import positive, number, text_number, assess_evidence, require_bool

def evaluate_mobility(spec):
    kind = spec["kind"]
    if kind not in {"ebike", "emotorcycle", "conversion"}:
        raise ValueError("未知出行业务类型")
    rated = positive(spec["rated_w"])
    cutoff = positive(spec["cutoff_kmh"])
    require_bool(spec["pedals"])
    market_confirmed = require_bool(spec["market_confirmed"])
    fraction = positive(spec["usable_fraction"])
    if fraction > 1:
        raise ValueError("可用能量比例不能大于一")
    energy = positive(spec["battery_wh"]) * fraction
    low = positive(spec["wh_per_km_low"])
    high = number(spec["wh_per_km_high"], minimum=low)
    required_km = number(spec["required_km"], minimum=0)
    required = ["electrical", "charger", "brake"]
    if kind == "conversion":
        required += ["frame", "mechanical_interface", "installer"]
    if kind == "emotorcycle":
        required += ["type_approval_route", "registration_route"]
    issues = assess_evidence(spec["evidence"], required, spec["market"], spec["revision"], spec["as_of"])
    if kind != "emotorcycle":
        # 阈值来自买方方案需求；这里没有硬编码全球道路分类规则。
        if rated > positive(spec["requirement_max_rated_w"]):
            issues.append("RATED_POWER_REQUIREMENT")
        if cutoff > positive(spec["requirement_max_cutoff_kmh"]):
            issues.append("ASSIST_CUTOFF_REQUIREMENT")
        if require_bool(spec["requirement_pedals"]) and not spec["pedals"]:
            issues.append("PEDAL_REQUIREMENT")
    if energy / high < required_km:
        issues.append("DUTY_RANGE_SHORTFALL")
    technical_ready = not issues
    market_evidence = assess_evidence(spec["evidence"], ["market_review"],
                                     spec["market"], spec["revision"], spec["as_of"])
    market_ready = market_confirmed and not market_evidence
    if not market_ready:
        issues.append("MARKET_PROFILE_PENDING")
    return {"route": "motorcycle_review" if kind == "emotorcycle" else
            ("conversion_review" if kind == "conversion" else "bicycle_review"),
            "technical_ready": technical_ready, "market_ready": market_ready,
            "issues": issues, "range_low_km": text_number(energy / high),
            "range_high_km": text_number(energy / low),
            "scope": "工况估算与资料筛选，不是续航保证或道路准入结论"}
