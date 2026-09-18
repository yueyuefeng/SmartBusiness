"""行业共用值、证据与经营规则；所有外部事实仍需真实核验。"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

def number(value, minimum=None, maximum=None):
    if isinstance(value, (bool, float)):
        raise ValueError("数值必须为十进制字符串或整数")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("无效十进制数") from error
    if not result.is_finite():
        raise ValueError("数值必须有限")
    if minimum is not None and result < minimum:
        raise ValueError("数值低于允许下限")
    if maximum is not None and result > maximum:
        raise ValueError("数值高于允许上限")
    return result

def positive(value):
    result = number(value, minimum=0)
    if result == 0:
        raise ValueError("数值必须大于零")
    return result

def text_number(value):
    return format(value.normalize(), "f") if value is not None else None

def require_bool(value):
    if type(value) is not bool:
        raise ValueError("必须使用布尔值")
    return value

def assess_evidence(records, required, market, revision, as_of):
    today = date.fromisoformat(as_of)
    valid = set()
    for record in records:
        if (record.get("market") == market and record.get("revision") == revision
                and record.get("status") == "verified" and record.get("ref")
                and date.fromisoformat(record["valid_until"]) >= today):
            valid.add(record["kind"])
    return ["EVIDENCE_MISSING:" + kind for kind in required if kind not in valid]

def profit_snapshot(finance):
    currency = finance["currency"]
    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError("需要明确三字母币种，不自动换汇")
    revenue = number(finance["revenue"], minimum=0)
    refund = number(finance.get("refund", "0"), minimum=0)
    net = revenue - refund
    direct, variable = Decimal(0), Decimal(0)
    ids, categories, missing = set(), set(), set()
    estimated = finance.get("revenue_status", "confirmed") != "confirmed"
    for cost in finance["costs"]:
        if not cost.get("id") or cost["id"] in ids:
            raise ValueError("成本记录标识必须唯一")
        ids.add(cost["id"])
        if cost["currency"] != currency:
            raise ValueError("跨币种必须提供已审核换汇记录，样例不自动转换")
        if cost["kind"] not in {"direct", "variable"}:
            raise ValueError("成本类型应为 direct 或 variable")
        if cost["status"] not in {"confirmed", "estimated", "missing"}:
            raise ValueError("未知成本状态")
        if cost.get("amount") is None or cost["status"] == "missing":
            missing.add(cost["category"])
            continue
        categories.add(cost["category"])
        amount = number(cost["amount"], minimum=0)
        estimated = estimated or cost["status"] != "confirmed"
        if cost["kind"] == "direct":
            direct += amount
        else:
            variable += amount
    missing |= set(finance["required_costs"]) - categories
    status = "incomplete" if missing else ("estimate" if estimated else "confirmed_inputs")
    return {"currency": currency, "net_revenue": text_number(net),
            "gross_profit": None if missing else text_number(net - direct),
            "contribution_profit": None if missing else text_number(net - direct - variable),
            "status": status, "missing_costs": sorted(missing),
            "scope": "经营口径，非净利润；不证明真实交易已发生"}

def publication_ready(approved_revision, current_revision, claims_verified, technical_ready, market_confirmed):
    flags = [claims_verified, technical_ready, market_confirmed]
    for flag in flags:
        require_bool(flag)
    return bool(approved_revision and approved_revision == current_revision and all(flags))

@dataclass
class BusinessCycle:
    """带证据的内存流程演示，不替代审批、合同或生产事件总线。"""
    case_id: str
    stage: str = "opportunity"
    events: dict = field(default_factory=dict)

    def advance(self, event_id, target, evidence_refs):
        stages = ("opportunity", "resource_verified", "model_validated", "campaign_recorded",
                  "quoted", "contracted", "delivered", "reconciled", "reviewed")
        if not event_id or not evidence_refs or not all(isinstance(e, str) and e for e in evidence_refs):
            raise ValueError("每次推进必须具有事件标识和证据引用")
        payload = (target, tuple(evidence_refs))
        if event_id in self.events:
            if self.events[event_id] != payload:
                raise ValueError("同一事件标识不能用于不同内容")
            return self.stage
        if self.stage not in stages or target not in stages or stages.index(target) != stages.index(self.stage) + 1:
            raise ValueError("不允许跳过业务阶段")
        self.stage = target
        self.events[event_id] = payload
        return self.stage
