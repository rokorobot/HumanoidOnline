---
name: free-backlink-finder
description: Research and verify up to 50 free, legitimate backlink opportunities for a website (directories, resource pages, community profiles, guest posts, competitor links), with evidence-based link attributes, ranking, outreach templates and a 7-day plan. Use for "free backlink finder", "find backlinks", "link building research".
argument-hint: "<website URL> | <niche> | <target country>"
---

# Free Backlink Finder

## 0. Collect the input fields

Arguments given: `$ARGUMENTS`

Parse them as `Website | Niche | Target Country`. If any of the three is missing, **stop and ask the user in chat** before doing any research. Ask in exactly this format and wait for the reply:

```
Please fill in:
Website: 
Niche: 
Target Country: 
```

Once you have all three, substitute them into the prompt below and run it.

---

## The research prompt

Act as an expert SEO link-building researcher. Your mission is to find 50 legitimate, free backlink opportunities for my website.

Website: {WEBSITE}
Niche: {NICHE}
Target Country: {COUNTRY}

### Step 1: Analyze My Website

Visit my website and identify:

* My niche, audience, and primary topics
* Products, services, or resources worth linking to
* Relevant industries and communities
* Natural opportunities to earn backlinks

### Step 2: Find 50 Free Backlink Opportunities

Search the live web and identify opportunities across these categories:

1. Free directories (10): Niche-specific, business, startup, and resource directories that accept free submissions.
2. Resource pages (10): Websites with curated lists where my content would be a relevant addition.
3. Community and profile links (10): Legitimate platforms where businesses or creators can publish profiles with website links.
4. Guest posting (10): Relevant websites accepting unpaid guest articles or contributor submissions.
5. Competitor backlink opportunities (10): Websites linking to similar businesses that I could realistically approach.

Prioritize lesser-known, niche-relevant opportunities over generic SEO directories.

### Step 3: Verify Every Opportunity

For each opportunity:

* Confirm the website is live.
* Find the exact submission, registration, contributor guidelines, or contact page.
* Verify that a free submission option exists.
* Determine whether an external website link is allowed.
* Identify whether the link is followed, nofollow, sponsored, or unknown. Never guess.
* Exclude paid-only listings, spam networks, link farms, and irrelevant websites.
* Flag anything that cannot be verified.

Do not invent URLs, domain authority metrics, or submission requirements.

### Step 4: Present the Results

Create a table with:

| Website | Opportunity Type | Submission URL | Cost | Link Attribute | Difficulty |

For each opportunity, also explain exactly how to obtain the backlink and why it is relevant to my website.

Include source links supporting your verification.

### Step 5: Rank the Opportunities

Rank all 50 opportunities using:

* Niche relevance
* Likelihood of approval
* Ease of acquisition
* Potential referral traffic
* Trustworthiness of the website

Do not use domain authority as the sole ranking factor.

### Step 6: Create an Action Plan

Finally, provide:

1. The 10 easiest backlinks I can pursue today.
2. The 10 most valuable editorial opportunities.
3. Five personalized outreach email templates.
4. A seven-day backlink acquisition plan.
5. A checklist for tracking submissions, approvals, and acquired links.

### Important Rules

* No paid opportunities.
* No fake or fabricated websites.
* No guaranteed dofollow claims without evidence.
* No duplicate domains.
* No spammy link schemes.
* If fewer than 50 legitimate opportunities can be verified, return fewer rather than inventing results.

Goal: Give me a researched, actionable list of free backlink opportunities I can realistically pursue, not a generic list of websites everyone already knows.

---

## How to run it efficiently (lessons from the first run)

- **Find candidates:** run several `WebSearch` queries in one turn: niche "write for us", "contributor guidelines", "submit"; niche directories; GitHub "awesome" lists; university LibGuides for the topic; newsletters that take link tips; competitor trackers.
- **Find competitor links without paid SEO tools:**
  - List the competitors' outbound domains (badges, partners, events) from their homepages.
  - Search for pages that mention competitor domains, e.g. features and launch posts.
  - Note where competitors launched (Product Hunt, AlternativeTo, Brandfetch, and similar).
- **Check liveness in one batch:** run `curl -sL -w "%{http_code}"` over a URL list, using a browser user agent.
- **Check link attributes with evidence, not memory:**
  - Fetch a page that has the *same kind* of link you would get: a listing page, an in-article link, or a profile website link. Run `python3 -I scripts/rel.py page.html <url>` on it.
  - For in-article links, read the site's RSS feed (`/feed/`). Check `content:encoded` for `rel`.
  - Use `scripts/txt.py page.html "free|paid|nofollow|dofollow|bio|link"` to pull the site's stated policy.
  - Report it as *Followed (observed)*, *Nofollow (observed)*, *Stated*, or *Unknown*.
- **Cloudflare-blocked sites** (Product Hunt, AlternativeTo, Crunchbase, Reddit and others): try `browser-harness` once. If it still shows a challenge page, mark the attribute **Unknown**. Don't keep retrying.
- **Duplicate domains:** combine several GitHub repos or several services on one site into one row.
- **Exclude** guest-post farms (generic "write for us" sites covering every topic) and cross-linked site networks.
- **Output:** write the full report to `marketing/backlink-opportunities-<YYYY-MM>.md`, and give a condensed ranked table in chat. Commit or push only when the user asks.
