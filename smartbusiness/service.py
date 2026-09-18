"""应用服务：领域操作的事务、校验和审计边界。"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from industry_pilots.runner import run_case
from .domain import Conflict, Forbidden, ContentReview, DeliveryTask, fields, text, choice, source_url, money
from .repository import Repository, encoded


OPERATIONS = {
    "capture_signal": ("signals", "SignalCaptured"),
    "propose_opportunity": ("opportunities", "OpportunityProposed"),
    "add_resource": ("resources", "ResourceCandidateAdded"),
    "draft_content": ("contents", "ContentDrafted"),
    "review_content": ("contents", "ContentReviewedInternally"),
    "add_contact": ("contacts", "ContactAdded"),
    "record_note": ("notes", "CommunicationRecordedLocally"),
    "create_task": ("tasks", "DeliveryTaskCreated"),
    "record_task_result": ("tasks", "TaskResultSelfReported"),
    "evaluate_case": (None, "SyntheticScenarioEvaluated"),
}

class BusinessService:
    def __init__(self, db_path, cases_dir=None):
        self.repo = Repository(db_path)
        cases_dir = cases_dir or Path(__file__).resolve().parents[1] / "examples" / "industry"
        self.cases = {}
        for file in sorted(Path(cases_dir).glob("*.json")):
            case = json.loads(file.read_text(encoding="utf-8"))
            if case["id"] in self.cases:
                raise ValueError("案例 ID 重复")
            run_case(case)
            self.cases[case["id"]] = case
        if not self.cases:
            raise ValueError("案例目录为空")

    def execute(self, operation, payload, key, actor="agent"):
        # 身份由传输适配器设定，不能从工具参数指定。鉴权先于幂等结果读取。
        if actor not in ("agent", "operator"):
            raise Forbidden("未知操作身份")
        if operation == "review_content" and actor != "operator":
            raise Forbidden("内部评审只能由工作台操作员执行")
        if not isinstance(operation, str) or operation not in OPERATIONS:
            raise ValueError("不支持的业务操作")
        key = text(key, "幂等键", 128)
        fingerprint = hashlib.sha256(encoded([actor, operation, payload]).encode("utf-8")).hexdigest()
        with self.repo.transaction() as db:
            replay = self.repo.replay(db, key, fingerprint)
            if replay is not None:
                return {"result": replay, "replayed": True}
            now = datetime.now(timezone.utc).isoformat()
            result = getattr(self, "_" + operation)(db, payload)
            kind, event_name = OPERATIONS[operation]
            if kind:
                result.setdefault("id", uuid4().hex)
                result.setdefault("created_at", now)
                result["updated_at"] = now
                self.repo.save(db, kind, result)
            event = {"id": uuid4().hex, "type": event_name, "operation": operation,
                     "entity_id": result.get("id"), "actor": actor, "command_key": key,
                     "created_at": now, "external_effect": False}
            self.repo.commit_command(db, key, fingerprint, result, event)
        return {"result": result, "replayed": False}

    def dashboard(self):
        return {**self.repo.snapshot(), "cases": [run_case(case) for case in self.cases.values()],
                "runtime": {"provider": "DeepSeek Harness", "model_connected": False,
                            "model_status": "not_observed_by_workbench", "publication_enabled": False,
                            "deployment": "local_single_operator"}}

    def case(self, case_id):
        if not isinstance(case_id, str) or case_id not in self.cases:
            raise ValueError("未知行业案例")
        case = deepcopy(self.cases[case_id])
        return {"definition": case, "result": run_case(case)}

    def _capture_signal(self, db, payload):
        fields(payload, ("case_id", "title", "source_url", "excerpt", "customer_problem"))
        self.case(payload["case_id"])
        return {"case_id": payload["case_id"], "title": text(payload["title"], "标题", 300),
                "source_url": source_url(payload["source_url"]), "excerpt": text(payload["excerpt"], "原文摘录"),
                "customer_problem": text(payload["customer_problem"], "客户问题"),
                "status": "unverified", "trust": "external_untrusted_data"}

    def _propose_opportunity(self, db, payload):
        fields(payload, ("signal_id", "customer_segment", "value_proposition", "monetization", "market"))
        signal = self.repo.get(db, "signals", payload["signal_id"])
        return {"signal_id": signal["id"], "case_id": signal["case_id"],
                "customer_segment": text(payload["customer_segment"], "客户群", 1000),
                "value_proposition": text(payload["value_proposition"], "价值主张"),
                "monetization": choice(payload["monetization"], ("brokerage", "product", "software"), "变现方式"),
                "market": text(payload["market"], "候选市场", 300), "status": "hypothesis",
                "market_confirmed": False, "profit_verified": False}

    def _add_resource(self, db, payload):
        fields(payload, ("case_id", "name", "kind", "source_url", "capabilities", "quote_amount", "currency"))
        self.case(payload["case_id"])
        currency = text(payload["currency"], "币种", 3)
        if not currency.isascii() or not currency.isalpha() or currency.upper() != currency:
            raise ValueError("币种须为三个大写 ASCII 字母")
        if len(currency) != 3:
            raise ValueError("币种须为三个大写 ASCII 字母")
        return {"case_id": payload["case_id"], "name": text(payload["name"], "资源名称", 300),
                "kind": text(payload["kind"], "资源类型", 100), "source_url": source_url(payload["source_url"]),
                "capabilities": text(payload["capabilities"], "能力说明"), "quote_amount": money(payload["quote_amount"]),
                "currency": currency, "status": "unverified", "quote_status": "self_reported"}

    def _draft_content(self, db, payload):
        fields(payload, ("opportunity_id", "channel", "title", "body"))
        opportunity = self.repo.get(db, "opportunities", payload["opportunity_id"])
        return {"opportunity_id": opportunity["id"], "case_id": opportunity["case_id"],
                "channel": text(payload["channel"], "拟用渠道", 100), "title": text(payload["title"], "标题", 300),
                "body": text(payload["body"], "正文"), "status": "draft", "revision": 1,
                "claims_verified": False, "publication_allowed": False}

    def _review_content(self, db, payload):
        fields(payload, ("content_id", "decision", "comment"))
        content = self.repo.get(db, "contents", payload["content_id"])
        return ContentReview(content).decide(payload["decision"], payload["comment"])

    def _add_contact(self, db, payload):
        fields(payload, ("name", "company", "channel", "external_ref"))
        return {key: text(value, key, 500) for key, value in payload.items()} | {"status": "manually_entered"}

    def _record_note(self, db, payload):
        fields(payload, ("contact_id", "body", "direction"))
        contact = self.repo.get(db, "contacts", payload["contact_id"])
        return {"contact_id": contact["id"], "body": text(payload["body"], "沟通记录"),
                "direction": choice(payload["direction"], ("inbound", "outbound", "internal"), "沟通方向"),
                "status": "recorded_locally", "sent": False}

    def _create_task(self, db, payload):
        fields(payload, ("opportunity_id", "kind", "title", "acceptance"))
        opportunity = self.repo.get(db, "opportunities", payload["opportunity_id"])
        return {"opportunity_id": opportunity["id"], "case_id": opportunity["case_id"],
                "kind": choice(payload["kind"], ("software", "hardware", "contract", "esg"), "工作类型"),
                "title": text(payload["title"], "工作标题", 300), "acceptance": text(payload["acceptance"], "验收条件"),
                "status": "open"}

    def _record_task_result(self, db, payload):
        fields(payload, ("task_id", "outcome", "evidence_ref", "notes"))
        task = self.repo.get(db, "tasks", payload["task_id"])
        return DeliveryTask(task).record_result(payload["outcome"], payload["evidence_ref"], payload["notes"])

    def _evaluate_case(self, db, payload):
        fields(payload, ("case_id",), ("revenue", "cost_changes"))
        case = self.case(payload["case_id"])["definition"]
        if "revenue" in payload:
            case["finance"]["revenue"] = money(payload["revenue"])
            case["finance"]["revenue_status"] = "estimated"
        changes = payload.get("cost_changes", [])
        if not isinstance(changes, list) or len(changes) > 100:
            raise ValueError("成本变更必须是最多 100 项的数组")
        costs = {item["id"]: item for item in case["finance"]["costs"]}
        seen = set()
        for change in changes:
            fields(change, ("id", "amount"))
            cost_id = text(change["id"], "成本项 ID", 100)
            if cost_id not in costs or cost_id in seen:
                raise ValueError("成本项不存在或重复")
            seen.add(cost_id)
            costs[cost_id]["amount"] = money(change["amount"])
            costs[cost_id]["status"] = "estimated"
        return {**run_case(case), "scenario": True, "input_changes": deepcopy(payload)}
