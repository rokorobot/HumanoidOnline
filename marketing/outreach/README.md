# Backlink outreach

Works through the 40 opportunities in [`../backlink-opportunities-2026-11.md`](../backlink-opportunities-2026-11.md).
Standard library only; no installs.

| File | What it is |
|---|---|
| `targets.csv` | The tracker: one row per opportunity. Open it in Excel or Google Sheets. |
| `pitches/<id>.md` | A personalized draft for each target. Email drafts have `Subject:` / `Followup-Subject:` headers and a `--- follow-up ---` section. The rest are text to paste into a form, PR or post. `listing.md` is the shared directory copy. |
| `outreach.py` | `status`, `send` (dry run by default), `send --live`, `check` |
| `test_outreach.py` | `python3 -m unittest marketing/outreach/test_outreach.py` |

## How a pitch goes out (approval mode)

1. Read the draft in `pitches/<id>.md` and edit it if you like.
2. Set that row's `status` to `approved` in `targets.csv`.
3. Run `python3 marketing/outreach/outreach.py send` to preview, then `send --live` to send.
   - It sends at most 5 emails per run.
   - It sends each approved pitch once, then marks it `sent` with the date.
   - It sends one follow-up 9 days later if the row is still `sent`.
4. When someone replies, set the row's `status` to `replied`. That stops the follow-up. Other statuses: `rejected`, `optout`, `accepted`.
5. When a link goes live, paste its URL into `live_url`. `check` (also run weekly by the loop) records the real `rel` attribute (`followed`/`nofollow`/`ugc`/`sponsored`/`missing`) and sets the row to `live`.

Rows with `channel` = `form`, `post`, `pr` or `manual` are never emailed. Submit those by hand, or ask the agent to fill the form (you approve each submit). Reddit, Hacker News and forum posts must be posted by you: automated posting breaks those sites' rules.

## Settings (environment variables or `marketing/outreach/.env`, never committed)

`SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `OUTREACH_FROM`, `OUTREACH_FROM_NAME`, `OUTREACH_SENDER_TITLE`, `OUTREACH_POSTAL_ADDRESS`

- **Gmail:** `smtp.gmail.com`. Use an app password (needs 2-step verification on the account).
- **Outlook / Microsoft 365:** `smtp.office365.com`.
- `send --live` refuses to run without a postal address. Every email carries the sender's name, the address and a "reply no" opt-out (US CAN-SPAM). Check the stricter EU/Czech rules on unsolicited commercial email before sending at volume.

## Before each batch

The figures in the drafts are from the 10 November 2026 snapshot (52 published humanoids; 5 with a confirmed North America offer). Re-check https://humanoidonline.com/research/humanoid-availability/north-america and update the drafts if the numbers have changed.
