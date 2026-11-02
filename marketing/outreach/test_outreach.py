"""Tests for outreach.py. Run: python3 -m unittest marketing/outreach/test_outreach.py"""
import datetime as dt
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outreach as o  # noqa: E402

CFG = {"name": "Ada Lovelace", "title": "Founder", "from": "ada@humanoidonline.com",
       "address": "Example St 1, Prague", "host": "", "port": 587, "user": "", "password": ""}


def row(**kw):
    base = {"id": "x", "channel": "email", "contact": "ed@example.com", "status": "approved",
            "sent_at": "", "followup_at": ""}
    base.update(kw)
    return base


class TestDue(unittest.TestCase):
    today = dt.date(2026, 11, 20)

    def test_only_approved_email_rows_with_contact(self):
        rows = [row(id="a"), row(id="b", status="draft"), row(id="c", channel="form"),
                row(id="d", contact=""), row(id="e", status="optout")]
        pitches, followups = o.due(rows, self.today)
        self.assertEqual([r["id"] for r in pitches], ["a"])
        self.assertEqual(followups, [])

    def test_followup_once_after_wait(self):
        rows = [row(id="old", status="sent", sent_at="2026-11-01"),
                row(id="new", status="sent", sent_at="2026-11-15"),
                row(id="done", status="sent", sent_at="2026-11-01", followup_at="2026-11-10"),
                row(id="replied", status="replied", sent_at="2026-11-01")]
        _, followups = o.due(rows, self.today)
        self.assertEqual([r["id"] for r in followups], ["old"])

    def test_cap_per_run_counts_followups_first(self):
        rows = [row(id=f"p{i}") for i in range(4)] + \
               [row(id=f"f{i}", status="sent", sent_at="2026-11-01") for i in range(3)]
        pitches, followups = o.due(rows, self.today)
        self.assertEqual(len(pitches) + len(followups), o.MAX_PER_RUN)
        self.assertEqual(len(followups), 3)


class TestLinkRel(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(o.link_rel('<a href="https://humanoidonline.com/robots">x</a>'), "followed")
        self.assertEqual(o.link_rel('<a rel="noopener" href="https://www.humanoidonline.com/">x</a>'), "followed")
        self.assertEqual(o.link_rel('<a href="https://humanoidonline.com/" rel="nofollow noopener">'), "nofollow")
        self.assertEqual(o.link_rel("<a href='https://humanoidonline.com/' rel='ugc'>"), "ugc")
        self.assertEqual(o.link_rel('<a href="https://humanoidonline.com" rel="sponsored">'), "sponsored")
        self.assertEqual(o.link_rel('<a href="https://example.com/?u=humanoidonline.com">'), "missing")


class TestPitches(unittest.TestCase):
    def test_parse_and_build(self):
        headers, body, follow = o.parse_pitch("Subject: Hi\nFollowup-Subject: Re: Hi\n\nBody {sender_name}\n--- follow-up ---\nAgain")
        self.assertEqual(headers["subject"], "Hi")
        self.assertEqual(body, "Body {sender_name}")
        self.assertEqual(follow, "Again")

    def test_every_email_target_has_a_complete_pitch(self):
        _, rows = o.load()
        for r in rows:
            if r["channel"] != "email":
                continue
            with self.subTest(r["id"]):
                self.assertRegex(r["contact"], r"^[^@\s]+@[^@\s]+\.[a-z]+$")
                msg = o.build(r, CFG)
                follow = o.build(r, CFG, followup=True)
                self.assertTrue(msg["Subject"] and follow["Subject"])
                text = msg.get_content() + follow.get_content()
                self.assertNotRegex(text, r"\{[a-z_]+\}")  # every placeholder filled
                self.assertIn(CFG["address"], text)  # CAN-SPAM footer present
                self.assertIn("reply \"no\"", text)

    def test_tracker_has_unique_ids_and_domains(self):
        _, rows = o.load()
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        hosts = [re.sub(r"^www\.", "", r["submission_url"].split("/")[2]) for r in rows]
        self.assertEqual(len(hosts), len(set(hosts)), "duplicate domains in tracker")


if __name__ == "__main__":
    unittest.main()
