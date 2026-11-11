"""All five analyses, written to site/data.json for the page."""
import json
import re
import statistics as st
from pathlib import Path

from . import data as D

ROOT = Path(__file__).resolve().parent.parent
ALLOWANCE = 0.12          # personal, fatigue and delay allowance on standard time
SHIFT_SECONDS = 7.5 * 3600


def suppliers():
    """Total landed cost: price + expected cost of defects + expected cost of late deliveries."""
    rows = []
    for part, desc, qty, quotes in D.PARTS:
        for sup, (price, lt, moq) in quotes.items():
            s = D.SUPPLIERS[sup]
            defect_cost = price * s["ppm"] / 1e6 * 4            # a bad part costs ~4x its price in rework and scrap
            late_cost = (1 - s["otd"]) * 0.08 * price * 6        # expediting and line disruption, scaled by value
            rows.append({"part": part, "desc": desc, "supplier": sup, "price": price, "lead_weeks": lt, "moq": moq,
                         "otd": s["otd"], "ppm": s["ppm"], "landed": round(price + defect_cost + late_cost, 4), "annual_qty": qty})
    return rows


def mrp():
    """Weekly projected on-hand per part from the build plan, stock and open POs; flags the first shortage."""
    weeks = range(1, 13)
    need = {p: [sum(D.PRODUCTS[prod].get(p, 0) * D.BUILD_PLAN[prod][w - 1] for prod in D.PRODUCTS) for w in weeks] for p in D.ON_HAND}
    out = []
    for part, desc, _, quotes in D.PARTS:
        oh, proj, short = D.ON_HAND[part], [], None
        receipts = {}
        for (p, sup, q, due, actual) in D.OPEN_POS:
            if p == part:
                receipts[actual] = receipts.get(actual, 0) + q
        for w in weeks:
            oh += receipts.get(w, 0) - need[part][w - 1]
            proj.append(oh)
            if oh < 0 and short is None:
                short = w
        best_lt = min(lt for _, lt, _ in quotes.values())
        po = next(((sup, q, due, actual) for (p, sup, q, due, actual) in D.OPEN_POS if p == part), None)
        out.append({"part": part, "desc": desc, "need": need[part], "projected": proj, "first_short_week": short,
                    "fastest_lead_weeks": best_lt, "order_by_week": (short - best_lt) if short else None,
                    "open_po": {"supplier": po[0], "qty": po[1], "due": po[2], "now_expected": po[3]} if po else None})
    return out


