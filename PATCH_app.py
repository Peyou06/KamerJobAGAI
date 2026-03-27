"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   PATCH app.py — Intégration Agent IA                                      ║
║   Ajoute ces 4 blocs aux endroits indiqués dans ton app.py existant        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOC 1 — À ajouter en haut de app.py, après les imports existants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from agent_ia import agent_bp, init_agent, init_agent_db

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOC 2 — Après la ligne  app = Flask(__name__)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app.secret_key = os.environ.get('SECRET_KEY', 'camerajob_secret_2025_change_en_prod')
app.register_blueprint(agent_bp)
init_agent(get_db)          # donne l'accès DB au module Agent

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOC 3 — Dans la fonction init_db(), après conn.commit() de la création des tables
#           (ajoute ceci avant le bloc "if c.execute('SELECT COUNT(*)'...)")
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    init_agent_db(conn)     # crée les tables Agent IA

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BLOC 4 — Route de la page Agent IA (ajoute avant if __name__=='__main__')
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/agent')
def agent_page():
    return render_template('agent.html')
