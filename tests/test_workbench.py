"""先定义可观察的业务与安全行为，再实现持久化工作台。"""
import json
import tempfile
import unittest
from pathlib import Path
from smartbusiness.service import BusinessService, Conflict, Forbidden


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "business.sqlite3"
        self.service = BusinessService(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, operation, payload, key="command-1", actor="agent"):
        return self.service.execute(operation, payload, key, actor)

    def signal(self):
        return self.command("capture_signal", {
            "case_id": "EN-H01", "title": "家庭停电时需要供电",
            "source_url": "https://example.com/interview/1", "excerpt": "用户访谈摘录",
            "customer_problem": "关键负载无法持续工作"}, "signal-1")["result"]

    def opportunity(self):
        signal = self.signal()
        return self.command("propose_opportunity", {
            "signal_id": signal["id"], "customer_segment": "家庭住户",
            "value_proposition": "先诊断关键负载与备电需求",
            "monetization": "brokerage", "market": "待选择欧洲成员国"}, "opportunity-1")["result"]

    def content(self):
        opportunity = self.opportunity()
        return self.command("draft_content", {
            "opportunity_id": opportunity["id"], "channel": "待接入渠道",
            "title": "备电需求诊断", "body": "邀请了解家庭关键负载场景。"}, "content-1")["result"]

    def test_six_cases_remain_synthetic_and_market_pending(self):
        cases = self.service.dashboard()["cases"]
        self.assertEqual(len(cases), 6)
        self.assertTrue(all(case["synthetic"] for case in cases))
        self.assertTrue(all("MARKET_PROFILE_PENDING" in case["blockers"] for case in cases))

    def test_captured_evidence_is_unverified_and_persisted(self):
        signal = self.signal()
        self.assertEqual(signal["status"], "unverified")
        restarted = BusinessService(self.path)
        self.assertEqual(restarted.dashboard()["signals"][0]["id"], signal["id"])

    def test_duplicate_command_replays_without_duplicate_event(self):
        signal = self.signal()
        replay = self.command("capture_signal", {
            "case_id": "EN-H01", "title": "家庭停电时需要供电",
            "source_url": "https://example.com/interview/1", "excerpt": "用户访谈摘录",
            "customer_problem": "关键负载无法持续工作"}, "signal-1")
        self.assertTrue(replay["replayed"])
        self.assertEqual(signal["id"], replay["result"]["id"])
        self.assertEqual(len(self.service.dashboard()["events"]), 1)

    def test_duplicate_key_with_changed_payload_conflicts(self):
        self.signal()
        with self.assertRaises(Conflict):
            self.command("add_contact", {"name": "甲", "company": "乙", "channel": "邮件", "external_ref": "local"}, "signal-1")

    def test_unknown_case_and_forged_evidence_status_rejected(self):
        for payload in ({"case_id": "../../secrets"}, {"case_id": "EN-H01", "status": "verified"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.command("capture_signal", payload)
        self.assertEqual(self.service.dashboard()["events"], [])

    def test_unsafe_url_is_not_fetched_or_saved(self):
        with self.assertRaises(ValueError):
            self.command("capture_signal", {"case_id": "EN-H01", "title": "x", "source_url": "javascript:alert(1)", "excerpt": "x", "customer_problem": "x"})

    def test_opportunity_references_signal_and_stays_hypothesis(self):
        opportunity = self.opportunity()
        self.assertEqual(opportunity["status"], "hypothesis")
        self.assertEqual(opportunity["case_id"], "EN-H01")
        self.assertEqual(len(self.service.dashboard()["events"]), 2)

    def test_orphan_opportunity_and_unknown_monetization_rejected(self):
        payload = {"signal_id": "missing", "customer_segment": "x", "value_proposition": "y", "monetization": "product", "market": "pending"}
        with self.assertRaises(ValueError):
            self.command("propose_opportunity", payload)
        payload["signal_id"] = self.signal()["id"]
        payload["monetization"] = "guaranteed_profit"
        with self.assertRaises(ValueError):
            self.command("propose_opportunity", payload)

    def test_resource_is_candidate_and_money_rejects_float(self):
        payload = {"case_id": "MO-E01", "name": "待验证供应方", "kind": "factory", "source_url": "https://example.com/factory", "capabilities": "电机", "quote_amount": "100.20", "currency": "CNY"}
        resource = self.command("add_resource", payload)["result"]
        self.assertEqual(resource["status"], "unverified")
        self.assertEqual(resource["quote_amount"], "100.2")
        payload["quote_amount"] = 100.2
        with self.assertRaises(ValueError):
            self.command("add_resource", payload, "bad-money")

    def test_agent_cannot_approve_content_even_with_prior_operator_key(self):
        content = self.content()
        payload = {"content_id": content["id"], "decision": "accepted", "comment": "仅内部评审"}
        with self.assertRaises(Forbidden):
            self.command("review_content", payload, "approve-1")
        approved = self.command("review_content", payload, "approve-1", "operator")["result"]
        self.assertEqual(approved["status"], "accepted")
        self.assertFalse(approved["publication_allowed"])
        with self.assertRaises(Forbidden):
            self.command("review_content", payload, "approve-1", "agent")

    def test_review_is_final_and_duplicate_key_replay_stable(self):
        content = self.content()
        payload = {"content_id": content["id"], "decision": "rejected", "comment": "缺少证据"}
        self.command("review_content", payload, "review-1", "operator")
        self.assertTrue(self.command("review_content", payload, "review-1", "operator")["replayed"])
        with self.assertRaises(Conflict):
            self.command("review_content", payload, "review-2", "operator")

    def test_messages_are_local_records_not_transmissions(self):
        contact = self.command("add_contact", {"name": "演示客户", "company": "自填", "channel": "WhatsApp", "external_ref": "local-demo"})["result"]
        note = self.command("record_note", {"contact_id": contact["id"], "body": "待跟进需求", "direction": "outbound"}, "note-1")["result"]
        self.assertEqual(note["status"], "recorded_locally")
        self.assertFalse(note["sent"])

    def test_task_requires_evidence_and_preserves_original_acceptance(self):
        opportunity = self.opportunity()
        task = self.command("create_task", {"opportunity_id": opportunity["id"], "kind": "esg", "title": "收集材料排放证据", "acceptance": "明确边界和系数来源"}, "task-1")["result"]
        with self.assertRaises(ValueError):
            self.command("record_task_result", {"task_id": task["id"], "outcome": "done", "evidence_ref": "", "notes": "完成"}, "result-1")
        result = self.command("record_task_result", {"task_id": task["id"], "outcome": "blocked", "evidence_ref": "local://review/1", "notes": "缺少供应商数据"}, "result-1")["result"]
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["acceptance"], task["acceptance"])

    def test_scenario_changes_estimate_but_never_original_case(self):
        baseline = self.service.case("EN-H01")["result"]
        result = self.command("evaluate_case", {"case_id": "EN-H01", "revenue": "10000", "cost_changes": [{"id": "cost-0", "amount": "6000"}]})["result"]
        self.assertTrue(result["scenario"])
        self.assertEqual(result["finance"]["contribution_profit"], "1700")
        self.assertEqual(baseline, self.service.case("EN-H01")["result"])
        self.assertFalse(result["publication_allowed"])

    def test_scenario_rejects_unknown_cost_duplicate_and_non_string_money(self):
        for payload in ({"case_id": "EN-H01", "revenue": 2.1}, {"case_id": "EN-H01", "cost_changes": [{"id": "absent", "amount": "1"}]}, {"case_id": "EN-H01", "cost_changes": [{"id": "cost-0", "amount": "1"}, {"id": "cost-0", "amount": "2"}]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.command("evaluate_case", payload)

    def test_no_publish_payment_device_or_shell_operations(self):
        for operation in ("publish", "send_message", "pay", "execute_shell", "control_battery"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.command(operation, {})

    def test_input_limits_and_invalid_actor(self):
        with self.assertRaises(ValueError):
            self.command("add_contact", {"name": "x" * 10001, "company": "x", "channel": "x", "external_ref": "x"})
        with self.assertRaises(Forbidden):
            self.command("add_contact", {}, actor="admin")
        with self.assertRaises(ValueError):
            self.command("add_contact", {}, key="")

    def test_sql_injection_text_is_stored_as_data(self):
        text = "'; DROP TABLE events; --"
        self.command("add_contact", {"name": text, "company": "x", "channel": "x", "external_ref": "x"})
        dashboard = self.service.dashboard()
        self.assertEqual(dashboard["contacts"][0]["name"], text)
        self.assertEqual(len(dashboard["events"]), 1)
        self.assertFalse(dashboard["runtime"]["model_connected"])


if __name__ == "__main__":
    unittest.main()
