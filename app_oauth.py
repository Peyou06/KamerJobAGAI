"""CamerJob Watch — Flask app with sqlite3 (no ORM needed)"""
from flask import Flask, render_template, request, jsonify, send_file
import sqlite3, threading, io, json, re, os
from datetime import datetime, timedelta, timezone

def now_utc():
    return datetime.now(timezone.utc)

def now_iso():
    return now_utc().isoformat()

def now_fmt(fmt):
    return now_utc().strftime(fmt)

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), 'camerajob.db')

# ─── DB helpers ───────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, url TEXT NOT NULL,
        source_type TEXT DEFAULT 'emploi', is_active INTEGER DEFAULT 1,
        scrape_freq INTEGER DEFAULT 60, last_scraped TEXT,
        total_found INTEGER DEFAULT 0, created_at TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        offer_type TEXT DEFAULT 'emploi', title TEXT NOT NULL,
        organization TEXT, location TEXT DEFAULT 'Cameroun',
        description TEXT, sector TEXT, contract_type TEXT,
        salary TEXT, deadline TEXT, posted_date TEXT, url TEXT,
        source_name TEXT, source_id INTEGER, is_active INTEGER DEFAULT 1,
        is_favorite INTEGER DEFAULT 0, tags TEXT,
        scraped_at TEXT, reference TEXT, budget TEXT, authority TEXT
    );
    CREATE TABLE IF NOT EXISTS scrape_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER, source_name TEXT, status TEXT,
        found INTEGER DEFAULT 0, new_items INTEGER DEFAULT 0,
        message TEXT, started_at TEXT, ended_at TEXT
    );
    ''')
    conn.commit()
    # Seed if empty
    if c.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 0:
        seed(conn)
    conn.close()

def seed(conn):
    now = now_iso()
    sources = [
        ('Emploi Cameroun','https://www.emploi.cm/offres-emploi','emploi',60,'Principal site emploi camerounais'),
        ('CamJob','https://www.camjob.net/jobs','emploi',120,'Plateforme emploi locale'),
        ('LinkedIn Cameroun','https://www.linkedin.com/jobs/search/?location=Cameroun','emploi',180,'Offres LinkedIn Cameroun'),
        ('ReliefWeb Cameroun','https://reliefweb.int/jobs/cmr','emploi',240,'ONG et humanitaire'),
        ('Optionfinance','https://www.optionfinance.net/emploi/','emploi',120,'Finance et banque'),
        ('ARMP','https://www.armp.cm','appel_offre',60,'Marchés publics officiels'),
        ('Journal Marchés Publics','https://www.journaldesmarchespublics.com','appel_offre',120,'Multi-secteurs'),
        ('Banque Mondiale','https://projects.worldbank.org/en/projects-operations/procurement?countrycode_exact=CM','appel_offre',360,'BM Cameroun'),
    ]
    conn.executemany('INSERT INTO sources(name,url,source_type,scrape_freq,notes,created_at) VALUES(?,?,?,?,?,?)',
                     [(n,u,t,f,notes,now) for n,u,t,f,notes in sources])
    offers = [
        ('emploi','Ingénieur Développeur Full Stack React/Node.js','Orange Cameroun','Douala','Informatique & Tech','CDI','300 000 - 500 000 FCFA/mois','31/03/2025','Orange Cameroun recrute un développeur Full Stack maîtrisant React, Node.js et PostgreSQL.','https://emploi.cm','Emploi Cameroun','01/03/2025','','',''),
        ('emploi','Médecin Généraliste — Zone Rurale','Médecins Sans Frontières','Maroua','Santé','CDD 12 mois','USD 2 200/mois','20/03/2025','MSF recrute un médecin généraliste pour son projet dans la région de l\'Extrême-Nord.','https://reliefweb.int','ReliefWeb Cameroun','05/03/2025','','',''),
        ('emploi','Responsable Comptable Senior','Afriland First Bank','Douala','Finance & Banque','CDI','450 000 - 650 000 FCFA/mois','25/03/2025','Poste de responsable comptable pour superviser la comptabilité générale et analytique.','https://optionfinance.net','Optionfinance','03/03/2025','','',''),
        ('emploi','Ingénieur Génie Civil — Projets Routiers','MINTP','Yaoundé','Génie Civil & BTP','Contrat','À négocier','30/03/2025','Ministère des Travaux Publics recrute des ingénieurs pour le suivi de projets routiers.','https://emploi.cm','Emploi Cameroun','02/03/2025','','',''),
        ('emploi','Coordinateur de Projet Développement Rural','Plan International','Bafoussam','Humanitaire & ONG','CDD','USD 2 000/mois','15/04/2025','Coordination de projets de développement communautaire dans les régions de l\'Ouest.','https://reliefweb.int','ReliefWeb Cameroun','04/03/2025','','',''),
        ('emploi','Data Analyst — Business Intelligence','MTN Cameroun','Douala','Informatique & Tech','CDI','350 000 - 500 000 FCFA','10/04/2025','Analyse des données clients et performance réseau pour améliorer l\'expérience utilisateur.','https://emploi.cm','Emploi Cameroun','06/03/2025','','',''),
        ('appel_offre','Construction du Pont sur le Wouri — Tronçon Douala-Limbe','MINTP','Douala','Génie Civil & BTP','','','15/04/2025','Appel d\'offres international pour la construction d\'un pont stratégique reliant Douala à Limbe.','https://armp.cm','ARMP','01/03/2025','AO/MINTP/2025/001','5 000 000 000 FCFA','Ministère des Travaux Publics'),
        ('appel_offre','Fourniture de Matériels Informatiques pour 150 Lycées','MINESEC','Yaoundé','Informatique & Tech','','','28/03/2025','Fourniture et installation de matériels informatiques dans 150 lycées publics du Cameroun.','https://armp.cm','ARMP','05/03/2025','AO/MINESEC/2025/042','850 000 000 FCFA','Ministère des Enseignements Secondaires'),
        ('appel_offre','Réhabilitation du Réseau d\'Eau Potable de Garoua','CDE','Garoua','Génie Civil & BTP','','','05/04/2025','Travaux de réhabilitation et extension du réseau d\'eau potable dans la ville de Garoua.','https://journaldesmarchespublics.com','Journal Marchés Publics','04/03/2025','AO/CDE/2025/007','2 300 000 000 FCFA','Camerounaise des Eaux'),
        ('appel_offre','Mission de Conseil en Organisation RH — SONARA','SONARA','Limbe','Administration & RH','','','20/03/2025','Recrutement d\'un cabinet conseil pour l\'audit et la réorganisation de la gestion RH.','https://armp.cm','ARMP','03/03/2025','AO/SONARA/2025/011','120 000 000 FCFA','Société Nationale de Raffinage'),
    ]
    now_str = now_iso()
    conn.executemany('''INSERT INTO offers(offer_type,title,organization,location,sector,contract_type,salary,deadline,description,url,source_name,posted_date,reference,budget,authority,scraped_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                     [(o[0],o[1],o[2],o[3],o[4],o[5],o[6],o[7],o[8],o[9],o[10],o[11],o[12],o[13],o[14],now_str) for o in offers])
    conn.commit()
    print('✅ DB seeded with demo data')

def row_to_dict(row):
    return dict(row) if row else None

