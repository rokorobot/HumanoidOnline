"""Backlink outreach helper for HumanoidOnline. Standard library only.

Usage (from the repo root):
  python3 marketing/outreach/outreach.py status          # summary of the tracker
  python3 marketing/outreach/outreach.py send            # dry run: show what would be sent
  python3 marketing/outreach/outreach.py send --live     # send approved pitches + due follow-ups
  python3 marketing/outreach/outreach.py check           # check live links, record rel attribute

Workflow: a row with channel=email and status=approved gets its pitch
(pitches/<id>.md) sent once. Rows sent FOLLOWUP_DAYS ago that are still
status=sent get one follow-up. Any other status (replied, rejected, optout,
live, ...) is never emailed again. See README.md.
"""
import csv
import datetime as dt
import os
import re
import smtplib
import sys
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKER = os.path.join(HERE, "targets.csv")
PITCHES = os.path.join(HERE, "pitches")
SITE = "humanoidonline.com"
MAX_PER_RUN = 5
FOLLOWUP_DAYS = 9
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def load(path=TRACKER):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def save(fields, rows, path=TRACKER):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_pitch(text):
    """Split a pitch file into headers (To, Subject, Followup-Subject) and body.

    The body ends at a line '--- follow-up ---'; the text after it is the follow-up.
    """
    head, _, rest = text.partition("\n\n")
    headers = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    body, _, followup = rest.partition("\n--- follow-up ---\n")
    return headers, body.strip(), followup.strip()


def fill(text, cfg):
    return (text.replace("{sender_name}", cfg["name"])
                .replace("{sender_title}", cfg["title"]))


def footer(cfg):
    # CAN-SPAM: identify the sender, give a postal address and a way to opt out.
    return ("\n\n--\n{name}, {title}\nHumanoidOnline (a Humanoid.Company project) · https://humanoidonline.com\n"
            "{address}\nIf you'd prefer not to hear from me again, just reply \"no\" and I won't follow up."
            ).format(**cfg)


def due(rows, today):
    """Return (pitches, followups) to send today, at most MAX_PER_RUN in total."""
    pitches, followups = [], []
    for r in rows:
        if r["channel"] != "email" or not r["contact"]:
            continue
        if r["status"] == "approved":
            pitches.append(r)
        elif r["status"] == "sent" and r["sent_at"] and not r["followup_at"]:
            if today - dt.date.fromisoformat(r["sent_at"]) >= dt.timedelta(days=FOLLOWUP_DAYS):
                followups.append(r)
    followups = followups[:MAX_PER_RUN]
    pitches = pitches[:MAX_PER_RUN - len(followups)]
    return pitches, followups


def load_env(path=os.path.join(HERE, ".env")):
    """Read KEY=VALUE lines from marketing/outreach/.env (git-ignored) without overriding the environment."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def config():
    load_env()
    cfg = {
        "name": os.environ.get("OUTREACH_FROM_NAME", ""),
        "title": os.environ.get("OUTREACH_SENDER_TITLE", "Founder"),
        "from": os.environ.get("OUTREACH_FROM", ""),
        "address": os.environ.get("OUTREACH_POSTAL_ADDRESS", ""),
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
    }
    return cfg


def build(r, cfg, followup=False):
    with open(os.path.join(PITCHES, r["id"] + ".md"), encoding="utf-8") as f:
        headers, body, follow = parse_pitch(f.read())
    msg = EmailMessage()
    msg["From"] = formataddr((cfg["name"], cfg["from"]))
    msg["To"] = r["contact"]
    msg["Subject"] = headers.get("followup-subject" if followup else "subject", "")
    msg["Message-ID"] = make_msgid(domain=cfg["from"].split("@")[-1] or None)
    msg.set_content(fill(follow if followup else body, cfg) + footer(cfg))
    return msg


def cmd_send(live):
    fields, rows = load()
    today = dt.date.today()
    pitches, followups = due(rows, today)
    if not pitches and not followups:
        print("Nothing to send.")
        return 0
    cfg = config()
    missing = [k for k in ("name", "from", "address", "host", "user", "password") if not cfg[k]]
    if live and missing:
        print("Refusing to send: missing settings:", ", ".join(missing))
        return 1
    smtp = None
    if live:
        smtp = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
        smtp.starttls()
        smtp.login(cfg["user"], cfg["password"])
    try:
        for r, is_followup in [(r, False) for r in pitches] + [(r, True) for r in followups]:
            msg = build(r, cfg, is_followup)
            label = "FOLLOW-UP" if is_followup else "PITCH"
            print(f"{label} {r['id']} -> {r['contact']} | {msg['Subject']}")
            if not live:
                continue
            smtp.send_message(msg)
            if is_followup:
                r["followup_at"] = today.isoformat()
            else:
                r["status"], r["sent_at"] = "sent", today.isoformat()
            save(fields, rows)  # save after every email so a crash never double-sends
    finally:
        if smtp:
            smtp.quit()
    if not live:
        print("\nDry run. Nothing was sent. Add --live to send.")
    return 0


def link_rel(html, site=SITE):
    """Return 'followed', 'nofollow', 'sponsored', 'ugc' (first link found) or 'missing'."""
    for m in re.finditer(r"<a\s[^>]*href=[\"']https?://(?:www\.)?" + re.escape(site) + r"[^>]*>", html, re.I):
        rel = re.search(r"rel=[\"']([^\"']*)[\"']", m.group(0), re.I)
        words = rel.group(1).lower().split() if rel else []
        for w in ("sponsored", "ugc", "nofollow"):
            if w in words:
                return w
        return "followed"
    return "missing"


def cmd_check():
    fields, rows = load()
    today = dt.date.today().isoformat()
    for r in rows:
        if not r["live_url"]:
            continue
        try:
            req = urllib.request.Request(r["live_url"], headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
            r["rel_observed"] = link_rel(html)
        except Exception as e:  # report and keep going; a dead page is a finding
            r["rel_observed"] = "error: " + type(e).__name__
        r["last_checked"] = today
        if r["rel_observed"] != "missing" and not r["rel_observed"].startswith("error"):
            r["status"] = "live"
        print(f"{r['id']}: {r['rel_observed']}  {r['live_url']}")
    save(fields, rows)
    return 0


def cmd_status():
    _, rows = load()
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("Status:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    pitches, followups = due(rows, dt.date.today())
    print(f"Ready to send now: {len(pitches)} pitches, {len(followups)} follow-ups")
    for r in rows:
        if r["status"] == "live":
            print(f"LIVE {r['id']}: {r['rel_observed']} {r['live_url']}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("send", "check", "status"):
        print(__doc__)
        sys.exit(2)
    if args[0] == "send":
        sys.exit(cmd_send("--live" in args))
    sys.exit(cmd_check() if args[0] == "check" else cmd_status())
