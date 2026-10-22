# HO-DATA-30 Phase 2 — new manufacturer evidence: addendum to the Phase 1 brief

First read the Phase 1 brief at
`C:/Users/Robert/AppData/Local/Temp/claude/C--Users-Robert-HumanoidOnline/134b99f9-30db-4d44-b044-01ec8e63f4b7/scratchpad/h30w/BRIEF.md`.
All its rules apply unchanged: authority, manufacturer hosts only, never robotshop, no bypassing, the field semantics,
the CLEAN/HELD definitions, the output format and the "a wrong CLEAN is worse than silent" principle.

## What is different in Phase 2
Your group file lists, per robot, only the cells that Phase 1 found **source-silent, unavailable or host-unconfirmed**
(`silent_fields`), plus the values already known. The first-pass documents (main product pages, main spec tables) have
been read. Go **deeper**:

1. **First-party PDFs:** datasheets, brochures, user manuals and quick-start guides on manufacturer hosts or their CDNs.
   Look for "download", "brochure", "datasheet", "manual" and "spec" links in page HTML and JS assets.
2. **Image-based specification tables on manufacturer hosts.** Many sites (UBTECH, Kepler, AgiBot, Unitree) publish the
   spec table as an image.
   - Download the image to `raw/` and record its sha256.
   - Look at it with the Read tool. For a PDF, render it to PNG with
     `uv run --with pymupdf python -I <script>` (`fitz.open(pdf)[i].get_pixmap(dpi=130).save(png)`).
   - Transcribe the exact text of the relevant row.
   - Use status **`IMAGE_CLEAN`** (instead of CLEAN) when the value is clearly legible and meets every CLEAN rule.
   - In `note`, add the image URL, the page or element that embeds it, and where in the image the row is.
   - Never guess a partly legible value; record it as CHECKED_SILENT with a note.
3. **Developer documentation and official repositories:**
   - GitHub orgs: check via `https://github.com/<org>` HTML or `https://api.github.com/orgs/<org>/repos`, and read
     README files raw.
   - Hugging Face orgs.
   - Developer portals.
   - The Chinese-locale versions of manufacturer sites and documents (zh pages often carry fuller spec tables).
   - The host must demonstrably be the manufacturer's: linked from the manufacturer's site, or the manufacturer's
     domain. Record how you established that in `note`.
4. **Technical contacts** (for owner-sent data requests): collect every **published** contact route per manufacturer
   from first-party pages, such as a sales or technical email, a developer support email, a contact form URL or a
   partner portal. Quote it with its source URL. Do not submit forms and do not send anything.

## Output
In your output dir:
- `findings.jsonl`: one row per listed cell, same schema as Phase 1. `status` may also be `IMAGE_CLEAN`.
- `sources.md`: as in Phase 1.
- `contacts.md`: per manufacturer, the published contact routes with source URLs, and which one looks like the
  technical or developer route.

Final reply:
- counts by status;
- every CLEAN and IMAGE_CLEAN row (slug, field, value, url, raw_file);
- the contacts found;
- the best remaining leads.
