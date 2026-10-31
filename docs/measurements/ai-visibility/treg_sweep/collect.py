"""HO-AEO-00 treg sweep: 10 frozen queries x 4 surfaces -> raw evidence JSON."""
import json, os, subprocess, sys, datetime, concurrent.futures as cf
out = sys.argv[1]; region = "DE"
os.makedirs(f"{out}/evidence", exist_ok=True)
Q = [("COMMERCIAL-003","Which humanoid robots can be purchased in Europe?"),
("COMMERCIAL-004","Which humanoid robots can be purchased in North America?"),
("COMMERCIAL-005","Which humanoid robots can be purchased in Asia?"),
("COMMERCIAL-002","Which humanoid robots are commercially available?"),
("COMMERCIAL-001","How much does the Unitree G1 cost?"),
("CAPABILITY-001","Which humanoid robots have SDK access?"),
("CAPABILITY-003","Which humanoid robots are suitable for research?"),
("COMPARE-002","Unitree G1 vs Booster K1."),
("ENTITY-003","How tall is the Unitree G1?"),
("MARKET-002","How many commercial humanoid robots exist?")]
S = {"chatgpt": ("cloro.ai-search.chatgpt.scrape", lambda p: {"prompt":p,"country":region,"include":{"markdown":True}}),
     "gemini": ("cloro.ai-search.gemini.scrape", lambda p: {"prompt":p,"country":region,"include":{"markdown":True}}),
     "aimode": ("cloro.google.serp.ai_mode", lambda p: {"prompt":p,"gl":region,"hl":"en","include":{"markdown":True}}),
     "perplexity": ("perplexity.web.answer.fast", lambda p: {"preset":"fast","input":p,"max_steps":1,"max_output_tokens":512})}
def run(qid, text, s):
    path = f"{out}/evidence/{qid}__{s}.json"
    if os.path.exists(path): return path, "skip"
    ep, body = S[s]; ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    r = subprocess.run(["treg","call",ep,"--method","POST","--json","--data",json.dumps(body(text))],
                       capture_output=True, text=True, timeout=300)
    rec = {"observed_at": ts, "endpoint": ep, "request": body(text), "exit_code": r.returncode,
           "stdout": r.stdout if r.returncode else None, "stderr": r.stderr[-2000:] or None}
    try: rec["response"] = json.loads(r.stdout); rec["stdout"] = None
    except Exception: rec["stdout"] = r.stdout[-5000:]
    json.dump(rec, open(path,"w"), indent=1, ensure_ascii=False)
    return path, r.returncode
with cf.ThreadPoolExecutor(4) as ex:
    for f in cf.as_completed([ex.submit(run,q,t,s) for q,t in Q for s in S]): print(*f.result(), flush=True)
