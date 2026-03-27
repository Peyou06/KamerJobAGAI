# 📦 Guide d'installation — Agent IA CamerJob Watch

## Fichiers fournis
- `agent_ia.py`           → Module Python principal (backend)
- `templates/agent.html`  → Page interface Agent IA
- `PATCH_app.py`          → 4 blocs à ajouter dans app.py

---

## Étape 1 — Placer les fichiers

```
ton_projet/
├── app.py                ← ton fichier existant
├── agent_ia.py           ← NOUVEAU (copier ici)
├── credentials.json      ← NOUVEAU (télécharger depuis Google Cloud)
└── templates/
    ├── base.html
    ├── index.html
    └── agent.html        ← NOUVEAU (copier ici)
```

---

## Étape 2 — Modifier app.py (4 petits changements)

### 2a. En haut du fichier, après les imports :
```python
from agent_ia import agent_bp, init_agent, init_agent_db
```

### 2b. Après  app = Flask(__name__)  :
```python
app.secret_key = os.environ.get('SECRET_KEY', 'camerajob_secret_2025')
app.register_blueprint(agent_bp)
init_agent(get_db)
```

### 2c. Dans init_db(), après conn.commit() (création tables) :
```python
init_agent_db(conn)
```

### 2d. Ajouter la route (avant if __name__=='__main__') :
```python
@app.route('/agent')
def agent_page():
    return render_template('agent.html')
```

---

## Étape 3 — Ajouter le lien dans la sidebar (base.html)

Cherche la section nav de base.html et ajoute :
```html
<div class="nav-section">AGENT IA</div>
<a href="/agent" class="nav-link {% if request.path=='/agent' %}active{% endif %}">
  <span class="icon">🤖</span> Agent IA
</a>
```

---

## Étape 4 — Installer les dépendances

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

*Note : La clé API Anthropic est appelée directement via urllib — pas besoin d'installer le SDK anthropic.*

---

## Étape 5 — Configurer Google Cloud (pour Gmail)

1. Va sur https://console.cloud.google.com
2. **Créer un projet** (ex: "CamerJob Watch")
3. **APIs et services** → **Bibliothèque** → Chercher "Gmail API" → Activer
4. **APIs et services** → **Identifiants** → **Créer des identifiants** → **ID client OAuth 2.0**
5. Type d'application : **Application de bureau**
6. Télécharger le fichier JSON → le renommer `credentials.json`
7. Le placer dans le dossier de ton app

> ⚠️ La première fois, Google peut demander une "vérification de l'application".
> Pour usage personnel/dev, ajoute ton email comme "testeur autorisé" dans la console.

---

## Étape 6 — Obtenir une clé API Anthropic

1. Va sur https://console.anthropic.com/account/keys
2. Crée une clé API (commence par `sk-ant-`)
3. Copie-la → dans l'interface Agent IA → "Configuration" → "Clé API Claude"

---

## Fonctionnalités disponibles

| Fonctionnalité                      | Prérequis         |
|-------------------------------------|-------------------|
| Créer un compte / Se connecter      | Rien              |
| Compléter son profil                | Compte créé       |
| Générer lettre de motivation        | Clé API Anthropic |
| Générer email de candidature        | Clé API Anthropic |
| Générer résumé CV                   | Clé API Anthropic |
| Connecter Gmail                     | credentials.json  |
| Envoyer candidatures automatiquement| Clé API + Gmail   |
| Historique des postulations         | Compte créé       |

---

## Dépannage courant

### "credentials.json introuvable"
→ Télécharger depuis Google Cloud Console et placer dans le dossier de l'app.

### "Clé API invalide ou expirée (401)"
→ Vérifier que la clé commence par `sk-ant-` et qu'elle est active sur console.anthropic.com

### "Limite de requêtes atteinte (429)"
→ Attendre 1 minute. Le plan gratuit Anthropic a des limites.

### "google-auth-oauthlib non installé"
→ `pip install google-auth-oauthlib google-api-python-client`

### Gmail ne redirige pas
→ Vérifier que l'URI de redirection dans Google Cloud est exactement :
   `http://localhost:5000/api/agent/gmail/callback`
