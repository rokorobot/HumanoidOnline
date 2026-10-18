"""Synchronize code-declared discovery source identities into the runtime DB.

Idempotent, limited to REGISTERING missing sources as DISABLED, with UNKNOWN
ToS/robots. Existing source approvals, enablement and cadence are never touched.
No network requests to manufacturer websites.

    python -m app.cli.source_registry_manifest --plan
    python -m app.cli.source_registry_manifest --apply --by 'Operator'
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.discovery import DiscoverySource
from app.services.discovery.source_registry import register_source

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / 'db/discovery/owner_authorized_source_targets_20261018.json'


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not data:
        raise ValueError('manifest must be a non-empty JSON array')
    keys = [entry['key'] for entry in data]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate discovery source keys')
    for entry in data:
        if not entry['host'] or '/' in entry['host'] or '.' not in entry['host']:
            raise ValueError('host must be a bare domain')
        if entry['source_class'] not in ('MANUFACTURER', 'DISTRIBUTOR'):
            raise ValueError('unsupported source class')
    return data


def sync(*, apply: bool, by: str | None) -> tuple[int,int]:
    records = load_manifest()
    if apply and (not by or not by.strip()):
        raise ValueError('--apply requires --by')
    created = 0
    existing = 0
    with SessionLocal() as session:
        for entry in records:
            found = session.scalars(
                select(DiscoverySource).where(DiscoverySource.key == entry['key'])
            ).first()
            homepage = f"https://{entry['host']}/"
            if found:
                # Never silently overwrite a real source with a changed host/class.
                if found.homepage_url != homepage or found.source_class != entry['source_class']:
                    raise ValueError(f"source mismatch (manual review required): {entry['key']}")
                existing += 1
                print(f"PRESENT {entry['key']}: unchanged")
            else:
                created += 1
                if apply:
                    register_source(
                        session, key=entry['key'], name=entry['source_name'],
                        source_class=entry['source_class'], homepage_url=homepage,
                        registered_by=by or '')
                print(f"{'REGISTERED' if apply else 'WOULD_REGISTER'} {entry['key']} (DISABLED)")
        if apply:
            session.commit()
        else:
            session.rollback()
    print(f"summary: {created} {'registered' if apply else 'would register'}, {existing} existing")
    return created, existing


def main() -> None:
    parser = argparse.ArgumentParser()
    p = parser.add_mutually_exclusive_group(required=True)
    p.add_argument('--plan', action='store_true')
    p.add_argument('--apply', action='store_true')
    parser.add_argument('--by')
    args = parser.parse_args()
    sync(apply=args.apply, by=args.by)


if __name__ == '__main__':
    main()
