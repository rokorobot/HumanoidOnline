"""Author canonical catalogue entries, and fill their specifications by hand.

The verified catalogue is hand-authored JSON under `db/catalogue/`, imported by
`db/import_catalogue.py`. That is how all seven original robots got in: a person
read official pages, typed what was there, left the rest null, and attached
evidence to the *commercial* facts. Nothing about it requires the DATA-D1
discovery pipeline — discovery is the road for entities arriving from outside,
and this is the road for robots whose existence and maker are already known.

Two commands, for the two halves of that job:

    # 1) create identity-only stubs for robots not yet in the catalogue
    uv run db/catalogue_entries.py stubs --from humanoid_radar_v1

    # 2) export a per-robot block, fill it in, apply it back
    uv run db/catalogue_entries.py export --out var/catalogue/specs.json
    uv run db/catalogue_entries.py apply var/catalogue/specs.json \
        --operator "robert@humanoid.company"

**Stubs are honest, not empty.** A stub asserts identity, manufacturer and an
official URL, sets `commercial_status = ANNOUNCED`, leaves every specification
`null`, and says so in `specs_note`. It makes no commercial claim, so there is
no commercial fact for G2 to demand evidence of — verified by importing one.

**Stubs are unpublished.** `is_published` is false, because publishing a sparse
profile is a product decision (imagery, presentation, sitemap exposure, whether
an all-UNKNOWN robot joins buyer matching) and not a side effect of authoring.

**Specifications carry no per-field evidence in the canonical model** —
`commercial_status_evidence`, `pricing_offers` and `deployments` do, `specs` does
not. So this tool records the source URL and retrieval date for the block into
`specs_note` rather than leaving provenance to memory. That is convention doing
the work of a schema, which is worth knowing when reading a spec later.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = REPO_ROOT / "db" / "catalogue"
ROBOTS_DIR = CATALOGUE / "robots"
MANUFACTURERS = CATALOGUE / "manufacturers.json"
BOOTSTRAP_DIR = REPO_ROOT / "db" / "discovery" / "bootstrap"

WORKSHEET_VERSION = 1

#: The specification fields a canonical robot carries, in the order they appear
#: in an existing catalogue file. Numeric unless noted.
SPEC_FIELDS: tuple[str, ...] = (
    "height_cm", "weight_kg", "arm_span_cm", "reach_cm", "payload_kg",
    "walk_speed_ms", "runtime_minutes",
    "battery_wh", "mobility", "degrees_of_freedom", "hand_type", "hand_dof",
    "autonomy", "has_manipulation", "has_teleoperation", "has_vision",
    "has_language_ui", "has_sdk", "has_api", "ros_support", "developer_edition",
    "simulation_support",
)
_NUMERIC = {
    "height_cm", "weight_kg", "arm_span_cm", "reach_cm", "payload_kg",
    "walk_speed_ms", "runtime_minutes", "battery_wh", "degrees_of_freedom",
    "hand_dof",
}
_BOOLEAN = {
    "has_manipulation", "has_teleoperation", "has_vision", "has_language_ui",
    "has_sdk", "has_api", "ros_support", "developer_edition", "simulation_support",
}
_ENUM = {
    "mobility": {"BIPEDAL", "WHEELED", "HYBRID", "QUADRUPED", "STATIONARY", "OTHER"},
    "autonomy": {
        "TELEOPERATED", "ASSISTED", "SUPERVISED_AUTONOMY", "TASK_AUTONOMOUS",
        "HIGHLY_AUTONOMOUS",
    },
}

UNVERIFIED_NOTE = "Specifications not yet verified."

#: Generic corporate words dropped when deriving a slug, matching the existing
#: catalogue's own convention (`agility-robotics` -> `agility-digit`).
#: `dynamics` is deliberately NOT here — it is part of the brand in "Boston
#: Dynamics" and "LimX Dynamics", and dropping it yields a meaningless `boston`.
_SUFFIXES = ("robotics", "technologies", "technology", "robots", "ai", "inc",
             "ltd", "llc", "corp", "co", "company", "labs", "lab")


class AuthoringError(RuntimeError):
    """Refusal. Raised before anything is written."""


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def manufacturer_slug(name: str) -> str:
    return slugify(name)


def brand_token(mfr_slug: str) -> str:
    """The brand part of a manufacturer slug, corporate suffixes removed."""
    parts = [p for p in mfr_slug.split("-") if p not in _SUFFIXES]
    return "-".join(parts) or mfr_slug


def robot_slug(mfr_name: str, robot_name: str) -> str:
    """`<brand>-<model>`, without repeating the brand when the model already
    carries it: "Figure AI" + "Figure 01" is `figure-01`, matching the existing
    `figure-02`, not `figure-figure-01`."""
    brand = brand_token(manufacturer_slug(mfr_name))
    model = slugify(robot_name)
    lead = brand.split("-")[0]
    if model == lead or model.startswith(f"{lead}-"):
        return f"{brand[:len(lead)]}{model[len(lead):]}" if model.startswith(lead) else model
    return f"{brand}-{model}"


def _norm(value: str | None) -> str:
    """Loose comparison key for matching a bootstrap name to an existing entry."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def load_manufacturers() -> dict:
    return json.loads(MANUFACTURERS.read_text(encoding="utf-8"))


