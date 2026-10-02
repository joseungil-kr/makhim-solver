import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://makhim-solver.pages.dev"
ROOT = Path(".")
BANNED_PROVIDER_VOICE = ["사용자는", "사용자가", "검색자는", "검색자가"]

def route_for(path: Path):
    p = path.as_posix()
    if p == "index.html":
        return "/"
    if p.endswith("/index.html"):
        return "/" + p[:-10]
    return "/" + p

def text_content(html):
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()

html_files = [p for p in ROOT.rglob("*.html") if ".git" not in p.parts and ".github" not in p.parts]
pages = {}
errors = []

for path in html_files:
    html = path.read_text(encoding="utf-8")
    route = route_for(path)
    title = re.findall(r"<title>([\s\S]*?)</title>", html, re.I)
    h1s = re.findall(r"<h1(?:\s[^>]*)?>([\s\S]*?)</h1>", html, re.I)
    desc = re.findall(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.I)
    robots = re.findall(r'<meta\s+name="robots"\s+content="([^"]*)"', html, re.I)
    canon = re.findall(r'<link\s+rel="canonical"\s+href="([^"]*)"', html, re.I)
    links = re.findall(r'href="([^"]+)"', html, re.I)
    images = re.findall(r'src="([^"]+)"', html, re.I)
    text = text_content(html)

    is_404 = path.as_posix() == "404.html"
    noindex = bool(robots and "noindex" in robots[0].lower())

    if not is_404:
        if len(title) != 1:
            errors.append(f"{route}: title count={len(title)}")
        if len(h1s) != 1:
            errors.append(f"{route}: h1 count={len(h1s)}")
        if len(desc) != 1:
            errors.append(f"{route}: description count={len(desc)}")
        if len(canon) != 1:
            errors.append(f"{route}: canonical count={len(canon)}")
        elif not canon[0].startswith(BASE):
            errors.append(f"{route}: canonical host mismatch")

    for word in BANNED_PROVIDER_VOICE:
        if word in text:
            errors.append(f"{route}: banned provider-voice token '{word}'")

    if 'name="sitefactory-gate"' in html and not noindex:
        errors.append(f"{route}: gated page must be noindex")

    for src in images:
        if src.startswith("/assets/"):
            local = ROOT / src.lstrip("/")
            if not local.exists():
                errors.append(f"{route}: missing image {src}")

    pages[route] = {
        "path": path,
        "title": title[0].strip() if title else "",
        "h1": re.sub(r"<[^>]+>", "", h1s[0]).strip() if h1s else "",
        "desc": desc[0].strip() if desc else "",
        "robots": robots[0] if robots else "",
        "noindex": noindex,
        "is_404": is_404,
        "links": [x for x in links if x.startswith("/")],
    }

# Duplicate title/H1 among indexable pages.
for field in ("title", "h1"):
    seen = {}
    for route, page in pages.items():
        if page["noindex"] or page["is_404"]:
            continue
        value = page[field]
        if value in seen:
            errors.append(f"duplicate {field}: {seen[value]} and {route}")
        else:
            seen[value] = route

# Internal target validation and inbound count.
inbound = {r: 0 for r,p in pages.items() if not p["is_404"]}
for route, page in pages.items():
    for link in set(page["links"]):
        clean = link.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        if clean.startswith("/assets/") or clean.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".xml", ".txt")):
            continue
        # Static directories are represented with trailing slash.
        if clean in inbound:
            inbound[clean] += 1
        elif clean.endswith("/") and clean[:-1] in inbound:
            inbound[clean[:-1]] += 1
        elif clean + "/" in inbound:
            inbound[clean + "/"] += 1
        elif clean not in ("/favicon.ico",):
            errors.append(f"{route}: broken internal link -> {clean}")

for route, count in inbound.items():
    page = pages.get(route)
    if route != "/" and page and not page["noindex"] and count < 1:
        errors.append(f"{route}: orphan indexable page")

# Sitemap must equal indexable routes.
sitemap_path = ROOT / "sitemap.xml"
if not sitemap_path.exists():
    errors.append("missing sitemap.xml")
else:
    root = ET.parse(sitemap_path).getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = {x.text.strip() for x in root.findall("s:url/s:loc", ns) if x.text}
    expected = {BASE + r for r,p in pages.items() if not p["noindex"] and not p["is_404"]}
    missing = expected - sitemap_urls
    extra = sitemap_urls - expected
    if missing:
        errors.append("sitemap missing: " + ", ".join(sorted(missing)))
    if extra:
        errors.append("sitemap extra/noindex: " + ", ".join(sorted(extra)))

# robots.txt must allow crawling and point to sitemap.
robots_path = ROOT / "robots.txt"
if not robots_path.exists():
    errors.append("missing robots.txt")
else:
    robots = robots_path.read_text(encoding="utf-8")
    if "Allow: /" not in robots:
        errors.append("robots.txt does not allow root")
    if f"Sitemap: {BASE}/sitemap.xml" not in robots:
        errors.append("robots.txt sitemap mismatch")

if errors:
    print("SEO QA FAILED")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print(f"SEO QA PASS: {len(pages)} HTML files, {sum(1 for p in pages.values() if not p['noindex'] and not p['is_404'])} indexable pages")
