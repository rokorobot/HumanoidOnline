"""Before/after matching comparison for a use-case-fit change (no database).

The matching engine is a pure function, so a change to `use_case_fits` in the
catalogue JSON can be evaluated without importing anything: this builds the
engine's inputs straight from `db/catalogue/` at two points (a git ref and the
working tree) and reports how the top-4 result moves for a fixed set of
representative buyer requirements.

    python scripts/use_case_matching_regression.py --before origin/main

It mirrors `app/services/matching/repository.load_candidates` with two stated
simplifications, identical on both sides so they cannot create a difference:
capability booleans are read from the raw `specs` (the repository resolves them
through the G4 resolver), and the freshest-evidence tie-break is not populated
(ties fall through to slug order). Use it to see what a fit change does to
ranking, not as a substitute for the API tests.

`--override slug:use_case:score` (score may be `null`) applies a hypothetical
fit to the AFTER side only, to preview a change that is not in the tree.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.matching.engine import match  # noqa: E402
from app.services.matching.inputs import (  # noqa: E402
    OfferInput,
    PriceInput,
    RequirementInput,
    RobotInput,
)

CATALOGUE = "db/catalogue"


def _req(**kw) -> RequirementInput:
    base = dict(
        use_case=None, country=None, payload_min_kg=None, operating_hours_day=None,
        manipulation_required=None, autonomy_required=None, budget_currency=None,
        budget_min=None, budget_max=None, required_by=None, preferred_transaction="UNKNOWN",
    )
    base.update(kw)
    return RequirementInput(**base)


SCENARIOS: list[tuple[str, RequirementInput]] = [
    ("Research & Education, no country, any transaction",
     _req(use_case="research-education")),
    ("Research & Education, Germany, buy",
     _req(use_case="research-education", country="DE", preferred_transaction="BUY")),
    ("Research & Education, Czechia, buy, budget up to EUR 40,000",
     _req(use_case="research-education", country="CZ", preferred_transaction="BUY",
          budget_currency="EUR", budget_max=40000.0)),
    ("Manufacturing, no country, payload 10 kg, manipulation required",
     _req(use_case="manufacturing", payload_min_kg=10.0, manipulation_required=True)),
    ("Warehouse & Logistics, United States, RaaS",
     _req(use_case="warehouse-logistics", country="US", preferred_transaction="RAAS")),
    ("Events & Entertainment, Bulgaria, rent",
     _req(use_case="events-entertainment", country="BG", preferred_transaction="RENT")),
    ("Home, United States, buy",
     _req(use_case="home", country="US", preferred_transaction="BUY")),
    ("Retail & Service, no country, any transaction",
     _req(use_case="retail-service")),
    ("Healthcare & Rehabilitation, no country, any transaction",
     _req(use_case="healthcare-rehabilitation")),
    ("Security & Inspection, no country, any transaction",
     _req(use_case="security-inspection")),
    ("Control: no use case stated, Germany, buy",
     _req(country="DE", preferred_transaction="BUY")),
]


def _read_tree() -> tuple[dict, list[dict]]:
    regions = json.loads((ROOT / CATALOGUE / "regions.json").read_text(encoding="utf-8"))
    robots = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / CATALOGUE / "robots").glob("*.json"))
    ]
    return regions, robots


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, encoding="utf-8"
    ).stdout


def _read_ref(ref: str) -> tuple[dict, list[dict]]:
    regions = json.loads(_git("show", f"{ref}:{CATALOGUE}/regions.json"))
    names = _git("ls-tree", "--name-only", f"{ref}", f"{CATALOGUE}/robots/").split()
    robots = [json.loads(_git("show", f"{ref}:{n}")) for n in sorted(names) if n.endswith(".json")]
    return regions, robots


def _applicable(regions: dict, country: str | None) -> set[str] | None:
    """The country, its ancestor regions and GLOBAL. None = geography inactive."""
    if country is None:
        return None
    parent = {r["code"]: r.get("parent_code") for r in regions["regions"]}
    out = {"GLOBAL"}
    code: str | None = country
    while code is not None and code not in out:
        out.add(code)
        code = parent.get(code)
    return out


def candidates(regions: dict, robots: list[dict], req: RequirementInput) -> list[RobotInput]:
    applicable = _applicable(regions, req.country)

    def geo_ok(code: str | None) -> bool:
        return applicable is None or code is None or code in applicable

    out: list[RobotInput] = []
    for r in robots:
        if not r.get("is_published"):
            continue
        specs = r.get("specs") or {}
        fit = None
        for f in r.get("use_case_fits") or []:
            if f["use_case_slug"] == req.use_case:
                fit = f.get("fit_score")
                break
        offers = tuple(
            OfferInput(
                transaction_type=o["transaction_type"],
                availability_status=o["availability_status"],
                is_current=o.get("is_current", True),
                region_code=None,
                geo_applicable=geo_ok(o.get("region_code")),
                available_from=None,
            )
            for o in r.get("availability_offers") or []
            if o.get("condition", "NEW") == "NEW"
        )
        prices = tuple(
            PriceInput(
                transaction_type=p["transaction_type"],
                price_type=p["price_type"],
                currency=p.get("currency"),
                price=p.get("price"),
                price_min=p.get("price_min"),
                price_max=p.get("price_max"),
                billing_period=p.get("billing_period", "ONE_TIME"),
                is_current=p.get("is_current", True),
                geo_applicable=geo_ok(p.get("region_code")),
            )
            for p in r.get("pricing_offers") or []
            if p.get("edition_confirmed") is not False and p.get("condition", "NEW") == "NEW"
        )
        out.append(
            RobotInput(
                slug=r["slug"], name=r["name"], manufacturer_name=r["manufacturer_slug"],
                manufacturer_country=None, commercial_status=r["commercial_status"],
                payload_kg=specs.get("payload_kg"),
                has_manipulation=specs.get("has_manipulation"),
                autonomy=specs.get("autonomy"),
                runtime_minutes=specs.get("runtime_minutes"),
                has_sdk=specs.get("has_sdk"), ros_support=specs.get("ros_support"),
                developer_edition=specs.get("developer_edition"),
                use_case_fit=fit, offers=offers, prices=prices,
                deployment_count=len(r.get("deployments") or []),
            )
        )
    return out


def _apply_overrides(robots: list[dict], overrides: list[str]) -> None:
    for spec in overrides:
        slug, use_case, score = spec.split(":")
        value = None if score == "null" else float(score)
        robot = next(r for r in robots if r["slug"] == slug)
        fits = robot.setdefault("use_case_fits", [])
        for f in fits:
            if f["use_case_slug"] == use_case:
                f["fit_score"] = value
                break
        else:
            fits.append({"use_case_slug": use_case, "fit_score": value})


def _fmt(outcome) -> list[str]:
    return [f"{m.rank}. {m.slug} ({m.score})" for m in outcome.matches]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", default="origin/main", help="git ref for the BEFORE catalogue")
    ap.add_argument("--override", action="append", default=[], metavar="SLUG:USE_CASE:SCORE")
    args = ap.parse_args()

    before = _read_ref(args.before)
    after = _read_tree()
    _apply_overrides(after[1], args.override)

    changed = 0
    print(f"# Matching comparison: {args.before} -> working tree")
    if args.override:
        print(f"\nHypothetical overrides on the AFTER side: {', '.join(args.override)}")
    for title, req in SCENARIOS:
        b = match(req, candidates(*before, req))
        a = match(req, candidates(*after, req))
        same = _fmt(b) == _fmt(a)
        changed += not same
        print(f"\n## {title}\n\n{'UNCHANGED' if same else 'CHANGED'}\n")
        print("| Rank | Before | After |\n|---|---|---|")
        fb, fa = _fmt(b), _fmt(a)
        for i in range(max(len(fb), len(fa))):
            left = fb[i].split(". ", 1)[1] if i < len(fb) else ""
            right = fa[i].split(". ", 1)[1] if i < len(fa) else ""
            print(f"| {i + 1} | {left} | {right} |")
    print(f"\n{changed} of {len(SCENARIOS)} scenarios changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
