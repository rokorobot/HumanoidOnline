"""HO-DATA-02A gap matrix. Read-only: reads catalogue JSON at a commit + a prod claim export.

usage: python gap_matrix.py <worktree> <prod_claims.json> <out_dir>
"""
import collections, csv, glob, json, os, sys

WT, CLAIMS, OUT = sys.argv[1:4]

PRIORITY = {
    "height_cm": "P0", "weight_kg": "P0", "payload_kg": "P0", "runtime_minutes": "P0",
    "walk_speed_ms": "P0", "degrees_of_freedom": "P0",
    "battery_wh": "P1-tech", "mobility": "P1-tech", "hand_type": "P1-tech", "hand_dof": "P1-tech",
    "has_vision": "P1-tech", "has_sdk": "P1-tech", "has_api": "P1-tech", "ros_support": "P1-tech",
    "simulation_support": "P1-tech", "developer_edition": "P1-tech", "has_language_ui": "P1-tech",
    "autonomy": "P1-capability", "has_manipulation": "P1-capability", "has_teleoperation": "P1-capability",
    "arm_span_cm": "P2", "reach_cm": "P2",
}
BOOLEAN = {k for k in PRIORITY if k.startswith("has_") or k in ("ros_support", "simulation_support", "developer_edition")}

# Manufacturer -> owner-authorized / permitted discovery source (prod discovery_source, 2026-10-22).
SOURCE = {"agibot": "agibot-official", "agility-robotics": "agility-robotics-official",
          "booster-robotics": "booster-robotics-official", "figure-ai": "figure-ai-official",
          "neura-robotics": "neura-robotics-official", "unitree": "unitree-robotics-official",
          "xpeng-robotics": "xpeng-official"}

