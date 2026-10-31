import datetime as dt
import pathlib
import unittest

import indexnow

XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://humanoidonline.com/</loc></url>
<url><loc>https://humanoidonline.com/robots/a</loc><lastmod>2026-10-31T01:00:00.000Z</lastmod></url>
<url><loc>https://humanoidonline.com/robots/b</loc><lastmod>2026-10-20T01:00:00.000Z</lastmod></url>
</urlset>"""
NOW = dt.datetime(2026, 10, 31, 12, tzinfo=dt.timezone.utc)


class IndexNowTest(unittest.TestCase):
    def test_window_selects_only_recent_lastmod(self):
        self.assertEqual(indexnow.select(indexnow.parse_sitemap(XML), NOW, 26, False),
                         ["https://humanoidonline.com/robots/a"])

    def test_all_includes_urls_without_lastmod(self):
        self.assertEqual(len(indexnow.select(indexnow.parse_sitemap(XML), NOW, 26, True)), 3)

    def test_payload_points_at_the_served_key_file(self):
        p = indexnow.payload(["https://humanoidonline.com/"])
        self.assertEqual(p["host"], "humanoidonline.com")
        self.assertEqual(p["keyLocation"], f"https://humanoidonline.com/{indexnow.KEY}.txt")
        key_file = pathlib.Path(__file__).parents[1] / "apps/web/public" / f"{indexnow.KEY}.txt"
        self.assertEqual(key_file.read_text(), indexnow.KEY)


if __name__ == "__main__":
    unittest.main()