def existing_robots() -> dict[str, dict]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(ROBOTS_DIR.glob("*.json"))
    }


def load_bootstrap(dataset: str) -> list[dict]:
    path = BOOTSTRAP_DIR / f"{dataset}.json"
    if not path.is_file():
        available = sorted(p.stem for p in BOOTSTRAP_DIR.glob("*.json"))
        raise AuthoringError(f"no dataset {dataset!r} in {BOOTSTRAP_DIR}; have {available}")
    return json.loads(path.read_text(encoding="utf-8"))


def make_stub(*, slug: str, name: str, mfr_slug: str, official_url: str | None) -> dict:
    """An identity-only catalogue entry. Asserts existence and maker, nothing else."""
    return {
        "slug": slug,
        "name": name,
        "manufacturer_slug": mfr_slug,
        "model_code": None,
        "summary": None,
        "announced_year": None,
        # ANNOUNCED is the absence of a maturity claim, not a claim of immaturity
        # (docs/16 §6): it must never be read as NOT_AVAILABLE.
        "commercial_status": "ANNOUNCED",
        # Authoring is not publishing. See the module docstring.
        "is_published": False,
        "specs": dict.fromkeys(SPEC_FIELDS),
        "specs_note": UNVERIFIED_NOTE,
        "official_url": official_url,
        "commercial_status_evidence": [],
        "variants": [],
        "pricing_offers": [],
        "availability_offers": [],
        "deployments": [],
        "capabilities": [],
        "use_case_fits": [],
        "images": [],
    }


def make_manufacturer_stub(*, slug: str, name: str, website: str | None) -> dict:
    return {
        "slug": slug,
        "name": name,
        "legal_name": None,
        "country_region_code": None,
        "website_url": website,
        "founded_year": None,
        "description": None,
        "target_markets": [],
        "commercial_model": None,
        "deployment_status": None,
        "is_public_company": False,
        "ticker": None,
        "evidence": [],
    }


def plan_stubs(dataset: str) -> dict:
    """Work out what is missing. Pure — writes nothing."""
    records = load_bootstrap(dataset)
    mfr_doc = load_manufacturers()
    # Match on BOTH the recorded name and the slug. A catalogue entry named
    # "Figure" carries the slug `figure-ai`, while the bootstrap calls the same
    # company "Figure AI" — matching on name alone appends a second
    # manufacturer whose slug collides with the first.
    known_mfrs: dict[str, str] = {}
    known_slugs: set[str] = set()
    for m in mfr_doc["manufacturers"]:
        known_mfrs[_norm(m["name"])] = m["slug"]
        known_mfrs[_norm(m["slug"])] = m["slug"]
        known_slugs.add(m["slug"])
    robots = existing_robots()
    known_robots = {
        (_norm(r.get("manufacturer_slug")), _norm(r.get("name"))): slug
        for slug, r in robots.items()
    }

    new_mfrs: dict[str, dict] = {}
    new_robots: list[dict] = []
    skipped: list[dict] = []

    for rec in records:
        mfr_name = str(rec["manufacturer"])
        name = str(rec["name"])
        official = (rec.get("data") or {}).get("official_url") or rec.get("discovery_url")

        derived = manufacturer_slug(mfr_name)
        mslug = known_mfrs.get(_norm(mfr_name)) or known_mfrs.get(_norm(derived)) or derived
        if mslug not in known_slugs and mslug not in new_mfrs:
            new_mfrs[mslug] = make_manufacturer_stub(
                slug=mslug, name=mfr_name,
                website=_origin(official),
            )

        # Already catalogued? Match on (manufacturer, model), not on a guessed slug.
        if (_norm(mslug), _norm(name)) in known_robots:
            skipped.append({"name": name, "manufacturer": mfr_name,
                            "slug": known_robots[(_norm(mslug), _norm(name))],
                            "why": "already in the catalogue"})
            continue

        slug = robot_slug(mfr_name, name)
        if slug in robots or any(r["slug"] == slug for r in new_robots):
            skipped.append({"name": name, "manufacturer": mfr_name, "slug": slug,
                            "why": "slug collision — rename by hand"})
            continue

        new_robots.append(make_stub(slug=slug, name=name, mfr_slug=mslug,
                                    official_url=official))

    return {"manufacturers": list(new_mfrs.values()), "robots": new_robots,
            "skipped": skipped}


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    m = re.match(r"^(https?://[^/]+)", url)
    return m.group(1) if m else None


