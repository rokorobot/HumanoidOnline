"""Build docs/24 §4 observations.json from raw treg evidence files."""
import json, glob, hashlib, os, re, sys
from urllib.parse import urlsplit
run = sys.argv[1]; run_id = os.path.basename(run.rstrip('/'))
QT = dict(re.findall(r'\("([A-Z]+-\d+)","([^"]+)"\)', open(os.path.join(os.path.dirname(__file__), 'collect.py')).read()))
ORDER = list(QT)
SURF = {"chatgpt": ("ChatGPT", "ChatGPT via treg/cloro.ai-search.chatgpt.scrape"),
        "gemini": ("Gemini", "Gemini via treg/cloro.ai-search.gemini.scrape"),
        "aimode": ("Google", "Google AI Mode via treg/cloro.google.serp.ai_mode"),
        "perplexity": ("Perplexity", "Perplexity API via treg/perplexity.web.answer.fast")}
HO = re.compile(r"humanoid[\s-]?online|humanoid\.company", re.I)
def clean(u):
    p = urlsplit(u); q = '&'.join(x for x in p.query.split('&') if x and not x.startswith(('utm_','hsa_')))
    return p._replace(query=q, fragment='').geturl()
def dom(u): d = urlsplit(u).netloc.lower(); return d[4:] if d.startswith('www.') else d
obs = []
for qid in ORDER:
    for s, (engine, surface) in SURF.items():
        path = f"{run}/evidence/{qid}__{s}.json"; raw = open(path, 'rb').read(); d = json.loads(raw)
        r = d['response']['result']
        if s == 'perplexity':
            text = ' '.join(c['text'] for o in r['output'] if o['type']=='message' for c in o['content'])
            res = {x['id']: x['url'] for o in r['output'] if o['type']=='search_results' for x in o['results']}
            refs = sorted({int(n) for n in re.findall(r'\[(\d+)\]', text)})
            urls = [res[n] for n in refs if n in res]; model = r.get('model')
            ctx = f"{len(urls)} sources cited by [n] markers (of {len(res)} search results); answer capped at 512 output tokens"
        else:
            r = r.get('result', r); text = r.get('markdown') or r.get('text') or ''
            urls = [x['url'] for x in (r.get('sources') or [])] + [x['url'] for x in (r.get('citationPills') or [])]
            model = r.get('model'); ctx = f"{len(r.get('sources') or [])} sources, {len(r.get('citationPills') or [])} citation pills"
        urls = list(dict.fromkeys(clean(u) for u in urls))
        ho_src = [u for u in urls if HO.search(dom(u))]
        ho_link = re.findall(r'https?://(?:www\.)?humanoidonline\.com\S*', text)
        state = ("CITED" if ho_src else "LINKED_NOT_CITED" if ho_link else
                 "MENTIONED_NOT_LINKED" if HO.search(text) else "NOT_CITED") if text.strip() else "ENGINE_ERROR"
        sha = hashlib.sha256(raw).hexdigest()
        obs.append({
          "observation_id": f"{run_id}-{len(obs)+1:04d}", "run_id": run_id, "observed_at": d['observed_at'],
          "engine": engine, "product_surface": surface, "engine_version_or_label": model,
          "query_id": qid, "query_text": QT[qid], "locale": "en", "region": "DE", "language": "en",
          "authentication_state": "unknown", "personalization_state": "unknown",
          "humanoidonline_cited": state, "humanoidonline_url": (ho_src or ho_link or [None])[0],
          "citation_position": "unknown" if state == "CITED" else "not-applicable",
          "citation_context": ctx + ("; no HumanoidOnline source, link or mention" if state == "NOT_CITED" else ""),
          "answer_correctness": None, "answer_correctness_notes": "Pending owner review (docs/24 §6).",
          "competitor_sources": sorted({dom(u) for u in urls} - {dom(u) for u in ho_src}),
          "competitor_urls": [u for u in urls if u not in ho_src],
          "humanoidonline_fact_used_without_citation": "unknown", "possible_unattributed_use_notes": "",
          "evidence_type": "api-response-json", "evidence_reference": os.path.relpath(path, os.path.join(os.path.dirname(__file__), '../../../..')),
          "reviewed_by": None, "reviewed_at": None,
          "notes": f"sha256:{sha}; collected by agent via treg on owner instruction (docs/29 D7); result state derived mechanically from returned sources and answer text; awaiting owner review"})
json.dump({"run_id": run_id, "registry_version": "2", "window_start": min(o['observed_at'] for o in obs),
           "window_end": max(o['observed_at'] for o in obs), "observations": obs},
          open(f"{run}/observations.json", 'w'), indent=1, ensure_ascii=False)
from collections import Counter
print(Counter(o['humanoidonline_cited'] for o in obs))
c = Counter(d for o in obs for d in o['competitor_sources']); print(c.most_common(25))
for q in ORDER[:3]:
    for o in obs:
        if o['query_id']==q: print(q, o['engine'], o['competitor_sources'][:12])
