"""合成数据的业务行为测试，不能证明真实产品或交易有效。"""
import unittest
from copy import deepcopy
from industry_pilots.energy import evaluate_energy
from industry_pilots.mobility import evaluate_mobility
from industry_pilots.shared import assess_evidence, profit_snapshot, publication_ready, BusinessCycle

def energy():
    return {
        "capacity_kwh": "15", "initial_kwh": "8", "reserve_kwh": "2",
        "max_charge_kw": "5", "max_discharge_kw": "5",
        "charge_efficiency": "0.9", "discharge_efficiency": "0.9",
        "import_limit_kw": "200", "export_limit_kw": "10",
        "thermal_capacity_kwh": "8", "thermal_initial_kwh": "2",
        "demand_rate": "10", "billing_period_complete": False,
        "backup": {"load_kw": "2", "hours": "2", "peak_kw": "4"},
        "intervals": [
            {"hours": "1", "load_kw": "2", "pv_kw": "6", "charge_kw": "4",
             "discharge_kw": "0", "buy_rate": "0.1", "sell_rate": "0.05"},
            {"hours": "1", "load_kw": "4", "pv_kw": "0", "charge_kw": "0",
             "discharge_kw": "3.24", "buy_rate": "0.3", "sell_rate": "0.05"}
        ]
    }

def record(kind, market="DEMO", revision="r1"):
    return {"kind": kind, "market": market, "revision": revision, "status": "verified",
            "valid_until": "2027-01-01", "ref": "synthetic-" + kind}

def mobility(kind="ebike"):
    kinds = ["electrical", "charger", "brake"]
    if kind == "conversion":
        kinds += ["frame", "mechanical_interface", "installer"]
    if kind == "emotorcycle":
        kinds += ["type_approval_route", "registration_route"]
    return {"kind": kind, "market": "DEMO", "revision": "r1", "as_of": "2026-09-18",
            "market_confirmed": False, "rated_w": "250", "cutoff_kmh": "25",
            "pedals": True, "requirement_max_rated_w": "250", "requirement_max_cutoff_kmh": "25",
            "requirement_pedals": True, "battery_wh": "750", "usable_fraction": "0.9",
            "wh_per_km_low": "10", "wh_per_km_high": "20", "required_km": "30",
            "evidence": [record(k) for k in kinds]}

def finance():
    return {"currency": "CNY", "revenue": "1000", "refund": "100",
            "required_costs": ["product", "acquisition"],
            "costs": [{"id": "c1", "category": "product", "kind": "direct", "amount": "500",
                       "currency": "CNY", "status": "confirmed"},
                      {"id": "c2", "category": "acquisition", "kind": "variable", "amount": "100",
                       "currency": "CNY", "status": "confirmed"}]}

class EnergyTests(unittest.TestCase):
    def test_losses_and_cycle_energy_are_accounted(self):
        result = evaluate_energy(energy())
        self.assertTrue(result["feasible"])
        self.assertEqual(result["battery_end_kwh"], "8")
        self.assertEqual(result["energy_savings"], "0.772")

    def test_incomplete_billing_period_cannot_claim_demand_savings(self):
        self.assertIsNone(evaluate_energy(energy())["demand_savings"])

    def test_complete_period_uses_actual_peak_including_charging(self):
        spec = energy()
        spec["billing_period_complete"] = True
        result = evaluate_energy(spec)
        self.assertEqual(result["demand_savings"], "32.4")

    def test_power_constraint_independent_of_capacity(self):
        spec = energy()
        spec["max_charge_kw"] = "3"
        self.assertIn("CHARGE_POWER", evaluate_energy(spec)["violations"])

    def test_energy_reserve_is_not_free_capacity(self):
        spec = energy()
        spec["intervals"][1]["discharge_kw"] = "9"
        self.assertIn("BATTERY_BOUNDS", evaluate_energy(spec)["violations"])

    def test_simultaneous_charge_discharge_rejected(self):
        spec = energy()
        spec["intervals"][0]["discharge_kw"] = "1"
        self.assertIn("SIMULTANEOUS_BATTERY_FLOW", evaluate_energy(spec)["violations"])

    def test_export_limit_checked(self):
        spec = energy()
        spec["export_limit_kw"] = "0"
        spec["intervals"][0]["pv_kw"] = "20"
        self.assertIn("EXPORT_LIMIT", evaluate_energy(spec)["violations"])

    def test_thermal_and_electric_ledgers_are_separate(self):
        spec = energy()
        spec["intervals"][0].update(pv_kw="8", hp_input_kw="2", cop="3",
                                   heat_demand_kw="2", thermal_charge_kw="4")
        spec["intervals"][1].update(heat_demand_kw="4", thermal_discharge_kw="4")
        result = evaluate_energy(spec)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["thermal_end_kwh"], "2")
        self.assertEqual(result["energy_savings"], "0.772")

    def test_heat_cannot_be_created_without_input(self):
        spec = energy()
        spec["intervals"][0]["heat_demand_kw"] = "5"
        self.assertIn("THERMAL_BALANCE", evaluate_energy(spec)["violations"])

    def test_backup_cannot_count_unavailable_grid_or_unproven_solar(self):
        spec = energy()
        spec["backup"]["hours"] = "10"
        self.assertIn("BACKUP_ENERGY", evaluate_energy(spec)["violations"])

    def test_invalid_numeric_inputs_rejected(self):
        for value in ["NaN", "Infinity", "-1"]:
            with self.subTest(value=value):
                spec = energy()
                spec["capacity_kwh"] = value
                with self.assertRaises(ValueError):
                    evaluate_energy(spec)

    def test_efficiency_outside_bounds_rejected(self):
        spec = energy()
        spec["charge_efficiency"] = "1.1"
        with self.assertRaises(ValueError):
            evaluate_energy(spec)

    def test_unequal_end_energy_does_not_claim_comparable_savings(self):
        spec = energy()
        spec["intervals"][1]["discharge_kw"] = "2"
        result = evaluate_energy(spec)
        self.assertIsNone(result["energy_savings"])
        self.assertIn("END_STATE_NOT_COMPARABLE", result["notes"])

    def test_invalid_schedule_does_not_produce_savings(self):
        spec = energy()
        spec["max_charge_kw"] = "1"
        result = evaluate_energy(spec)
        self.assertFalse(result["feasible"])
        self.assertIsNone(result["energy_savings"])