# ─── Scraper ──────────────────────────────────────────────────────────────────
class ScraperEngine:
    def __init__(self): self.running = {}

    def _guess_sector(self, title):
        t = title.lower()
        for sector, kws in [
            ('Informatique & Tech',['développeur','informatique','data','tech','digital','web','logiciel','software']),
            ('Finance & Banque',['comptable','finance','banque','audit','trésorerie']),
            ('Santé',['médecin','infirmier','santé','pharmacie','hôpital','clinique']),
            ('Éducation',['enseignant','professeur','formateur','université','école']),
            ('Génie Civil & BTP',['génie civil','btp','construction','architecte','topographe']),
            ('Télécoms',['télécom','réseau','orange','mtn','camtel']),
            ('Agriculture',['agriculture','élevage','agro','plantation','cacao']),
            ('Transport & Logistique',['transport','logistique','chauffeur','supply chain']),
            ('Humanitaire & ONG',['ong','humanitaire','ngo','unicef','pnud','fao']),
            ('Administration & RH',['administrateur','secrétaire','rh','ressources humaines','manager']),
        ]:
            if any(k in t for k in kws): return sector
        return 'Autre'

    def scrape_source(self, source_id):
        conn = get_db()
        src = row_to_dict(conn.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone())
        if not src: conn.close(); return
        now = now_iso()
        conn.execute('INSERT INTO scrape_logs(source_id,source_name,status,started_at) VALUES(?,?,?,?)',
                     (source_id,src['name'],'running',now))
        conn.commit()
        log_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        try:
            self.running[source_id] = True
            results = self._fetch(src)
            new_count = 0
            for item in results:
                existing = conn.execute('SELECT id FROM offers WHERE url=? AND source_name=?',(item.get('url',''),src['name'])).fetchone()
                if not existing and item.get('title'):
                    conn.execute('''INSERT INTO offers(offer_type,title,organization,location,description,sector,url,source_name,source_id,posted_date,reference,budget,authority,scraped_at)
                                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                 (item.get('offer_type',src['source_type']),item['title'],item.get('organization',''),
                                  item.get('location','Cameroun'),item.get('description',''),item.get('sector',''),
                                  item.get('url',''),src['name'],source_id,now_fmt('%d/%m/%Y'),
                                  item.get('reference',''),item.get('budget',''),item.get('authority',''),now_iso()))
                    new_count += 1
            conn.execute('UPDATE sources SET last_scraped=?,total_found=total_found+? WHERE id=?',(now_iso(),new_count,source_id))
            conn.execute('UPDATE scrape_logs SET status=?,found=?,new_items=?,ended_at=? WHERE id=?',
                        ('success',len(results),new_count,now_iso(),log_id))
            conn.commit()
        except Exception as e:
            conn.execute('UPDATE scrape_logs SET status=?,message=?,ended_at=? WHERE id=?',
                        ('error',str(e)[:500],now_iso(),log_id))
            conn.commit()
        finally:
            self.running[source_id] = False
            conn.close()

    # Sites JS-heavy nécessitant un navigateur headless
    JS_SITES = ['minajobs.net', 'louma-jobs.com', 'armp.cm', 'emploi.cm', 'camjob.net', 'unjobs.org']

    def _get_html(self, url):
        import urllib.request
        HEADERS = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        }
        needs_js = any(js in url for js in self.JS_SITES)
        if needs_js:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.set_extra_http_headers({'Accept-Language': 'fr-FR,fr;q=0.9'})
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    try:
                        page.wait_for_selector('h2,h3,article,.job,.offre', timeout=8000)
                    except:
                        pass
                    html = page.content()
                    browser.close()
                    return html, 'playwright'
            except ImportError:
                pass
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode('utf-8', errors='replace'), 'urllib'
        except Exception as e:
            raise Exception(f"Acces impossible a {url}: {e}")

    def _fetch(self, src):
        url = src['url']
        if 'minajobs.net' in url:
            return self._spider_minajobs(src)
        elif 'louma-jobs.com' in url:
            return self._spider_louma(src)
        elif 'cameroondesks.com' in url:
            return self._spider_cameroondesks(src)
        elif 'infosconcourseducation.com' in url or 'infosconcours' in url:
            return self._spider_infosconcours(src)
        elif 'unjobs.org' in url:
            return self._spider_unjobs(src)
        return self._spider_generic(src)

    # ── Spider dédié MinaJobs ─────────────────────────────────────────────────
    def _spider_minajobs(self, src):
        """
        Spider spécifique pour cameroun.minajobs.net
        Structure HTML :
          Chaque offre est un bloc répété contenant :
            - Un lien <a href="/offre-xxx"> avec le titre en texte
            - L'organisation juste après le lien
            - La ville/region dans l'URL ou dans le texte
          Pattern texte : "Titre · Organisation | ville-region-cameroun | Publiée depuis X"
        On scrape plusieurs pages régionales pour maximiser la collecte.
        """
        import urllib.request
        from urllib.parse import urljoin

        PAGES = [
            'https://cameroun.minajobs.net/offres-emplois-stages-a/tout-le-cameroun',
            'https://cameroun.minajobs.net/offres-emplois-stages-a/douala-region-littoral-cameroun',
            'https://cameroun.minajobs.net/offres-emplois-stages-a/yaounde-region-centre-cameroun',
            'https://cameroun.minajobs.net/offres-emplois-stages-a/bafoussam-region-ouest-cameroun',
            'https://cameroun.minajobs.net/offres-emplois-stages-a/garoua-region-nord-cameroun',
        ]

        HEADERS = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Referer': 'https://cameroun.minajobs.net/',
        }

        results = []
        seen_urls = set()

        for page_url in PAGES:
            try:
                req = urllib.request.Request(page_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
            except Exception:
                continue  # Passer à la page suivante si une échoue

            # ── Extraction des blocs d'offres ──
            # MinaJobs répète chaque offre 2 fois dans le HTML (mobile + desktop)
            # On extrait les liens vers les offres individuelles
            # Pattern URL: /offre-emploi-XXXX ou /offre-stage-XXXX

            # 1. Extraire tous les liens d'offres individuelles
            offer_links = re.findall(
                r'href="((?:https://cameroun\.minajobs\.net)?/offre-(?:emploi|stage|appel)[^"]*)"',
                html, re.I
            )
            # Dédupliquer les liens
            unique_links = []
            for lnk in offer_links:
                full = lnk if lnk.startswith('http') else f'https://cameroun.minajobs.net{lnk}'
                if full not in seen_urls:
                    seen_urls.add(full)
                    unique_links.append(full)

            # 2. Extraire titre + organisation depuis le HTML de la liste
            # Structure répétée : <a href="/offre-...">TITRE</a> ... ORGANISATION | ville | Publiée depuis X
            # On récupère les blocs complets autour de chaque lien d'offre
            block_pattern = re.compile(
                r'href="(?:https://cameroun\.minajobs\.net)?(/offre-[^"]+)"[^>]*>\s*(.*?)\s*</a>'
                r'(?:.*?)\|\s*([^|<\n]+?)\s*\|\s*(?:Publiée depuis\s*(\d+))?',
                re.S | re.I
            )

            seen_titles = set()
            for m in block_pattern.finditer(html):
                slug    = m.group(1)
                raw_title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                raw_org   = re.sub(r'<[^>]+>', '', m.group(3)).strip() if m.group(3) else ''
                days_ago  = m.group(4) or ''

                # Nettoyage
                title = re.sub(r'\s+', ' ', raw_title).strip()
                org   = re.sub(r'\s+', ' ', raw_org).strip()

                # Filtres qualité
                if len(title) < 8 or len(title) > 400: continue
                if title in seen_titles: continue
                skip = ['minajobs','publiez vos offres','gratuit','whatsapp','newsletter',
                        'connexion','inscription','accueil','menu','chaine']
                if any(s in title.lower() for s in skip): continue
                if any(s in org.lower() for s in ['minajobs','tout-le-cameroun']): continue

                seen_titles.add(title)

                # URL complète
                offer_url = f'https://cameroun.minajobs.net{slug}'

                # Localisation depuis le slug URL
                location = self._minajobs_location_from_slug(slug)

                # Type d'offre
                offer_type = src['source_type']
                if 'appel' in slug.lower() or 'appel' in title.lower():
                    offer_type = 'appel_offre'
                elif 'stage' in slug.lower():
                    offer_type = 'emploi'

                # Date de publication approximative
                posted = ''
                if days_ago:
                    from datetime import timedelta
                    d = now_utc() - timedelta(days=int(days_ago))
                    posted = d.strftime('%d/%m/%Y')

                results.append({
                    'title':        title,
                    'organization': org,
                    'location':     location,
                    'url':          offer_url,
                    'offer_type':   offer_type,
                    'sector':       self._guess_sector(title + ' ' + org),
                    'posted_date':  posted,
                    'source_name':  src['name'],
                })

        # Si le pattern avec | n'a rien donné, fallback sur extraction simple des titres
        if not results:
            results = self._minajobs_fallback(src, PAGES[0], HEADERS)

        return results

    def _minajobs_location_from_slug(self, slug):
        """Extrait la ville depuis le slug de l'URL MinaJobs."""
        loc_map = {
            'douala': 'Douala', 'yaounde': 'Yaoundé', 'yaounde': 'Yaoundé',
            'bafoussam': 'Bafoussam', 'garoua': 'Garoua', 'maroua': 'Maroua',
            'bertoua': 'Bertoua', 'ngaoundere': 'Ngaoundéré', 'ebolowa': 'Ebolowa',
            'bamenda': 'Bamenda', 'buea': 'Buea', 'limbe': 'Limbé', 'kribi': 'Kribi',
            'edea': 'Edéa', 'nkongsamba': 'Nkongsamba',
        }
        slug_lower = slug.lower()
        for key, city in loc_map.items():
            if key in slug_lower:
                return city
        return 'Cameroun'

    def _minajobs_fallback(self, src, url, headers):
        """Fallback : extraction simple si le pattern principal échoue."""
        import urllib.request
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode('utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"MinaJobs inaccessible: {e}")

        results = []
        seen = set()

        # Extraire uniquement les <a href="/offre-...">TITRE</a>
        for m in re.finditer(r'href="(/offre-[^"]+)"[^>]*>\s*([^<]{10,350}?)\s*</a>', html, re.I):
            slug, title = m.group(1), m.group(2).strip()
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) < 8 or title in seen: continue
            if any(s in title.lower() for s in ['minajobs','publiez','gratuit','connexion']): continue
            seen.add(title)
            results.append({
                'title':      title,
                'organization': '',
                'location':   self._minajobs_location_from_slug(slug),
                'url':        f'https://cameroun.minajobs.net{slug}',
                'offer_type': src['source_type'],
                'sector':     self._guess_sector(title),
            })

        if not results:
            results.append({
                'title': f'Voir toutes les offres — {src["name"]}',
                'organization': 'MinaJobs', 'location': 'Cameroun',
                'url': url, 'offer_type': src['source_type'],
                'description': 'Accédez à cameroun.minajobs.net pour consulter les offres.'
            })
        return results

    # ── Spider Louma-Jobs ─────────────────────────────────────────────────────
    def _spider_louma(self, src):
        """
        Louma-Jobs structure :
          <h3><a href="/cameroun/recrutements-emplois-stages/YYYY/slug/">TITRE</a></h3>
          + ville dans texte avant h3, catégorie, type contrat, date cloture
        On scrape la page principale + page 2.
        """
        import urllib.request
        from urllib.parse import urljoin
        BASE = 'https://louma-jobs.com/cameroun'
        PAGES = [
            f'{BASE}/recrutements-emplois-stages/',
            f'{BASE}/recrutements-emplois-stages/page/2/',
            f'{BASE}/recrutements-emplois-stages/page/3/',
        ]
        HDR = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
               'Accept-Language':'fr-FR,fr;q=0.9'}
        results, seen = [], set()
        for page_url in PAGES:
            try:
                req = urllib.request.Request(page_url, headers=HDR)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
            except: continue

            # Extraire les blocs d'offres — chaque offre a un <h3> avec lien
            # Pattern: ville\n\n### [TITRE](url)\ncatégories\nType\ndate cloture
            blocks = re.findall(
                r'(Douala|Yaoundé|Yaound&#233;|Cameroun|Bafoussam|Garoua|Maroua|Bamenda|Buea|Limbe|Kribi|Ngaoundéré)?\s*'
                r'<h3[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>'
                r'(?:.*?cat[eé]gories?\s*:\s*([^\n<]+))?'
                r'(?:.*?Type\s*:\s*([^\n<]+))?'
                r'(?:.*?date\s+cloture\s*:\s*([^\n<]+))?',
                html, re.S | re.I
            )
            for m in blocks:
                ville_raw, url_rel, title_raw, cats, contract, deadline = m
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'\s+', ' ', title).strip()
                if len(title) < 5 or title in seen: continue
                skip = ['whatsapp','telegram','newsletter','rejoignez','restez informé']
                if any(s in title.lower() for s in skip): continue
                seen.add(title)
                location = ville_raw.replace('&#233;', 'é').strip() if ville_raw else 'Cameroun'
                offer_url = url_rel if url_rel.startswith('http') else urljoin(BASE, url_rel)
                contract_clean = re.sub(r'\s+', ' ', contract or '').strip()
                deadline_clean = re.sub(r'\s+', ' ', deadline or '').strip()
                sector = self._guess_sector(title + ' ' + (cats or ''))
                results.append({
                    'title': title, 'organization': '',
                    'location': location, 'url': offer_url,
                    'offer_type': src['source_type'], 'sector': sector,
                    'contract_type': contract_clean[:80], 'deadline': deadline_clean[:40],
                })
        # Fallback si les blocs complexes n'ont rien donné
        if not results:
            results = self._louma_fallback(src, HDR)
        return results

    def _louma_fallback(self, src, HDR):
        import urllib.request
        from urllib.parse import urljoin
        url = 'https://louma-jobs.com/cameroun/recrutements-emplois-stages/'
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode('utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Louma inaccessible: {e}")
        results, seen = [], set()
        for m in re.finditer(r'<h3[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S|re.I):
            offer_url, title_raw = m.group(1), m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) < 5 or title in seen: continue
            if any(s in title.lower() for s in ['whatsapp','telegram','rejoignez']): continue
            seen.add(title)
            full_url = offer_url if offer_url.startswith('http') else urljoin('https://louma-jobs.com', offer_url)
            results.append({'title': title, 'organization': '', 'location': 'Cameroun',
                           'url': full_url, 'offer_type': src['source_type'],
                           'sector': self._guess_sector(title)})
        return results

    # ── Spider CameroonDesks (Blogger) ────────────────────────────────────────
    def _spider_cameroondesks(self, src):
        """
        CameroonDesks = blog Blogger.
        Titres dans <h2><a href="https://www.cameroondesks.com/YYYY/MM/slug.html">TITRE</a></h2>
        On scrape les labels jobs, concours, stage, bourses.
        """
        import urllib.request
        from urllib.parse import urljoin
        PAGES = [
            'https://www.cameroondesks.com/search/label/jobs',
            'https://www.cameroondesks.com/search/label/offre%20d%27emploi',
            'https://www.cameroondesks.com/search/label/concours',
            'https://www.cameroondesks.com/search/label/stage',
        ]
        HDR = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
               'Accept-Language':'fr-FR,fr;q=0.9', 'Referer':'https://www.cameroondesks.com/'}
        results, seen = [], set()
        for page_url in PAGES:
            try:
                req = urllib.request.Request(page_url, headers=HDR)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
            except: continue
            # Blogger: titres dans <h2 class="post-title ..."> ou <h3 class="post-title">
            # avec liens vers *.cameroondesks.com/YYYY/MM/slug.html
            for m in re.finditer(
                r'<h[23][^>]*class="[^"]*post-title[^"]*"[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
                html, re.S | re.I
            ):
                offer_url, title_raw = m.group(1), m.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'\s+', ' ', title).strip()
                if len(title) < 8 or title in seen: continue
                skip = ['read more','plus de détails','rejoindre','whatsapp']
                if any(s in title.lower() for s in skip): continue
                seen.add(title)
                # Déduire type d'offre depuis l'URL de la page source
                offer_type = src['source_type']
                if 'concours' in page_url: offer_type = 'emploi'
                elif 'stage' in page_url: offer_type = 'emploi'
                results.append({
                    'title': title, 'organization': 'Cameroon Desks',
                    'location': 'Cameroun', 'url': offer_url,
                    'offer_type': offer_type, 'sector': self._guess_sector(title),
                })
        # Fallback : h2 générique sur la homepage
        if not results:
            try:
                req = urllib.request.Request('https://www.cameroondesks.com/', headers=HDR)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
                for m in re.finditer(r'<h2[^>]*>\s*<a\s+href="(https://www\.cameroondesks\.com/[^"]+)"[^>]*>(.*?)</a>', html, re.S|re.I):
                    url_m, title_raw = m.group(1), m.group(2)
                    title = re.sub(r'<[^>]+>', '', title_raw).strip()
                    title = re.sub(r'\s+', ' ', title).strip()
                    if len(title) < 8 or title in seen: continue
                    seen.add(title)
                    results.append({'title':title,'organization':'Cameroon Desks','location':'Cameroun',
                                   'url':url_m,'offer_type':src['source_type'],'sector':self._guess_sector(title)})
            except: pass
        return results

    # ── Spider InfosConcours ──────────────────────────────────────────────────
    def _spider_infosconcours(self, src):
        """
        InfosConcours = WordPress.
        Articles dans <h2 class="entry-title"><a href="URL">TITRE</a></h2>
        On scrape emploi, recrutement, concours, stage, bourses.
        """
        import urllib.request
        PAGES = [
            'https://infosconcourseducation.com/category/offre-demploiss/',
            'https://infosconcourseducation.com/category/offre-demplois/',
            'https://infosconcourseducation.com/category/concours/',
            'https://infosconcourseducation.com/category/stage/',
            'https://infosconcourseducation.com/category/bourses/',
            'https://infosconcourseducation.com/category/offre-demploiss/page/2/',
            'https://infosconcourseducation.com/category/offre-demplois/page/2/',
        ]
        HDR = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
               'Accept-Language':'fr-FR,fr;q=0.9'}
        results, seen = [], set()
        for page_url in PAGES:
            try:
                req = urllib.request.Request(page_url, headers=HDR)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
            except: continue
            # WordPress classique : <h2 class="entry-title"> ou <h3 class="entry-title">
            for m in re.finditer(
                r'<h[23][^>]*class="[^"]*(?:entry-title|post-title)[^"]*"[^>]*>\s*(?:<a\s+href="([^"]+)"[^>]*>)?(.*?)(?:</a>)?\s*</h[23]>',
                html, re.S | re.I
            ):
                offer_url, title_raw = m.group(1) or '', m.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'\s+', ' ', title).strip()
                if len(title) < 8 or title in seen: continue
                skip = ['connexion','inscription','accueil','menu','rejoindre','whatsapp','groupe vip']
                if any(s in title.lower() for s in skip): continue
                seen.add(title)
                # Offre type: concours/bourse = emploi, stage = emploi
                offer_type = src['source_type']
                results.append({
                    'title': title, 'organization': 'InfosConcours Education',
                    'location': 'Cameroun', 'url': offer_url or page_url,
                    'offer_type': offer_type, 'sector': self._guess_sector(title),
                })
        return results

    # ── Spider UNJobs ─────────────────────────────────────────────────────────
    def _spider_unjobs(self, src):
        """
        UNJobs.org — offres ONU/ONG internationales au Cameroun.
        Structure : <div class="j"> contenant titre, organisation, deadline.
        Pages: /duty_stations/yao (Yaoundé), /duty_stations/cameroon
        """
        import urllib.request
        PAGES = [
            'https://unjobs.org/duty_stations/yao',
            'https://unjobs.org/duty_stations/cameroon',
            'https://unjobs.org/duty_stations/yao/2',
        ]
        HDR = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
               'Accept':'text/html,application/xhtml+xml,*/*',
               'Accept-Language':'en-US,en;q=0.9,fr;q=0.8',
               'Referer':'https://unjobs.org/'}
        results, seen = [], set()
        for page_url in PAGES:
            try:
                req = urllib.request.Request(page_url, headers=HDR)
                with urllib.request.urlopen(req, timeout=20) as r:
                    html = r.read().decode('utf-8', errors='replace')
            except: continue
            # UNJobs: <div class="j"><a href="/vacancies/XXXX">TITRE</a>...ORG...DEADLINE
            for m in re.finditer(
                r'<div[^>]*class="[^"]*\bj\b[^"]*"[^>]*>.*?'
                r'<a\s+href="(/vacancies/[^"]+)"[^>]*>(.*?)</a>'
                r'(.*?)</div>',
                html, re.S | re.I
            ):
                slug, title_raw, rest = m.group(1), m.group(2), m.group(3)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'\s+', ' ', title).strip()
                if len(title) < 5 or title in seen: continue
                seen.add(title)
                # Extraire organisation depuis le reste du bloc
                org_m = re.search(r'<(?:span|div)[^>]*class="[^"]*(?:org|organization|source)[^"]*"[^>]*>(.*?)</', rest, re.S|re.I)
                org = re.sub(r'<[^>]+>', '', org_m.group(1)).strip() if org_m else 'ONU/ONG'
                # Deadline
                dl_m = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})', rest)
                deadline = dl_m.group(1) if dl_m else ''
                results.append({
                    'title': title, 'organization': org,
                    'location': 'Yaoundé', 'url': f'https://unjobs.org{slug}',
                    'offer_type': src['source_type'], 'sector': 'Humanitaire & ONG',
                    'deadline': deadline,
                })
            # Fallback: liens simples /vacancies/
            if not results:
                for m in re.finditer(r'<a\s+href="(/vacancies/[^"]+)"[^>]*>([^<]{10,300})</a>', html, re.I):
                    slug, title = m.group(1), m.group(2).strip()
                    if title in seen or len(title) < 8: continue
                    seen.add(title)
                    results.append({'title': title, 'organization': 'ONU/ONG',
                                   'location': 'Yaoundé', 'url': f'https://unjobs.org{slug}',
                                   'offer_type': src['source_type'], 'sector': 'Humanitaire & ONG'})
        return results

    # ── Spider générique amélioré (fallback universel) ────────────────────────
    def _spider_generic(self, src):
        import urllib.request
        from urllib.parse import urljoin
        url = src['url']
        HDR = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
               'Accept':'text/html,application/xhtml+xml,*/*;q=0.9',
               'Accept-Language':'fr-FR,fr;q=0.9,en;q=0.8'}
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode('utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"Accès impossible: {e}")

        results, seen = [], set()
        SKIP = {'menu','accueil','contact','connexion','inscription','home','login',
                'register','newsletter','whatsapp','telegram','facebook','twitter',
                'youtube','instagram','apropos','à propos','politique'}

        # Priorité 1 — liens WordPress/Blogger courants
        for m in re.finditer(
            r'<(?:h[123]|a)[^>]*class="[^"]*(?:entry-title|post-title|job-title|offer-title)[^"]*"[^>]*>'
            r'(?:\s*<a\s+href="([^"]+)"[^>]*>)?(.*?)(?:</a>)?\s*</(?:h[123]|a)>',
            html, re.S | re.I
        ):
            offer_url, title_raw = m.group(1) or url, m.group(2)
            title = re.sub(r'<[^>]+>', '', title_raw).strip()
            title = re.sub(r'\s+', ' ', title)
            if 8 <= len(title) <= 350 and title not in seen and not any(s in title.lower() for s in SKIP):
                seen.add(title)
                results.append({'title': title, 'organization': src['name'], 'location': 'Cameroun',
                                'url': offer_url if offer_url.startswith('http') else urljoin(url, offer_url),
                                'offer_type': src['source_type'], 'sector': self._guess_sector(title)})

        # Priorité 2 — H2/H3 génériques avec liens
        if len(results) < 3:
            for m in re.finditer(r'<h[23][^>]*>\s*<a\s+href="([^"#][^"]*)"[^>]*>(.*?)</a>\s*</h[23]>', html, re.S|re.I):
                offer_url, title_raw = m.group(1), m.group(2)
                title = re.sub(r'<[^>]+>', '', title_raw).strip()
                title = re.sub(r'\s+', ' ', title)
                if 8 <= len(title) <= 350 and title not in seen and not any(s in title.lower() for s in SKIP):
                    seen.add(title)
                    full_url = offer_url if offer_url.startswith('http') else urljoin(url, offer_url)
                    results.append({'title': title, 'organization': src['name'], 'location': 'Cameroun',
                                   'url': full_url, 'offer_type': src['source_type'], 'sector': self._guess_sector(title)})

        if not results:
            results.append({'title': f'Voir offres — {src["name"]}', 'organization': src['name'],
                           'location': 'Cameroun', 'url': url, 'offer_type': src['source_type'],
                           'description': f'Accédez à {url} pour consulter les offres.'})
        return results

    def scrape_all(self):
        conn = get_db()
        sources = conn.execute('SELECT id FROM sources WHERE is_active=1').fetchall()
        conn.close()
        for s in sources:
            if not self.running.get(s['id']):
                threading.Thread(target=self.scrape_source,args=(s['id'],),daemon=True).start()

scraper = ScraperEngine()

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    conn = get_db()
    stats = {
        'total': conn.execute('SELECT COUNT(*) FROM offers WHERE is_active=1').fetchone()[0],
        'emploi': conn.execute("SELECT COUNT(*) FROM offers WHERE is_active=1 AND offer_type='emploi'").fetchone()[0],
        'ao': conn.execute("SELECT COUNT(*) FROM offers WHERE is_active=1 AND offer_type='appel_offre'").fetchone()[0],
        'sources': conn.execute('SELECT COUNT(*) FROM sources WHERE is_active=1').fetchone()[0],
        'new_today': conn.execute("SELECT COUNT(*) FROM offers WHERE is_active=1 AND scraped_at>=?",(( now_utc()-timedelta(days=1)).isoformat(),)).fetchone()[0],
        'favorites': conn.execute('SELECT COUNT(*) FROM offers WHERE is_active=1 AND is_favorite=1').fetchone()[0],
    }
    recent = [dict(r) for r in conn.execute('SELECT * FROM offers WHERE is_active=1 ORDER BY scraped_at DESC LIMIT 8').fetchall()]
    conn.close()
    return render_template('index.html', stats=stats, recent=recent)

@app.route('/offers')
def offers(): return render_template('offers.html')

@app.route('/sources')
def sources_page(): return render_template('sources.html')

@app.route('/reports')
def reports(): return render_template('reports.html')

# ─── API Offers ───────────────────────────────────────────────────────────────
@app.route('/api/offers')
def api_offers():
    page = request.args.get('page',1,type=int)
    per_page = request.args.get('per_page',20,type=int)
    offset = (page-1)*per_page
    where,params = ['is_active=1'],[]
    if t := request.args.get('type'): where.append('offer_type=?'); params.append(t)
    if s := request.args.get('sector'): where.append('sector LIKE ?'); params.append(f'%{s}%')
    if l := request.args.get('location'): where.append('location LIKE ?'); params.append(f'%{l}%')
    if kw := request.args.get('q'): where.append('(title LIKE ? OR organization LIKE ? OR description LIKE ?)'); params+=[f'%{kw}%',f'%{kw}%',f'%{kw}%']
    if request.args.get('favorites')=='true': where.append('is_favorite=1')
    if sid := request.args.get('source_id'): where.append('source_id=?'); params.append(int(sid))
    w = ' AND '.join(where)
    conn = get_db()
    total = conn.execute(f'SELECT COUNT(*) FROM offers WHERE {w}',params).fetchone()[0]
    rows = conn.execute(f'SELECT * FROM offers WHERE {w} ORDER BY scraped_at DESC LIMIT ? OFFSET ?',params+[per_page,offset]).fetchall()
    conn.close()
    import math
    return jsonify({'offers':[dict(r) for r in rows],'total':total,'page':page,'pages':math.ceil(total/per_page)})

@app.route('/api/offers/<int:oid>')
def api_offer(oid):
    conn = get_db()
    r = conn.execute('SELECT * FROM offers WHERE id=?',(oid,)).fetchone()
    conn.close()
    return jsonify(dict(r)) if r else ('not found',404)

@app.route('/api/offers/<int:oid>/favorite',methods=['POST'])
def toggle_fav(oid):
    conn = get_db()
    r = conn.execute('SELECT is_favorite FROM offers WHERE id=?',(oid,)).fetchone()
    new_val = 0 if r and r['is_favorite'] else 1
    conn.execute('UPDATE offers SET is_favorite=? WHERE id=?',(new_val,oid)); conn.commit(); conn.close()
    return jsonify({'is_favorite':bool(new_val)})

@app.route('/api/offers/<int:oid>',methods=['DELETE'])
def del_offer(oid):
    conn = get_db(); conn.execute('UPDATE offers SET is_active=0 WHERE id=?',(oid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/offers/add',methods=['POST'])
def add_offer():
    d = request.get_json()
    if not d.get('title'): return jsonify({'error':'Title required'}),400
    conn = get_db()
    conn.execute('''INSERT INTO offers(offer_type,title,organization,location,description,sector,contract_type,salary,deadline,url,source_name,reference,budget,authority,scraped_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                 (d.get('offer_type','emploi'),d['title'],d.get('organization',''),d.get('location','Cameroun'),
                  d.get('description',''),d.get('sector',''),d.get('contract_type',''),d.get('salary',''),
                  d.get('deadline',''),d.get('url',''),'Manuel',d.get('reference',''),d.get('budget',''),
                  d.get('authority',''),now_iso()))
    oid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()
    return jsonify({'success':True,'id':oid})

# ─── API Sources ──────────────────────────────────────────────────────────────
@app.route('/api/sources')
def api_sources():
    conn = get_db(); rows = conn.execute('SELECT * FROM sources ORDER BY created_at DESC').fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/sources/add',methods=['POST'])
def add_source():
    d = request.get_json()
    conn = get_db()
    conn.execute('INSERT INTO sources(name,url,source_type,scrape_freq,is_active,notes,created_at) VALUES(?,?,?,?,?,?,?)',
                 (d['name'],d['url'],d.get('source_type','emploi'),d.get('scrape_freq',60),
                  1 if d.get('is_active',True) else 0,d.get('notes',''),now_iso()))
    sid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    s = dict(conn.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone())
    conn.commit(); conn.close()
    return jsonify({'success':True,'id':sid,'source':s})

@app.route('/api/sources/<int:sid>',methods=['PUT'])
def update_source(sid):
    d = request.get_json(); conn = get_db()
    conn.execute('UPDATE sources SET name=?,url=?,source_type=?,scrape_freq=?,is_active=?,notes=? WHERE id=?',
                 (d['name'],d['url'],d['source_type'],d['scrape_freq'],1 if d['is_active'] else 0,d.get('notes',''),sid))
    conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/sources/<int:sid>',methods=['DELETE'])
def del_source(sid):
    conn = get_db(); conn.execute('DELETE FROM sources WHERE id=?',(sid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/sources/<int:sid>/scrape',methods=['POST'])
def trigger_scrape(sid):
    conn = get_db(); s = conn.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone(); conn.close()
    if not s: return jsonify({'success':False,'message':'Source introuvable'})
    if scraper.running.get(sid): return jsonify({'success':False,'message':'Déjà en cours'})
    threading.Thread(target=scraper.scrape_source,args=(sid,),daemon=True).start()
    return jsonify({'success':True,'message':f'Scraping de "{s["name"]}" lancé'})

@app.route('/api/sources/scrape-all',methods=['POST'])
def scrape_all():
    threading.Thread(target=scraper.scrape_all,daemon=True).start()
    return jsonify({'success':True,'message':'Scraping de toutes les sources lancé'})

@app.route('/api/sources/<int:sid>/status')
def source_status(sid):
    conn = get_db()
    log = conn.execute('SELECT * FROM scrape_logs WHERE source_id=? ORDER BY started_at DESC LIMIT 1',(sid,)).fetchone()
    conn.close()
    return jsonify({'running':scraper.running.get(sid,False),'last_log':dict(log) if log else None})

# ─── Stats ────────────────────────────────────────────────────────────────────
@app.route('/api/stats')
def api_stats():
    conn = get_db()
    sectors = conn.execute("SELECT sector,COUNT(*) as c FROM offers WHERE is_active=1 AND sector!='' GROUP BY sector ORDER BY c DESC LIMIT 10").fetchall()
    locations = conn.execute("SELECT location,COUNT(*) as c FROM offers WHERE is_active=1 GROUP BY location ORDER BY c DESC LIMIT 8").fetchall()
    src_stats = conn.execute("SELECT source_name,COUNT(*) as c FROM offers WHERE is_active=1 GROUP BY source_name ORDER BY c DESC LIMIT 10").fetchall()
    daily = []
    for i in range(7):
        day = now_utc()-timedelta(days=6-i)
        d0 = day.replace(hour=0,minute=0,second=0).isoformat()
        d1 = day.replace(hour=23,minute=59,second=59).isoformat()
        c = conn.execute("SELECT COUNT(*) FROM offers WHERE is_active=1 AND scraped_at>=? AND scraped_at<=?",(d0,d1)).fetchone()[0]
        daily.append({'date':day.strftime('%d/%m'),'count':c})
    logs = conn.execute('SELECT * FROM scrape_logs ORDER BY started_at DESC LIMIT 20').fetchall()
    total = conn.execute('SELECT COUNT(*) FROM offers WHERE is_active=1').fetchone()[0]
    emploi = conn.execute("SELECT COUNT(*) FROM offers WHERE is_active=1 AND offer_type='emploi'").fetchone()[0]
    conn.close()
    return jsonify({
        'total':total,'emploi':emploi,'appel_offre':total-emploi,
        'favorites':0,'sources_count':0,'new_today':0,
        'sectors':[{'name':r[0],'count':r[1]} for r in sectors],
        'locations':[{'name':r[0],'count':r[1]} for r in locations],
        'sources_stats':[{'name':r[0],'count':r[1]} for r in src_stats],
        'daily':daily,
        'logs':[{'source_name':l['source_name'],'status':l['status'],'found':l['found'],
                 'new_items':l['new_items'],'message':l['message'] or '','started_at':l['started_at'][:16]} for l in logs]
    })

# ─── Export Excel ─────────────────────────────────────────────────────────────
@app.route('/api/export/excel')
def export_excel():
    try: import openpyxl; from openpyxl.styles import Font,PatternFill,Alignment,Border,Side; from openpyxl.utils import get_column_letter
    except: return jsonify({'error':'openpyxl non disponible'}),500

    where,params = ['is_active=1'],[]
    if t := request.args.get('type'): where.append('offer_type=?'); params.append(t)
    if s := request.args.get('sector'): where.append('sector LIKE ?'); params.append(f'%{s}%')
    if kw := request.args.get('q'): where.append('title LIKE ?'); params.append(f'%{kw}%')
    conn = get_db()
    items = conn.execute(f'SELECT * FROM offers WHERE {" AND ".join(where)} ORDER BY scraped_at DESC',params).fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    thin = Border(*[Side(style='thin',color='DDDDDD')]*4)
    thin = Border(left=Side(style='thin',color='DDDDDD'),right=Side(style='thin',color='DDDDDD'),top=Side(style='thin',color='DDDDDD'),bottom=Side(style='thin',color='DDDDDD'))
    def hdr(cell, color='1B5E20'):
        cell.font=Font(color='FFFFFF',bold=True,size=11,name='Calibri')
        cell.fill=PatternFill(start_color=color,end_color=color,fill_type='solid')
        cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
        cell.border=thin

    ws1=wb.active; ws1.title='Toutes les offres'
    cols=['#','Type','Titre','Organisation','Ville','Secteur','Contrat','Salaire','Deadline','Source','Lien','Date']
    widths=[5,14,45,28,16,22,16,20,14,20,40,14]
    for i,(h,w) in enumerate(zip(cols,widths),1):
        hdr(ws1.cell(row=1,column=i,value=h)); ws1.column_dimensions[get_column_letter(i)].width=w
    ws1.row_dimensions[1].height=26
    ef=PatternFill(start_color='E3F2FD',end_color='E3F2FD',fill_type='solid')
    af=PatternFill(start_color='FFF8E1',end_color='FFF8E1',fill_type='solid')
    wf=PatternFill(start_color='FFFFFF',end_color='FFFFFF',fill_type='solid')
    la=Alignment(horizontal='left',vertical='top',wrap_text=True); ca=Alignment(horizontal='center',vertical='center')
    for ri,o in enumerate(items,2):
        f=ef if o['offer_type']=='emploi' else af if ri%2==0 else wf
        vals=[ri-1,'Emploi' if o['offer_type']=='emploi' else "Appel d'offre",o['title'] or '',o['organization'] or '',
              o['location'] or '',o['sector'] or '',o['contract_type'] or '',o['salary'] or '',o['deadline'] or '',
              o['source_name'] or '',o['url'] or '',(o['scraped_at'] or '')[:10]]
        for ci,v in enumerate(vals,1):
            c=ws1.cell(row=ri,column=ci,value=v); c.fill=f; c.border=thin; c.alignment=ca if ci<=2 else la

    ws2=wb.create_sheet("Appels d'Offres")
    cols2=['#','Référence','Titre','Autorité','Organisation','Ville','Secteur','Budget','Deadline','Source','Lien']
    ws2c=[5,18,45,28,25,16,22,20,14,20,40]
    for i,(h,w) in enumerate(zip(cols2,ws2c),1):
        hdr(ws2.cell(row=1,column=i,value=h),'E65100'); ws2.column_dimensions[get_column_letter(i)].width=w
    ws2.row_dimensions[1].height=26
    ao_f=PatternFill(start_color='FFF3E0',end_color='FFF3E0',fill_type='solid')
    for ri,o in enumerate([x for x in items if x['offer_type']=='appel_offre'],2):
        f=ao_f if ri%2==0 else wf
        vals=[ri-1,o['reference'] or '',o['title'] or '',o['authority'] or '',o['organization'] or '',
              o['location'] or '',o['sector'] or '',o['budget'] or '',o['deadline'] or '',o['source_name'] or '',o['url'] or '']
        for ci,v in enumerate(vals,1):
            c=ws2.cell(row=ri,column=ci,value=v); c.fill=f; c.border=thin; c.alignment=ca if ci<=2 else la

    ws3=wb.create_sheet('Statistiques')
    ws3.column_dimensions['A'].width=35; ws3.column_dimensions['B'].width=20
    ws3.merge_cells('A1:B1'); t=ws3['A1']; t.value=f"CamerJob Watch — Export du {now_fmt('%d/%m/%Y %H:%M')}"
    t.font=Font(color='FFFFFF',bold=True,size=13); t.fill=PatternFill(start_color='37474F',end_color='37474F',fill_type='solid')
    t.alignment=Alignment(horizontal='center',vertical='center'); ws3.row_dimensions[1].height=30
    rows3=[['',''],['RÉSUMÉ',''],[f'Total offres',len(items)],[f"Offres d'emploi",sum(1 for x in items if x['offer_type']=='emploi')],[f"Appels d'offres",sum(1 for x in items if x['offer_type']=='appel_offre')],['','']]
    from collections import Counter
    for s,c in Counter(o['sector'] for o in items if o['sector']).most_common(10): rows3.append([s,c])
    for ri,row in enumerate(rows3,2):
        for ci,v in enumerate(row,1):
            cell=ws3.cell(row=ri,column=ci,value=v)
            if v=='RÉSUMÉ': cell.font=Font(bold=True,color='1B5E20',size=12)

    for ws in [ws1,ws2]: ws.freeze_panes='A2'
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return send_file(out,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,download_name=f"camerajob_{now_fmt('%Y%m%d_%H%M')}.xlsx")

# ─── Nouvelles pages ──────────────────────────────────────────────────────────
@app.route('/portails')
def portails():
    return render_template('portails.html')

@app.route('/cv')
def cv_page():
    return render_template('cv.html')

@app.route('/parametres')
def parametres():
    return render_template('parametres.html')

# ─── API Portails ──────────────────────────────────────────────────────────────
def _ensure_portails_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS portails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, url TEXT NOT NULL,
        category TEXT DEFAULT 'Emploi',
        description TEXT, created_at TEXT
    )''')
    conn.commit()
    if conn.execute('SELECT COUNT(*) FROM portails').fetchone()[0] == 0:
        seed_portails = [
            ('MinaJobs Cameroun','https://minajobs.net','Emploi','Offres emplois et stages au Cameroun'),
            ('InfosConcours Education','https://infosconcourseducation.com','Concours','Concours, recrutements et bourses'),
            ('Louma Jobs','https://louma-jobs.com/cameroun/','Emploi','15000+ offres emploi Cameroun'),
            ('UNJobs Yaoundé','https://unjobs.org/duty_stations/yao','ONG/ONU','Offres ONU et ONG à Yaoundé'),
            ('Cameroon Desks','https://www.cameroondesks.com/','Emploi','Emplois, concours, bourses Cameroun'),
            ('Emploi.cm','https://www.emploi.cm/','Emploi','Principal portail emploi officiel'),
            ('Emploi Cari Africa','https://emploi.cm.cari.africa/emploi','Emploi','Offres emploi Cari Africa Cameroun'),
            ('JobArtis Cameroun','https://www.jobartiscameroun.com/emplois','Emploi','Emploi artisanat et services'),
            ('Alerte Emploi Cameroun','https://alerteemploicameroun.com','Emploi','Alertes emploi quotidiennes'),
            ('LinkedIn Cameroun','https://cm.linkedin.com/jobs/cameroun-jobs?countryRedirected=1','Emploi','Offres LinkedIn Cameroun'),
        ]
        conn.executemany('INSERT INTO portails(name,url,category,description,created_at) VALUES(?,?,?,?,?)',
                         [(n,u,c,d,now_iso()) for n,u,c,d in seed_portails])
        conn.commit()

@app.route('/api/portails')
def api_portails():
    conn = get_db()
    _ensure_portails_table(conn)
    rows = conn.execute('SELECT * FROM portails ORDER BY category,name').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/portails/add', methods=['POST'])
def api_add_portail():
    d = request.get_json()
    if not d.get('name') or not d.get('url'):
        return jsonify({'error':'Nom et URL requis'}),400
    conn = get_db()
    _ensure_portails_table(conn)
    conn.execute('INSERT INTO portails(name,url,category,description,created_at) VALUES(?,?,?,?,?)',
                 (d['name'],d['url'],d.get('category','Emploi'),d.get('description',''),now_iso()))
    pid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()
    return jsonify({'success':True,'id':pid})

@app.route('/api/portails/<int:pid>', methods=['DELETE'])
def api_del_portail(pid):
    conn = get_db()
    conn.execute('DELETE FROM portails WHERE id=?',(pid,))
    conn.commit(); conn.close()
    return jsonify({'success':True})

# ─── Ajouter offre depuis URL ──────────────────────────────────────────────────
@app.route('/api/offers/add-from-url', methods=['POST'])
def add_offer_from_url():
    import urllib.request
    d = request.get_json()
    url = d.get('url','').strip()
    if not url: return jsonify({'error':'URL requise'}),400
    HDR = {
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
        'Accept-Language':'fr-FR,fr;q=0.9','Accept':'text/html,*/*'
    }
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='replace')
        # Titre
        tm = re.search(r'<title[^>]*>(.*?)</title>', html, re.S|re.I)
        title = re.sub(r'<[^>]+>','', tm.group(1) if tm else '').strip()
        title = re.sub(r'\s+',' ', title)[:250] or f'Offre depuis {url[:60]}'
        for sep in [' | ',' - ',' — ',' – ']:
            if sep in title: title = title.split(sep)[0].strip(); break
        # Organisation
        org_m = re.search(r'property=["\']og:site_name["\'][^>]*content=["\'](.*?)["\']', html, re.I)
        if not org_m: org_m = re.search(r'content=["\'](.*?)["\'][^>]*property=["\']og:site_name["\']', html, re.I)
        org = org_m.group(1).strip() if org_m else re.sub(r'^https?://(www\.)?','',url).split('/')[0]
        # Description
        desc_m = re.search(r'name=["\']description["\'][^>]*content=["\'](.*?)["\']', html, re.I)
        if not desc_m: desc_m = re.search(r'content=["\'](.*?)["\'][^>]*name=["\']description["\']', html, re.I)
        desc = desc_m.group(1).strip()[:500] if desc_m else ''
        # Si preview seulement (pas de sauvegarde)
        if d.get('preview_only'):
            return jsonify({'title':title,'organization':org,'description':desc})
        # Sauvegarder
        conn = get_db()
        conn.execute('''INSERT INTO offers(offer_type,title,organization,location,description,sector,url,source_name,scraped_at)
                       VALUES(?,?,?,?,?,?,?,?,?)''',
                     (d.get('offer_type','emploi'),title,org,d.get('location','Cameroun'),
                      desc,scraper._guess_sector(title),url,'Manuel (URL)',now_iso()))
        oid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.commit(); conn.close()
        return jsonify({'success':True,'id':oid,'title':title,'organization':org})
    except Exception as e:
        return jsonify({'error':str(e)[:200]}),500

# ─── Reset offres (paramètres) ─────────────────────────────────────────────────
@app.route('/api/db/reset-offers', methods=['POST'])
def reset_offers():
    conn = get_db()
    conn.execute('UPDATE offers SET is_active=0')
    conn.commit(); conn.close()
    return jsonify({'success':True})


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT IA v4 — OAuth2 Google + Templates intelligents + Claude optionnel
# ═══════════════════════════════════════════════════════════════════════════════
import hashlib, secrets, smtplib, imaplib, base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask import session, redirect, url_for

# ── Config OAuth2 Google ───────────────────────────────────────────────────────
# Ces valeurs viennent des variables d'environnement (à configurer sur Render)
GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI  = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5000/agent/oauth/callback')

GOOGLE_AUTH_URL    = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL   = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO    = 'https://www.googleapis.com/oauth2/v2/userinfo'
GOOGLE_GMAIL_SEND  = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
GOOGLE_GMAIL_DRAFT = 'https://gmail.googleapis.com/gmail/v1/users/me/drafts'

OAUTH_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
]

app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ── Tables DB Agent ────────────────────────────────────────────────────────────
def init_agent_db():
    conn = get_db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS agent_users (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT NOT NULL,
        email            TEXT UNIQUE NOT NULL,
        password_hash    TEXT DEFAULT '',
        auth_method      TEXT DEFAULT 'local',
        google_id        TEXT DEFAULT '',
        access_token     TEXT DEFAULT '',
        refresh_token    TEXT DEFAULT '',
        token_expires    TEXT DEFAULT '',
        gmail_address    TEXT DEFAULT '',
        gmail_app_pwd    TEXT DEFAULT '',
        gmail_verified   INTEGER DEFAULT 0,
        anthropic_key    TEXT DEFAULT '',
        api_verified     INTEGER DEFAULT 0,
        cv_text          TEXT DEFAULT '',
        cv_filename      TEXT DEFAULT '',
        cv_data          BLOB,
        lettre_modele    TEXT DEFAULT '',
        sectors          TEXT DEFAULT '',
        created_at       TEXT,
        last_login       TEXT
    );
    CREATE TABLE IF NOT EXISTS agent_sessions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        token      TEXT UNIQUE NOT NULL,
        expires_at TEXT
    );
    CREATE TABLE IF NOT EXISTS agent_candidatures (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id        INTEGER NOT NULL,
        offer_title    TEXT DEFAULT '',
        offer_org      TEXT DEFAULT '',
        offer_url      TEXT DEFAULT '',
        offer_desc     TEXT DEFAULT '',
        lettre         TEXT DEFAULT '',
        email_sujet    TEXT DEFAULT '',
        email_corps    TEXT DEFAULT '',
        destinataire   TEXT DEFAULT '',
        statut         TEXT DEFAULT 'genere',
        methode        TEXT DEFAULT 'template',
        created_at     TEXT,
        sent_at        TEXT
    );
    CREATE TABLE IF NOT EXISTS admin_envois (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        sujet    TEXT,
        nb_dest  INTEGER DEFAULT 0,
        statut   TEXT DEFAULT 'ok',
        sent_at  TEXT
    );
    ''')
    conn.commit()
    conn.close()

init_agent_db()

# ── Helpers auth ───────────────────────────────────────────────────────────────
def _hp(p): return hashlib.sha256(p.encode()).hexdigest()

def _mk_token(uid):
    token = secrets.token_urlsafe(40)
    conn = get_db()
    conn.execute('DELETE FROM agent_sessions WHERE user_id=?', (uid,))
    conn.execute('INSERT INTO agent_sessions(user_id,token,expires_at) VALUES(?,?,?)',
                 (uid, token, (now_utc()+timedelta(days=30)).isoformat()))
    conn.commit(); conn.close()
    return token

def _get_user():
    token = request.cookies.get('agt') or request.headers.get('X-Token','')
    if not token: return None
    conn = get_db()
    row = conn.execute('''SELECT u.* FROM agent_users u
        JOIN agent_sessions s ON s.user_id=u.id
        WHERE s.token=? AND s.expires_at>?''', (token, now_iso())).fetchone()
    conn.close()
    return dict(row) if row else None

def _http_get(url, headers=None):
    import urllib.request as ur
    req = ur.Request(url, headers=headers or {})
    with ur.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def _http_post(url, data, headers=None):
    import urllib.request as ur, urllib.parse as up
    if isinstance(data, dict):
        body = up.urlencode(data).encode()
        hdrs = {'Content-Type': 'application/x-www-form-urlencoded'}
    else:
        body = json.dumps(data).encode() if not isinstance(data, bytes) else data
        hdrs = {'Content-Type': 'application/json'}
    hdrs.update(headers or {})
    req = ur.Request(url, data=body, headers=hdrs)
    with ur.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

# ── OAuth2 Google ──────────────────────────────────────────────────────────────
@app.route('/agent/oauth/start')
def agent_oauth_start():
    """Redirige vers Google pour authentification"""
    if not GOOGLE_CLIENT_ID:
        return jsonify({'error': 'OAuth Google non configuré. Variables GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET manquantes.'}), 500
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = {
        'client_id':     GOOGLE_CLIENT_ID,
        'redirect_uri':  GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope':         ' '.join(OAUTH_SCOPES),
        'access_type':   'offline',
        'prompt':        'consent',
        'state':         state,
    }
    from urllib.parse import urlencode
    url = GOOGLE_AUTH_URL + '?' + urlencode(params)
    return redirect(url)

@app.route('/agent/oauth/callback')
def agent_oauth_callback():
    """Callback OAuth2 — échange le code contre les tokens"""
    error = request.args.get('error')
    if error:
        return redirect(f'/agent?oauth_error={error}')
    code  = request.args.get('code','')
    state = request.args.get('state','')
    if state != session.get('oauth_state',''):
        return redirect('/agent?oauth_error=invalid_state')
    if not code:
        return redirect('/agent?oauth_error=no_code')
    try:
        # Échanger le code contre les tokens
        token_data = _http_post(GOOGLE_TOKEN_URL, {
            'code':          code,
            'client_id':     GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri':  GOOGLE_REDIRECT_URI,
            'grant_type':    'authorization_code',
        })
        access_token  = token_data.get('access_token','')
        refresh_token = token_data.get('refresh_token','')
        expires_in    = token_data.get('expires_in', 3600)
        token_expires = (now_utc() + timedelta(seconds=expires_in)).isoformat()
        # Récupérer infos utilisateur
        userinfo = _http_get(GOOGLE_USERINFO, {
            'Authorization': f'Bearer {access_token}'
        })
        google_id = userinfo.get('id','')
        name      = userinfo.get('name','') or userinfo.get('email','').split('@')[0]
        email     = userinfo.get('email','')
        if not email:
            return redirect('/agent?oauth_error=no_email')
        conn = get_db()
        existing = conn.execute('SELECT * FROM agent_users WHERE email=?', (email,)).fetchone()
        if existing:
            uid = existing['id']
            conn.execute('''UPDATE agent_users SET name=?,google_id=?,access_token=?,
                            refresh_token=?,token_expires=?,gmail_address=?,gmail_verified=1,
                            auth_method=?,last_login=? WHERE id=?''',
                         (name, google_id, access_token,
                          refresh_token or existing['refresh_token'],
                          token_expires, email, 'google', now_iso(), uid))
        else:
            conn.execute('''INSERT INTO agent_users
                (name,email,auth_method,google_id,access_token,refresh_token,
                 token_expires,gmail_address,gmail_verified,created_at,last_login)
                VALUES(?,?,?,?,?,?,?,?,1,?,?)''',
                (name, email, 'google', google_id, access_token,
                 refresh_token, token_expires, email, now_iso(), now_iso()))
            uid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.commit(); conn.close()
        token = _mk_token(uid)
        resp  = redirect('/agent?oauth_success=1')
        resp.set_cookie('agt', token, max_age=30*24*3600, httponly=True, samesite='Lax')
        return resp
    except Exception as e:
        return redirect(f'/agent?oauth_error={str(e)[:80]}')

def _refresh_access_token(u):
    """Rafraîchit le token Google si expiré"""
    if not u.get('refresh_token'): return u
    try:
        expires = u.get('token_expires','')
        if expires and now_iso() < expires: return u  # Encore valide
        td = _http_post(GOOGLE_TOKEN_URL, {
            'client_id':     GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': u['refresh_token'],
            'grant_type':    'refresh_token',
        })
        new_token = td.get('access_token', u['access_token'])
        new_exp   = (now_utc() + timedelta(seconds=td.get('expires_in',3600))).isoformat()
        conn = get_db()
        conn.execute('UPDATE agent_users SET access_token=?,token_expires=? WHERE id=?',
                     (new_token, new_exp, u['id']))
        conn.commit(); conn.close()
        u['access_token'] = new_token
    except: pass
    return u

# ── Gmail via API Google (OAuth) ───────────────────────────────────────────────
def _gmail_send_oauth(user, to, subject, body, attachment_data=None, attachment_name=None):
    """Envoie via Gmail API avec token OAuth"""
    user = _refresh_access_token(user)
    token = user.get('access_token','')
    if not token: raise Exception('Token OAuth manquant. Reconnectez-vous avec Google.')
    # Construire le message MIME
    msg = MIMEMultipart()
    msg['From']    = user['gmail_address']
    msg['To']      = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    if attachment_data and attachment_name:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
        msg.attach(part)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    _http_post(GOOGLE_GMAIL_SEND, {'raw': raw},
               {'Authorization': f'Bearer {token}'})

def _gmail_draft_oauth(user, to, subject, body, attachment_data=None, attachment_name=None):
    """Sauvegarde dans les brouillons Gmail via API OAuth"""
    user = _refresh_access_token(user)
    token = user.get('access_token','')
    if not token: raise Exception('Token OAuth manquant. Reconnectez-vous avec Google.')
    msg = MIMEMultipart()
    msg['From']    = user['gmail_address']
    msg['To']      = to or user['gmail_address']
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    if attachment_data and attachment_name:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
        msg.attach(part)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    _http_post(GOOGLE_GMAIL_DRAFT, {'message': {'raw': raw}},
               {'Authorization': f'Bearer {token}'})

def _gmail_send_smtp(gmail, pwd, to, subject, body, attachment_data=None, attachment_name=None):
    """Fallback SMTP si pas d'OAuth"""
    msg = MIMEMultipart()
    msg['From'] = gmail; msg['To'] = to; msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    if attachment_data and attachment_name:
        part = MIMEBase('application','octet-stream'); part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',f'attachment; filename="{attachment_name}"')
        msg.attach(part)
    with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=20) as s:
        s.login(gmail,pwd); s.sendmail(gmail,to,msg.as_string())

