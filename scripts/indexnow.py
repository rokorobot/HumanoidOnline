"""IndexNow: tell Bing (and other IndexNow engines) which public URLs changed.

Reads the live sitemap and submits URLs whose <lastmod> falls inside the window
(default 26 h, for a daily run), or every URL with --all. URLs without a lastmod
are only sent with --all. The key is public by design: IndexNow verifies it at
https://<host>/<key>.txt (apps/web/public/<key>.txt).
"""
import argparse
import datetime as dt
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

SITE = "https://humanoidonline.com"
KEY = "3af02102c0a811f35f42d481bd560018"
ENDPOINT = "https://api.indexnow.org/indexnow"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_sitemap(xml: str) -> list[tuple[str, dt.datetime | None]]:
    out = []
    for url in ET.fromstring(xml).findall("s:url", NS):
        loc = url.findtext("s:loc", namespaces=NS)
        mod = url.findtext("s:lastmod", namespaces=NS)
        out.append((loc.strip(), dt.datetime.fromisoformat(mod.replace("Z", "+00:00")) if mod else None))
    return out


def select(entries, now: dt.datetime, hours: float, everything: bool) -> list[str]:
    if everything:
        return [loc for loc, _ in entries]
    since = now - dt.timedelta(hours=hours)
    return [loc for loc, mod in entries if mod is not None and mod >= since]


def payload(urls: list[str]) -> dict:
    return {"host": SITE.split("//")[1], "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt", "urlList": urls}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="submit every sitemap URL")
    ap.add_argument("--hours", type=float, default=26)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with urllib.request.urlopen(f"{SITE}/sitemap.xml", timeout=30) as r:
        urls = select(parse_sitemap(r.read().decode()), dt.datetime.now(dt.timezone.utc), a.hours, a.all)
    print(f"{len(urls)} URL(s) to submit")
    for u in urls:
        print(" ", u)
    if not urls or a.dry_run:
        return 0
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload(urls)).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print("IndexNow:", r.status)  # 200 or 202 = accepted
        return 0 if r.status in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
