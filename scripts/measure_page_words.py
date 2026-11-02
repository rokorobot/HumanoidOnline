#!/usr/bin/env python3
"""Count words inside <main> for /use-cases/<slug> and /manufacturers/<slug> pages.

usage: measure_page_words.py [BASE_URL] [--json]
Slugs come from db/catalogue/use_cases.json and manufacturers.json.
"""
import json, re, sys, urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"script", "style", "noscript", "svg"}

class MainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth = 0; self.skip = 0; self.words = []
    def handle_starttag(self, tag, attrs):
        if tag == "main": self.depth += 1
        elif tag in SKIP and self.depth: self.skip += 1
    def handle_endtag(self, tag):
        if tag == "main" and self.depth: self.depth -= 1
        elif tag in SKIP and self.depth and self.skip: self.skip -= 1
    def handle_data(self, data):
        if self.depth and not self.skip: self.words += re.findall(r"\S+", data)

def count(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ho-wordcount/1.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    p = MainText(); p.feed(html); return len(p.words)

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = (args[0] if args else "https://humanoidonline.com").rstrip("/")
    ucs = [u["slug"] for u in json.load(open(ROOT/"db/catalogue/use_cases.json"))["use_cases"]]
    mfs = [m["slug"] for m in json.load(open(ROOT/"db/catalogue/manufacturers.json"))["manufacturers"]]
    out = {}
    for kind, slugs in (("use-cases", ucs), ("manufacturers", mfs)):
        for s in slugs:
            try: out[f"/{kind}/{s}"] = count(f"{base}/{kind}/{s}")
            except Exception as e: out[f"/{kind}/{s}"] = f"ERR {e}"
    if "--json" in sys.argv: print(json.dumps(out, indent=1))
    else:
        for k, v in out.items(): print(f"{v}\t{k}")

if __name__ == "__main__": main()