def _gmail_draft_smtp(gmail, pwd, to, subject, body, attachment_data=None, attachment_name=None):
    """Brouillon SMTP fallback"""
    msg = MIMEMultipart()
    msg['From']=gmail; msg['To']=to or gmail; msg['Subject']=subject
    msg.attach(MIMEText(body,'plain','utf-8'))
    if attachment_data and attachment_name:
        part = MIMEBase('application','octet-stream'); part.set_payload(attachment_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition',f'attachment; filename="{attachment_name}"')
        msg.attach(part)
    with imaplib.IMAP4_SSL('imap.gmail.com') as imap:
        imap.login(gmail,pwd)
        _, folders = imap.list()
        draft = '[Gmail]/Drafts'
        for fdr in (folders or []):
            fs = (fdr.decode() if isinstance(fdr,bytes) else fdr).lower()
            if 'draft' in fs or 'brouillon' in fs:
                import re as _re
                m = _re.search(r'"[^"]+"$|[^ ]+$', fdr.decode() if isinstance(fdr,bytes) else fdr)
                if m: draft = m.group().strip('"'); break
        imap.append(draft,'\\Draft',None,msg.as_bytes())

# ── Test Gmail SMTP ────────────────────────────────────────────────────────────
def _test_smtp(addr, pwd):
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=12) as s: s.login(addr,pwd)
        return True,''
    except smtplib.SMTPAuthenticationError:
        return False,('Authentification Gmail échouée.\n\nAssurez-vous que :\n'
            '1. La validation en 2 étapes est activée (myaccount.google.com → Sécurité)\n'
            '2. Vous utilisez un MOT DE PASSE D\'APPLICATION Gmail (16 caractères)\n'
            '   Chemin : Compte Google → Sécurité → Mots de passe des applications')
    except Exception as e:
        return False, str(e)

