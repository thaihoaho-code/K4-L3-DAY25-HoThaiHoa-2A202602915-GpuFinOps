"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing, sustainability

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    cleanest_region = min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
    carbon_jobs = []
    baseline_carbon_g = optimized_carbon_g = 0.0
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        tier = pricing.recommend_tier(hpd, interruptible)
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od)
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

        # Extension: shift only checkpointable/interruptible jobs to the cleanest
        # listed region and compare their estimated operational emissions.
        if interruptible:
            energy_wh = num(c["watts"]) * hpd * num(j["days"]) * ngpu
            base_g = sustainability.carbon_g(energy_wh, "us-east-1")
            clean_g = sustainability.carbon_g(energy_wh, cleanest_region)
            baseline_carbon_g += base_g
            optimized_carbon_g += clean_g
            carbon_jobs.append({"job_id": j["job_id"], "energy_kwh": energy_wh / 1000,
                                "us_east_gco2e": base_g, "cleanest_gco2e": clean_g,
                                "saved_gco2e": base_g - clean_g})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")
        print(f"\ncarbon-aware schedule (interruptible jobs, {cleanest_region}):")
        for r in carbon_jobs:
            print(f"  {r['job_id']:18}{r['energy_kwh']:>9.1f} kWh  saved {r['saved_gco2e']:>10,.0f} gCO2e")
        carbon_saved = baseline_carbon_g - optimized_carbon_g
        carbon_pct = carbon_saved / baseline_carbon_g * 100 if baseline_carbon_g else 0.0
        print(f"  total: {baseline_carbon_g / 1000:,.1f} -> {optimized_carbon_g / 1000:,.1f} kgCO2e  ({carbon_pct:.1f}% saved)")

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "optimized_monthly": round(optimized_monthly), "savings_pct": round(savings_pct, 1),
            "carbon_schedule": {
                "cleanest_region": cleanest_region,
                "interruptible_jobs": carbon_jobs,
                "energy_kwh": round(sum(r["energy_kwh"] for r in carbon_jobs), 2),
                "baseline_gco2e": round(baseline_carbon_g),
                "optimized_gco2e": round(optimized_carbon_g),
                "saved_gco2e": round(baseline_carbon_g - optimized_carbon_g),
            }}


if __name__ == "__main__":
    run()
