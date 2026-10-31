import json, sys
from collections import Counter
run = sys.argv[1]; d = json.load(open(f"{run}/observations.json")); O = d['observations']; N = len(O)
surf = list(dict.fromkeys(o['product_surface'] for o in O)); qs = list(dict.fromkeys(o['query_id'] for o in O))
st = Counter(o['humanoidonline_cited'] for o in O)
obsv = [o for o in O if o['humanoidonline_cited'] not in ('UNOBSERVABLE','ENGINE_ERROR','AMBIGUOUS')]; D = len(obsv)
cit = sum(o['humanoidonline_cited']=='CITED' for o in obsv); lnk = sum(o['humanoidonline_cited'] in ('CITED','LINKED_NOT_CITED') for o in obsv)
L = []; w = L.append
w(f"# AI Visibility Baseline — {d['run_id']} (R1)\n")
w("Internal measurement record under `docs/24` as amended by `docs/29` (incl. D7). Makes no external claim.\n")
w("## 1. Disclosure\n")
w(f"| Item | Value |\n|---|---|\n| Window | {d['window_start']} → {d['window_end']} (UTC) |\n| Registry | v2 (10 queries, `docs/29` §5) |")
w("| Collection | treg-only (owner decision D7, 2026-10-31); no manual reference run |\n| Surfaces included | " + "<br>".join(f"`{s}`" for s in surf) + " |")
w("| Surfaces excluded | ChatGPT / Gemini / Perplexity / Google AI Mode consumer UIs as seen by a human (no manual run, D7); Microsoft Copilot; Google AI Overviews (`docs/29` §4) |")
w("| Region / language | `DE` / `en` for the three cloro surfaces; Perplexity API has no region parameter |\n| Reviewer | Pending — owner (D5). Result states derived mechanically; correctness not yet scored |")
w(f"| Observations | {N} — " + ", ".join(f"{k} {v}" for k, v in st.items()) + f" |\n| Observability coverage | {D} of {N} observable |\n| Spend | ≈ $0.09 of the $2 R1 + R2 authorization |\n")
w("## 2. Headline\n")
w("| Metric | Value |\n|---|---|")
w(f"| `citation_rate` | {cit} of {D} |\n| `linked_source_rate` | {lnk} of {D} |\n| `first_source_rate` | 0 of {D} |\n| `correct_answer_with_citation_rate` | 0 of {D} (no `CITED` observation, so independent of the pending correctness review) |")
w("| `citation_correctness_rate` | not reported — 0 `CITED` |\n| `unattributed_use_rate` | not assessed (field `unknown` throughout) |\n")
w("**HumanoidOnline was not cited, linked or mentioned in any of the 40 answers.** humanoidonline.com was reachable (HTTP 200) and `robots.txt` allows all crawlers on the day of the run.\n")
w("## 3. By surface and by query\n")
w("| Surface | CITED | Observable |\n|---|---|---|")
for s in surf: g=[o for o in obsv if o['product_surface']==s]; w(f"| `{s}` | {sum(o['humanoidonline_cited']=='CITED' for o in g)} | {len(g)} |")
w("\n| Query | Text | CITED | Observable |\n|---|---|---|---|")
for q in qs: g=[o for o in obsv if o['query_id']==q]; w(f"| `{q}` | {g[0]['query_text']} | {sum(o['humanoidonline_cited']=='CITED' for o in g)} | {len(g)} |")
w("\n## 4. Regional resources (queries 1–3)\n")
w("Post-publication baseline: Europe published 2026-10-05, North America 2026-10-23, Asia 2026-10-24 (`docs/29` §2). No pre-publication baseline exists for NA or Asia.\n")
w("| Query | Surface | HumanoidOnline URL cited | Sources cited instead |\n|---|---|---|---|")
for q in qs[:3]:
    for o in O:
        if o['query_id']==q: w(f"| `{q}` | {o['engine']} | none | {', '.join(o['competitor_sources']) or '—'} |")
w("\n## 5. By URL\n")
w("| Target URL | Cited in |\n|---|---|\n| `/research/humanoid-availability/europe` | 0 of 4 (COMMERCIAL-003) |\n| `/research/humanoid-availability/north-america` | 0 of 4 (COMMERCIAL-004) |\n| `/research/humanoid-availability/asia` | 0 of 4 (COMMERCIAL-005) |\n| any HumanoidOnline URL | 0 of 40 |\n")
w(f"## 6. Competitor sources\n\n`competitor_citation_frequency`, top 25 domains, each as answers citing it of {D} observable answers.\n")
w("| Domain | Answers |\n|---|---|")
for k, v in Counter(x for o in obsv for x in o['competitor_sources']).most_common(25): w(f"| {k} | {v} of {D} |")
w("\nDirectory/aggregator sites comparable to HumanoidOnline that *were* cited include humanoid.guide, humanoza.com, blog.robozaps.com, humanoid.observer, deploy.report, robotsguide.com and humanoid.press.\n")
w("## 7. Repeatability\n\nPending R2 (5–9 days after R1, `docs/29` §6.1: 2026-11-05 to 2026-11-09).\n")
w("## 8. Catalogue findings\n\nPending owner correctness review. Raw answers are in `evidence/` for that review.\n")
w("## 9. Deviations from `docs/29` §6\n")
for x in ["**Collector:** treg-only, agent-run on owner instruction (D7); no manual run, no human-view reference.",
 "**Region:** `DE`, not the expected `CZ` — cloro's ChatGPT endpoint refuses `CZ`; `DE` used on all three cloro surfaces for consistency. Perplexity API takes no region.",
 "**Perplexity surface:** Perplexity's Agent API (`fast` preset, 1 step, ≤ 512 output tokens), not the Perplexity web app; treg offers no scrape of the web app. Not comparable with a human Perplexity web observation.",
 "**Session / authentication:** provider-run sessions; authentication and personalization recorded as `unknown`.",
 "**Evidence:** raw API response JSON per observation (with SHA-256 in `notes`), not screenshots. cloro's hosted HTML renders were not requested.",
 "**Review:** result states derived mechanically from returned source URLs and answer text (`humanoidonline` / `humanoid.company`); `reviewed_by` and correctness are blank until the owner reviews.",
 "**Retry:** `COMMERCIAL-001` × Gemini timed out once upstream (HTTP 502, not charged) and succeeded on immediate retry; the retry is the recorded observation."]: w(f"- {x}")
open(f"{run}/REPORT.md", "w").write("\n".join(L) + "\n")
