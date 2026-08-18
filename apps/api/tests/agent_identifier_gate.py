"""The recursive identifier gate shared by every AGENT-02 projection test.

`docs/20` §8 makes the slug the canonical external identifier and states that
internal database UUIDs are never the public contract; §20 forbids database
selectors; §21.10 requires that no raw database identifier appear in any request
or response.

The gate is recursive on purpose. Asserting that a top-level `id` key is gone
would pass just as happily with a UUID nested inside `manufacturer`, or inside
one deployment's evidence, or three levels down a list of offers. The assertion
that matters is that no database identifier appears *anywhere* in the serialized
result, at any depth.

It lives here rather than in one test module because `search_robots` and
`get_robot` must be held to the same standard — and a second, subtly weaker copy
of a security assertion is worse than no second copy at all. `get_robot` is the
larger surface (offers, deployments, images, four kinds of evidence), so it is
the one that would most easily hide a leak behind a divergent gate.

Note that `evidence_ref` values are scanned like everything else. They are
AES-SIV ciphertext in base64url and do not match the UUID shape, so no exemption
is carved out — an exemption is exactly where a leak would eventually live.
"""
from __future__ import annotations

import re

#: Canonical 8-4-4-4-12 hex form, word-bounded so it matches a UUID *value*
#: rather than any hex-ish run inside a longer opaque token.
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

#: Key names that would carry a database selector if present at any depth.
#: Names, not values: a key called `robot_id` is a contract violation even when
#: whatever it holds happens not to look like a UUID today.
FORBIDDEN_KEYS = {
    "id", "robot_id", "manufacturer_id", "provider_id", "region_id",
    "subject_id", "variant_id", "use_case_id", "image_id", "offer_id",
    "country_region_id", "parent_id", "evidence_id", "deployment_id",
    "pricing_offer_id", "availability_offer_id", "evidence_source_id",
    "capability_id", "specification_id", "country_id",
}


def walk(node, path: str = "$"):
    """Yield every (path, key, value) triple in a nested JSON-ish structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}", key, value
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def assert_no_database_identifier(payload) -> None:
    """Recursive projection-safety gate (§8, §20, §21.10)."""
    for path, key, value in walk(payload):
        assert key not in FORBIDDEN_KEYS, f"database selector key at {path}"
        if isinstance(value, str):
            assert not UUID_PATTERN.search(value), f"UUID value at {path}: {value!r}"


def assert_absent_everywhere(payload, *planted: str) -> None:
    """Prove specific real row identities appear nowhere in a payload.

    The strongest form of the gate: rather than trusting a pattern to describe
    what a leak looks like, plant the actual `robot.id` / `evidence_source.id` /
    offer ids and hunt for them — in hyphenated and bare-hex spelling, and in
    both cases, since a leak that went through `.hex` or `.upper()` is still a
    leak.
    """
    haystack = repr(payload).lower()
    for value in planted:
        text = str(value).lower()
        assert text not in haystack, f"row identity {value!r} present in payload"
        assert text.replace("-", "") not in haystack, f"bare-hex {value!r} in payload"