# Held evidence (prod candidate_claim / discovery_claim_proposal) that maps to a still-UNKNOWN core cell.
# DIRECT = the value states the field's meaning; DECISION = an owner semantic/identity call is needed first.
HELD = {
    ("4ne1-mini", "has_sdk"): ("DIRECT", "datasheet 'ROS2, C++, & Python SDK' (proposal DATASHEET_INTERFACES)"),
    ("4ne1-mini", "ros_support"): ("DIRECT", "datasheet 'ROS2, C++, & Python SDK' (proposal DATASHEET_INTERFACES)"),
    ("4ne1-mini", "walk_speed_ms"): ("DECISION", "'Max. 4.6 km/h' deliberately UNMAPPED: max speed is not walking speed"),
    ("booster-t2-education", "battery_wh"): ("DECISION", "'Battery Rating 48 V, 10 Ah' -> 480 Wh only by V x Ah derivation"),
    ("booster-t2-professional", "battery_wh"): ("DECISION", "'Battery Rating 48 V, 10 Ah' -> 480 Wh only by V x Ah derivation"),
    ("booster-t2-education", "payload_kg"): ("DECISION", "'Maximum Dual-Arm Payload 10 kg*' (footnoted); note keeps payload UNKNOWN"),
    ("booster-t2-professional", "payload_kg"): ("DECISION", "'Maximum Dual-Arm Payload 10 kg*' (footnoted); note keeps payload UNKNOWN"),
    ("booster-t2-education", "has_language_ui"): ("DECISION", "'Large-Model Support: Supported' + mic array/speaker (G1 precedent)"),
    ("booster-t2-professional", "has_language_ui"): ("DECISION", "'Large-Model Support: Supported' + mic array/speaker (G1 precedent)"),
    ("booster-t2-education", "hand_type"): ("DECISION", "'End Effector (Optional): standard, gripper, or dexterous hand' - configuration-dependent"),
    ("booster-t2-professional", "hand_type"): ("DECISION", "'End Effector (Optional): standard, gripper, or dexterous hand' - configuration-dependent"),
    ("unitree-h2-edu", "hand_type"): ("DECISION", "H2 EDU column 'Dexterous Hand (Multiple Model Options)' - option, not fitted spec"),
    ("unitree-r1-edu-u1", "degrees_of_freedom"): ("DECISION", "R1 EDU column '26-40' - range; per-U-edition value not stated"),
    **{(f"unitree-r1-edu-u{i}", "weight_kg"): ("DECISION", "R1 EDU column 'About 29kg' - generic EDU column; U-edition hand fit-out may change mass")
       for i in range(3, 7)},
    # D8: Unitree base-edition columns print '/' for these rows; whether '/' is a stated negative is an owner ruling.
    ("unitree-g1", "has_sdk"): ("DECISION", "G1 column 'Secondary Development: /'"),
    **{(s, f): ("DECISION", f"{s.split('-')[1].upper()} column '{row}: /'")
       for s in ("unitree-h2", "unitree-r1")
       for f, row in (("has_sdk", "Secondary Development"), ("hand_type", "Dexterous Hand"), ("hand_dof", "Dexterous Hand"))},
    ("agility-digit", "reach_cm"): ("DECISION", "'Digit 5' NEW_ENTITY claim 'Reach 2.2m' - identity + vertical-vs-arm reach semantics"),
    ("agility-digit", "runtime_minutes"): ("DECISION", "'Digit 5' 'Work/Shift 20HRS/24HRS', 'Run to charge 10:1' - shift, not battery runtime"),
}
FETCHED_NOT_EXTRACTED = {"agibot-a2-ultra": "https://www.agibot.com/products/A2 fetched by agibot-official; 0 A2 claims extracted (all 70 are X2)"}
OUT_OF_PREFIX = {
    "booster-t1": "booster-robotics-official authorizes /booster-t2, /booster-k1 only",
    "unitree-h1": "unitree-robotics-official authorizes /H2, /R1, /g1 only",
    "figure-02": "figure-ai-official authorizes /figure only (F.03 page)",
}
# Cells whose specs_note records the checked primary source as silent.
_UNI_R1E = ["ros_support", "autonomy", "walk_speed_ms", "battery_wh", "reach_cm", "arm_span_cm"]
SILENT = {
    "1x-neo": ["degrees_of_freedom", "battery_wh"],
    "apptronik-apollo": ["autonomy", "degrees_of_freedom"],
    "unitree-g1": ["walk_speed_ms", "battery_wh", "arm_span_cm"],
    "unitree-g1-edu-plus-u2": ["arm_span_cm", "walk_speed_ms", "autonomy", "battery_wh"],
    "unitree-h1": ["degrees_of_freedom"],
    "unitree-h2": ["walk_speed_ms", "autonomy", "reach_cm", "arm_span_cm", "ros_support", "simulation_support"],
    "unitree-h2-edu": ["walk_speed_ms", "autonomy", "reach_cm", "arm_span_cm", "ros_support", "simulation_support"],
    "unitree-r1": _UNI_R1E + ["simulation_support"],
    **{f"unitree-r1-edu-u{i}": _UNI_R1E for i in range(1, 7)},
    "booster-k1-educational": "*", "booster-k1-geek": "*", "booster-k1-professional": "*",
    "pal-reem-c": "*", "pal-talos": "*",
}

# Records whose own product/spec page an authorized source has already crawled (prod fetched_page). A gap there
# with no mapped claim means the crawled page does not state the field (Alza retail pages are not spec pages).
CRAWLED = {"unitree-g1": "unitree.com/g1", "unitree-g1-edu-plus-u2": "unitree.com/g1 (G1 EDU column)",
           "unitree-h2": "unitree.com/H2", "unitree-h2-edu": "unitree.com/H2 (H2 EDU column)",
           "unitree-r1": "unitree.com/R1", **{f"unitree-r1-edu-u{i}": "unitree.com/R1 (R1 EDU column)" for i in range(1, 7)},
           "booster-t2-education": "booster.tech/booster-t2", "booster-t2-professional": "booster.tech/booster-t2",
           "figure-03": "figure.ai/figure", "4ne1-mini": "neura-robotics.com product pages + datasheet",
           "xpeng-iron": "xpeng.com IRON page + 3 news pages", "agility-digit": "agilityrobotics.com/solutions/digit-5 (identity pending, D7)"}

robots = [json.load(open(f, encoding="utf-8-sig")) for f in sorted(glob.glob(os.path.join(WT, "db/catalogue/robots/*.json")))]
pub = [r for r in robots if r["is_published"]]
claims = json.load(open(CLAIMS, encoding="utf-8"))
claim_robots = {c[0] for c in claims["claims"] if c[0]} | {p[0] for p in claims["proposals"]}


