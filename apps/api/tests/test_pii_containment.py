"""WS8.1 / R2 + R5 — PII containment, proven at the response body and the log.

WS8-L6 makes this a release blocker, not a nicety: no unauthenticated or public
surface may expose `commercial_lead` / `buyer_requirement` contact data.

The sharp edge is `GET /api/buyer-requirements/{id}`. It is public and
unauthenticated (it powers "Adjust Requirements"), and the underlying row
*carries contact identity* — captured directly on the Find a Humanoid contact
step (`contact_name`, `contact_email`, `organization`, `contact_phone` are all
columns on `buyer_requirement`) and, historically, denormalized there at WS7
lead capture too. Only the read schema keeps them out of the response. That is
exactly the kind of invariant that survives by accident until someone adds a
field, so it is pinned here with both a real submission-time identity and a
real lead attached to a real requirement (see also
`test_buyer_requirements.py::test_public_requirement_read_never_exposes_identity`
for the submission-time case specifically).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from app.db.session import engine

#: Field names that must never appear in a public response body.
PII_FIELDS = ("contact_email", "contact_name", "organization", "contact_phone")

#: Unauthenticated GET surfaces. Slug-bearing routes are filled in at runtime.
STATIC_PUBLIC_GETS = (
    "/",
    "/health",
    "/ready",
    "/api/robots",
    "/api/manufacturers",
    "/api/use-cases",
    "/api/regions",
    "/api/market-snapshot",
)


def _iter_api_routes(app):
    """Walk nested routers.

    This FastAPI version keeps included routers as `_IncludedRouter` wrappers in
    `app.routes` rather than flattening them, so a shallow scan silently sees
    zero API routes — and a route-introspection assertion that scans nothing
    passes vacuously. Traverse.
    """
    stack = list(app.routes)
    while stack:
        route = stack.pop()
        # `_IncludedRouter` keeps its children on `.original_router.routes`;
        # plain Mounts use `.routes`.
        nested = getattr(getattr(route, "original_router", None), "routes", None)
        if nested is None:
            nested = getattr(route, "routes", None)
        if nested:
            stack.extend(nested)
            continue
        yield route


def _exec(sql: str, **params):
    with engine.connect() as conn:
        conn.execute(text("SET search_path TO humanoid, public"))
        result = conn.execute(text(sql), params)
        conn.commit()
        return result


def _cleanup(lead_id: str | None, requirement_id: str) -> None:
    """Leave the shared seeded database exactly as we found it."""
    if lead_id:
        _exec("DELETE FROM commercial_lead WHERE id = :i", i=lead_id)
    _exec("DELETE FROM match_result WHERE requirement_id = :i", i=requirement_id)
    _exec("DELETE FROM buyer_requirement WHERE id = :i", i=requirement_id)


def _warehouse_requirement(client) -> str:
    raw = {
        "wizard_version": 1,
        "answers": {
            "task": {"state": "ANSWERED", "use_case": "warehouse-logistics"},
            "country": {"state": "ANSWERED", "value": "US"},
        },
    }
    resp = client.post(
        "/api/buyer-requirements",
        json={
            "contact_name": "Test Buyer",
            "organization": "Test Org",
            "contact_email": "buyer@example.com",
            "use_case": "warehouse-logistics",
            "country": "US",
            "preferred_transaction": "RAAS",
            "raw_input": raw,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _public_get_urls(client) -> list[str]:
    urls = list(STATIC_PUBLIC_GETS)
    robots = client.get("/api/robots", params={"limit": 3}).json().get("items", [])
    for robot in robots:
        urls.append(f"/api/robots/{robot['slug']}")
    if len(robots) >= 2:
        ids = ",".join(r["slug"] for r in robots[:2])
        urls.append(f"/api/robots/compare?ids={ids}")
    mfrs = client.get("/api/manufacturers", params={"limit": 3}).json().get("items", [])
    urls += [f"/api/manufacturers/{m['slug']}" for m in mfrs]
    ucs = client.get("/api/use-cases").json().get("items", [])
    urls += [f"/api/use-cases/{u['slug']}" for u in ucs[:3]]
    return urls


# ---- R2 -------------------------------------------------------------------


def test_r2_public_reads_never_carry_lead_pii(client, database_url) -> None:
    """Crawl every public GET and assert no PII field name is present anywhere."""
    for url in _public_get_urls(client):
        resp = client.get(url)
        assert resp.status_code in (200, 404), (url, resp.status_code)
        if resp.status_code != 200:
            continue
        body = resp.text
        for field in PII_FIELDS:
            assert f'"{field}"' not in body, f"{field} leaked on {url}"


def test_r2_requirement_read_hides_identity_attached_by_lead_capture(
    client, database_url
) -> None:
    """The high-risk path: capture a lead, then re-read the requirement publicly.

    Lead capture may populate the requirement's contact identity. The public
    read must still return the anonymous projection — the buyer's own email must
    not become world-readable via a guessable requirement id.
    """
    sentinel_email = f"pii-probe-{uuid.uuid4().hex[:10]}@example.com"
    sentinel_org = f"Org-{uuid.uuid4().hex[:8]}"
    sentinel_phone = "+1-555-0100"
    rid = _warehouse_requirement(client)
    matches = client.get(f"/api/buyer-requirements/{rid}/matches").json()["matches"]
    slugs = [m["robot"]["slug"] for m in matches]

    lead = client.post(
        "/api/commercial-leads",
        json={
            "requirement_id": rid,
            "contact_email": sentinel_email,
            "contact_name": "Probe Person",
            "organization": sentinel_org,
            "contact_phone": sentinel_phone,
            "robot_slugs": slugs,
        },
    )
    assert lead.status_code in (200, 201), lead.text
    lead_id = lead.json()["id"]

    try:
        # The identity really was captured — otherwise this test proves nothing.
        stored = _exec(
            "SELECT contact_email, contact_phone FROM commercial_lead WHERE id = :i",
            i=lead_id,
        ).one()
        assert stored.contact_email == sentinel_email
        assert stored.contact_phone == sentinel_phone

        resp = client.get(f"/api/buyer-requirements/{rid}")
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert sentinel_email not in body
        assert sentinel_org not in body
        assert sentinel_phone not in body
        assert "Probe Person" not in body
        for field in PII_FIELDS:
            assert f'"{field}"' not in body

        # And the sentinel must not surface on any other public surface either.
        for url in _public_get_urls(client):
            other = client.get(url)
            if other.status_code == 200:
                assert sentinel_email not in other.text, url
    finally:
        _cleanup(lead_id, rid)


def test_r2_no_public_read_endpoint_exists_for_leads(client) -> None:
    """WS7 froze this: a lead carries PII and has no public GET/PATCH."""
    from app.main import app

    lead_routes = [
        (r.path, sorted(r.methods))
        for r in _iter_api_routes(app)
        if getattr(r, "path", "").startswith("/api/commercial-leads")
    ]
    assert lead_routes, "the lead route disappeared"
    for path, methods in lead_routes:
        assert set(methods) <= {"POST"}, (path, methods)


# ---- R5 -------------------------------------------------------------------


def test_r5_pii_is_never_carried_in_a_url_or_query_string(client) -> None:
    """Contact data is only ever accepted in a request *body*.

    A PII-bearing query string would leak into proxy logs, browser history and
    referrer headers regardless of how careful the application is.
    """
    from app.main import app

    for route in _iter_api_routes(app):
        path = getattr(route, "path", "")
        for field in PII_FIELDS:
            assert field not in path, (path, field)
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for param in dependant.query_params:
            assert param.name not in PII_FIELDS, (path, param.name)


def test_r5_lead_capture_does_not_write_pii_to_logs(
    client, database_url, caplog
) -> None:
    """Capture everything logged during a real lead capture; assert it is clean."""
    sentinel_email = f"log-probe-{uuid.uuid4().hex[:10]}@example.com"
    sentinel_phone = "+1-555-0199"
    rid = _warehouse_requirement(client)
    matches = client.get(f"/api/buyer-requirements/{rid}/matches").json()["matches"]
    slugs = [m["robot"]["slug"] for m in matches]

    lead_id = None
    try:
        with caplog.at_level(logging.DEBUG):
            resp = client.post(
                "/api/commercial-leads",
                json={
                    "requirement_id": rid,
                    "contact_email": sentinel_email,
                    "contact_name": "Log Probe",
                    "organization": "LogProbe Ltd",
                    "contact_phone": sentinel_phone,
                    "robot_slugs": slugs,
                    "message": "please contact me",
                },
            )
        assert resp.status_code in (200, 201), resp.text
        lead_id = resp.json()["id"]

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert sentinel_email not in logged
        assert "Log Probe" not in logged
        assert "LogProbe Ltd" not in logged
        assert sentinel_phone not in logged
    finally:
        _cleanup(lead_id, rid)


def test_r5_requirement_submission_does_not_write_identity_to_logs(
    client, database_url, caplog
) -> None:
    """Same proof as above, for the Find a Humanoid contact step itself: capture
    everything logged during a real requirement submission carrying identity;
    assert it is clean."""
    sentinel_email = f"wizard-log-probe-{uuid.uuid4().hex[:10]}@example.com"
    sentinel_phone = "+1-555-0188"
    req_id = None
    try:
        with caplog.at_level(logging.DEBUG):
            resp = client.post(
                "/api/buyer-requirements",
                json={
                    "contact_name": "Wizard Log Probe",
                    "organization": "WizardLogProbe Ltd",
                    "contact_email": sentinel_email,
                    "contact_phone": sentinel_phone,
                    "raw_input": {"wizard_version": 1, "answers": {}},
                },
            )
        assert resp.status_code == 201, resp.text
        req_id = resp.json()["id"]

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert sentinel_email not in logged
        assert "Wizard Log Probe" not in logged
        assert "WizardLogProbe Ltd" not in logged
        assert sentinel_phone not in logged
    finally:
        if req_id:
            _exec("DELETE FROM buyer_requirement WHERE id = :i", i=req_id)
