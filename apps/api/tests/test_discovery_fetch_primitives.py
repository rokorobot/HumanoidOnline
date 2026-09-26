"""Discovery Stage B — pure primitives: fingerprint, robots.txt, bounded fetcher.

No database and no network: the fetcher runs over httpx.MockTransport with a
fake clock, and the socket guard fails the test on any real connection.
"""
from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from app.services.discovery import fingerprint as fp
from app.services.discovery.fetcher import (
    USER_AGENT,
    FetchLimits,
    HttpFetcher,
    KillSwitchEngaged,
)
from app.services.discovery.robots import RobotsRules, parse

pytestmark = pytest.mark.usefixtures("no_external_network")

APP = Path(__file__).resolve().parents[1] / "app"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class Site:
    """Scripted responses per URL; the last response for a URL repeats."""

    def __init__(self, routes: dict[str, list]) -> None:
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(str(request.url))
        if not queue:
            return httpx.Response(404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def fetcher(site: Site, clock: FakeClock | None = None, **limits) -> HttpFetcher:
    clock = clock or FakeClock()
    return HttpFetcher(limits=FetchLimits(**limits), transport=httpx.MockTransport(site),
                       monotonic=clock.monotonic, sleep=clock.sleep)


# ---------------------------------------------------------------- fingerprint --


def test_fingerprint_is_deterministic_and_versioned():
    body = b"<html><body><h1>H1</h1><p>Price on request</p></body></html>"
    assert fp.fingerprint(body, "text/html") == fp.fingerprint(body, "text/html")
    assert fp.FINGERPRINT_VERSION == "html-text+jsonld/1"


def test_fingerprint_ignores_scripts_styles_and_whitespace_but_not_text():
    a = b"<html><script>var nonce='1'</script><style>.a{}</style><p>Pre-order  now</p></html>"
    b = b"<html><script>var nonce='2'</script><p>Pre-order\n now</p></html>"
    c = b"<html><p>Sold out</p></html>"
    assert fp.fingerprint(a, "text/html") == fp.fingerprint(b, "text/html")
    assert fp.fingerprint(a, "text/html") != fp.fingerprint(c, "text/html")


def test_fingerprint_tracks_structured_data_changes():
    def page(price: str) -> bytes:
        return (b'<html><script type="application/ld+json">{"@type":"Product",'
                b'"offers":{"price":"' + price.encode() + b'"}}</script><p>H1</p></html>')
    assert fp.fingerprint(page("100"), "text/html") != fp.fingerprint(page("120"), "text/html")
    reordered = (b'<html><script type="application/ld+json">{"offers":{"price":"100"},'
                 b'"@type":"Product"}</script><p>H1</p></html>')
    assert fp.fingerprint(page("100"), "text/html") == fp.fingerprint(reordered, "text/html")


def test_fingerprint_json_and_binary():
    assert fp.fingerprint(b'{"b":1,"a":2}', "application/json") == fp.fingerprint(
        b'{ "a": 2, "b": 1 }', "application/json")
    assert fp.fingerprint(b"\x00\x01", "application/pdf") == fp.sha256_hex(b"\x00\x01")


# ---------------------------------------------------------------- robots.txt --


def test_robots_longest_match_wins_not_first_match():
    rules = parse("User-agent: *\nAllow: /\nDisallow: /private\n")
    assert rules.allows("https://m.example/products/x")
    assert not rules.allows("https://m.example/private/x")  # first-match parsers get this wrong


def test_robots_specific_group_replaces_wildcard_group():
    text = ("User-agent: *\nDisallow: /\n\n"
            "User-agent: HumanoidOnlineMarketBot\nDisallow: /internal/\n")
    rules = parse(text)
    assert rules.allows("https://m.example/products/x")
    assert not rules.allows("https://m.example/internal/x")


def test_robots_wildcards_anchor_and_ties():
    rules = parse("User-agent: *\nDisallow: /*.pdf$\nDisallow: /p/\nAllow: /p/\n")
    assert not rules.allows("https://m.example/docs/spec.pdf")
    assert rules.allows("https://m.example/docs/spec.pdf?x=1")
    assert rules.allows("https://m.example/p/x")  # equal length: allow wins


def test_robots_empty_disallow_and_no_group_allow_everything():
    assert parse("User-agent: *\nDisallow:\n").allows("https://m.example/a")
    assert parse("").allows("https://m.example/a")


def test_robots_disallow_all_model_and_robots_file_itself():
    rules = RobotsRules(disallow_all=True)
    assert not rules.allows("https://m.example/products/x")
    assert rules.allows("https://m.example/robots.txt")


# -------------------------------------------------------------------- fetcher --


def test_exact_user_agent_and_no_browser_identity():
    site = Site({"https://m.example/a": [httpx.Response(200, text="ok")]})
    with fetcher(site) as f:
        f.get("https://m.example/a")
    assert site.requests[0].headers["user-agent"] == USER_AGENT
    assert USER_AGENT == "HumanoidOnlineMarketBot/0.1 (+https://humanoidonline.com/crawler-policy)"
    for path in APP.rglob("*.py"):
        assert "Mozilla/5.0" not in path.read_text(encoding="utf-8"), path


def test_no_browser_or_javascript_execution_anywhere_in_app():
    banned = {"playwright", "selenium", "pyppeteer", "splinter", "requests_html"}
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not {n.split(".")[0] for n in names} & banned, path


def test_conditional_headers_are_sent_as_given():
    site = Site({"https://m.example/a": [httpx.Response(304)]})
    with fetcher(site) as f:
        r = f.get("https://m.example/a", {"If-None-Match": '"v1"',
                                          "If-Modified-Since": "Wed, 01 Jan 2026 00:00:00 GMT"})
    assert r.status == 304 and r.body is None
    assert site.requests[0].headers["if-none-match"] == '"v1"'
    assert site.requests[0].headers["if-modified-since"] == "Wed, 01 Jan 2026 00:00:00 GMT"


def test_retries_are_bounded_with_increasing_backoff_for_5xx():
    clock = FakeClock()
    site = Site({"https://m.example/a": [httpx.Response(503)]})
    with fetcher(site, clock) as f:
        r = f.get("https://m.example/a")
    assert r.status == 503
    assert len(site.requests) == 3  # 1 + max 2 retries
    # Backoff doubles (2 s, 4 s); each wait also satisfies the per-host interval.
    assert clock.sleeps == [2.0, 4.0]


def test_transient_failure_then_success():
    site = Site({"https://m.example/a": [httpx.ConnectError("boom"),
                                         httpx.Response(200, text="x")]})
    with fetcher(site) as f:
        r = f.get("https://m.example/a")
    assert r.status == 200 and r.body == b"x" and len(site.requests) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 429])
