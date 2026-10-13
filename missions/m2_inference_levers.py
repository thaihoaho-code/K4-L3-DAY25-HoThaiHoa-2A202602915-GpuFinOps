"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0
    reasoning = {True: {"requests": 0, "tokens": 0, "cost": 0.0, "wh": 0.0},
                 False: {"requests": 0, "tokens": 0, "cost": 0.0, "wh": 0.0}}
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_reasoning = bool(int(num(r["is_reasoning"])))
        tokens = inp + out
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        request_cost = pricing.request_cost(
            inp, out, pin, pout, cached_in=cached, batch=is_batch
        )
        opt_cost += request_cost

        # Extension: attribute optimized inference cost and estimated energy
        # separately for reasoning and non-reasoning traffic.
        group = reasoning[is_reasoning]
        group["requests"] += 1
        group["tokens"] += tokens
        group["cost"] += request_cost
        group["wh"] += sustainability.wh_per_query(tokens, is_reasoning=is_reasoning)

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0
    reasoning_cost_share = reasoning[True]["cost"] / opt_cost if opt_cost else 0.0
    reasoning_request_share = reasoning[True]["requests"] / len(rows) if rows else 0.0
    total_wh = reasoning[True]["wh"] + reasoning[False]["wh"]
    reasoning_energy_share = reasoning[True]["wh"] / total_wh if total_wh else 0.0

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("reasoning budget (optimized traffic):")
        print(f"  requests : {reasoning[True]['requests']}/{len(rows)} ({reasoning_request_share:.1%})")
        print(f"  tokens   : {reasoning[True]['tokens']:,}/{total_tokens:,} ({reasoning[True]['tokens'] / total_tokens:.1%})")
        print(f"  cost     : ${reasoning[True]['cost']:.2f}/${opt_cost:.2f} ({reasoning_cost_share:.1%})")
        print(f"  energy   : {reasoning[True]['wh']:.0f}/{total_wh:.0f} Wh ({reasoning_energy_share:.1%})")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "reasoning": {
            "requests": reasoning[True]["requests"],
            "request_share_pct": round(reasoning_request_share * 100, 1),
            "token_share_pct": round(reasoning[True]["tokens"] / total_tokens * 100, 1) if total_tokens else 0.0,
            "cost_usd": round(reasoning[True]["cost"], 2),
            "cost_share_pct": round(reasoning_cost_share * 100, 1),
            "energy_wh": round(reasoning[True]["wh"], 2),
            "energy_share_pct": round(reasoning_energy_share * 100, 1),
            "non_reasoning_cost_usd": round(reasoning[False]["cost"], 2),
            "non_reasoning_energy_wh": round(reasoning[False]["wh"], 2),
        },
    }


if __name__ == "__main__":
    run()
