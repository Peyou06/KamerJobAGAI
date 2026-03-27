#!/bin/bash
# =============================================================
# CamerJob Watch — Script de démarrage
# =============================================================

echo "🇨🇲  CamerJob Watch — Démarrage"
echo "=================================="

# Créer l'environnement virtuel si nécessaire
if [ ! -d "venv" ]; then
  echo "📦 Création de l'environnement virtuel..."
  python3 -m venv venv
fi

# Activer l'environnement
source venv/bin/activate

# Installer les dépendances
echo "📦 Installation des dépendances..."
pip install -r requirements.txt -q

# Créer les dossiers nécessaires
mkdir -p instance exports

# Lancer l'application
echo ""
echo "✅ Démarrage sur http://0.0.0.0:5000"
echo "   Accessible en LAN sur http://$(hostname -I | awk '{print $1}'):5000"
echo ""
python app.py
