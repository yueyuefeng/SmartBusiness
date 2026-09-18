"""运行六个合成行业案例，不发消息、不控制设备、不执行真实交易。"""
import argparse
import json
from pathlib import Path
from .energy import evaluate_energy
from .mobility import evaluate_mobility
from .shared import assess_evidence, profit_snapshot, publication_ready, BusinessCycle, number, require_bool

def run_case(case):
    if case.get("synthetic") is not True:
        raise ValueError("此运行器只接收显式标记的合成示例")
    market_confirmed = require_bool(case["market_confirmed"])
    qualified, resources = [], []
    for resource in case["resources"]:
        issues = assess_evidence(resource["evidence"], ["capacity", "quote"],
                                 case["market"], case["revision"], case["as_of"])
        resources.append({"id": resource["id"], "issues": issues})
        if not issues:
            qualified.append(resource["id"])
    if case["industry"] == "energy":
        technical = evaluate_energy(case["technical"])
        blockers = list(technical["violations"])
        blockers += assess_evidence(case["review_evidence"], case["required_reviews"],
                                    case["market"], case["revision"], case["as_of"])
        technical_ready = not blockers
        market_ready = market_confirmed and not assess_evidence(case["review_evidence"],
                         ["market_review"], case["market"], case["revision"], case["as_of"])
    elif case["industry"] == "mobility":
        spec = dict(case["technical"])
        if (spec["market"], spec["revision"], spec["as_of"]) != (case["market"], case["revision"], case["as_of"]):
            raise ValueError("案例与行业模型的市场/版本/评价时间不一致")
        spec["market_confirmed"] = market_confirmed
        technical = evaluate_mobility(spec)
        technical_ready, market_ready = technical["technical_ready"], technical["market_ready"]
        blockers = [issue for issue in technical["issues"] if issue != "MARKET_PROFILE_PENDING"]
    else:
        raise ValueError("未知行业")
    if not market_ready:
        blockers.append("MARKET_PROFILE_PENDING")
    if not qualified:
        blockers.append("NO_QUALIFIED_RESOURCE")
    finance = profit_snapshot(case["finance"])
    if finance["contribution_profit"] is None:
        blockers.append("FINANCE_INCOMPLETE")
    elif number(finance["contribution_profit"]) <= 0:
        blockers.append("NON_POSITIVE_CONTRIBUTION")
    marketing = case["marketing"]
    publish_gate = publication_ready(marketing["approved_revision"], marketing["current_revision"],
                     marketing["claims_verified"], technical_ready, market_ready)
    if not marketing["claims_verified"] or marketing["approved_revision"] != marketing["current_revision"]:
        blockers.append("CONTENT_REVIEW_PENDING")
    cycle = BusinessCycle(case["id"])
    if qualified:
        cycle.advance(case["id"] + "-e1", "resource_verified", ["synthetic://resource-proof"])
    if not blockers:
        for index, stage in enumerate(("model_validated", "campaign_recorded", "quoted"), start=2):
            cycle.advance(case["id"] + "-e" + str(index), stage, ["synthetic://" + stage])
        if finance["status"] == "confirmed_inputs":
            for index, stage in enumerate(("contracted", "delivered", "reconciled", "reviewed"), start=5):
                cycle.advance(case["id"] + "-e" + str(index), stage, ["synthetic://" + stage])
        else:
            blockers.append("ACTUAL_SETTLEMENT_PENDING")
    return {"id": case["id"], "title": case["title"], "synthetic": True, "market": case["market"],
            "notice": "合成案例：未实施真实营销、合同、交付、收款或认证。",
            "technical": technical, "resources": resources, "qualified_resources": qualified,
            "finance": finance, "publication_gate_passed": publish_gate,
            "publication_allowed": False, "cycle_stage": cycle.stage, "blockers": sorted(set(blockers)),
            "simulation_events": [{"id": key, "stage": value[0], "refs": list(value[1])}
                                  for key, value in cycle.events.items()],
            "trace": case["trace"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parents[1] / "examples" / "industry")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    files = sorted(args.cases.glob("*.json"))
    if not files:
        parser.error("未找到案例 JSON")
    results = [run_case(json.loads(file.read_text(encoding="utf-8"))) for file in files]
    report = {"schema_version": 1, "synthetic": True, "cases": results}
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print("已生成合成行业案例报告：" + str(args.output))
    else:
        print(encoded, end="")

if __name__ == "__main__":
    main()