def _test_api(key):
    if not key or not key.startswith('sk-ant-'):
        return False,"Clé invalide. Doit commencer par 'sk-ant-'. Obtenez-en une sur console.anthropic.com"
    try:
        import urllib.request as ur
        body=json.dumps({'model':'claude-haiku-4-5-20251001','max_tokens':5,
                         'messages':[{'role':'user','content':'ok'}]}).encode()
        req=ur.Request('https://api.anthropic.com/v1/messages',data=body,
                       headers={'Content-Type':'application/json','x-api-key':key,
                                'anthropic-version':'2023-06-01'})
        with ur.urlopen(req,timeout=12): pass
        return True,''
    except Exception as e:
        s=str(e)
        if '401' in s: return False,'Clé API invalide ou expirée'
        if '429' in s: return False,'Quota dépassé. Vérifiez votre solde sur console.anthropic.com'
        return False,f'Erreur: {s[:120]}'

# ── Génération ─────────────────────────────────────────────────────────────────
def _gen_template(cv, lettre_mod, title, org, desc, name):
    cv_l = (cv or '').lower()
    skills=[]
    for sk,kw in [('Python','python'),('JavaScript','javascript'),('SQL','sql'),
                  ('Excel','excel'),('AutoCAD','autocad'),('Power BI','power bi'),
                  ('PHP','php'),('Java','java'),('React','react'),('SAGE','sage')]:
        if kw in cv_l: skills.append(sk)
    org_l = org.lower()
    if any(k in org_l for k in ['ong','ngo','unicef','pnud','solidar','msf','croix']):
        c_org = "dont la mission humanitaire force mon admiration"
        m_org = "contribuer à votre mission au service du développement humain"
    elif any(k in org_l for k in ['minist','état','public','national','gouver']):
        c_org = "qui joue un rôle fondamental dans le développement du Cameroun"
        m_org = "mettre mes compétences au service de l'intérêt général"
    elif any(k in org_l for k in ['banque','financ','crédit','assur']):
        c_org = "dont l'excellence dans le secteur financier camerounais est reconnue"
        m_org = "évoluer dans un environnement de rigueur et de performance"
    else:
        c_org = "dont le dynamisme correspond à mes ambitions professionnelles"
        m_org = "contribuer activement à votre développement"
    comp = f"maîtrise de {', '.join(skills[:3])}" if skills else "solide formation académique"
    prenom = name.split()[0] if name else "Candidat"
    date_fr = now_utc().strftime("%d/%m/%Y")
    lettre = f"""{name}
Yaoundé, le {date_fr}

À l'attention du Service des Ressources Humaines
{org}

Objet : Candidature au poste de {title}

Madame, Monsieur,

C'est avec un vif intérêt que je me permets de vous soumettre ma candidature au poste de {title} au sein de {org}, {c_org}.

Titulaire d'une solide formation et fort(e) d'une expérience terrain adaptée aux réalités du marché camerounais, je dispose des compétences pour exceller dans ce rôle. Ma {comp} ainsi que ma capacité à travailler en équipe dans des environnements exigeants constituent des atouts que je suis convaincu(e) de pouvoir mettre au service de votre organisation.

Au cours de mon parcours, j'ai développé une aptitude à analyser les situations complexes, proposer des solutions innovantes et atteindre les objectifs fixés dans les délais impartis. Je suis reconnu(e) pour mon sens de l'organisation, mon intégrité professionnelle et mon engagement sans réserve.

Mon souhait est de {m_org}. Je suis convaincu(e) que cette opportunité me permettra de donner le meilleur de moi-même tout en apportant une valeur ajoutée significative à votre équipe.

Je reste disponible pour un entretien à votre convenance et vous adresse, Madame, Monsieur, l'expression de mes salutations distinguées.

{name}"""
    sujet = f"Candidature — {title} | {name}"
    corps = f"""Madame, Monsieur,

Je me permets de vous soumettre ma candidature pour le poste de {title} au sein de {org}.

Vous trouverez en pièce jointe mon curriculum vitæ ainsi que ma lettre de motivation détaillant mon parcours et les atouts que je pourrai apporter à votre équipe.

Je reste disponible pour tout entretien à votre convenance.

Dans l'attente de votre retour, veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

{name}"""
    return lettre, sujet, corps

