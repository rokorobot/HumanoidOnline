# HO-DATA-02B retrieval log (2026-10-22)

**Work order:** "HO-DATA-02B 2026-10-22", AGENT_ASSISTED_RESEARCH (docs/26 R5). Retrieval was read-only; nothing
was written to any source.

**Who fetched:**
- **ORCH** is the orchestrator (Claude Opus 5.5) using raw `curl`. The hash column is the first 16 hex characters of
  the sha256 of the body.
- **AGENT** is one of five Sonnet research agents using WebFetch, which returns a model summary of the page, not a
  byte copy. No hash is available for these.

**Outcomes:** OK, 301 (redirect), 404, ECONNRESET, DNS (host not found), TOO_LARGE, NO_SPECS (fetched, but no
specification content), JS/IMG (values are rendered only in an image or by script).

## Manufacturer / first-party

| URL | By | Outcome | Hash | Used for |
|---|---|---|---|---|
| https://www.agibot.com/products/A2_Ultra | ORCH, AGENT | OK | 1b596c3d3c3a11fa | A2 Ultra spec table (EN) |
| https://agibot.com/jp/products/A2_Ultra | ORCH, AGENT | OK | a1984883aecaa036 | A2 Ultra spec table (JP), speed/payload conflict |
| https://store.agibot.com/products/a2-ultra.json | AGENT | OK | — | weight 69.0 kg (relayed) |
| https://store.agibot.com/products/a2-ultra | AGENT | TOO_LARGE | — | — |
| https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/specifications/ | ORCH, AGENT | OK | f30c459c972c497f | T1 specifications |
| https://docs.booster.tech/zh-CN/docs/product-manual/t1/getting-started/overview/ | AGENT | OK | — | T1 overview |
| https://docs.booster.tech/zh-CN, /zh-CN/product-manual/ | AGENT | OK | — | manual index |
| https://www.booster.tech/booster-t1 (+ 4 URL variants) | AGENT | NO_SPECS (T2/K1 landing only) | — | — |
| https://www.booster.tech/booster-t2 | AGENT | OK | — | T2 footnote, end effector, battery |
| https://github.com/BoosterRobotics, /booster_assets, /booster_robotics_sdk | AGENT | OK | — | T1 DoF layouts (lead) |
| https://booster.gitbook.io/booster-robotics-developer-docs | AGENT | 404 | — | — |
| https://www.galbot.com/g1 → http://www.galbot.com/g1/ | ORCH, AGENT | 301 → OK | 4f3b10993e3cdb1d | Galbot G1 spec table |
| https://www.ubtrobot.com/en/humanoid/products/walker-s2 | ORCH, AGENT | OK (spec = image) | aee635e54335ad39 | Walker S2 EN |
| https://www.ubtrobot.com/cn/humanoid/products/walker-s2 | ORCH | OK | 7ab544e5285c6eb4 | Walker S2 CN tiles |
| https://owebsite-cdn.ubtrobot.com/resources/image/2025/07/24/701244770754629.png | ORCH | OK (image) | d5dc2a359465139d | Walker S2 hardware diagram (EN) |
| https://owebsite-cdn.ubtrobot.com/resources/image/2025/07/24/701244363923525.png | ORCH | OK (image) | — | Walker S2 hardware diagram (CN) |
| https://maxtronics.com/wp-content/uploads/nao-v6-datasheet-en-20260605-maxtronics_v5.pdf | ORCH, AGENT | OK | d452b3e2ca0cd0e6 | NAO6 datasheet |
| https://maxtronics.com/nao6/ | ORCH, AGENT | OK | 20ec1d3c8590c0b1 | NAO6 page (58 cm, 25 DoF) |
| https://maxtronics.com/en/nao | AGENT | OK (NO_SPECS) | — | publisher |
| https://www.aldebaran.com/en/nao, /en/pepper | AGENT | 301 → maxtronics.com | — | ownership chain |
| https://maxtronics.com/en/pepper, /pepper/, /en/pepper-robot-in-europe/, /en/support/kb/pepper/general/pepper-technical-specifications/ | AGENT | OK (NO_SPECS) | — | Pepper status |
| https://us.softbankrobotics.com/pepper | AGENT | OK (NO_SPECS) | — | — |
| https://developer.softbankrobotics.com/pepper-naoqi-25/pepper-documentation/pepper-technical-specifications | AGENT | 301 → aldebaran.com | — | — |
| https://doc.aldebaran.com/2-8/… (NAO6), /2-5/… and /2-4/… (Pepper: index, dimensions, masses, battery) | AGENT | ECONNRESET | — | BLOCKED |
| https://web.archive.org/… | AGENT | refused by the fetch tool | — | — |
| https://www.rainbow-robotics.com/, /en/, /company/회사소개/, /…/헤리티지-스토리/, /en/company/heritage-story/, /en/company/core-technology/ | AGENT | OK (NO_SPECS) | — | HUBO heritage only |
| https://www.unitree.com/g1, /H2 | AGENT | OK | — | "/" and footnotes |
| https://www.unitree.com/R1 | ORCH, AGENT | OK | 0dad7acfd9c1f093 | R1 torque/load row, "/" |
| https://shop.unitree.com/products/unitree-r1 | ORCH, AGENT | OK | 0628b7c8ad5a3a30 | "Only the EDU version supports secondary development." |
| https://neurarobotics.px.media/plk/Jj/4NE1Minidatasheet.pdf | AGENT | OK | — | 4NE1 Mini datasheet |
| https://neura-robotics.com/product/4ne1-mini-reservation | ORCH, AGENT | OK | c75543d69a8a79e6 | interfaces for Standard and Pro |
| https://www.agilityrobotics.com/solutions/digit-5 | AGENT | OK | — | Digit 5 footnotes |

## Originating lab (scope extension, flagged D11)

| URL | By | Outcome | Used for |
|---|---|---|---|
| https://breakthroughs.kaist.ac.kr/sub02/view/id/289 | AGENT | OK | DRC-HUBO+ 173 cm / 82 kg / 32 DoF (relayed) |
| https://news.kaist.ac.kr/newsen/html/news/?mode=V&mng_no=4010 | AGENT | OK | DRC-HUBO (2013) 34 DoF / 4.7 ft / 120 lbs (relayed) |
| http://hubolab.kaist.ac.kr/ | AGENT | DNS | — |

## Third-party (leads only; never used as values)

Seen in WebSearch snippets, or named by agents and not fetched:
- Wikipedia (NAO, Rainbow Robotics), aiwiki.ai
- generationrobots.com, quakelogic.net (T1 datasheet), RoboCup team spec sheets (hsl.robocup.org)
- the ROS wiki HUBO page, koasas.kaist.ac.kr, pure.seoultech.ac.kr
- newatlas.com, therobotreport.com, and Korean news sites

RobotShop was not opened.
