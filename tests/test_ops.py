from ops import analysis as A
from ops import data as D


def run():
    if not hasattr(run, "out"):
        run.out = A.main()
    return run.out


def test_bottleneck_is_above_takt_and_rebalancing_fixes_it():
    L = run()["line"]
    assert L["bottleneck"] == "Calibrate"
    assert L["cycle_before"] > L["takt"] > L["cycle_after"]
    assert L["capacity_before"] < L["demand_per_day"] <= L["capacity_after"]


def test_interruptions_are_kept_out_of_standard_times():
    for s in run()["line"]["steps"]:
        assert s["mean"] < max(s["observations"])


def test_lens_fix_is_a_real_shift_not_noise():
    Q = run()["quality"]
    assert Q["pareto"][0][0] == "Lens misaligned"
    assert sum(1 for c in Q["chart"] if c["week"] >= 7 and c["p"] < c["lcl"]) >= 4


def test_delayed_po_creates_an_early_shortage_that_needs_expediting():
    m = next(x for x in run()["mrp"] if x["part"] == "P-101")
    assert m["first_short_week"] == 4 and m["order_by_week"] <= 0


def test_every_wrong_extraction_is_routed_to_a_person():
    a = run()["automation"]
    assert a["wrong"] > 0 and a["wrong_caught"] == a["wrong"]


def test_clean_emails_extract_exactly():
    e = "Apex Components quotation\nPart: P-102\nUnit price: USD 11.20\nMinimum order: 250 pcs\nLead time: 6 wks"
    assert A.extract(e) == {"part": "P-102", "supplier": "Apex Components", "price": 11.20, "moq": 250, "lead_weeks": 6}


def test_landed_cost_is_never_below_price():
    assert all(s["landed"] >= s["price"] for s in run()["suppliers"])
