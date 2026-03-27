# 🇨🇲 CamerJob Watch — Plateforme de Veille Emploi & Appels d'Offres

## Installation rapide

```bash
# 1. Installer les dépendances
pip install flask flask-sqlalchemy openpyxl

# 2. Lancer l'application
python app.py

# 3. Accéder via navigateur
# Local     : http://localhost:5000
# Réseau LAN: http://[IP-DE-VOTRE-MACHINE]:5000
```

## Fonctionnalités
- ✅ Dashboard avec statistiques et graphiques
- ✅ Consultation des offres d'emploi et appels d'offres
- ✅ Scraping automatique des sources configurées
- ✅ Ajout manuel d'offres
- ✅ Gestion des sources (ajout, modification, suppression)
- ✅ Export Excel (toutes offres, AO, filtré)
- ✅ Favoris, recherche et filtres avancés
- ✅ Journal des activités de scraping
- ✅ Accessible en réseau local (LAN)

## Sources incluses par défaut
- Emploi Cameroun (emploi.cm)
- CamJob (camjob.net)
- LinkedIn Cameroun
- ReliefWeb Cameroun
- Optionfinance
- ARMP (marchés publics)
- Journal des Marchés Publics
- Banque Mondiale - Cameroun

## Ajouter une source
Allez dans "Sources" > "+ Ajouter une source" et renseignez l'URL.
