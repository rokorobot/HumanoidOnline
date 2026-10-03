# XPENG (xpeng.com) structural review: 2026-10-03

Read-only inspection of the official XPENG site for the humanoid robot **IRON**, performed before
the `xpeng-official` adapter was written. It limits what the adapter assumes.

## Authority

Robert Konecny (product owner), work order "XPENG / IRON governed manufacturer onboarding",
2026-10-03: XPENG official web sources on `xpeng.com` are **OWNER-APPROVED / ALLOWED** for governed
research and discovery of the XPENG humanoid IRON. robots.txt and terms are recorded for
provenance and do not reopen that decision. No technical access control is ever bypassed.

## Requests (5, crawler user agent `HumanoidOnlineMarketBot/0.1`, 3 s apart, all HTTP 200)

| URL | Result |
|---|---|
| `https://www.xpeng.com/robots.txt` | 200; `User-agent: *` disallows only `/api` and several query-string patterns; no group names our token; no crawl-delay |
| `https://www.xpeng.com/technology/ai_robot_iron` | 200, server-rendered, about 398 KB |
| `https://www.xpeng.com/news/01a080371029a057bc8e8a02a2c6012b` | 200 (2026-09-08 production-line release) |
| `https://www.xpeng.com/au/news/019e71be4f9e9dd703de8a0282290455` | 200 (2025-11-05 Next-Gen IRON release, Australian copy) |
| `https://www.xpeng.com/news/019301d2135392fa562d8a0282200016` | 200 (2024-11-06 AI Day 2024 release) |

`robots_status` is therefore honestly `ALLOWED`. There was no technical block.

## Page structure

- All four pages carry a correct `canonical` link and `og:url`. The IRON product page's `<title>`,
  `og:title` and JSON-LD `WebPage.name` are **generic XPENG car-site boilerplate**, so identity is
  read from the visible title block (`XPENG Next-Gen IRON: The Most Human-Like Robot`) plus the URL
  slug, and never from the title tag.
- News bodies are `<font>` runs separated by `<br>`, not `<p>` elements. The extractor therefore
  works on visible text *lines* (any non-inline element, `<br>` or `<img>` ends a line).
- The 2024 release lists several products; only the "XPENG AI Robot Iron" bullet is read.
- The product page has no `<h1>`; the news pages' dates are visible text lines.

## What the adapter is (and is not)

A **fixed set of four seed pages**, no link-following (`target_cap` is the minimum). Only the product
page can yield a candidate (identity only). XPENG cars, Robotaxi, flying cars and generic Physical AI
are never read as humanoid candidates. Every specification, date and plan is a **proposal**, never a
claim, produced by the separately versioned `xpeng-iron-proposals` extractor.

## IRON identity and generation chronology (official wording)

| Date | Official source | What XPENG says |
|---|---|---|
| 2024-11-06 | AI Day 2024 release | "XPENG AI Robot Iron ... developed over five years, has more than 60 joints and 200 degrees of freedom"; already integrated into XPENG's daily operations, internal applications such as factories and stores |
| 2025-11-05 | Next-Gen IRON release | "In 2024, XPENG released its **first-generation IRON**"; **Next-Gen IRON** is a comprehensive upgrade ("Compared with the first-generation IRON, the Next-Gen IRON has achieved comprehensive upgrades in bionic structure, intelligence system, and energy architecture"): 82 DoF throughout the body, 22 DoF in the hand, 3 Turing AI chips, 3000 TOPS effective computing power, all-solid-state battery |
| 2026-09-08 | production-line release | "XPENG's next-generation IRON": 76 DoF across the body and 21 in each hand, three Turing AI chips, up to 2,250 TOPS; production lines commissioned; mass production planned by the end of this year, initial rollouts in XPENG's own stores and campuses, market launch and delivery in China and overseas planned for 2027 |
| undated | IRON product page | titled "XPENG Next-Gen IRON"; states 22-DoF hands and three Turing chips; carries a teaser that IRON "Rolls Off XPENG's New Production Line" |

Conclusion used for catalogue identity: XPENG itself names **one IRON product line** with a
first-generation robot (2024) and a "Next-Gen IRON" (2025) whose 2026 production configuration it
calls "next-generation IRON" again. There is one catalogue robot, `xpeng-iron`, representing the
current Next-Gen line; the first-generation robot is historical evidence. The differing 2025 / 2026
figures (body DoF 82 / 76, hand DoF 22 / 21, 3000 / 2,250 TOPS) are different official statements about
the Next-Gen robot at different times; they are kept apart, never averaged and not called errors.
The product page still carries the 2025 hand figure (22) while the newest release says 21; that is
recorded and left for a human, not resolved here.

## Maturity

Nothing in these sources moves `commercial_status` off `UNKNOWN` without interpretation (the data
dictionary maps no maturity from manufacturing progress, internal use, planned mass production or a
planned 2027 launch). The previous catalogue value `ANNOUNCED` had no evidence row, so it is reset to
`UNKNOWN`, which asserts nothing.
