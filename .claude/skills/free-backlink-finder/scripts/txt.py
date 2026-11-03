# usage: txt.py page.html "kw1|kw2"  -> prints text snippets around each keyword (free/paid/nofollow terms)
import sys,re,html as H
s=open(sys.argv[1],errors='ignore').read()
s=re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>',' ',s)
s=H.unescape(re.sub(r'<[^>]+>',' ',s)); s=re.sub(r'\s+',' ',s)
kw=sys.argv[2].split('|')
out=[]
for k in kw:
    for m in re.finditer(re.escape(k),s,re.I):
        out.append(s[max(0,m.start()-160):m.end()+200])
        if len([o for o in out if k.lower() in o.lower()])>=3: break
seen=set()
for o in out:
    if o[:60] in seen: continue
    seen.add(o[:60]); print('  ..',o)
