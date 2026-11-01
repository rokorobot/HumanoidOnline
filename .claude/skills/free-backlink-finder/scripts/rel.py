import sys,re,urllib.parse
# usage: rel.py file baseurl  -> summarizes rel attributes of external <a> links
html=open(sys.argv[1],errors='ignore').read()
base=urllib.parse.urlparse(sys.argv[2]).netloc.replace('www.','')
tot=0;stats={}
ex=[]
for m in re.finditer(r'<a\s[^>]*href="(https?://[^"]+)"[^>]*>',html,re.I):
    tag=m.group(0);h=urllib.parse.urlparse(m.group(1)).netloc.replace('www.','')
    if base in h or h.endswith(base): continue
    r=re.search(r'rel="([^"]*)"',tag)
    k=r.group(1) if r else '(none)'
    stats[k]=stats.get(k,0)+1
    if len(ex)<6: ex.append((h,k))
print(sorted(stats.items(),key=lambda x:-x[1])[:6], ex)