def _gen_claude(key, cv, lettre_mod, title, org, desc, name):
    import urllib.request as ur
    prompt = f"""Expert RH marché camerounais.
CV: {(cv or '')[:2500]}
{"Style lettre: "+(lettre_mod or '')[:600] if lettre_mod else ""}
Offre: {title} chez {org}
Description: {desc or 'N/A'}
Candidat: {name}

Format STRICT:
===LETTRE===
[Lettre professionnelle 4 paragraphes, français formel, adaptée à {org}]
===FIN_LETTRE===
===EMAIL_SUJET===
[Objet email max 70 caractères]
===FIN_SUJET===
===EMAIL_CORPS===
[Corps 5 lignes, mentionner CV+lettre joints]
===FIN_EMAIL==="""
    body = json.dumps({'model':'claude-sonnet-4-20250514','max_tokens':1500,
                       'messages':[{'role':'user','content':prompt}]}).encode()
    req = ur.Request('https://api.anthropic.com/v1/messages', data=body,
                     headers={'Content-Type':'application/json','x-api-key':key,
                              'anthropic-version':'2023-06-01'})
    with ur.urlopen(req, timeout=45) as r:
        result = json.loads(r.read())
    g = result['content'][0]['text']
    def ex(txt,s,e): return txt.split(s)[1].split(e)[0].strip() if s in txt and e in txt else ''
    return (ex(g,'===LETTRE===','===FIN_LETTRE===') or g,
            ex(g,'===EMAIL_SUJET===','===FIN_SUJET==='),
            ex(g,'===EMAIL_CORPS===','===FIN_EMAIL==='))

