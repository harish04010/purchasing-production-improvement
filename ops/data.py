"""
Generated operating data for a fictional small electronics assembler, Brightline Instruments,
which builds two handheld measurement devices (the HM-1 and the HM-2) on one assembly line.
Seeded, so every run gives the same numbers. Nothing here describes a real company.
"""
import random

rng = random.Random(7)

SUPPLIERS = {"Apex Components": {"otd": 0.96, "ppm": 350}, "Northline Parts": {"otd": 0.88, "ppm": 900},
             "Coastal Electronics": {"otd": 0.93, "ppm": 1500}}

PARTS = [  # part, description, annual qty, quotes: supplier -> (unit price, lead time weeks, MOQ)
    ("P-101", "Optical sensor module", 70000, {"Apex Components": (18.40, 8, 500), "Northline Parts": (16.90, 10, 1000), "Coastal Electronics": (15.75, 12, 1000)}),
    ("P-102", "Main PCB assembly", 70000, {"Apex Components": (11.20, 6, 250), "Northline Parts": (10.60, 7, 500), "Coastal Electronics": (10.10, 9, 500)}),
    ("P-103", "LiPo battery 2000mAh", 70000, {"Apex Components": (4.85, 5, 500), "Northline Parts": (4.60, 6, 500), "Coastal Electronics": (4.20, 8, 1000)}),
    ("P-104", "Molded housing (front)", 70000, {"Apex Components": (1.95, 4, 1000), "Northline Parts": (1.70, 5, 2000), "Coastal Electronics": (1.82, 4, 1000)}),
    ("P-105", "Molded housing (rear)", 70000, {"Apex Components": (1.80, 4, 1000), "Northline Parts": (1.62, 5, 2000), "Coastal Electronics": (1.71, 4, 1000)}),
    ("P-106", "Display 1.3in OLED", 35000, {"Apex Components": (6.30, 7, 250), "Northline Parts": (5.95, 8, 500), "Coastal Electronics": (5.40, 10, 500)}),
    ("P-107", "USB-C connector", 70000, {"Apex Components": (0.62, 3, 1000), "Northline Parts": (0.55, 4, 2000), "Coastal Electronics": (0.49, 6, 5000)}),
    ("P-108", "Lens window", 70000, {"Apex Components": (0.88, 5, 1000), "Northline Parts": (0.81, 6, 1000), "Coastal Electronics": (0.74, 7, 2000)}),
]

PRODUCTS = {"HM-1": {"P-101": 1, "P-102": 1, "P-103": 1, "P-104": 1, "P-105": 1, "P-107": 1, "P-108": 1},
            "HM-2": {"P-101": 1, "P-102": 1, "P-103": 1, "P-104": 1, "P-105": 1, "P-106": 1, "P-107": 1, "P-108": 1}}
_PLAN = {"HM-1": [40, 45, 45, 50, 50, 55, 55, 60, 60, 60, 55, 55], "HM-2": [35, 40, 40, 45, 45, 50, 55, 55, 60, 60, 60, 55]}
SCALE = 15   # units per week = plan x 15 (about 300 a day by the end of the quarter)
BUILD_PLAN = {k: [v * SCALE for v in vs] for k, vs in _PLAN.items()}
ON_HAND = {k: v * 15 for k, v in {"P-101": 260, "P-102": 520, "P-103": 610, "P-104": 900, "P-105": 880, "P-106": 240, "P-107": 1800, "P-108": 1200}.items()}
OPEN_POS = [  # part, supplier, qty, due week, now-expected week (one supplier just pushed a delivery out)
    ("P-101", "Northline Parts", 7500, 4, 7), ("P-102", "Apex Components", 7500, 3, 3), ("P-103", "Apex Components", 7500, 5, 5),
    ("P-106", "Coastal Electronics", 7500, 6, 6), ("P-108", "Apex Components", 15000, 8, 8)]

STEPS = [  # assembly step, mean seconds, sd
    ("Kit parts", 38, 4), ("Install PCB + sensor", 74, 7), ("Solder battery leads", 52, 6), ("Fit display + lens", 61, 6),
    ("Close housing", 44, 4), ("Calibrate", 96, 9), ("Test + pack", 49, 5)]
TASKS_MOVABLE = {"Calibrate": [("Warm-up and zero reference", 28)]}   # can move to the previous station with a second fixture

DEFECT_TYPES = ["Lens misaligned", "Solder bridge on battery leads", "Housing gap", "Display dead pixels", "Calibration out of spec",
                "Missing screw", "Scratched lens", "USB-C loose"]


def time_study():
    """30 observed cycles per step, with occasional interruptions (part hunting, fixture jams)."""
    obs = {}
    for name, mu, sd in STEPS:
        xs = []
        for _ in range(30):
            x = rng.gauss(mu, sd)
            if rng.random() < 0.07:
                x += rng.uniform(25, 60)         # interruption: logged separately, excluded from standard time
            xs.append(round(x, 1))
        obs[name] = xs
    return obs


def defect_log():
    """12 weeks of inspection results. Lens misalignment dominates until a worn fixture is replaced in week 7."""
    weeks = []
    for w in range(1, 13):
        built = sum(BUILD_PLAN[p][w - 1] for p in BUILD_PLAN)
        counts = {}
        for i, t in enumerate(DEFECT_TYPES):
            rate = [0.031, 0.012, 0.009, 0.006, 0.006, 0.004, 0.003, 0.002][i]
            if t == "Lens misaligned" and w >= 7:
                rate = 0.006                      # fixture replaced and locating pins added in week 7
            if t == "Lens misaligned" and 4 <= w < 7:
                rate = 0.038                      # fixture wear getting worse
            counts[t] = sum(1 for _ in range(built) if rng.random() < rate)
        weeks.append({"week": w, "inspected": built, "defects": counts})
    return weeks


def quote_emails():
    """Supplier quote emails in the formats suppliers actually send, with the true values for checking."""
    templates = [
        "Hi, quoting {part} ({desc}): ${price} each at MOQ {moq}, lead time {lt} weeks. Regards, {sup}",
        "{sup} quotation\nPart: {part}\nUnit price: USD {price}\nMinimum order: {moq} pcs\nLead time: {lt} wks",
        "Re: RFQ {part} - we can do {price} USD/unit, {lt}-week lead time, min {moq}. Thanks! {sup}",
        "Price for {desc} ({part}) is ${price} per piece. Lead time approx {lt} weeks from PO. MOQ: {moq}. -- {sup}",
        "Quote attached. Summary: {part}, {moq} pcs minimum, delivery {ltd} days ARO, ${price}/ea. {sup}",
        # the awkward ones real inboxes contain: price per hundred, MOQ in thousands, lead time in words
        "{sup}: {part} {desc} - {price100} USD per 100 pcs, MOQ {moqk}, lead time {ltword} weeks.",
    ]
    words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 12: "twelve"}
    emails = []
    for part, desc, _, quotes in PARTS:
        for sup, (price, lt, moq) in quotes.items():
            t = rng.choice(templates)
            p = price * rng.choice([1, 1, 1, 0.97, 1.03])
            emails.append({"text": t.format(part=part, desc=desc, price=f"{p:.2f}", moq=moq, lt=lt, ltd=lt * 7, sup=sup, price100=f"{p * 100:.2f}",
                                            moqk=f"{moq // 1000}k" if moq % 1000 == 0 else moq, ltword=words.get(lt, lt)),
                           "truth": {"part": part, "supplier": sup, "price": round(p, 2), "moq": moq, "lead_weeks": lt}})
    return emails
