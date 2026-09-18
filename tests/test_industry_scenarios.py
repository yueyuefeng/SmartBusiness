import json
import unittest
from copy import deepcopy
from pathlib import Path
from industry_pilots.runner import run_case

ROOT = Path(__file__).resolve().parents[1]

def load(case_id):
    return json.loads((ROOT / "examples" / "industry" / (case_id + ".json")).read_text(encoding="utf-8"))

class ScenarioTests(unittest.TestCase):
    def test_six_cases_run_and_remain_explicitly_synthetic(self):
        for file in sorted((ROOT / "examples" / "industry").glob("*.json")):
            with self.subTest(case=file.stem):
                result = run_case(load(file.stem))
                self.assertTrue(result["synthetic"])
                self.assertFalse(result["publication_allowed"])
                self.assertEqual(result["cycle_stage"], "resource_verified")
                self.assertIn("MARKET_PROFILE_PENDING", result["blockers"])

    def test_household_costs_include_installation_and_warranty(self):
        result = run_case(load("EN-H01"))
        self.assertEqual(result["finance"]["contribution_profit"], "1700")
        self.assertEqual(result["finance"]["status"], "estimate")

    def test_commercial_observation_not_annualized(self):
        result = run_case(load("EN-C01"))
        self.assertEqual(result["technical"]["energy_savings"], "7.15")
        self.assertIsNone(result["technical"]["annual_return"])
        self.assertIsNone(result["technical"]["demand_savings"])

    def test_conversion_missing_frame_is_blocked(self):
        result = run_case(load("MO-K01"))
        self.assertIn("EVIDENCE_MISSING:frame", result["blockers"])

    def test_expired_offer_cannot_be_selected(self):
        result = run_case(load("EN-H01"))
        self.assertEqual(result["qualified_resources"], ["EN-H01-supplier-a"])

    def test_complete_synthetic_cycle_requires_all_gates(self):
        data = load("EN-H01")
        data["market_confirmed"] = True
        data["review_evidence"].append({"kind": "market_review", "market": data["market"],
            "revision": "r1", "status": "verified", "valid_until": "2027-01-01", "ref": "synthetic://market-review"})
        data["marketing"]["claims_verified"] = True
        data["finance"]["revenue_status"] = "confirmed"
        for cost in data["finance"]["costs"]:
            cost["status"] = "confirmed"
        result = run_case(data)
        self.assertEqual(result["cycle_stage"], "reviewed")
        self.assertEqual(len(result["simulation_events"]), 8)
        self.assertTrue(result["synthetic"])

    def test_real_transactions_not_accepted_by_demo_runner(self):
        data = load("EN-H01")
        data["synthetic"] = False
        with self.assertRaises(ValueError):
            run_case(data)

    def test_missing_resource_evidence_stops_at_opportunity(self):
        data = load("EN-H01")
        data["resources"] = []
        self.assertEqual(run_case(data)["cycle_stage"], "opportunity")

if __name__ == "__main__":
    unittest.main()