# ── Pages ──────────────────────────────────────────────────────────────────────
@app.route('/agent')
def agent_page():
    oauth_cfg = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    return render_template('agent.html', oauth_configured=oauth_cfg)

@app.route('/admin/agent')
def admin_agent():
    return render_template('admin_agent.html')

# ── Auth API ───────────────────────────────────────────────────────────────────
@app.route('/api/agent/register', methods=['POST'])
def agent_register():
    d = request.get_json() or {}
    name=d.get('name','').strip(); email=d.get('email','').strip().lower(); pwd=d.get('password','')
    if not name: return jsonify({'ok':False,'err':'Nom requis'}),400
    if not email or '@' not in email: return jsonify({'ok':False,'err':'Email invalide'}),400
    if len(pwd)<6: return jsonify({'ok':False,'err':'Mot de passe minimum 6 caractères'}),400
    conn=get_db()
    if conn.execute('SELECT id FROM agent_users WHERE email=?',(email,)).fetchone():
        conn.close(); return jsonify({'ok':False,'err':'Cet email est déjà utilisé'}),409
    conn.execute('INSERT INTO agent_users(name,email,password_hash,auth_method,created_at) VALUES(?,?,?,?,?)',
                 (name,email,_hp(pwd),'local',now_iso()))
    uid=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()
    token=_mk_token(uid)
    r=jsonify({'ok':True,'name':name})
    r.set_cookie('agt',token,max_age=30*24*3600,httponly=True,samesite='Lax')
    return r