class MobilityTests(unittest.TestCase):
    def test_unknown_market_never_becomes_road_approval(self):
        result = evaluate_mobility(mobility())
        self.assertTrue(result["technical_ready"])
        self.assertFalse(result["market_ready"])
        self.assertIn("MARKET_PROFILE_PENDING", result["issues"])
        self.assertNotIn("road_legal", result)

    def test_range_is_interval_not_guaranteed_mileage(self):
        result = evaluate_mobility(mobility())
        self.assertEqual(result["range_low_km"], "33.75")
        self.assertEqual(result["range_high_km"], "67.5")

    def test_conversion_requires_donor_frame_evidence(self):
        spec = mobility("conversion")
        spec["evidence"] = [e for e in spec["evidence"] if e["kind"] != "frame"]
        result = evaluate_mobility(spec)
        self.assertFalse(result["technical_ready"])
        self.assertIn("EVIDENCE_MISSING:frame", result["issues"])

    def test_kit_document_for_other_revision_is_not_valid(self):
        spec = mobility("conversion")
        for evidence in spec["evidence"]:
            evidence["revision"] = "r0"
        self.assertFalse(evaluate_mobility(spec)["technical_ready"])

    def test_motorcycle_has_separate_route(self):
        spec = mobility("emotorcycle")
        spec.update(rated_w="3000", cutoff_kmh="70", pedals=False)
        result = evaluate_mobility(spec)
        self.assertEqual(result["route"], "motorcycle_review")
        self.assertTrue(result["technical_ready"])

    def test_higher_power_bicycle_not_silently_relabelled(self):
        spec = mobility()
        spec["rated_w"] = "1000"
        result = evaluate_mobility(spec)
        self.assertFalse(result["technical_ready"])
        self.assertIn("RATED_POWER_REQUIREMENT", result["issues"])

    def test_range_under_required_duty_cycle_is_flagged(self):
        spec = mobility()
        spec["required_km"] = "100"
        self.assertIn("DUTY_RANGE_SHORTFALL", evaluate_mobility(spec)["issues"])

    def test_zero_consumption_is_invalid(self):
        spec = mobility()
        spec["wh_per_km_low"] = "0"
        with self.assertRaises(ValueError):
            evaluate_mobility(spec)

class SharedTests(unittest.TestCase):
    def test_expired_resource_evidence_is_not_verified(self):
        evidence = record("capacity")
        evidence["valid_until"] = "2026-01-01"
        self.assertIn("EVIDENCE_MISSING:capacity",
                      assess_evidence([evidence], ["capacity"], "DEMO", "r1", "2026-09-18"))

    def test_wrong_market_evidence_does_not_match(self):
        self.assertTrue(assess_evidence([record("capacity", "OTHER")], ["capacity"],
                                        "DEMO", "r1", "2026-09-18"))

    def test_profit_refunds_and_costs_have_distinct_roles(self):
        result = profit_snapshot(finance())
        self.assertEqual(result["net_revenue"], "900")
        self.assertEqual(result["gross_profit"], "400")
        self.assertEqual(result["contribution_profit"], "300")
        self.assertEqual(result["status"], "confirmed_inputs")

    def test_missing_cost_never_becomes_zero(self):
        data = finance()
        data["costs"] = data["costs"][:1]
        result = profit_snapshot(data)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["contribution_profit"])

    def test_estimates_are_not_actual_profit(self):
        data = finance()
        data["costs"][0]["status"] = "estimated"
        self.assertEqual(profit_snapshot(data)["status"], "estimate")

    def test_cross_currency_addition_requires_explicit_conversion(self):
        data = finance()
        data["costs"][0]["currency"] = "USD"
        with self.assertRaises(ValueError):
            profit_snapshot(data)

    def test_duplicate_cost_id_is_rejected(self):
        data = finance()
        data["costs"].append(deepcopy(data["costs"][0]))
        with self.assertRaises(ValueError):
            profit_snapshot(data)

    def test_content_edit_or_market_unknown_blocks_publication(self):
        self.assertFalse(publication_ready("r1", "r2", True, True, True))
        self.assertFalse(publication_ready("r1", "r1", True, True, False))
        self.assertTrue(publication_ready("r1", "r1", True, True, True))

    def test_business_cycle_requires_order_and_evidence(self):
        cycle = BusinessCycle("case1")
        with self.assertRaises(ValueError):
            cycle.advance("e1", "reviewed", ["profit"])
        with self.assertRaises(ValueError):
            cycle.advance("e1", "resource_verified", [])
        self.assertEqual(cycle.stage, "opportunity")

    def test_business_cycle_idempotent_replay(self):
        cycle = BusinessCycle("case1")
        cycle.advance("e1", "resource_verified", ["resource-proof"])
        cycle.advance("e1", "resource_verified", ["resource-proof"])
        self.assertEqual(len(cycle.events), 1)
        with self.assertRaises(ValueError):
            cycle.advance("e1", "model_validated", ["different"])

if __name__ == "__main__":
    unittest.main()
