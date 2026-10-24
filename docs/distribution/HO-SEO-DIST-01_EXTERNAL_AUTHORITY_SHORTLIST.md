# HO-SEO-DIST-01 — External Authority & Distribution Shortlist

| | |
|---|---|
| Status | **DRAFT — docs only. Nothing has been submitted, pitched, registered or posted.** |
| Date | 2026-10-24 |
| Governing doc | [`docs/23` §19 Authority development](../23_AI_CITATION_AND_DISCOVERY_STRATEGY.md) (no change to docs/23 or docs/24) |
| Measurement | Existing docs/24 / docs/29 loop; no new metric introduced here |
| Input lists | Specialist robotics outlets (researched 2026-10-24) first; [`alvinunreal/awesome-submitlist`](https://github.com/alvinunreal/awesome-submitlist) (CC0, `data/destinations.json`, 1,915 entries, synced 2026-10-19) second |

## 1. Purpose and boundary

docs/23 §19 says authority should come from robotics publications, manufacturers,
universities, labs, distributors, conferences, analysts, open technical projects and
datasets. It forbids automated backlink schemes, purchased links and fake mentions.

This document is a **ranked shortlist of places that could legitimately reference
HumanoidOnline**, with the evidence for each. It is not a submission plan in itself.

Hard rules for anything that follows from this shortlist:

1. **Every external submission, pitch, profile or post is a separate owner approval.**
   Approving this document approves none of them.
2. No paid listings, sponsored articles or paid press-release distribution.
3. No automation: no bulk submission, no submission tools, no scripted posting.
4. No fabricated author or reviewer identities (docs/23). Pitches go out under a real,
   owner-chosen name.
5. Company directories link to the homepage. Editorial pitches link to the specific
   research page that holds the evidence and methodology.
6. Success is measured as **published references, referral visits and later AI
   citations** (docs/24 loop), never as backlink count or domain rating.

## 2. What the submitlist contributes (and doesn't)

The dataset is mostly built around software launches: 1,556 of its 1,915 entries are
GitHub awesome-lists, and the leading categories are `developer-tools` (1,113),
`software` (356) and `ai` (263). A keyword pass for robot/humanoid found only
robotics awesome-lists, the Weekly Robotics project list, and the generic
startup/tech destinations (Hacker News, MIT Technology Review, StartupBlink, F6S,
EU-Startups, Crunchbase, Product Hunt). Its domain-rating, traffic and link-type
fields are the project's own claims and are **not** used to rank anything below.

Consequence: the specialist robotics outlets in §3 come from separate research, and
they carry the shortlist.

## 3. Shortlist

Link targets (production): homepage `https://humanoidonline.com/`; research pages
`/research/humanoid-availability/europe`, `/north-america`, `/asia`.

Channel status values:
- `CHANNEL_FOUND` — the outlet publishes a submission or tips route (checked 2026-10-24).
- `CHANNEL_UNVERIFIED` — a fit, but no confirmed public route; needs a manual check.
- `OWNER_DECISION` — blocked on a decision listed in §5 before it can be drafted.

### Tier A — specialist robotics (primary)

| # | Destination | Offer | Link target | Channel | Notes / evidence |
|---|---|---|---|---|---|
| A1 | **The Robot Report** (WTWH) | News tip: regional availability findings | Research page | `CHANNEL_FOUND` | Contact page lists a dedicated tips address. [contact](https://www.therobotreport.com/?p=78626) |
| A2 | **Robohub** | Contributed article on the evidence/UNKNOWN methodology; or ≤100-word tip | Research page | `CHANNEL_FOUND` | Takes tips (≤100 words + URLs), press releases and articles from non-professional writers; assigns an editor. [contribute](https://robohub.org/contribute/) |
| A3 | **Humanoids Daily** | Tip: humanoid availability by region | Research page | `CHANNEL_FOUND` | Humanoid-only outlet; contact page asks for tips on launches and industry movements. [contact](https://www.humanoidsdaily.com/contact) |
| A4 | **Weekly Robotics** (Mat Sadowski) | Link suggestion, or a "Publish with Weekly Robotics" article | Research page | `CHANNEL_FOUND` | Active (#381, 19 Oct 2026); site offers article publishing via the editor. Also in submitlist (`msadowski/awesome-weekly-robotics`). Beware the look-alike domain flagged on ROS Discourse. [site](https://www.weeklyrobotics.com/) |
| A5 | **IEEE Spectrum — Robotics** | Pitch: data-driven availability story | Research page | `CHANNEL_UNVERIFIED` | Strong fit; no public tips route found in this pass. Video Friday takes event submissions, which isn't relevant. |
| A6 | **Robotics 24/7** (Peerless Media) | News tip to editorial | Research page | `CHANNEL_UNVERIFIED` | Contacts page names editorial staff; no submission process described. [contacts](https://robotics247.com/site/contacts) |
| A7 | **Robotics & Automation News** | Free editorial feature request only | Research page | `CHANNEL_FOUND` | Free feature-request form exists; site also sells press releases and sponsored articles. **Paid options excluded.** [terms](https://roboticsandautomationnews.com/about/terms-of-use/) |
| A8 | **Humanoid awesome-lists on GitHub** (`jk4e/list-ai-humanoid-robots`, `jonyzhang2023/awesome-humanoid-learning`) | One-line PR adding HumanoidOnline as a catalogue/resource | Homepage | `CHANNEL_UNVERIFIED` | Each repo's CONTRIBUTING rules to be read before drafting. "Open technical projects" in §19. |
| A9 | **General robotics awesome-list** (`brandonhimpfen/awesome-robotics`, from submitlist) | One-line PR under resources/databases | Homepage | `CHANNEL_UNVERIFIED` | Same as A8; only if a fitting section exists. |
| A10 | **Humanoids Summit** — Silicon Valley, 1–2 Dec 2026 | Speaker application: regional availability data | Research page | `OWNER_DECISION` (D5) | Official site said SV applications were open; Tokyo 2026 closed. [site](https://humanoidssummit.com/hs2025sv) |
| A11 | **euRobotics** | Newsletter contribution / event listing | Research page | `OWNER_DECISION` (D3) | Newsletter has been members-only since 2021; membership is an organisation decision. [2026 newsletters](https://eu-robotics.net/2026-newsletters/) |
| A12 | **ROS Discourse — General** | — | — | Low fit | The General category is for ROS news and release announcements. HumanoidOnline is not ROS software. Revisit only if a data release ships. [about](https://discourse.ros.org/t/about-the-general-category/36) |

### Tier B — research/data channel

| # | Destination | Offer | Channel | Notes |
|---|---|---|---|---|
| B1 | **Dataset DOI** (e.g., Zenodo) | Citable snapshot of published catalogue facts | `OWNER_DECISION` (D4) | Fits §19 "research papers and datasets" and is the kind of reference researchers and AI systems cite. Needs a licence and export decision; **new scope, not part of this WorkOrder.** |

### Tier C — from the submitlist (secondary)

| # | Destination | Offer | Link target | Channel | Notes / evidence |
|---|---|---|---|---|---|
| C1 | **Hacker News** | Regular submission of a research page (not Show HN) | Research page | `CHANNEL_FOUND` | Show HN excludes "blog posts … lists and other reading material", so a research page goes in as a regular post. No vote solicitation. [Show HN rules](https://news.ycombinator.com/showhn.html) |
| C2 | **MIT Technology Review** | News pitch only with a specific, newsworthy finding | Research page | `CHANNEL_FOUND`, selective | Wants a specific story with clear urgency, not a topic. **AI-written pitches are deleted automatically**, so the owner writes it. [how to pitch](https://www.technologyreview.com/how-to-pitch-mit-technology-review/) |
| C3 | **EU-Startups** | European humanoid-market research pitch | Research page (Europe) | `CHANNEL_UNVERIFIED` + D1 | Listed in submitlist as an editorial citation; about page returned 403 in this pass. |
| C4 | **Crunchbase** | Organisation profile | Homepage | `OWNER_DECISION` (D1) | Requires a socially authenticated account (owner action); scope limited to the tech ecosystem. [requirements](https://support.crunchbase.com/hc/en-us/articles/115010642588-Requirements-to-Create-a-Crunchbase-Profile-Page) |
| C5 | **F6S** | Company profile | Homepage | `OWNER_DECISION` (D1) | Startup profile platform; eligibility not checked until D1 is settled. |
| C6 | **StartupBlink** | Startup map listing | Homepage | `OWNER_DECISION` (D1) | Listed in submitlist as nofollow; submission at `/startups/add`. |

### Excluded

| Destination | Reason |
|---|---|
| Product Hunt | Product launch format, weak fit for a reference catalogue. An earlier claim that its featuring rules exclude directories/reports was **not re-verified** in this pass. |
| Generic AI/SaaS directories and paid directories in the submitlist | No robotics audience. These are the low-value directory links docs/23 §19 is meant to avoid. |
| Other humanoid databases/guides | Competitors are radar only (DATA-D1); a listing there is not independent authority. |
| Wikipedia / Wikidata self-insertion | Conflict of interest; references must come from independent editors. |
| r/robotics and similar subreddits | Self-promotion rules could not be read (fetch blocked). Deferred, not rejected. |

## 4. Preconditions before any editorial pitch

1. **Editorial status of the research pages.** Records show the North America and
   Asia research resources' editorial copy is still marked DRAFT. Pitches should
   point only at pages the owner considers final.
2. **The pitched finding must be on the page.** Each pitch cites one specific,
   evidence-linked finding; UNKNOWN stays UNKNOWN in pitch copy too.
3. **One outlet at a time per finding** for news tips. No identical blast to every
   Tier A outlet.

## 5. Owner decisions (open)

| ID | Decision | Blocks |
|---|---|---|
| D1 | Which legal/public identity HumanoidOnline presents (entity, founder name, location) on company profiles | C3–C6 |
| D2 | Whose name signs pitches and articles (no fabricated identities; MIT TR bans AI-written pitches) | All Tier A/C pitches |
| D3 | Whether to join euRobotics | A11 |
| D4 | Whether to publish a licensed dataset snapshot (new scope; own WorkOrder) | B1 |
| D5 | Whether to apply to speak at Humanoids Summit SV | A10 |
| D6 | Approval of each individual draft before it is sent | Everything |

## 6. Proposed next step (PROPOSE ONLY)

Draft, without sending, the first three Tier A items once D2 is answered: A2 Robohub
article outline, A3 Humanoids Daily tip, A4 Weekly Robotics suggestion. Each draft
names its target page and the single finding it carries. The owner approves or edits
each one and sends it, or approves sending it.

Record results (accepted / declined / no reply, published URL, date) in a follow-up
section of this document. Referral and citation effects go through the existing
docs/24 loop.
