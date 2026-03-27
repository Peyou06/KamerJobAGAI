"""
CamerJob Watch — Outil de diagnostic des sources
Exécute ce script sur ta machine pour voir exactement pourquoi un site échoue.
Usage: python diagnostic.py
"""
import urllib.request, re, sys

SITES = [
    ('MinaJobs',       'https://cameroun.minajobs.net/offres-emplois-stages-a/tout-le-cameroun'),
    ('Louma-Jobs',     'https://louma-jobs.com/cameroun/recrutements-emplois-stages/'),
    ('CameroonDesks',  'https://www.cameroondesks.com/search/label/jobs'),
    ('InfosConcours',  'https://infosconcourseducation.com/category/offre-demploiss/'),
    ('UNJobs',         'https://unjobs.org/duty_stations/yaounde'),
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}

JS_SIGNALS = [
    ('React/Vue app',    r'<div id=["\']app["\']>\s*</div>'),
    ('Next.js',          r'__NEXT_DATA__'),
    ('Angular',          r'ng-version='),
    ('Cloudflare check', r'cf-browser-verification|challenge-form|Ray ID'),
    ('AJAX chargement',  r'data-ajax|data-src|data-load'),
    ('Infinite scroll',  r'infinite.?scroll|load.?more'),
    ('API externe',      r'fetch\(["\']https?://api\.|axios\.get\('),
    ('Captcha',          r'recaptcha|hcaptcha|turnstile'),
]

print("=" * 65)
print("  CamerJob Watch — DIAGNOSTIC DES SOURCES")
print("=" * 65)

for name, url in SITES:
    print(f"\n{'─'*65}")
    print(f"🔍 {name}")
    print(f"   URL: {url}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode('utf-8', errors='replace')
            status = r.status
            final_url = r.url
            size = len(html)

        print(f"   ✅ HTTP {status} — {size:,} caractères")
        if final_url != url:
            print(f"   🔀 Redirigé vers: {final_url}")

        # Détection JS
        js_found = []
        for label, pattern in JS_SIGNALS:
            if re.search(pattern, html, re.I):
                js_found.append(label)

        if js_found:
            print(f"   ⚠️  PROBLÈME DÉTECTÉ — Contenu dynamique:")
            for j in js_found:
                print(f"      → {j}")
            print(f"   💡 SOLUTION: Ce site nécessite un navigateur headless (Playwright)")
        else:
            print(f"   ✅ HTML statique — urllib peut fonctionner")

        # Compter les offres potentielles
        h2 = len(re.findall(r'<h[23][^>]*>', html))
        links = len(re.findall(r'href="https?://[^"]+(?:offre|emploi|job|poste|stage|recrutement)[^"]*"', html, re.I))
        job_links = len(re.findall(r'href="[^"]*(?:/offre-|/job-|/emploi-|/recrutements-)[^"]*"', html, re.I))

        print(f"   📊 H2/H3 trouvés: {h2} | Liens offres: {links} | Liens job-slug: {job_links}")

        # Afficher un extrait du HTML utile
        snippet = re.sub(r'\s+', ' ', html[1000:2500]).strip()
        print(f"   📄 Extrait HTML (chars 1000-2500):")
        print(f"      {snippet[:400]}...")

    except Exception as e:
        print(f"   ❌ ERREUR: {type(e).__name__}: {e}")
        if 'Name or service not known' in str(e) or 'Errno -3' in str(e):
            print(f"   → DNS: Le domaine est inaccessible depuis ce serveur")
        elif '403' in str(e):
            print(f"   → 403 Forbidden: Le site bloque les scrapers")
        elif '429' in str(e):
            print(f"   → 429 Too Many Requests: Rate limiting actif")
        elif 'timeout' in str(e).lower():
            print(f"   → Timeout: Le site est trop lent à répondre")
        elif 'SSL' in str(e):
            print(f"   → SSL/HTTPS: Problème de certificat")

print(f"\n{'='*65}")
print("RÉSUMÉ DES SOLUTIONS:")
print("  Sites statiques (HTML)  → urllib suffit ✅")
print("  Sites JS/React/Vue      → Playwright requis")
print("  Sites Cloudflare        → Playwright + délai requis")
print("  Sites avec redirection  → Utiliser l'URL finale")
print(f"{'='*65}")
print("\nPour installer Playwright:")
print("  pip install playwright")
print("  playwright install chromium")
