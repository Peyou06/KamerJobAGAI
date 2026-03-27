"""
Moteur de scraping modulaire pour CamerJob Watch
Chaque source est scrapée de façon indépendante et robuste
"""
import requests
from bs4 import BeautifulSoup
import hashlib, time, random
from datetime import datetime
from urllib.parse import urljoin, urlparse
import re


HEADERS_LIST = [
    {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
    {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36'},
    {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36'},
]


def get_headers():
    h = random.choice(HEADERS_LIST).copy()
    h['Accept-Language'] = 'fr-FR,fr;q=0.9,en;q=0.8'
    h['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    return h


def make_hash(titre, organisation, url=''):
    contenu = f"{titre.strip().lower()}{organisation.strip().lower()}{url}"
    return hashlib.md5(contenu.encode('utf-8')).hexdigest()


def nettoyer_texte(texte):
    if not texte:
        return ''
    return re.sub(r'\s+', ' ', texte.strip())


class ScrapingEngine:
    def __init__(self, db, Offre, Source, LogActivite, log_fn):
        self.db = db
        self.Offre = Offre
        self.Source = Source
        self.LogActivite = LogActivite
        self.log = log_fn
        self.session = requests.Session()

    def fetch_page(self, url, timeout=15):
        """Récupère une page web avec gestion des erreurs"""
        try:
            time.sleep(random.uniform(1.5, 4.0))
            resp = self.session.get(url, headers=get_headers(), timeout=timeout,
                                    allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            return BeautifulSoup(resp.text, 'html.parser')
        except requests.exceptions.Timeout:
            raise Exception(f"Timeout lors de la connexion à {url}")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Impossible de se connecter à {url}")
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Erreur HTTP {e.response.status_code} pour {url}")
        except Exception as e:
            raise Exception(f"Erreur inattendue : {str(e)}")

    def sauvegarder_offre(self, data, source):
        """Sauvegarde une offre si elle n'existe pas déjà"""
        unique = make_hash(
            data.get('titre', ''),
            data.get('organisation', ''),
            data.get('url', '')
        )

        if self.Offre.query.filter_by(unique_hash=unique).first():
            return False  # Doublon

        offre = self.Offre(
            type_offre=data.get('type_offre', source.type_source if source.type_source != 'mixte' else 'emploi'),
            titre=data.get('titre', '')[:490],
            organisation=data.get('organisation', '')[:290],
            localisation=data.get('localisation', 'Cameroun')[:190],
            secteur=data.get('secteur', '')[:90],
            description=data.get('description', ''),
            type_contrat=data.get('type_contrat', '')[:90],
            salaire=data.get('salaire', '')[:190],
            date_limite=data.get('date_limite', '')[:90],
            date_publication=data.get('date_publication', datetime.utcnow().strftime('%d/%m/%Y'))[:90],
            url=data.get('url', '')[:2000],
            source=source.nom,
            source_url=source.url,
            unique_hash=unique
        )
        self.db.session.add(offre)
        return True

    def scraper_source(self, source):
        """Scrape une source donnée selon son URL et type"""
        self.log('scraping', f'Début du scraping : {source.nom}', source.id)
        source.statut = 'en_cours'
        self.db.session.commit()

        nb_nouvelles = 0
        try:
            # Dispatch vers le bon scraper selon le domaine
            domain = urlparse(source.url).netloc.lower()

            if 'emploi.cm' in domain:
                resultats = self._scraper_emploi_cm(source)
            elif 'armp.cm' in domain:
                resultats = self._scraper_armp(source)
            elif 'camjob' in domain:
                resultats = self._scraper_camjob(source)
            elif 'reliefweb' in domain:
                resultats = self._scraper_reliefweb(source)
            elif 'optionfinance' in domain:
                resultats = self._scraper_optionfinance(source)
            elif 'worldbank' in domain or 'banquemondiale' in domain:
                resultats = self._scraper_worldbank(source)
            else:
                # Scraper générique avec les sélecteurs configurés
                resultats = self._scraper_generique(source)

            for data in resultats:
                if self.sauvegarder_offre(data, source):
                    nb_nouvelles += 1

            self.db.session.commit()
            source.statut = 'actif'
            source.derniere_collecte = datetime.utcnow()
            source.nb_offres_today = nb_nouvelles
            source.nb_offres_total = (source.nb_offres_total or 0) + nb_nouvelles
            self.db.session.commit()

            self.log('scraping',
                     f'✅ {source.nom} : {nb_nouvelles} nouvelles offres collectées', source.id)

        except Exception as e:
            source.statut = 'erreur'
            self.db.session.commit()
            self.log('erreur', f'❌ Erreur sur {source.nom} : {str(e)}', source.id)

        return nb_nouvelles

    def scraper_toutes_sources(self):
        """Scrape toutes les sources actives"""
        sources = self.Source.query.filter_by(actif=True).all()
        total = 0
        self.log('scraping', f'🔄 Lancement scraping : {len(sources)} sources actives')

        for source in sources:
            try:
                nb = self.scraper_source(source)
                total += nb
                time.sleep(random.uniform(2, 5))
            except Exception as e:
                self.log('erreur', f'Erreur source {source.nom}: {str(e)}')

        self.log('scraping', f'🏁 Scraping terminé : {total} nouvelles offres au total')
        return total

    # ─────────────────────────────────────────────
    #  SCRAPERS SPÉCIFIQUES
    # ─────────────────────────────────────────────

    def _scraper_emploi_cm(self, source):
        """Scraper pour emploi.cm"""
        resultats = []
        try:
            soup = self.fetch_page(source.url)
            # Sélecteurs multiples pour robustesse
            cards = (soup.select('div.job-item, article.offer, div.offer-card, '
                                 'div.liste-offre li, .jobs-list .item'))
            
            if not cards:
                # Fallback : chercher tous les liens qui ressemblent à des offres
                cards = soup.select('a[href*="offre"], a[href*="emploi"], a[href*="job"]')

            for card in cards[:50]:
                titre_el = card.select_one('h2, h3, h4, .title, .job-title, strong')
                orga_el  = card.select_one('.company, .employer, .organization, .entreprise')
                lien_el  = card if card.name == 'a' else card.select_one('a')
                local_el = card.select_one('.location, .localisation, .ville, .city')
                date_el  = card.select_one('.date, .posted, time, .date-publication')

                titre = nettoyer_texte(titre_el.get_text() if titre_el else '')
                if not titre or len(titre) < 5:
                    continue

                lien = ''
                if lien_el:
                    lien = urljoin(source.url, lien_el.get('href', ''))

                resultats.append({
                    'titre': titre,
                    'organisation': nettoyer_texte(orga_el.get_text() if orga_el else 'N/A'),
                    'localisation': nettoyer_texte(local_el.get_text() if local_el else 'Cameroun'),
                    'date_publication': nettoyer_texte(date_el.get_text() if date_el else ''),
                    'url': lien,
                    'type_offre': 'emploi',
                    'secteur': 'Emploi',
                })
        except Exception as e:
            self.log('erreur', f'Erreur emploi.cm: {str(e)}', source.id)

        return resultats

    def _scraper_armp(self, source):
        """Scraper pour ARMP (Marchés Publics Cameroun)"""
        resultats = []
        try:
            soup = self.fetch_page(source.url)
            rows = soup.select('table tr, .marche-item, .avis-item, article')

            for row in rows[1:50]:  # Skip header
                cells = row.select('td')
                if len(cells) >= 2:
                    titre_el = cells[1] if len(cells) > 1 else cells[0]
                    ref_el   = cells[0]
                    date_el  = cells[-1] if len(cells) > 3 else None
                    lien_el  = row.select_one('a')

                    titre = nettoyer_texte(titre_el.get_text())
                    if not titre or len(titre) < 5:
                        continue

                    resultats.append({
                        'titre': titre,
                        'organisation': nettoyer_texte(ref_el.get_text()) or 'ARMP Cameroun',
                        'localisation': 'Cameroun',
                        'date_limite': nettoyer_texte(date_el.get_text() if date_el else ''),
                        'url': urljoin(source.url, lien_el.get('href', '')) if lien_el else source.url,
                        'type_offre': 'appel_offre',
                        'secteur': 'Marchés Publics',
                    })
                else:
                    # Format non-tabulaire
                    titre_el = row.select_one('h2, h3, .title, strong, a')
                    if titre_el:
                        titre = nettoyer_texte(titre_el.get_text())
                        lien_el = row.select_one('a')
                        if titre and len(titre) > 5:
                            resultats.append({
                                'titre': titre,
                                'organisation': 'ARMP Cameroun',
                                'localisation': 'Cameroun',
                                'url': urljoin(source.url, lien_el.get('href', '')) if lien_el else source.url,
                                'type_offre': 'appel_offre',
                                'secteur': 'Marchés Publics',
                            })
        except Exception as e:
            self.log('erreur', f'Erreur ARMP: {str(e)}', source.id)

        return resultats

    def _scraper_reliefweb(self, source):
        """Scraper pour ReliefWeb (ONG/Humanitaire)"""
        resultats = []
        try:
            # ReliefWeb a une API publique
            api_url = 'https://api.reliefweb.int/v1/jobs?appname=camerajob&profile=list&preset=latest&filter[field]=country.name&filter[value]=Cameroon&limit=50'
            resp = requests.get(api_url, headers=get_headers(), timeout=15)
            data = resp.json()

            for item in data.get('data', []):
                fields = item.get('fields', {})
                resultats.append({
                    'titre': fields.get('title', 'Offre ONG'),
                    'organisation': fields.get('source', [{}])[0].get('name', 'ONG') if fields.get('source') else 'ONG',
                    'localisation': 'Cameroun',
                    'date_limite': fields.get('date', {}).get('closing', ''),
                    'date_publication': fields.get('date', {}).get('created', ''),
                    'url': fields.get('url', source.url),
                    'type_offre': 'emploi',
                    'secteur': 'ONG / Humanitaire',
                    'type_contrat': fields.get('type', [{}])[0].get('name', '') if fields.get('type') else '',
                })
        except Exception as e:
            # Fallback HTML
            try:
                resultats = self._scraper_generique(source)
            except:
                self.log('erreur', f'Erreur ReliefWeb: {str(e)}', source.id)

        return resultats

    def _scraper_optionfinance(self, source):
        """Scraper pour Optionfinance (Finance/Banque)"""
        resultats = []
        try:
            soup = self.fetch_page(source.url)
            articles = soup.select('article, .post, .emploi-item, .job-listing')
            for article in articles[:30]:
                titre_el = article.select_one('h1, h2, h3, .entry-title, a')
                lien_el  = article.select_one('a')
                date_el  = article.select_one('time, .date, .published')

                titre = nettoyer_texte(titre_el.get_text() if titre_el else '')
                if not titre or len(titre) < 5:
                    continue

                resultats.append({
                    'titre': titre,
                    'organisation': 'Optionfinance',
                    'localisation': 'Cameroun',
                    'date_publication': nettoyer_texte(date_el.get_text() if date_el else ''),
                    'url': urljoin(source.url, lien_el.get('href', '')) if lien_el else source.url,
                    'type_offre': 'emploi',
                    'secteur': 'Finance / Banque',
                })
        except Exception as e:
            self.log('erreur', f'Erreur Optionfinance: {str(e)}', source.id)

        return resultats

    def _scraper_worldbank(self, source):
        """Scraper pour Banque Mondiale (Appels d'offres)"""
        resultats = []
        try:
            api_url = 'https://search.worldbank.org/api/v2/projects?format=json&countrycode_exact=CM&fl=id,project_name,countryname,status,totalcommamt,closingdate&rows=30'
            resp = requests.get(api_url, headers=get_headers(), timeout=15)
            data = resp.json()

            for projet in data.get('projects', {}).values():
                if isinstance(projet, dict) and projet.get('project_name'):
                    resultats.append({
                        'titre': f"Marché BM: {projet.get('project_name', '')}",
                        'organisation': 'Banque Mondiale',
                        'localisation': 'Cameroun',
                        'date_limite': projet.get('closingdate', ''),
                        'url': f"https://projects.worldbank.org/en/projects-operations/project-detail/{projet.get('id', '')}",
                        'type_offre': 'appel_offre',
                        'secteur': 'Développement International',
                        'salaire': f"{projet.get('totalcommamt', '')} USD" if projet.get('totalcommamt') else '',
                    })
        except Exception as e:
            self.log('erreur', f'Erreur Banque Mondiale: {str(e)}', source.id)

        return resultats

    def _scraper_camjob(self, source):
        """Scraper pour CamJob"""
        resultats = []
        try:
            soup = self.fetch_page(source.url)
            items = soup.select('.job, .offer, article, li.job-item, div.job-card')
            
            if not items:
                items = soup.select('a[href*="emploi"], a[href*="offre"], a[href*="job"]')

            for item in items[:40]:
                titre_el = item.select_one('h2, h3, h4, .title, strong') or (item if item.name == 'a' else None)
                lien_el  = item.select_one('a') or (item if item.name == 'a' else None)
                orga_el  = item.select_one('.company, .employer, .org')
                local_el = item.select_one('.location, .city, .ville')

                titre = nettoyer_texte(titre_el.get_text() if titre_el else '')
                if not titre or len(titre) < 5:
                    continue

                resultats.append({
                    'titre': titre,
                    'organisation': nettoyer_texte(orga_el.get_text() if orga_el else 'N/A'),
                    'localisation': nettoyer_texte(local_el.get_text() if local_el else 'Cameroun'),
                    'url': urljoin(source.url, lien_el.get('href', '')) if lien_el else source.url,
                    'type_offre': 'emploi',
                    'secteur': 'Emploi',
                })
        except Exception as e:
            self.log('erreur', f'Erreur CamJob: {str(e)}', source.id)

        return resultats

    def _scraper_generique(self, source):
        """Scraper générique basé sur les sélecteurs configurés pour la source"""
        resultats = []
        try:
            soup = self.fetch_page(source.url)

            # Utilise les sélecteurs configurés ou des sélecteurs par défaut
            sel_titre = source.selecteur_titre or 'h2, h3, article h4, .job-title, .title'
            sel_orga  = source.selecteur_orga  or '.company, .employer, .organization'
            sel_lien  = source.selecteur_lien  or 'a'

            titres = soup.select(sel_titre)

            for el in titres[:50]:
                titre = nettoyer_texte(el.get_text())
                if not titre or len(titre) < 5 or len(titre) > 400:
                    continue

                # Cherche le conteneur parent pour les autres infos
                parent = el.parent or el

                orga_el  = parent.select_one(sel_orga)
                lien_el  = el.find('a') or parent.select_one(sel_lien)
                local_el = parent.select_one('.location, .localisation, .ville, .city')
                date_el  = parent.select_one('.date, time, .posted, .published')

                lien = ''
                if lien_el:
                    href = lien_el.get('href', '')
                    lien = urljoin(source.url, href) if href else ''

                resultats.append({
                    'titre': titre,
                    'organisation': nettoyer_texte(orga_el.get_text() if orga_el else source.nom),
                    'localisation': nettoyer_texte(local_el.get_text() if local_el else 'Cameroun'),
                    'date_publication': nettoyer_texte(date_el.get_text() if date_el else ''),
                    'url': lien,
                    'type_offre': 'emploi' if source.type_source == 'emploi' else 'appel_offre',
                    'secteur': '',
                })
        except Exception as e:
            self.log('erreur', f'Erreur scraper générique ({source.nom}): {str(e)}', source.id)

        return resultats