def test_no_retry_for_4xx(status):
    site = Site({"https://m.example/a": [httpx.Response(status)]})
    with fetcher(site) as f:
        assert f.get("https://m.example/a").status == status
    assert len(site.requests) == 1


def test_timeout_is_retried_then_reported():
    site = Site({"https://m.example/a": [httpx.ReadTimeout("slow")]})
    with fetcher(site) as f:
        r = f.get("https://m.example/a")
    assert r.error_class == "timeout" and r.status is None and len(site.requests) == 3


def test_body_size_cap_discards_oversize_bodies():
    site = Site({
        "https://m.example/declared": [httpx.Response(200, content=b"x" * 50)],
        "https://m.example/streamed": [httpx.Response(200, content=iter([b"x" * 30, b"y" * 30]))],
    })
    with fetcher(site, max_body_bytes=40) as f:
        declared = f.get("https://m.example/declared")
        streamed = f.get("https://m.example/streamed")
    assert declared.error_class == streamed.error_class == "body_too_large"
    assert declared.body is None and streamed.body is None


def test_per_host_rate_limit_with_fake_clock():
    clock = FakeClock()
    site = Site({"https://m.example/a": [httpx.Response(200)],
                 "https://m.example/b": [httpx.Response(200)],
                 "https://other.example/c": [httpx.Response(200)]})
    with fetcher(site, clock, min_interval_seconds=3.0) as f:
        f.get("https://m.example/a")
        f.get("https://other.example/c")  # different host: no wait
        f.get("https://m.example/b")
    assert clock.sleeps == [3.0]


def test_limits_cannot_be_loosened():
    with pytest.raises(ValueError):
        FetchLimits(min_interval_seconds=1.0)
    with pytest.raises(ValueError):
        FetchLimits(page_cap=201)
    with pytest.raises(ValueError):
        FetchLimits(max_retries=3)


def test_kill_switch_stops_before_any_request():
    site = Site({"https://m.example/a": [httpx.Response(200)]})
    f = HttpFetcher(transport=httpx.MockTransport(site), kill_switch=lambda: True)
    with pytest.raises(KillSwitchEngaged):
        f.get("https://m.example/a")
    assert site.requests == []


def test_redirects_are_bounded_and_every_hop_is_checked():
    site = Site({
        "https://m.example/a": [httpx.Response(301, headers={"location": "/b"})],
        "https://m.example/b": [httpx.Response(302, headers={"location": "https://evil.example/x"})],
    })
    checked: list[str] = []

    def refusal(target):
        checked.append(target)
        return "OFF_HOST" if "evil" in target else None

    with fetcher(site) as f:
        result = f.get_following("https://m.example/a", None, refusal)
    assert result.final_url == "https://m.example/b"
    assert result.refused == ("https://evil.example/x", "OFF_HOST")
    assert [str(r.url) for r in site.requests] == ["https://m.example/a", "https://m.example/b"]
    assert checked == ["https://m.example/b", "https://evil.example/x"]

    loop = Site({"https://m.example/l": [httpx.Response(302, headers={"location": "/l"})]})
    with fetcher(loop, max_redirects=3) as f:
        result = f.get_following("https://m.example/l", None, lambda t: None)
    assert result.too_many_redirects and len(loop.requests) == 4
