"""docs/16 §11 — source-stable URL -> external_ref normalizer. Pure, offline."""
from __future__ import annotations

import pytest

from app.services.discovery.urlref import UnsupportedUrl, normalize_url

CASES = [
    # (input, expected, why)
    ("https://maker.example/products/ex-1", "https://maker.example/products/ex-1",
     "already stable"),
    ("HTTPS://Maker.EXAMPLE/products/ex-1", "https://maker.example/products/ex-1",
     "scheme/host case"),
    ("https://maker.example/products/ex-1/", "https://maker.example/products/ex-1",
     "trailing slash"),
    ("https://maker.example/", "https://maker.example/", "root keeps its slash"),
    ("https://maker.example", "https://maker.example/", "empty path is root"),
    ("https://maker.example:443/products/ex-1", "https://maker.example/products/ex-1",
     "default https port"),
    ("http://maker.example:80/p", "http://maker.example/p", "default http port"),
    ("https://maker.example:8443/p", "https://maker.example:8443/p", "non-default port kept"),
    ("https://maker.example/p#specs", "https://maker.example/p", "fragment dropped"),
    ("https://maker.example/p?utm_source=news&utm_medium=email", "https://maker.example/p",
     "utm_* stripped"),
    ("https://maker.example/p?UTM_Campaign=x", "https://maker.example/p", "tracking is case-blind"),
    ("https://maker.example/p?gclid=1&fbclid=2&msclkid=3&_ga=4&mc_cid=5",
     "https://maker.example/p", "click ids stripped"),
    ("https://maker.example/p?variant=edu&utm_source=x", "https://maker.example/p?variant=edu",
     "meaningful query kept"),
    ("https://maker.example/p?b=2&a=1", "https://maker.example/p?a=1&b=2",
     "query order is not identity"),
    ("https://maker.example/p?a=1&b=2", "https://maker.example/p?a=1&b=2", "same after sort"),
    ("https://maker.example/p?id=", "https://maker.example/p?id=", "blank value kept"),
    ("https://maker.example/Products/EX-1", "https://maker.example/Products/EX-1",
     "path case preserved"),
    ("https://maker.example/products/ex%201", "https://maker.example/products/ex%201",
     "path encoding preserved"),
    ("  https://maker.example/p  ", "https://maker.example/p", "surrounding whitespace"),
]


@pytest.mark.parametrize(("raw", "expected", "why"), CASES, ids=[c[2] for c in CASES])
def test_normalize_url(raw: str, expected: str, why: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", [c[0] for c in CASES])
def test_normalize_url_is_idempotent(raw: str) -> None:
    once = normalize_url(raw)
    assert normalize_url(once) == once


def test_variants_of_one_page_share_one_reference() -> None:
    variants = [
        "https://maker.example/products/ex-1",
        "https://MAKER.example/products/ex-1/",
        "https://maker.example/products/ex-1?utm_source=newsletter",
        "https://maker.example:443/products/ex-1#top",
    ]
    assert {normalize_url(v) for v in variants} == {"https://maker.example/products/ex-1"}


def test_different_pages_stay_different() -> None:
    pages = [
        "https://maker.example/products/ex-1",
        "https://maker.example/products/ex-1-edu",
        "https://maker.example/products/ex-1?variant=edu",
        "https://maker.example/Products/ex-1",
        "https://other.example/products/ex-1",
    ]
    assert len({normalize_url(p) for p in pages}) == len(pages)


@pytest.mark.parametrize("raw", [
    "", "/products/ex-1", "ftp://maker.example/p", "mailto:x@maker.example",
    "javascript:void(0)", "https://user:pw@maker.example/p", "https:///p",
])
def test_unsupported_urls_are_refused(raw: str) -> None:
    with pytest.raises(UnsupportedUrl):
        normalize_url(raw)