@app.route('/api/agent/login', methods=['POST'])
def agent_login():
    d=request.get_json() or {}
    email=d.get('email','').strip().lower(); pwd=d.get('password','')
    conn=get_db()
    u=conn.execute('SELECT * FROM agent_users WHERE email=? AND password_hash=?',(email,_hp(pwd))).fetchone()
    if not u: conn.close(); return jsonify({'ok':False,'err':'Email ou mot de passe incorrect'}),401
    conn.execute('UPDATE agent_users SET last_login=? WHERE id=?',(now_iso(),u['id']))
    conn.commit(); conn.close()
    token=_mk_token(u['id'])
    r=jsonify({'ok':True,'name':u['name']})
    r.set_cookie('agt',token,max_age=30*24*3600,httponly=True,samesite='Lax')
    return r

@app.route('/api/agent/logout', methods=['POST'])
def agent_logout():
    t=request.cookies.get('agt')
    if t:
        conn=get_db(); conn.execute('DELETE FROM agent_sessions WHERE token=?',(t,)); conn.commit(); conn.close()
    r=jsonify({'ok':True}); r.delete_cookie('agt'); return r

@app.route('/api/agent/me')
def agent_me():
    u=_get_user()
    if not u: return jsonify({'auth':False})
    conn=get_db()
    st={'total':    conn.execute('SELECT COUNT(*) FROM agent_candidatures WHERE user_id=?',(u['id'],)).fetchone()[0],
        'envoyes':  conn.execute("SELECT COUNT(*) FROM agent_candidatures WHERE user_id=? AND statut='envoye'",(u['id'],)).fetchone()[0],
        'brouillons':conn.execute("SELECT COUNT(*) FROM agent_candidatures WHERE user_id=? AND statut='brouillon'",(u['id'],)).fetchone()[0],
        'generes':  conn.execute("SELECT COUNT(*) FROM agent_candidatures WHERE user_id=? AND statut='genere'",(u['id'],)).fetchone()[0]}
    conn.close()
    return jsonify({'auth':True,'user':{'id':u['id'],'name':u['name'],'email':u['email'],
        'auth_method':u['auth_method'],'gmail':u['gmail_address'],'gmail_ok':bool(u['gmail_verified']),
        'api_ok':bool(u['api_verified']),'has_cv':bool(u['cv_text']),'has_lettre':bool(u['lettre_modele']),
        'sectors':u['sectors']},'stats':st})

