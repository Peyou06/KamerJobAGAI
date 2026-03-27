#!/bin/bash
echo "🇨🇲 Démarrage de CamerJob Watch..."
echo ""

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 non trouvé. Installez Python 3.8+"
    exit 1
fi

# Installer Flask si nécessaire
python3 -c "import flask" 2>/dev/null || pip3 install flask

# Optionnel: openpyxl pour l'export Excel
python3 -c "import openpyxl" 2>/dev/null || pip3 install openpyxl

# Trouver l'IP locale
LOCAL_IP=$(python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "localhost")

echo "🚀 Application démarrée!"
echo "   ➜  Local     : http://localhost:5000"
echo "   ➜  Réseau LAN: http://$LOCAL_IP:5000"
echo ""
echo "Partagez l'adresse LAN avec votre équipe."
echo "Ctrl+C pour arrêter."
echo ""

python3 app.py