def classify(r, field):
    slug = r["slug"]
    if (slug, field) in HELD:
        kind, why = HELD[(slug, field)]
        return f"HELD_{kind}", why
    if slug in FETCHED_NOT_EXTRACTED:
        return "FETCHED_NOT_EXTRACTED", FETCHED_NOT_EXTRACTED[slug]
    silent = SILENT.get(slug, [])
    if silent == "*" or field in silent:
        return "SOURCE_SILENT", "specs_note: checked primary source does not state it"
    if slug in CRAWLED:
        return "CRAWLED_PAGE_SILENT", f"crawled {CRAWLED[slug]}: no claim states this field"
    if slug in OUT_OF_PREFIX:
        return "SOURCE_PREFIX_EXTENSION", OUT_OF_PREFIX[slug]
    if (r["specs_note"] or "").strip() == "Specifications not yet verified.":
        return "RESEARCH_NEVER_STARTED", "placeholder specs_note; no spec research recorded"
    return "RESEARCH", "no held evidence and no recorded source check for this field"


rows, cells = [], []
for r in pub:
    src = SOURCE.get(r["manufacturer_slug"])
    row = {"slug": r["slug"], "manufacturer": r["manufacturer_slug"], "commercial_status": r["commercial_status"],
           "a4_source": src or "", "has_held_evidence": r["slug"] in claim_robots}
    for field, value in r["specs"].items():
        if value is None:
            cls, why = classify(r, field)
            row[field] = cls
            cells.append({"slug": r["slug"], "field": field, "priority": PRIORITY[field],
                          "kind": "boolean" if field in BOOLEAN else "value", "class": cls, "basis": why,
                          "a4_source": src or "", "commercial_status": r["commercial_status"]})
        else:
            row[field] = "KNOWN"
    rows.append(row)

os.makedirs(OUT, exist_ok=True)
fields = list(PRIORITY)
with open(os.path.join(OUT, "matrix.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, ["slug", "manufacturer", "commercial_status", "a4_source", "has_held_evidence"] + fields)
    w.writeheader(); w.writerows(rows)
with open(os.path.join(OUT, "gap_cells.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, list(cells[0])); w.writeheader(); w.writerows(cells)

n = len(pub)
print("published", n, "cells", n * len(fields), "unknown", len(cells), f"{len(cells) / (n * len(fields)):.1%}")
for tier in ("P0", "P1-tech", "P1-capability", "P2"):
    fs = [f for f in fields if PRIORITY[f] == tier]
    u = sum(1 for c in cells if c["priority"] == tier)
    print(tier, len(fs), "fields", u, "/", n * len(fs), f"{u / (n * len(fs)):.1%}")
vb = [c for c in cells if c["kind"] == "value"]; bb = [c for c in cells if c["kind"] == "boolean"]
print("value-fields unknown", len(vb), "boolean-fields unknown", len(bb))
print("by field:")
for f in fields:
    print(f"  {f:20} {PRIORITY[f]:14} unknown {sum(c['field'] == f for c in cells):2}/{n}")
print("by class:", collections.Counter(c["class"] for c in cells))
print("P0 by class:", collections.Counter(c["class"] for c in cells if c["priority"] == "P0"))
print("robots with held evidence:", sum(r["has_held_evidence"] for r in rows), "of", n)
print("robots with A4 source:", sum(bool(r["a4_source"]) for r in rows))
per = sorted(((sum(1 for c in cells if c["slug"] == r["slug"]), sum(1 for c in cells if c["slug"] == r["slug"] and c["priority"] == "P0"), r["slug"], r["commercial_status"]) for r in rows), reverse=True)
print("per robot (unknown, P0 unknown):")
for t in per:
    print("  ", t)
ext = collections.Counter(e["key"] for r in pub for e in (r.get("extended_specs") or []))
print("robots with any extended spec:", sum(1 for r in pub if r.get("extended_specs")))
print("status:", collections.Counter(r["commercial_status"] for r in pub))
print("no deployment rows:", sum(1 for r in pub if not r["deployments"]), "no capability rows:", sum(1 for r in pub if not r["capabilities"]))
