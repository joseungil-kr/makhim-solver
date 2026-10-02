import json, re
from pathlib import Path
import xml.etree.ElementTree as ET

BASE="https://makhim-solver.pages.dev"
manifest=json.loads(Path(".sitefactory/page_manifest.json").read_text(encoding="utf-8"))
truth=json.loads(Path(".sitefactory/business_truth.json").read_text(encoding="utf-8"))

root=ET.parse("sitemap.xml").getroot()
ns={"s":"http://www.sitemaps.org/schemas/sitemap/0.9"}
sitemap={x.text.strip() for x in root.findall("s:url/s:loc",ns) if x.text}

def path_for(url):
    return Path("index.html") if url=="/" else Path(url.strip("/"))/"index.html"

def html_text(h):
    h=re.sub(r"<script[\s\S]*?</script>"," ",h,flags=re.I)
    h=re.sub(r"<style[\s\S]*?</style>"," ",h,flags=re.I)
    h=re.sub(r"<[^>]+>"," ",h)
    return re.sub(r"\s+"," ",h).strip()

def tokens(q):
    return [x for x in re.split(r"[\s·,/]+",q) if len(x)>=1]

rows=[]
for p in manifest["pages"]:
    if not p.get("indexable"): continue
    url=p["url"]
    path=path_for(url)
    h=path.read_text(encoding="utf-8")
    title=(re.findall(r"<title>([\s\S]*?)</title>",h,re.I) or [""])[0]
    h1=(re.findall(r"<h1(?:\s[^>]*)?>([\s\S]*?)</h1>",h,re.I) or [""])[0]
    lead=(re.findall(r'<p class="(?:hero-lead|page-lead)">([\s\S]*?)</p>',h,re.I) or [""])[0]
    lead=re.sub(r"<[^>]+>","",lead).strip()
    desc=(re.findall(r'<meta name="description" content="([^"]*)"',h,re.I) or [""])[0]
    robots=(re.findall(r'<meta name="robots" content="([^"]*)"',h,re.I) or [""])[0]
    canon=(re.findall(r'<link rel="canonical" href="([^"]*)"',h,re.I) or [""])[0]
    imgs=[x for x in re.findall(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"',h,re.I) if "logo-makhim.png" not in x[0]]
    hrefs=re.findall(r'<a[^>]+href="([^"]+)"',h,re.I)
    actual_cta=[x for x in hrefs if re.match(r'^(tel:|sms:|mailto:|https?://(?!makhim-solver\.pages\.dev))',x,re.I)]
    text=html_text(h)
    qtokens=tokens(p["primary_keyword"])

    comp={}
    # 1) Query / intent alignment 20
    comp["query_alignment"]=0
    if all(t in title for t in qtokens): comp["query_alignment"]+=6
    if all(t in re.sub(r"<[^>]+>","",h1) for t in qtokens): comp["query_alignment"]+=6
    if any(t in lead for t in qtokens): comp["query_alignment"]+=5
    if 120 <= len(lead) <= 180: comp["query_alignment"]+=3

    # 2) Content / vertical specificity 20 — page-role aware
    comp["content"]=0
    sections=len(re.findall(r'class="content-section"',h))
    role=p.get("page_role","")
    if role in ("LOCAL_COMMERCIAL_HUB","COMMERCIAL_INFORMATION_HUB"):
        if 'class="service-grid"' in h and ('class="dong-grid"' in h or 'class="related-grid"' in h): comp["content"]+=5
    elif role=="REGION_HUB":
        if 'class="dong-grid"' in h and 'class="service-grid"' in h: comp["content"]+=5
    else:
        if sections>=5: comp["content"]+=5

    vertical_terms=["배관","누수","배수","막힘","역류","트랩","계량기","이물질","기름때","수위","방수"]
    if sum(1 for t in vertical_terms if t in text)>=4: comp["content"]+=5

    if role=="REGION_HUB":
        if ("18개" in text and "010-6725-2470" in text): comp["content"]+=5
    elif role=="REGION_SERVICE_LANDING":
        if ("비용" in text and ("전화" in text or "상담" in text)): comp["content"]+=5
    elif url.startswith("/service/"):
        if ("비용" in text and ("상담" in text or "작업 가능" in text)): comp["content"]+=5
    else:
        if ("확인" in text and ("다음" in text or "RELATED" in text)): comp["content"]+=5

    if ('tel:01067252470' in h and len(set(hrefs))>=4): comp["content"]+=5

    # 3) Technical 20
    comp["technical"]=0
    if "noindex" not in robots and "index" in robots: comp["technical"]+=4
    if canon==BASE+url: comp["technical"]+=4
    if BASE+url in sitemap: comp["technical"]+=4
    if 'application/ld+json' in h: comp["technical"]+=4
    # Live HTTP is verified by separate Live SEO QA; static score reserves 4 points.
    comp["technical"]+=4

    # 4) Internal architecture 15
    comp["architecture"]=0
    if url=="/" or 'class="breadcrumb"' in h: comp["architecture"]+=5
    related=[x for x in set(hrefs) if x.startswith("/") and x!=url]
    if len(related)>=2: comp["architecture"]+=5
    if p.get("parent") is None or p.get("parent") in related or p.get("parent")=="/": comp["architecture"]+=5

    # 5) Business Truth / provider voice 10
    comp["truth"]=0
    if truth.get("brand_name") in text and truth.get("business_number") in text: comp["truth"]+=5
    banned=["사용자는","사용자가","검색자는","검색자가","SEO","검색의도","Business Truth","QA"]
    if not any(x in text for x in banned): comp["truth"]+=5

    # 6) Visual intent 10
    comp["visual"]=0
    if imgs and all(src.startswith("/assets/") and alt.strip() for src,alt in imgs): comp["visual"]+=5
    expected="/assets/"+p["asset"]
    srcs=[x[0] for x in imgs]
    if url=="/":
        if expected in srcs and "/assets/drain-banner.webp" in srcs: comp["visual"]+=5
    elif len(imgs)==1 and expected in srcs:
        comp["visual"]+=5

    # 7) Actual conversion CTA 5 - HARD GATE
    comp["conversion"]=5 if actual_cta else 0

    raw=sum(comp.values())
    score=raw
    hard_gates=[]
    if not actual_cta:
        hard_gates.append("actual_cta_missing")
        score=min(score,94)
    if score>100: score=100
    rows.append({"url":url,"score":score,"raw":raw,"components":comp,"hard_gates":hard_gates})

print("SITE FACTORY SEO SCORE v1-v1.2")
for r in rows:
    print(f'{r["score"]:>3} {r["url"]}  hard_gate={",".join(r["hard_gates"]) or "-"}')
print("\nJSON")
print(json.dumps(rows,ensure_ascii=False,indent=2))