def write_stubs(plan: dict) -> dict:
    """Write the planned stubs. Never overwrites an existing robot file."""
    written: list[str] = []
    for robot in plan["robots"]:
        path = ROBOTS_DIR / f"{robot['slug']}.json"
        if path.exists():
            raise AuthoringError(f"refusing to overwrite {path}")
        path.write_text(json.dumps(robot, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        written.append(robot["slug"])

    if plan["manufacturers"]:
        doc = load_manufacturers()
        doc["manufacturers"].extend(plan["manufacturers"])
        doc["manufacturers"].sort(key=lambda m: m["slug"])
        MANUFACTURERS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    return {"robots": written,
            "manufacturers": [m["slug"] for m in plan["manufacturers"]]}


# ----------------------------------------------------------- spec worksheet --

def export_worksheet(*, only_incomplete: bool = True) -> dict:
    """One block per robot, every field in one place.

    Single-operator by design: there is one `--operator` for the whole file and
    no per-row attribution, because splitting entry across people needs a
    different shape and a different audit story.
    """
    blocks = []
    for slug, robot in sorted(existing_robots().items()):
        specs = robot.get("specs") or {}
        missing = [f for f in SPEC_FIELDS if specs.get(f) is None]
        if only_incomplete and not missing:
            continue
        blocks.append({
            "slug": slug,
            "_name": robot.get("name"),
            "_manufacturer_slug": robot.get("manufacturer_slug"),
            "_official_url": robot.get("official_url"),
            "_missing": len(missing),
            "source_url": "",
            "retrieved_on": "",
            "specs": {f: specs.get(f) for f in SPEC_FIELDS},
        })
    return {
        "worksheet_version": WORKSHEET_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "robot_count": len(blocks),
        "instructions": [
            "One block per robot. Open its `_official_url`, then fill `specs`.",
            "Leave a field null when the page does not state it — null means",
            "UNKNOWN and is always the honest answer. Never guess, never infer",
            "0 or false from silence.",
            "Set `source_url` to the page you read and `retrieved_on` to today",
            "(YYYY-MM-DD). Both are required for any block you change: the",
            "canonical model carries no per-spec evidence, so this note is the",
            "only provenance a later reader will have.",
            "Fields beginning with '_' are context and are ignored on apply.",
            f"mobility: {sorted(_ENUM['mobility'])}",
            f"autonomy: {sorted(_ENUM['autonomy'])}",
        ],
        "robots": blocks,
    }


def _coerce(field: str, value):
    """Validate one entered value, or refuse it. Null always passes: UNKNOWN."""
    if value is None or value == "":
        return None
    if field in _BOOLEAN:
        if isinstance(value, bool):
            return value
        raise AuthoringError(f"{field}: expected true/false/null, got {value!r}")
    if field in _NUMERIC:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise AuthoringError(f"{field}: expected a number or null, got {value!r}") from None
        if number <= 0:
            raise AuthoringError(
                f"{field}: {number} is not a plausible measurement. A zero or "
                "negative spec is almost always a mis-keyed UNKNOWN; leave it null."
            )
        return int(number) if field in {"runtime_minutes", "degrees_of_freedom",
                                        "hand_dof"} else number
    if field in _ENUM:
        text = str(value).strip().upper()
        if text not in _ENUM[field]:
            raise AuthoringError(f"{field}: {value!r} is not one of {sorted(_ENUM[field])}")
        return text
    return str(value).strip() or None


def apply_worksheet(worksheet: dict, *, operator: str, dry_run: bool = True) -> dict:
    """Write entered specifications back into the catalogue files."""
    if not operator or not operator.strip():
        raise AuthoringError("spec entry requires a named operator")
    if worksheet.get("worksheet_version") != WORKSHEET_VERSION:
        raise AuthoringError(
            f"worksheet version {worksheet.get('worksheet_version')!r} is not "
            f"{WORKSHEET_VERSION} — re-export rather than editing an old file"
        )

    robots = existing_robots()
    changes: list[dict] = []

    for block in worksheet.get("robots", []):
        slug = block.get("slug")
        robot = robots.get(slug)
        if robot is None:
            raise AuthoringError(f"{slug}: no such catalogue robot")

        current = robot.get("specs") or {}
        entered = block.get("specs") or {}
        updates: dict = {}
        for field in SPEC_FIELDS:
            value = _coerce(field, entered.get(field))
            if value != current.get(field):
                updates[field] = value
        if not updates:
            continue

        source = str(block.get("source_url") or "").strip()
        retrieved = str(block.get("retrieved_on") or "").strip()
        if not source or not retrieved:
            raise AuthoringError(
                f"{slug}: changed specifications require source_url and "
                "retrieved_on — a spec with no recorded source is the invention "
                "of market data by keyboard"
            )
        try:
            date.fromisoformat(retrieved)
        except ValueError:
            raise AuthoringError(f"{slug}: retrieved_on {retrieved!r} is not YYYY-MM-DD") from None

        changes.append({"slug": slug, "fields": updates, "source_url": source,
                        "retrieved_on": retrieved})

    if not dry_run:
        for change in changes:
            path = ROBOTS_DIR / f"{change['slug']}.json"
            robot = json.loads(path.read_text(encoding="utf-8"))
            robot.setdefault("specs", {}).update(change["fields"])
            remaining = [f for f in SPEC_FIELDS if robot["specs"].get(f) is None]
            robot["specs_note"] = (
                f"Entered by {operator.strip()} from {change['source_url']} "
                f"(retrieved {change['retrieved_on']})."
                + (f" {len(remaining)} field(s) not stated by the source and left"
                   " UNKNOWN." if remaining else "")
            )
            path.write_text(json.dumps(robot, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    return {"changed": changes, "dry_run": dry_run}


# ------------------------------------------------------------------- CLI ----

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Author canonical catalogue entries")
    sub = ap.add_subparsers(dest="command", required=True)

    st = sub.add_parser("stubs", help="create identity-only entries for missing robots")
    st.add_argument("--from", dest="dataset", default="humanoid_radar_v1")
    st.add_argument("--write", action="store_true", help="write; without it, dry run")

    ex = sub.add_parser("export", help="export a specification worksheet")
    ex.add_argument("--out", help="worksheet path; omit for stdout")
    ex.add_argument("--all", action="store_true", help="include already-complete robots")

    sub.add_parser("images-pending", help="list robots with no image yet")

    ia = sub.add_parser("images-apply", help="record confirmed images (downloads them)")
    ia.add_argument("worksheet")
    ia.add_argument("--write", action="store_true", help="download and write; else dry run")

    apl = sub.add_parser("apply", help="apply an edited worksheet")
    apl.add_argument("worksheet")
    apl.add_argument("--operator", required=True)
    apl.add_argument("--write", action="store_true", help="write; without it, dry run")

    args = ap.parse_args(argv)

    try:
        if args.command == "stubs":
            plan = plan_stubs(args.dataset)
            print(f"{len(plan['robots'])} new robot(s), "
                  f"{len(plan['manufacturers'])} new manufacturer(s), "
                  f"{len(plan['skipped'])} skipped")
            for s in plan["skipped"]:
                print(f"  SKIP  {s['manufacturer']} {s['name']}: {s['why']}")
            if not args.write:
                print("\nDry run. Re-run with --write to create the files.")
                return 0
            done = write_stubs(plan)
            print(f"wrote {len(done['robots'])} robot file(s), "
                  f"added {len(done['manufacturers'])} manufacturer(s)")
            print("All stubs are is_published=false. Publishing is a separate decision.")
            return 0

        if args.command == "images-pending":
            pending = robots_without_images()
            print(f"{len(pending)} robot(s) without an image")
            for slug in pending:
                print(f"  {slug}")
            return 0

        if args.command == "images-apply":
            sheet = json.loads(Path(args.worksheet).read_text(encoding="utf-8"))
            result = apply_image_worksheet(sheet, dry_run=not args.write)
            mode = "DRY RUN - nothing downloaded" if result["dry_run"] else "WRITTEN"
            print(f"[{mode}]")
            for a in result["applied"]:
                size = f" ({a['bytes']} bytes)" if a["bytes"] else ""
                print(f"  IMAGE   {a['slug']} -> {a['image_url']}{size}")
            for r in result["rejected"]:
                print(f"  REJECT  {r['slug']}: {r['why']}")
            for s_ in result["skipped"]:
                print(f"  PENDING {s_['slug']}: {s_['why']}")
            if result["dry_run"] and result["applied"]:
                print("Re-run with --write to download and record.")
            return 0

        if args.command == "export":
            sheet = export_worksheet(only_incomplete=not args.all)
            if args.out:
                path = Path(args.out)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(sheet, indent=2, ensure_ascii=False),
                                encoding="utf-8")
                print(f"wrote {sheet['robot_count']} robot block(s) to {path}")
            else:
                print(json.dumps(sheet, indent=2, ensure_ascii=False))
            return 0

        sheet = json.loads(Path(args.worksheet).read_text(encoding="utf-8"))
        result = apply_worksheet(sheet, operator=args.operator, dry_run=not args.write)
        mode = "DRY RUN - nothing written" if result["dry_run"] else "WRITTEN"
        print(f"[{mode}]  operator={args.operator}")
        for change in result["changed"]:
            print(f"  {change['slug']}: {len(change['fields'])} field(s) "
                  f"<- {change['source_url']}")
        if not result["changed"]:
            print("  no changes")
        elif result["dry_run"]:
            print("\nRe-run with --write to apply.")
        return 0

    except AuthoringError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2



# --------------------------------------------------------------- images -----
# MEDIA-01. The catalogue self-hosts images under apps/web/public/robots/, with
# provenance recorded per file. Six of the original seven are
# MANUFACTURER / OFFICIAL_MANUFACTURER_MEDIA taken from the maker's own site;
# Figure 02 is the EDITORIAL / ATTRIBUTION_REQUIRED exception and still displays.
#
# The gate this tool exists to protect: `identity_status = VERIFIED` means a
# HUMAN looked at the picture and confirmed it shows THAT model. Software cannot
# establish that — a correctly licensed, properly attributed photo of the wrong
# robot is the failure mode this catalogue has already met once, when a licensed
# image search offered an Istanbul tram for Booster's T1. So a candidate carries
# `confirmed_by` empty, and nothing is downloaded or recorded until a named
# person fills it in.

PUBLIC_ROBOT_IMAGES = REPO_ROOT / "apps" / "web" / "public" / "robots"

IMAGE_SOURCE_TYPES = {"MANUFACTURER", "PRESS_KIT", "DISTRIBUTOR", "EDITORIAL", "VIDEO_FRAME"}
IMAGE_TYPES = {"FRONT", "SIDE", "REAR", "ACTION", "WORKPLACE", "DETAIL", "DIMENSIONS"}
RIGHTS_STATUSES = {"UNKNOWN", "ATTRIBUTION_REQUIRED", "LICENSED", "PERMISSION_GRANTED"}
USAGE_BASES = {"OFFICIAL_MANUFACTURER_MEDIA", "PRESS_KIT_TERMS", "LICENCE", "PERMISSION", "NONE"}

#: Content types we will store, and the extension each becomes on disk.
IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png",
    "image/webp": ".webp", "image/avif": ".avif",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def robots_without_images() -> list[str]:
    return [slug for slug, r in existing_robots().items() if not (r.get("images") or [])]


def image_candidate(*, slug: str, image_url: str, source_url: str, source_name: str,
                    source_type: str = "MANUFACTURER", image_type: str = "FRONT",
                    attribution: str = "", note: str = "") -> dict:
    """One proposal, awaiting a human identity decision."""
    return {
        "slug": slug,
        "image_url": image_url,
        "source_url": source_url,
        "source_name": source_name,
        "source_type": source_type,
        "image_type": image_type,
        "attribution": attribution,
        "note": note,
        # --- the human gate ---
        "confirmed_by": "",          # a named person, or nothing happens
        "decision": "",              # confirm | reject
        "reject_reason": "",
    }


def _validate_image_row(row: dict) -> None:
    where = f"{row.get('slug', '?')}"
    for field in ("slug", "image_url", "source_url", "source_name"):
        if not str(row.get(field) or "").strip():
            raise AuthoringError(f"{where}: {field} is required")
    if row["source_type"] not in IMAGE_SOURCE_TYPES:
        raise AuthoringError(f"{where}: source_type must be one of {sorted(IMAGE_SOURCE_TYPES)}")
    if row["image_type"] not in IMAGE_TYPES:
        raise AuthoringError(f"{where}: image_type must be one of {sorted(IMAGE_TYPES)}")
    decision = (row.get("decision") or "").strip().lower()
    if decision not in {"", "confirm", "reject"}:
        raise AuthoringError(f"{where}: decision must be 'confirm', 'reject' or empty")
    if decision == "confirm" and not str(row.get("confirmed_by") or "").strip():
        raise AuthoringError(
            f"{where}: 'confirm' requires confirmed_by — identity_status VERIFIED "
            "means a NAMED PERSON looked at the picture and recognised the robot. "
            "Software cannot establish that."
        )
    if decision == "reject" and not str(row.get("reject_reason") or "").strip():
        raise AuthoringError(f"{where}: 'reject' requires a reject_reason")
    if not str(row.get("image_url", "")).lower().startswith(("http://", "https://")):
        raise AuthoringError(f"{where}: image_url must be an http(s) URL")


def rights_for(source_type: str) -> tuple[str, str, bool]:
    """`(rights_status, usage_basis, is_official)` by the catalogue's own precedent."""
    if source_type in {"MANUFACTURER", "PRESS_KIT"}:
        return "UNKNOWN", "OFFICIAL_MANUFACTURER_MEDIA", True
    # The Figure 02 precedent: an editorially retrieved image that merely credits
    # the maker is EDITORIAL with attribution required, never OFFICIAL.
    return "ATTRIBUTION_REQUIRED", "NONE", False


def apply_image_worksheet(worksheet: dict, *, dry_run: bool = True) -> dict:
    """Record confirmed images. Downloads only what a named human confirmed."""
    import urllib.request

    rows = worksheet.get("images", [])
    for row in rows:
        _validate_image_row(row)

    robots = existing_robots()
    applied, rejected, skipped = [], [], []

    for row in rows:
        slug = row["slug"]
        decision = (row.get("decision") or "").strip().lower()
        if slug not in robots:
            raise AuthoringError(f"{slug}: no such catalogue robot")
        if decision == "":
            skipped.append({"slug": slug, "why": "awaiting identity decision"})
            continue
        if decision == "reject":
            rejected.append({"slug": slug, "why": row["reject_reason"]})
            continue

        if dry_run:
            applied.append({"slug": slug, "image_url": row["image_url"], "bytes": None})
            continue

        req = urllib.request.Request(
            row["image_url"],
            headers={"User-Agent": "HumanoidOnlineCatalogue/0.1 (+https://humanoidonline.com)"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:  # noqa: S310 - explicit https URL
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in IMAGE_CONTENT_TYPES:
                raise AuthoringError(
                    f"{slug}: served {ctype!r}, not an image type we store "
                    f"({sorted(IMAGE_CONTENT_TYPES)})"
                )
            body = resp.read(MAX_IMAGE_BYTES + 1)
        if len(body) > MAX_IMAGE_BYTES:
            raise AuthoringError(f"{slug}: image exceeds {MAX_IMAGE_BYTES} bytes")

        ext = IMAGE_CONTENT_TYPES[ctype]
        PUBLIC_ROBOT_IMAGES.mkdir(parents=True, exist_ok=True)
        (PUBLIC_ROBOT_IMAGES / f"{slug}{ext}").write_bytes(body)

        rights, basis, official = rights_for(row["source_type"])
        block = {
            "image_url": f"/robots/{slug}{ext}",
            "source_url": row["source_url"],
            "source_name": row["source_name"],
            "source_type": row["source_type"],
            "image_type": row["image_type"],
            # VERIFIED only ever because a named human said so.
            "identity_status": "VERIFIED",
            "rights_status": rights,
            "usage_basis": basis,
            "is_official": official,
            "is_primary": True,
            "attribution": row.get("attribution") or "",
            "last_verified_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "identity_confirmed_by": row["confirmed_by"].strip(),
        }
        path = ROBOTS_DIR / f"{slug}.json"
        robot = json.loads(path.read_text(encoding="utf-8"))
        robot["images"] = [block]
        path.write_text(json.dumps(robot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        applied.append({"slug": slug, "image_url": block["image_url"], "bytes": len(body)})

    return {"applied": applied, "rejected": rejected, "skipped": skipped, "dry_run": dry_run}

if __name__ == "__main__":
    raise SystemExit(main())
