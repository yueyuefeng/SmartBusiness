"""给定调度的可行性与观察窗口费用比较；不是最优调度或施工设计。"""
from dataclasses import dataclass
from decimal import Decimal
from .shared import number, positive, text_number, require_bool

@dataclass(frozen=True)
class EnergyState:
    battery_kwh: Decimal
    thermal_kwh: Decimal

    def next(self, charge, discharge, eta_c, eta_d, thermal_charge, thermal_discharge, loss, hours):
        return EnergyState(
            self.battery_kwh + (charge * eta_c - discharge / eta_d) * hours,
            self.thermal_kwh * (1 - loss) + (thermal_charge - thermal_discharge) * hours)

@dataclass(frozen=True)
class GridExchange:
    """同一并网点的购售电分解，供基线与方案共用。"""
    imported_kw: Decimal
    exported_kw: Decimal

    @classmethod
    def from_net(cls, net):
        return cls(max(net, Decimal(0)), max(-net, Decimal(0)))

    def cost(self, buy, sell, hours):
        return (self.imported_kw * buy - self.exported_kw * sell) * hours

def evaluate_energy(spec):
    cap = positive(spec["capacity_kwh"])
    reserve = number(spec["reserve_kwh"], minimum=0, maximum=cap)
    initial = number(spec["initial_kwh"], minimum=reserve, maximum=cap)
    charge_limit = number(spec["max_charge_kw"], minimum=0)
    discharge_limit = number(spec["max_discharge_kw"], minimum=0)
    eta_c = positive(spec["charge_efficiency"])
    eta_d = positive(spec["discharge_efficiency"])
    if eta_c > 1 or eta_d > 1:
        raise ValueError("效率不能大于一")
    import_limit = number(spec["import_limit_kw"], minimum=0)
    export_limit = number(spec["export_limit_kw"], minimum=0)
    thermal_cap = number(spec.get("thermal_capacity_kwh", "0"), minimum=0)
    thermal_initial = number(spec.get("thermal_initial_kwh", "0"), minimum=0, maximum=thermal_cap)
    complete = require_bool(spec["billing_period_complete"])
    demand_rate = number(spec.get("demand_rate", "0"), minimum=0)
    if not spec["intervals"]:
        raise ValueError("至少提供一个观察区间")
    state = EnergyState(initial, thermal_initial)
    violations, notes, trace = [], [], []
    actual_bill = baseline_bill = peak_actual = peak_baseline = Decimal(0)
    for index, interval in enumerate(spec["intervals"]):
        hours = positive(interval["hours"])
        load = number(interval["load_kw"], minimum=0)
        pv = number(interval["pv_kw"], minimum=0)
        charge = number(interval["charge_kw"], minimum=0)
        discharge = number(interval["discharge_kw"], minimum=0)
        hp = number(interval.get("hp_input_kw", "0"), minimum=0)
        cop = positive(interval.get("cop", "1"))
        heat = number(interval.get("heat_demand_kw", "0"), minimum=0)
        tc = number(interval.get("thermal_charge_kw", "0"), minimum=0)
        td = number(interval.get("thermal_discharge_kw", "0"), minimum=0)
        loss = number(interval.get("thermal_loss_fraction", "0"), minimum=0, maximum=1)
        if charge and discharge:
            violations.append("SIMULTANEOUS_BATTERY_FLOW")
        if tc and td:
            violations.append("SIMULTANEOUS_THERMAL_FLOW")
        if charge > charge_limit:
            violations.append("CHARGE_POWER")
        if discharge > discharge_limit:
            violations.append("DISCHARGE_POWER")
        if hp * cop + td - tc != heat:
            violations.append("THERMAL_BALANCE")
        state = state.next(charge, discharge, eta_c, eta_d, tc, td, loss, hours)
        if not reserve <= state.battery_kwh <= cap:
            violations.append("BATTERY_BOUNDS")
        if not 0 <= state.thermal_kwh <= thermal_cap:
            violations.append("THERMAL_BOUNDS")
        baseline_net = load + hp - pv
        actual_net = baseline_net + charge - discharge
        actual = GridExchange.from_net(actual_net)
        baseline = GridExchange.from_net(baseline_net)
        imp, exp = actual.imported_kw, actual.exported_kw
        if imp > import_limit:
            violations.append("IMPORT_LIMIT")
        if exp > export_limit:
            violations.append("EXPORT_LIMIT")
        buy, sell = number(interval["buy_rate"]), number(interval["sell_rate"])
        baseline_bill += baseline.cost(buy, sell, hours)
        actual_bill += actual.cost(buy, sell, hours)
        peak_actual = max(peak_actual, imp)
        peak_baseline = max(peak_baseline, baseline.imported_kw)
        trace.append({"interval": index, "battery_kwh": text_number(state.battery_kwh),
                      "thermal_kwh": text_number(state.thermal_kwh), "import_kw": text_number(imp),
                      "export_kw": text_number(exp)})
    if "backup" in spec:
        backup = spec["backup"]
        load = positive(backup["load_kw"])
        hours = positive(backup["hours"])
        peak = number(backup["peak_kw"], minimum=load)
        if peak > discharge_limit:
            violations.append("BACKUP_POWER")
        if load * hours > (initial - reserve) * eta_d:
            violations.append("BACKUP_ENERGY")
        notes.append("BACKUP_CHECK_ASSUMES_REVIEWED_ISLAND_TOPOLOGY")
    comparable = state.battery_kwh == initial and state.thermal_kwh == thermal_initial
    if not comparable:
        notes.append("END_STATE_NOT_COMPARABLE")
    if not complete:
        notes.append("INCOMPLETE_BILLING_PERIOD")
    feasible = not violations
    return {"feasible": feasible, "violations": sorted(set(violations)), "notes": notes,
            "battery_end_kwh": text_number(state.battery_kwh),
            "thermal_end_kwh": text_number(state.thermal_kwh),
            "observed_energy_bill": text_number(actual_bill) if feasible else None,
            "baseline_energy_bill": text_number(baseline_bill),
            "energy_savings": text_number(baseline_bill - actual_bill) if feasible and comparable else None,
            "demand_savings": text_number((peak_baseline - peak_actual) * demand_rate)
                if complete and feasible and comparable else None,
            "annual_return": None, "trace": trace}