def line_balance(obs):
    demand_per_day = round(sum(sum(v) for v in D.BUILD_PLAN.values()) / 12 / 5)
    takt = SHIFT_SECONDS / demand_per_day
    steps = []
    for name, _, _ in D.STEPS:
        xs = obs[name]
        med = st.median(xs)
        clean = [x for x in xs if x < med * 1.35]              # interruptions are logged, not built into the standard
        normal = st.mean(clean)
        steps.append({"step": name, "observations": xs, "interruptions": len(xs) - len(clean), "mean": round(normal, 1),
                      "sd": round(st.stdev(clean), 1), "standard": round(normal * (1 + ALLOWANCE), 1)})
    before = max(s["standard"] for s in steps)
    bottleneck = max(steps, key=lambda s: s["standard"])["step"]
    moved = sum(sec for _, sec in D.TASKS_MOVABLE.get(bottleneck, []))
    after_steps = [dict(s) for s in steps]
    i = next(k for k, s in enumerate(after_steps) if s["step"] == bottleneck)
    after_steps[i]["standard"] = round(after_steps[i]["standard"] - moved * (1 + ALLOWANCE), 1)
    after_steps[i - 1]["standard"] = round(after_steps[i - 1]["standard"] + moved * (1 + ALLOWANCE), 1)
    after = max(s["standard"] for s in after_steps)
    return {"demand_per_day": demand_per_day, "takt": round(takt, 1), "steps": steps, "after": [s["standard"] for s in after_steps],
            "bottleneck": bottleneck, "moved_task": D.TASKS_MOVABLE.get(bottleneck, [("", 0)])[0][0], "moved_seconds": moved,
            "cycle_before": before, "cycle_after": after, "capacity_before": int(SHIFT_SECONDS // before), "capacity_after": int(SHIFT_SECONDS // after)}


def quality(log):
    totals = {}
    for w in log:
        for t, c in w["defects"].items():
            totals[t] = totals.get(t, 0) + c
    pareto = sorted(totals.items(), key=lambda kv: -kv[1])
    focus = "Lens misaligned"
    base = [w for w in log if w["week"] < 7]
    pbar = sum(w["defects"][focus] for w in base) / sum(w["inspected"] for w in base)
    chart = []
    for w in log:
        n, c = w["inspected"], w["defects"][focus]
        sigma = (pbar * (1 - pbar) / n) ** 0.5
        chart.append({"week": w["week"], "n": n, "p": c / n, "ucl": pbar + 3 * sigma, "lcl": max(0.0, pbar - 3 * sigma)})
    after = [w for w in log if w["week"] >= 7]
    p_after = sum(w["defects"][focus] for w in after) / sum(w["inspected"] for w in after)
    below = sum(1 for c in chart if c["week"] >= 7 and c["p"] < pbar)
    return {"pareto": pareto, "focus": focus, "p_before": pbar, "p_after": p_after, "chart": chart, "weeks_below_center_after": below,
            "units_saved": round((pbar - p_after) * sum(w["inspected"] for w in after))}


def extract(text):
    """The automation step: pull part, supplier, price, MOQ and lead time out of a quote email.
    Regex here so it runs anywhere; the interface is the same if an LLM does the reading."""
    part = re.search(r"\b(P-\d{3})\b", text)
    sup = next((s for s in D.SUPPLIERS if s in text), None)
    price = re.search(r"(?:\$|USD\s?)(\d+\.\d{2})|(\d+\.\d{2})\s?USD", text)
    moq = re.search(r"(?:MOQ:?|min(?:imum)?(?: order)?:?)\s*(\d+)|(\d+)\s*pcs minimum", text, re.I)
    lt = re.search(r"(\d+)[- ]?(?:weeks?|wks)", text, re.I)
    days = re.search(r"(\d+)\s*days", text, re.I)
    lead = int(lt.group(1)) if lt else (round(int(days.group(1)) / 7) if days else None)
    val = lambda m: next((g for g in m.groups() if g), None) if m else None
    return {"part": part.group(1) if part else None, "supplier": sup, "price": float(val(price)) if price else None,
            "moq": int(val(moq)) if moq and val(moq) else None, "lead_weeks": lead}


def needs_review(got, reference):
    """The checks that decide whether a person looks before the quote goes into the tracker.
    They can only use what's knowable without the answer: missing fields, and values far from
    what this part normally costs or ships in."""
    reasons = [f"{k} missing" for k, v in got.items() if v is None]
    ref = reference.get(got["part"])
    if got["price"] is not None and ref and not (ref["price"] / 3 <= got["price"] <= ref["price"] * 3):
        reasons.append("price far from this part's usual price")
    if got["moq"] is not None and got["moq"] < 50:
        reasons.append("MOQ implausibly small")
    return reasons


def automation(emails):
    fields = ["part", "supplier", "price", "moq", "lead_weeks"]
    reference = {p: {"price": sorted(q[0] for q in quotes.values())[1]} for p, _, _, quotes in D.PARTS}  # median of last round
    results, right = [], {f: 0 for f in fields}
    for e in emails:
        got = extract(e["text"])
        ok = {f: got[f] == e["truth"][f] for f in fields}
        for f in fields:
            right[f] += ok[f]
        reasons = needs_review(got, reference)
        results.append({"text": e["text"], "got": got, "truth": e["truth"], "ok": ok, "all_ok": all(ok.values()), "review": reasons})
    n = len(emails)
    wrong = [r for r in results if not r["all_ok"]]
    return {"n": n, "field_accuracy": {f: right[f] / n for f in fields}, "all_fields_right": sum(r["all_ok"] for r in results) / n,
            "routed_to_review": sum(1 for r in results if r["review"]), "wrong": len(wrong),
            "wrong_caught": sum(1 for r in wrong if r["review"]), "right_but_reviewed": sum(1 for r in results if r["all_ok"] and r["review"]),
            "examples": results}


def main():
    obs, log, emails = D.time_study(), D.defect_log(), D.quote_emails()
    out = {"suppliers": suppliers(), "mrp": mrp(), "line": line_balance(obs), "quality": quality(log), "automation": automation(emails)}
    (ROOT / "site" / "data.json").write_text(json.dumps(out, separators=(",", ":")))
    L, Q, A = out["line"], out["quality"], out["automation"]
    print("bottleneck", L["bottleneck"], L["cycle_before"], "->", L["cycle_after"], "s; capacity", L["capacity_before"], "->", L["capacity_after"], "/day; takt", L["takt"], "demand", L["demand_per_day"])
    print("pareto top", Q["pareto"][:3], "| p before", round(Q["p_before"], 4), "after", round(Q["p_after"], 4), "| saved", Q["units_saved"])
    print("shortages", [(m["part"], m["first_short_week"], m["order_by_week"]) for m in out["mrp"] if m["first_short_week"]])
    print("extraction", {k: round(v, 3) for k, v in A["field_accuracy"].items()}, "all right", round(A["all_fields_right"], 3),
          "| wrong", A["wrong"], "caught", A["wrong_caught"], "| reviewed", A["routed_to_review"], "of", A["n"], "| right-but-reviewed", A["right_but_reviewed"])
    return out


if __name__ == "__main__":
    main()