# ── Config ──────────────────────────────────────────────────────────────────────
@app.route('/api/agent/save-gmail',methods=['POST'])
def agent_save_gmail():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    d=request.get_json() or {}
    addr=(d.get('gmail') or '').strip(); pwd=(d.get('pwd') or '').strip()
    if not addr or '@' not in addr: return jsonify({'ok':False,'err':'Adresse Gmail invalide'}),400
    if not pwd: return jsonify({'ok':False,'err':'Mot de passe d\'application requis'}),400
    conn=get_db()
    conn.execute('UPDATE agent_users SET gmail_address=?,gmail_app_pwd=?,gmail_verified=0 WHERE id=?',(addr,pwd,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/agent/test-gmail',methods=['POST'])
def agent_test_gmail():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    d=request.get_json() or {}
    addr=(d.get('gmail') or u.get('gmail_address') or '').strip()
    pwd=(d.get('pwd') or u.get('gmail_app_pwd') or '').strip()
    if not addr or not pwd: return jsonify({'ok':False,'err':'Configurez Gmail et mot de passe avant de tester'}),400
    ok,err=_test_smtp(addr,pwd)
    conn=get_db()
    conn.execute('UPDATE agent_users SET gmail_address=?,gmail_app_pwd=?,gmail_verified=? WHERE id=?',(addr,pwd,1 if ok else 0,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':ok,'err':err})

@app.route('/api/agent/save-apikey',methods=['POST'])
def agent_save_apikey():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    key=(request.get_json() or {}).get('key','').strip()
    if not key: return jsonify({'ok':False,'err':'Clé requise'}),400
    conn=get_db(); conn.execute('UPDATE agent_users SET anthropic_key=?,api_verified=0 WHERE id=?',(key,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/agent/test-apikey',methods=['POST'])
def agent_test_apikey():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    key=((request.get_json() or {}).get('key') or u.get('anthropic_key') or '').strip()
    ok,err=_test_api(key)
    conn=get_db(); conn.execute('UPDATE agent_users SET anthropic_key=?,api_verified=? WHERE id=?',(key,1 if ok else 0,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':ok,'err':err})

@app.route('/api/agent/save-sectors',methods=['POST'])
def agent_save_sectors():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    sectors=','.join((request.get_json() or {}).get('sectors',[]))
    conn=get_db(); conn.execute('UPDATE agent_users SET sectors=? WHERE id=?',(sectors,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True})

# ── Upload ──────────────────────────────────────────────────────────────────────
def _extract(data, fname):
    try:
        if fname.lower().endswith('.pdf'):
            try:
                import pypdf, io as _io
                return '\n'.join(p.extract_text() or '' for p in pypdf.PdfReader(_io.BytesIO(data)).pages)
            except ImportError: return data.decode('utf-8',errors='ignore')
        if fname.lower().endswith('.docx'):
            try:
                import zipfile, xml.etree.ElementTree as ET, io as _io
                with zipfile.ZipFile(_io.BytesIO(data)) as z: xc=z.read('word/document.xml')
                return ' '.join(t.text or '' for t in ET.fromstring(xc).iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
            except: pass
        return data.decode('utf-8',errors='ignore')
    except: return ''

@app.route('/api/agent/upload-cv',methods=['POST'])
def agent_upload_cv():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    if 'file' not in request.files: return jsonify({'ok':False,'err':'Fichier manquant'}),400
    f=request.files['file']; data=f.read()
    text=_extract(data,f.filename)
    if not text or len(text)<20: return jsonify({'ok':False,'err':'Impossible d\'extraire le texte. Essayez un fichier DOCX ou TXT.'}),400
    conn=get_db(); conn.execute('UPDATE agent_users SET cv_text=?,cv_filename=?,cv_data=? WHERE id=?',(text,f.filename,data,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'chars':len(text),'preview':text[:300],'filename':f.filename})

@app.route('/api/agent/upload-lettre',methods=['POST'])
def agent_upload_lettre():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    if 'file' not in request.files: return jsonify({'ok':False,'err':'Fichier manquant'}),400
    f=request.files['file']; data=f.read(); text=_extract(data,f.filename)
    conn=get_db(); conn.execute('UPDATE agent_users SET lettre_modele=? WHERE id=?',(text,u['id']))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'chars':len(text)})

# ── GÉNÉRER ─────────────────────────────────────────────────────────────────────
@app.route('/api/agent/generer',methods=['POST'])
def agent_generer():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    d=request.get_json() or {}
    title=(d.get('title') or '').strip(); org=(d.get('org') or '').strip()
    if not title: return jsonify({'ok':False,'err':'Titre du poste obligatoire'}),400
    if not org:   return jsonify({'ok':False,'err':'Organisation obligatoire'}),400
    methode='template'; lettre=sujet=corps=''
    if u.get('api_verified') and u.get('anthropic_key'):
        try:
            lettre,sujet,corps=_gen_claude(u['anthropic_key'],u['cv_text'],u['lettre_modele'],title,org,d.get('desc',''),u['name'])
            methode='claude'
        except: lettre,sujet,corps=_gen_template(u['cv_text'],u['lettre_modele'],title,org,d.get('desc',''),u['name'])
    else:
        lettre,sujet,corps=_gen_template(u['cv_text'],u['lettre_modele'],title,org,d.get('desc',''),u['name'])
    conn=get_db()
    conn.execute('''INSERT INTO agent_candidatures(user_id,offer_title,offer_org,offer_url,offer_desc,
                    lettre,email_sujet,email_corps,statut,methode,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                 (u['id'],title,org,d.get('url',''),d.get('desc',''),lettre,sujet,corps,'genere',methode,now_iso()))
    cid=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()
    return jsonify({'ok':True,'cid':cid,'lettre':lettre,'sujet':sujet,'corps':corps,'methode':methode})

# ── POSTULER ────────────────────────────────────────────────────────────────────
@app.route('/api/agent/postuler',methods=['POST'])
def agent_postuler():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    d=request.get_json() or {}
    sujet=(d.get('sujet') or '').strip(); corps=(d.get('corps') or '').strip()
    lettre=(d.get('lettre') or '').strip(); dest=(d.get('dest') or '').strip()
    mode=d.get('mode','brouillon'); cid=d.get('cid')
    if not sujet: return jsonify({'ok':False,'err':'Objet de l\'email obligatoire'}),400
    if not corps: return jsonify({'ok':False,'err':'Corps de l\'email obligatoire'}),400
    if mode=='envoyer' and (not dest or '@' not in dest):
        return jsonify({'ok':False,'err':'Email du recruteur requis pour l\'envoi direct'}),400
    # Vérifier Gmail disponible
    use_oauth=(u['auth_method']=='google' and u.get('access_token') and u.get('gmail_address'))
    use_smtp=(u.get('gmail_verified') and u.get('gmail_address') and u.get('gmail_app_pwd'))
    if not use_oauth and not use_smtp:
        return jsonify({'ok':False,'err':'Gmail non configuré. Connectez-vous avec Google OU configurez le SMTP Gmail dans Configuration.'}),400
    body=corps
    if lettre: body+=f'\n\n{"─"*50}\n\nLETTRE DE MOTIVATION\n\n{lettre}'
    dest_f=dest or u['gmail_address']
    att_data=u.get('cv_data'); att_name=u.get('cv_filename')
    try:
        if mode=='envoyer':
            if use_oauth: _gmail_send_oauth(u,dest_f,sujet,body,att_data,att_name)
            else: _gmail_send_smtp(u['gmail_address'],u['gmail_app_pwd'],dest_f,sujet,body,att_data,att_name)
            statut='envoye'; msg=f'✅ Email envoyé à {dest_f} !'
        else:
            if use_oauth: _gmail_draft_oauth(u,dest_f,sujet,body,att_data,att_name)
            else: _gmail_draft_smtp(u['gmail_address'],u['gmail_app_pwd'],dest_f,sujet,body,att_data,att_name)
            statut='brouillon'; msg='✅ Sauvegardé dans vos brouillons Gmail !'
    except smtplib.SMTPAuthenticationError:
        return jsonify({'ok':False,'err':'Authentification Gmail échouée. Retestez la connexion dans Configuration.'}),400
    except Exception as e:
        return jsonify({'ok':False,'err':f'Erreur Gmail : {str(e)[:200]}'}),500
    conn=get_db()
    if cid: conn.execute('UPDATE agent_candidatures SET statut=?,destinataire=?,sent_at=? WHERE id=? AND user_id=?',(statut,dest_f,now_iso(),cid,u['id']))
    else: conn.execute('''INSERT INTO agent_candidatures(user_id,offer_title,offer_org,email_sujet,email_corps,lettre,destinataire,statut,methode,created_at,sent_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                       (u['id'],d.get('title',''),d.get('org',''),sujet,corps,lettre,dest_f,statut,'manuel',now_iso(),now_iso()))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'message':msg,'statut':statut})

# ── Offres ──────────────────────────────────────────────────────────────────────
@app.route('/api/agent/offres')
def agent_offres():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    sectors=[s.strip() for s in (u.get('sectors') or '').split(',') if s.strip()]
    conn=get_db()
    if not sectors and u.get('cv_text'):
        cv=u['cv_text'].lower()
        kmap={'Informatique & Tech':['python','javascript','développeur','web','data','informatique'],
              'Finance & Banque':['comptable','finance','banque','audit'],
              'Santé':['médecin','infirmier','santé','pharmacie'],
              'Génie Civil & BTP':['génie civil','btp','construction','architecte'],
              'Humanitaire & ONG':['ong','humanitaire','ngo','unicef'],
              'Administration & RH':['administrateur','rh','ressources humaines'],
              'Éducation':['enseignant','professeur','formateur'],
              'Télécoms':['télécom','réseau','orange','mtn']}
        sectors=[s for s,kws in kmap.items() if any(k in cv for k in kws)]
    if sectors:
        ph=','.join('?'*len(sectors))
        rows=conn.execute(f'SELECT * FROM offers WHERE is_active=1 AND sector IN ({ph}) ORDER BY scraped_at DESC LIMIT 40',sectors).fetchall()
    else:
        rows=conn.execute('SELECT * FROM offers WHERE is_active=1 ORDER BY scraped_at DESC LIMIT 30').fetchall()
    conn.close()
    return jsonify({'ok':True,'offers':[dict(r) for r in rows],'sectors':sectors,'matched':bool(sectors)})

# ── Historique ──────────────────────────────────────────────────────────────────
@app.route('/api/agent/historique')
def agent_historique():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    page=request.args.get('p',1,type=int); per=15
    conn=get_db()
    total=conn.execute('SELECT COUNT(*) FROM agent_candidatures WHERE user_id=?',(u['id'],)).fetchone()[0]
    rows=conn.execute('SELECT * FROM agent_candidatures WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?',(u['id'],per,(page-1)*per)).fetchall()
    conn.close()
    import math
    return jsonify({'ok':True,'items':[dict(r) for r in rows],'total':total,'pages':max(1,math.ceil(total/per))})

@app.route('/api/agent/historique/<int:cid>',methods=['DELETE'])
def agent_del_cand(cid):
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    conn=get_db(); conn.execute('DELETE FROM agent_candidatures WHERE id=? AND user_id=?',(cid,u['id']))
    conn.commit(); conn.close(); return jsonify({'ok':True})

@app.route('/api/agent/historique/<int:cid>')
def agent_get_cand(cid):
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    conn=get_db(); row=conn.execute('SELECT * FROM agent_candidatures WHERE id=? AND user_id=?',(cid,u['id'])).fetchone(); conn.close()
    return jsonify({'ok':True,'item':dict(row)}) if row else ('not found',404)

@app.route('/api/agent/export-candidatures')
def agent_export():
    u=_get_user()
    if not u: return jsonify({'ok':False,'err':'Non connecté'}),401
    try: import openpyxl; from openpyxl.styles import Font,PatternFill,Alignment,Border,Side; from openpyxl.utils import get_column_letter
    except: return jsonify({'error':'openpyxl manquant'}),500
    conn=get_db(); rows=conn.execute('SELECT * FROM agent_candidatures WHERE user_id=? ORDER BY created_at DESC',(u['id'],)).fetchall(); conn.close()
    wb=openpyxl.Workbook(); ws=wb.active; ws.title='Candidatures'
    thin=Border(left=Side(style='thin',color='DDDDDD'),right=Side(style='thin',color='DDDDDD'),top=Side(style='thin',color='DDDDDD'),bottom=Side(style='thin',color='DDDDDD'))
    hdrs=[('#',5),('Poste',38),('Organisation',26),('Statut',14),('Méthode',12),('Destinataire',28),('Date',14)]
    for i,(h,w) in enumerate(hdrs,1):
        c=ws.cell(row=1,column=i,value=h); c.font=Font(color='FFFFFF',bold=True,size=11)
        c.fill=PatternFill(start_color='1B5E20',end_color='1B5E20',fill_type='solid')
        c.alignment=Alignment(horizontal='center'); c.border=thin; ws.column_dimensions[get_column_letter(i)].width=w
    sc={'envoye':'E8F5E9','brouillon':'FFF8E1','genere':'E3F2FD'}
    for ri,r in enumerate(rows,2):
        f=PatternFill(start_color=sc.get(r['statut'],'FFFFFF'),end_color=sc.get(r['statut'],'FFFFFF'),fill_type='solid')
        for ci,v in enumerate([ri-1,r['offer_title'],r['offer_org'],r['statut'],r['methode'],r['destinataire'],(r['created_at'] or '')[:10]],1):
            c=ws.cell(row=ri,column=ci,value=v); c.fill=f; c.border=thin
            c.alignment=Alignment(horizontal='center' if ci==1 else 'left')
    ws.freeze_panes='A2'; out=io.BytesIO(); wb.save(out); out.seek(0)
    return send_file(out,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,download_name=f"candidatures_{now_fmt('%Y%m%d')}.xlsx")

# ── ADMIN ────────────────────────────────────────────────────────────────────────
@app.route('/api/admin/users')
def admin_users():
    conn=get_db()
    rows=conn.execute('''SELECT id,name,email,auth_method,gmail_address,gmail_verified,api_verified,
        sectors,created_at,last_login,(SELECT COUNT(*) FROM agent_candidatures WHERE user_id=agent_users.id) nb
        FROM agent_users ORDER BY created_at DESC''').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/admin/send-bulk',methods=['POST'])
def admin_send_bulk():
    d=request.get_json() or {}
    agmail=(d.get('agmail') or '').strip(); apwd=(d.get('apwd') or '').strip()
    if not agmail or not apwd: return jsonify({'ok':False,'err':'Gmail Admin requis'}),400
    ok,err=_test_smtp(agmail,apwd)
    if not ok: return jsonify({'ok':False,'err':err}),400
    target=d.get('target','all'); conn=get_db()
    if target=='all':
        users=conn.execute('SELECT name,email FROM agent_users').fetchall()
    elif target.startswith('sector:'):
        users=conn.execute('SELECT name,email FROM agent_users WHERE sectors LIKE ?',(f'%{target[7:]}%',)).fetchall()
    elif target.startswith('user:'):
        users=conn.execute('SELECT name,email FROM agent_users WHERE id=?',(target[5:],)).fetchall()
    else:
        users=conn.execute('SELECT name,email FROM agent_users').fetchall()
    ids=d.get('offer_ids',[]); sf=d.get('sector_filter','')
    if ids:
        ph=','.join('?'*len(ids)); offers=conn.execute(f'SELECT * FROM offers WHERE id IN ({ph}) AND is_active=1',ids).fetchall()
    elif sf:
        offers=conn.execute('SELECT * FROM offers WHERE is_active=1 AND sector LIKE ? ORDER BY scraped_at DESC LIMIT 15',(f'%{sf}%',)).fetchall()
    else:
        offers=conn.execute('SELECT * FROM offers WHERE is_active=1 ORDER BY scraped_at DESC LIMIT 10').fetchall()
    conn.close()
    if not offers: return jsonify({'ok':False,'err':'Aucune offre trouvée'}),400
    if not users:  return jsonify({'ok':False,'err':'Aucun destinataire trouvé'}),400
    bloc='\n\n'.join(f"📌 {o['title']}\n   🏢 {o['organization'] or 'N/A'}  ·  📍 {o['location'] or 'Cameroun'}\n   {('💰 '+o['salary']) if o['salary'] else ''}  {('⏰ '+o['deadline']) if o['deadline'] else ''}\n   {'🔗 '+o['url'] if o['url'] else ''}" for o in offers)
    sent=0; errs=[]
    for user in users:
        try:
            subj=f"[CamerJob Watch] {len(offers)} offre{'s' if len(offers)>1 else ''} pour vous"
            body=f"Bonjour {user['name']},\n\nVoici les offres sélectionnées pour votre profil :\n\n{bloc}\n\n─────────────────────────────────────\nPostulez via votre Agent IA : /agent\n\nCamerJob Watch"
            _gmail_send_smtp(agmail,apwd,user['email'],subj,body)
            sent+=1
        except Exception as e: errs.append(f"{user['email']}: {str(e)[:60]}")
    conn=get_db(); conn.execute('INSERT INTO admin_envois(sujet,nb_dest,statut,sent_at) VALUES(?,?,?,?)',(f'{len(offers)} offres',sent,'ok' if not errs else 'partial',now_iso())); conn.commit(); conn.close()
    return jsonify({'ok':True,'sent':sent,'total':len(users),'errors':errs[:3],'message':f'✅ {sent}/{len(users)} emails envoyés'})

@app.route('/api/admin/envois')
def admin_envois():
    conn=get_db(); rows=conn.execute('SELECT * FROM admin_envois ORDER BY sent_at DESC LIMIT 20').fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == '__main__':
    init_db()
    print('🚀 CamerJob Watch — http://0.0.0.0:5000')
    print('📡 Accessible sur le réseau local LAN via votre adresse IP:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)
