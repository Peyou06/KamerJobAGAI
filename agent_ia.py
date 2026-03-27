"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        CamerJob Watch — Module AGENT IA  (agent_ia.py)  v2.0               ║
║                                                                              ║
║  FONCTIONS INDÉPENDANTES :                                                   ║
║  1. Compte Agent  — création / connexion / profil                            ║
║  2. Clé API Claude — test réel avec diagnostic précis                        ║
║  3. Gmail OAuth2  — connexion sécurisée, token refresh auto                 ║
║  4. Générateur    — lettre / email / CV  (SANS envoyer)                      ║
║  5. Robot postulation — génère + envoie (INDÉPENDANT du générateur)          ║
║  6. Admin mailer  — envoie des offres ciblées aux utilisateurs               ║
║                                                                              ║
║  INTÉGRATION dans app.py :                                                   ║
║    from agent_ia import agent_bp, init_agent, init_agent_db                  ║
║    app.secret_key = os.environ.get('SECRET_KEY','camerajob_2025')            ║
║    app.register_blueprint(agent_bp)                                          ║
║    init_agent(get_db)       # après  app = Flask(...)                        ║
║    # Dans init_db() ajouter :  init_agent_db(conn)                          ║
║    # Route page : @app.route('/agent') → render_template('agent.html')      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os, json, hashlib, re, base64
from datetime import datetime, timezone
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Blueprint, request, jsonify, session

agent_bp = Blueprint('agent', __name__)

# ── Config Admin ───────────────────────────────────────────────────────────────
ADMIN_EMAIL    = os.environ.get('ADMIN_EMAIL',    'admin@camerajobwatch.cm')
ADMIN_NAME     = os.environ.get('ADMIN_NAME',     'CamerJob Watch')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin2025!')

# ── DB injecté depuis app.py ───────────────────────────────────────────────────
_get_db = None
def init_agent(fn): global _get_db; _get_db = fn
def _db():
    if _get_db is None: raise RuntimeError("init_agent(get_db) non appelé")
    return _get_db()
def _now(): return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 0.  BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════════════
def init_agent_db(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS agent_accounts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        email           TEXT NOT NULL UNIQUE,
        password_h      TEXT NOT NULL,
        phone           TEXT DEFAULT '',
        profession      TEXT DEFAULT '',
        location        TEXT DEFAULT 'Cameroun',
        skills          TEXT DEFAULT '',
        experience      TEXT DEFAULT '',
        education       TEXT DEFAULT '',
        languages       TEXT DEFAULT '',
        linkedin        TEXT DEFAULT '',
        bio             TEXT DEFAULT '',
        api_key         TEXT DEFAULT '',
        api_valid       INTEGER DEFAULT 0,
        api_tested_at   TEXT DEFAULT '',
        gmail_connected INTEGER DEFAULT 0,
        gmail_email     TEXT DEFAULT '',
        sectors_pref    TEXT DEFAULT '',
        locations_pref  TEXT DEFAULT '',
        notif_email     INTEGER DEFAULT 1,
        created_at      TEXT,
        last_login      TEXT,
        is_active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS agent_gmail_tokens (
        account_id INTEGER PRIMARY KEY,
        token_json TEXT NOT NULL,
        gmail_email TEXT DEFAULT '',
        updated_at  TEXT
    );
    CREATE TABLE IF NOT EXISTS agent_documents (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL,
        doc_type     TEXT NOT NULL,
        title        TEXT DEFAULT '',
        content      TEXT NOT NULL,
        offer_title  TEXT DEFAULT '',
        organization TEXT DEFAULT '',
        created_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS agent_applications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id      INTEGER NOT NULL,
        offer_title     TEXT DEFAULT '',
        organization    TEXT DEFAULT '',
        offer_url       TEXT DEFAULT '',
        recruiter_email TEXT DEFAULT '',
        cover_letter    TEXT DEFAULT '',
        email_subject   TEXT DEFAULT '',
        email_body      TEXT DEFAULT '',
        email_sent      INTEGER DEFAULT 0,
        sent_at         TEXT DEFAULT '',
        status          TEXT DEFAULT 'brouillon',
        error_msg       TEXT DEFAULT '',
        created_at      TEXT
    );
    CREATE TABLE IF NOT EXISTS admin_mailings (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        subject          TEXT NOT NULL,
        body_html        TEXT NOT NULL,
        offer_ids        TEXT DEFAULT '',
        target_sector    TEXT DEFAULT '',
        target_location  TEXT DEFAULT '',
        recipients_count INTEGER DEFAULT 0,
        sent_at          TEXT,
        status           TEXT DEFAULT 'sent'
    );
    ''')
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# 1.  COMPTE AGENT
# ══════════════════════════════════════════════════════════════════════════════
def _hash(pw): return hashlib.sha256(f"cjw_2025_{pw}".encode()).hexdigest()

def _clean(row):
    d = dict(row)
    for f in ('password_h','api_key'): d.pop(f, None)
    return d

@agent_bp.route('/api/agent/register', methods=['POST'])
def agent_register():
    d     = request.get_json() or {}
    name  = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip().lower()
    pw    = d.get('password','')
    if not name:  return jsonify({'error':'Le nom est requis'}), 400
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'error':'Email invalide'}), 400
    if len(pw) < 6:
        return jsonify({'error':'Mot de passe trop court (min 6 caractères)'}), 400
    conn = _db()
    if conn.execute('SELECT id FROM agent_accounts WHERE email=?',(email,)).fetchone():
        conn.close(); return jsonify({'error':'Email déjà enregistré'}), 400
    conn.execute('''INSERT INTO agent_accounts
        (name,email,password_h,phone,profession,location,skills,experience,
         education,languages,bio,sectors_pref,locations_pref,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (name,email,_hash(pw),d.get('phone',''),d.get('profession',''),
         d.get('location','Cameroun'),d.get('skills',''),d.get('experience',''),
         d.get('education',''),d.get('languages',''),d.get('bio',''),
         d.get('sectors_pref',''),d.get('locations_pref',''),_now()))
    aid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit()
    row = conn.execute('SELECT * FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    session['agent_id'] = aid
    return jsonify({'success':True,'account':_clean(row)})

@agent_bp.route('/api/agent/login', methods=['POST'])
def agent_login():
    d     = request.get_json() or {}
    email = (d.get('email') or '').strip().lower()
    pw    = d.get('password','')
    if not email or not pw: return jsonify({'error':'Email et mot de passe requis'}), 400
    conn = _db()
    row  = conn.execute('SELECT * FROM agent_accounts WHERE email=?',(email,)).fetchone()
    if not row or row['password_h'] != _hash(pw):
        conn.close(); return jsonify({'error':'Email ou mot de passe incorrect'}), 401
    conn.execute('UPDATE agent_accounts SET last_login=? WHERE id=?',(_now(),row['id']))
    conn.commit()
    session['agent_id'] = row['id']
    acc = _clean(row); conn.close()
    return jsonify({'success':True,'account':acc})

@agent_bp.route('/api/agent/logout', methods=['POST'])
def agent_logout():
    session.pop('agent_id',None); return jsonify({'success':True})

@agent_bp.route('/api/agent/me')
def agent_me():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    row  = conn.execute('SELECT * FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    return jsonify(_clean(row)) if row else (jsonify({'error':'Introuvable'}), 404)

@agent_bp.route('/api/agent/update', methods=['PUT'])
def agent_update():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d = request.get_json() or {}
    conn = _db()
    conn.execute('''UPDATE agent_accounts
        SET name=?,phone=?,profession=?,location=?,skills=?,experience=?,
            education=?,languages=?,bio=?,linkedin=?,sectors_pref=?,locations_pref=?,notif_email=?
        WHERE id=?''',
        (d.get('name',''),d.get('phone',''),d.get('profession',''),
         d.get('location','Cameroun'),d.get('skills',''),d.get('experience',''),
         d.get('education',''),d.get('languages',''),d.get('bio',''),
         d.get('linkedin',''),d.get('sectors_pref',''),d.get('locations_pref',''),
         1 if d.get('notif_email',True) else 0, aid))
    conn.commit()
    row = conn.execute('SELECT * FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    return jsonify({'success':True,'account':_clean(row)})


# ══════════════════════════════════════════════════════════════════════════════
# 2.  CLÉ API ANTHROPIC
# ══════════════════════════════════════════════════════════════════════════════
def _call_claude(api_key, messages, max_tokens=1500):
    """Appel direct à l'API Anthropic. Lève ValueError avec message précis."""
    import urllib.request as ur, urllib.error as ue
    payload = json.dumps({
        "model":"claude-haiku-4-5-20251001",
        "max_tokens":max_tokens,
        "messages":messages
    }).encode('utf-8')
    req = ur.Request('https://api.anthropic.com/v1/messages', data=payload,
        headers={'Content-Type':'application/json','x-api-key':api_key,
                 'anthropic-version':'2023-06-01'}, method='POST')
    try:
        with ur.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
            if data.get('content'):
                return ''.join(b.get('text','') for b in data['content'] if b.get('type')=='text')
            raise ValueError(f"Réponse inattendue : {str(data)[:150]}")
    except ue.HTTPError as e:
        code = e.code
        body = e.read().decode('utf-8','replace')
        if code==401: raise ValueError(
            "❌ Clé API invalide ou expirée (401).\n"
            "→ Vérifiez sur https://console.anthropic.com/account/keys\n"
            "→ La clé doit commencer par  sk-ant-")
        if code==403: raise ValueError(
            "❌ Accès refusé (403).\n"
            "→ Vérifiez votre plan Anthropic sur https://console.anthropic.com")
        if code==429: raise ValueError(
            "❌ Limite de requêtes atteinte (429).\n"
            "→ Attendez 1 minute et réessayez.")
        if code==500: raise ValueError("❌ Erreur serveur Anthropic (500). Réessayez plus tard.")
        raise ValueError(f"❌ HTTP {code} : {body[:150]}")
    except ue.URLError as e:
        raise ValueError(f"❌ Connexion impossible.\n→ Vérifiez votre connexion internet.\n→ {str(e.reason)[:80]}")
    except Exception as e:
        raise ValueError(f"❌ Erreur : {str(e)[:150]}")

def _get_api_key(aid):
    conn = _db()
    row  = conn.execute('SELECT api_key,api_valid FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    if not row or not (row['api_key'] or '').strip():
        raise ValueError('❌ Aucune clé API Anthropic.\n→ Allez dans Configuration → Clé API.')
    if not row['api_valid']:
        raise ValueError('❌ Clé API non validée.\n→ Configuration → Clé API → "Tester la clé".')
    return row['api_key']

def _get_profile(aid):
    conn = _db(); row = conn.execute('SELECT * FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close(); return dict(row) if row else {}

def _profile_ctx(p):
    return (f"Nom         : {p.get('name','')}\n"
            f"Profession  : {p.get('profession','')}\n"
            f"Ville       : {p.get('location','')}\n"
            f"Compétences : {p.get('skills','')}\n"
            f"Expériences : {p.get('experience','')}\n"
            f"Formation   : {p.get('education','')}\n"
            f"Langues     : {p.get('languages','')}\n"
            f"Bio         : {p.get('bio','')}")

@agent_bp.route('/api/agent/api-key', methods=['POST'])
def agent_save_api_key():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d   = request.get_json() or {}
    key = (d.get('api_key') or '').strip()
    if not key: return jsonify({'error':'Clé API vide'}), 400
    if not key.startswith('sk-ant-'):
        return jsonify({'error':
            '❌ Format invalide.\nLa clé doit commencer par : sk-ant-\n'
            'Obtenez la sur https://console.anthropic.com/account/keys'}), 400
    try:
        _call_claude(key,[{"role":"user","content":"OK"}],max_tokens=5)
        valid=1; msg='✅ Clé API valide et opérationnelle !'
    except ValueError as e:
        valid=0; msg=str(e)
    conn=_db()
    conn.execute('UPDATE agent_accounts SET api_key=?,api_valid=?,api_tested_at=? WHERE id=?',
                 (key,valid,_now(),aid))
    conn.commit(); conn.close()
    if valid: return jsonify({'success':True,'message':msg})
    return jsonify({'success':False,'error':msg}), 400

@agent_bp.route('/api/agent/api-key/test', methods=['POST'])
def agent_test_api_key():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    row  = conn.execute('SELECT api_key FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    if not row or not row['api_key']:
        return jsonify({'valid':False,'message':'Aucune clé enregistrée'})
    try:
        _call_claude(row['api_key'],[{"role":"user","content":"Réponds juste : OK"}],max_tokens=10)
        conn2=_db(); conn2.execute('UPDATE agent_accounts SET api_valid=1,api_tested_at=? WHERE id=?',(_now(),aid))
        conn2.commit(); conn2.close()
        return jsonify({'valid':True,'message':'✅ Claude répond correctement !'})
    except ValueError as e:
        conn2=_db(); conn2.execute('UPDATE agent_accounts SET api_valid=0 WHERE id=?',(aid,))
        conn2.commit(); conn2.close()
        return jsonify({'valid':False,'message':str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# 3.  GMAIL OAUTH2
# ══════════════════════════════════════════════════════════════════════════════
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

def _creds_path():
    for p in [os.path.join(os.path.dirname(os.path.abspath(__file__)),'credentials.json'),
              os.path.join(os.getcwd(),'credentials.json'),
              os.path.expanduser('~/credentials.json')]:
        if os.path.exists(p): return p
    return None

def _redirect_uri():
    return os.environ.get('APP_HOST','http://localhost:5000') + '/api/agent/gmail/callback'

@agent_bp.route('/api/agent/gmail/auth-url')
def gmail_auth_url():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    cp = _creds_path()
    if not cp:
        return jsonify({'error':
            '❌ credentials.json introuvable.\n\n'
            'Pour l\'obtenir :\n'
            '1. https://console.cloud.google.com\n'
            '2. Créez un projet → Activez "Gmail API"\n'
            '3. Identifiants → OAuth 2.0 → Application de bureau\n'
            '4. Téléchargez le JSON → renommez-le credentials.json\n'
            '5. Placez-le dans le dossier de l\'app\n'
            '6. Ajoutez votre email comme testeur autorisé dans la console Google'}), 400
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(cp, scopes=GMAIL_SCOPES, redirect_uri=_redirect_uri())
        auth_url, state = flow.authorization_url(access_type='offline', prompt='consent',
                                                  include_granted_scopes='true', state=str(aid))
        session['gmail_state'] = state
        session['gmail_aid']   = aid
        return jsonify({'auth_url':auth_url})
    except ImportError:
        return jsonify({'error':'❌ pip install google-auth-oauthlib google-api-python-client'}), 500
    except Exception as e:
        return jsonify({'error':f'❌ {str(e)[:250]}'}), 500

@agent_bp.route('/api/agent/gmail/callback')
def gmail_callback():
    code  = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state','')
    if error: return _html_page('error',f'Autorisation refusée : {error}','Réessayez.')
    if not code: return _html_page('error','Code manquant','Réessayez.')
    aid = session.get('gmail_aid')
    if not aid:
        try: aid = int(state)
        except: pass
    if not aid: return _html_page('error','Session expirée','Reconnectez-vous.')
    cp = _creds_path()
    if not cp: return _html_page('error','credentials.json introuvable','')
    try:
        from google_auth_oauthlib.flow import Flow
        import googleapiclient.discovery
        flow = Flow.from_client_secrets_file(cp, scopes=GMAIL_SCOPES, redirect_uri=_redirect_uri())
        flow.fetch_token(code=code)
        creds = flow.credentials
        svc   = googleapiclient.discovery.build('gmail','v1',credentials=creds)
        gmail_email = svc.users().getProfile(userId='me').execute().get('emailAddress','')
        td = {'token':creds.token,'refresh_token':creds.refresh_token,
              'token_uri':creds.token_uri,'client_id':creds.client_id,
              'client_secret':creds.client_secret,'scopes':list(creds.scopes or GMAIL_SCOPES),
              'expiry':creds.expiry.isoformat() if creds.expiry else ''}
        conn = _db()
        conn.execute('''INSERT INTO agent_gmail_tokens(account_id,token_json,gmail_email,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(account_id) DO UPDATE
            SET token_json=excluded.token_json,gmail_email=excluded.gmail_email,updated_at=excluded.updated_at''',
            (aid,json.dumps(td),gmail_email,_now()))
        conn.execute('UPDATE agent_accounts SET gmail_connected=1,gmail_email=? WHERE id=?',(gmail_email,aid))
        conn.commit(); conn.close()
        return _html_page('success','✅ Gmail connecté !',
                          f'Compte : <strong>{gmail_email}</strong>',gmail_email)
    except Exception as e:
        err = str(e)
        if 'redirect_uri_mismatch' in err.lower():
            ru = _redirect_uri()
            return _html_page('error','URI de redirection incorrecte',
                f'Dans Google Cloud Console, ajoutez exactement :<br>'
                f'<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px">{ru}</code><br>'
                f'dans les "URI de redirection autorisées" de votre client OAuth.')
        return _html_page('error',f'Erreur OAuth',err[:250])

def _html_page(status, title, detail, gmail_email=''):
    color  = '#00A550' if status=='success' else '#CE1126'
    icon   = '✅' if status=='success' else '❌'
    script = (f'<script>if(window.opener)window.opener.postMessage({{type:"gmail_ok",email:"{gmail_email}"}},"*");'
              f'setTimeout(()=>window.close(),2500);</script>') if status=='success' else ''
    return (f'<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">'
            f'<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;'
            f'justify-content:center;min-height:100vh;background:#f5f5f5;margin:0}}'
            f'.box{{background:#fff;border-radius:12px;padding:40px;text-align:center;'
            f'max-width:500px;box-shadow:0 4px 24px rgba(0,0,0,.1)}}'
            f'h2{{color:{color}}}p{{color:#555;line-height:1.6}}code{{font-family:monospace}}'
            f'</style></head><body><div class="box">'
            f'<div style="font-size:48px;margin-bottom:12px">{icon}</div>'
            f'<h2>{title}</h2><p>{detail}</p>'
            f'{"<p style=color:#888;font-size:12px>Fermeture dans 2s…</p>" if status=="success" else ""}'
            f'{script}</div></body></html>')

@agent_bp.route('/api/agent/gmail/status')
def gmail_status():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    row  = conn.execute('SELECT gmail_connected,gmail_email FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    return jsonify({'connected':bool(row['gmail_connected']) if row else False,
                    'email':(row['gmail_email'] or '') if row else ''})

@agent_bp.route('/api/agent/gmail/disconnect', methods=['POST'])
def gmail_disconnect():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    conn.execute('DELETE FROM agent_gmail_tokens WHERE account_id=?',(aid,))
    conn.execute('UPDATE agent_accounts SET gmail_connected=0,gmail_email="" WHERE id=?',(aid,))
    conn.commit(); conn.close()
    return jsonify({'success':True})

def _gmail_service(account_id):
    """Retourne un service Gmail prêt à l'emploi, avec refresh automatique."""
    conn = _db()
    row  = conn.execute('SELECT token_json FROM agent_gmail_tokens WHERE account_id=?',(account_id,)).fetchone()
    conn.close()
    if not row: raise ValueError('❌ Gmail non connecté.\n→ Connectez votre Gmail dans Configuration.')
    try:
        from google.oauth2.credentials          import Credentials
        from google.auth.transport.requests     import Request as GReq
        import googleapiclient.discovery
        td    = json.loads(row['token_json'])
        creds = Credentials(token=td.get('token'), refresh_token=td.get('refresh_token'),
                            token_uri=td.get('token_uri','https://oauth2.googleapis.com/token'),
                            client_id=td.get('client_id'), client_secret=td.get('client_secret'),
                            scopes=td.get('scopes', GMAIL_SCOPES))
        if not creds.valid:
            if creds.refresh_token:
                creds.refresh(GReq())
                td['token'] = creds.token
                conn2 = _db()
                conn2.execute('UPDATE agent_gmail_tokens SET token_json=?,updated_at=? WHERE account_id=?',
                              (json.dumps(td),_now(),account_id))
                conn2.commit(); conn2.close()
            else:
                raise ValueError('❌ Token Gmail expiré.\n→ Reconnectez votre Gmail dans Configuration.')
        return googleapiclient.discovery.build('gmail','v1',credentials=creds)
    except ImportError:
        raise ValueError('❌ pip install google-auth google-auth-httplib2 google-api-python-client')

def _send_gmail(account_id, to_email, subject, body_text, body_html=None):
    svc  = _gmail_service(account_id)
    conn = _db()
    row  = conn.execute('SELECT gmail_email FROM agent_accounts WHERE id=?',(account_id,)).fetchone()
    conn.close()
    from_addr = row['gmail_email'] if row else ''
    msg = MIMEMultipart('alternative')
    msg['to']='to_email' ; msg['to'] = to_email
    msg['from']    = from_addr
    msg['subject'] = subject
    msg.attach(MIMEText(body_text,'plain','utf-8'))
    if body_html: msg.attach(MIMEText(body_html,'html','utf-8'))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc.users().messages().send(userId='me', body={'raw':raw}).execute()

@agent_bp.route('/api/agent/gmail/test-send', methods=['POST'])
def gmail_test_send():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    row  = conn.execute('SELECT name,gmail_email,gmail_connected FROM agent_accounts WHERE id=?',(aid,)).fetchone()
    conn.close()
    if not row or not row['gmail_connected']:
        return jsonify({'error':'❌ Gmail non connecté'}), 400
    try:
        _send_gmail(aid, row['gmail_email'], '✅ Test Gmail — CamerJob Watch',
            f"Bonjour {row['name']},\n\nVotre connexion Gmail fonctionne parfaitement !\n\n— CamerJob Watch")
        return jsonify({'success':True,'message':f'✅ Email de test envoyé à {row["gmail_email"]}'})
    except ValueError as e: return jsonify({'error':str(e)}), 400
    except Exception as e:  return jsonify({'error':f'❌ {str(e)[:200]}'}), 500


# ══════════════════════════════════════════════════════════════════════════════
# 4.  GÉNÉRATEUR DE DOCUMENTS  (INDÉPENDANT — ne poste pas)
# ══════════════════════════════════════════════════════════════════════════════
def _save_doc(aid, doc_type, title, content, offer_title='', organization=''):
    conn = _db()
    conn.execute('INSERT INTO agent_documents(account_id,doc_type,title,content,offer_title,organization,created_at) VALUES(?,?,?,?,?,?,?)',
                 (aid,doc_type,title,content,offer_title,organization,_now()))
    doc_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()
    return doc_id

@agent_bp.route('/api/agent/generate/cover-letter', methods=['POST'])
def gen_cover_letter():
    """✍️ Génère une lettre de motivation. Ne fait AUCUN envoi."""
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d = request.get_json() or {}
    offer_title  = (d.get('offer_title') or '').strip()
    organization = (d.get('organization') or '').strip()
    description  = (d.get('description') or '')[:1500]
    if not offer_title: return jsonify({'error':'❌ Titre du poste requis'}), 400
    try:
        key = _get_api_key(aid); profile = _get_profile(aid)
    except ValueError as e: return jsonify({'error':str(e)}), 400
    if not profile.get('name'):
        return jsonify({'error':'❌ Profil incomplet → renseignez votre nom et profession dans Profil.'}), 400

    prompt = (f"Tu es expert en ressources humaines au Cameroun. "
              f"Rédige une lettre de motivation professionnelle en français.\n\n"
              f"=== PROFIL ===\n{_profile_ctx(profile)}\n\n"
              f"=== OFFRE ===\nPoste : {offer_title}\nEntreprise : {organization or 'non précisée'}\nDescription : {description or 'non fournie'}\n\n"
              f"CONSIGNES : 300-380 mots | Structure : en-tête + objet + accroche + corps 2-3 §  + conclusion + formule politesse | "
              f"Ton professionnel adapté au Cameroun | Personnalisé avec les infos fournies | "
              f"RETOURNE UNIQUEMENT LA LETTRE, sans balises ni commentaires.")
    try:
        content = _call_claude(key,[{"role":"user","content":prompt}],max_tokens=1200)
        doc_id  = _save_doc(aid,'cover_letter',f'Lettre — {offer_title}',content,offer_title,organization)
        return jsonify({'success':True,'content':content,'doc_id':doc_id})
    except ValueError as e: return jsonify({'error':str(e)}), 400
    except Exception as e:  return jsonify({'error':f'❌ Erreur génération : {str(e)[:150]}'}), 500

@agent_bp.route('/api/agent/generate/application-email', methods=['POST'])
def gen_application_email():
    """📧 Génère un email de candidature. Ne fait AUCUN envoi."""
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d = request.get_json() or {}
    offer_title  = (d.get('offer_title') or '').strip()
    organization = (d.get('organization') or '').strip()
    if not offer_title: return jsonify({'error':'❌ Titre du poste requis'}), 400
    try:
        key = _get_api_key(aid); profile = _get_profile(aid)
    except ValueError as e: return jsonify({'error':str(e)}), 400

    prompt = (f"Rédige un email de candidature professionnel en français, 130 mots max.\n"
              f"Candidat : {profile.get('name','')} — {profile.get('profession','')} — {profile.get('location','')}\n"
              f"Poste : {offer_title}\nEntreprise : {organization or 'non précisée'}\n"
              f"Ton direct et percutant. Mentionne CV + lettre en pièces jointes.\n"
              f"FORMAT OBLIGATOIRE :\nOBJET: [objet email]\n---\n[corps + signature]\n"
              f"RETOURNE UNIQUEMENT ce format, rien d'autre.")
    try:
        raw     = _call_claude(key,[{"role":"user","content":prompt}],max_tokens=450)
        m       = re.search(r'OBJET\s*:\s*(.+)',raw,re.I)
        subject = m.group(1).strip() if m else f'Candidature — {offer_title}'
        parts   = raw.split('---',1)
        body    = parts[1].strip() if len(parts)>1 else raw
        doc_id  = _save_doc(aid,'email',f'Email — {offer_title}',f'OBJET: {subject}\n---\n{body}',offer_title,organization)
        return jsonify({'success':True,'subject':subject,'body':body,'doc_id':doc_id})
    except ValueError as e: return jsonify({'error':str(e)}), 400
    except Exception as e:  return jsonify({'error':f'❌ {str(e)[:150]}'}), 500

@agent_bp.route('/api/agent/generate/cv-summary', methods=['POST'])
def gen_cv_summary():
    """📄 Génère un résumé professionnel CV. Ne fait AUCUN envoi."""
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d      = request.get_json() or {}
    target = (d.get('target_role') or '').strip()
    try:
        key = _get_api_key(aid); profile = _get_profile(aid)
    except ValueError as e: return jsonify({'error':str(e)}), 400

    prompt = (f"Rédige un profil professionnel CV en français, 150-200 mots, dynamique et percutant.\n"
              f"{_profile_ctx(profile)}\nPoste visé : {target or profile.get('profession','non précisé')}\n"
              f"3 paragraphes : identité/expertise | réalisations clés | objectif.\n"
              f"Adapté au marché camerounais. UNIQUEMENT le texte du profil.")
    try:
        content = _call_claude(key,[{"role":"user","content":prompt}],max_tokens=500)
        doc_id  = _save_doc(aid,'cv_summary',f'Résumé CV — {target or profile.get("profession","")}',content,target,'')
        return jsonify({'success':True,'content':content,'doc_id':doc_id})
    except ValueError as e: return jsonify({'error':str(e)}), 400
    except Exception as e:  return jsonify({'error':f'❌ {str(e)[:150]}'}), 500

@agent_bp.route('/api/agent/documents')
def list_documents():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    rows = conn.execute('SELECT id,doc_type,title,offer_title,organization,created_at FROM agent_documents WHERE account_id=? ORDER BY created_at DESC LIMIT 60',(aid,)).fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@agent_bp.route('/api/agent/documents/<int:did>')
def get_document(did):
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db(); row = conn.execute('SELECT * FROM agent_documents WHERE id=? AND account_id=?',(did,aid)).fetchone(); conn.close()
    return jsonify(dict(row)) if row else ('not found',404)

@agent_bp.route('/api/agent/documents/<int:did>', methods=['DELETE'])
def del_document(did):
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db(); conn.execute('DELETE FROM agent_documents WHERE id=? AND account_id=?',(did,aid)); conn.commit(); conn.close()
    return jsonify({'success':True})


# ══════════════════════════════════════════════════════════════════════════════
# 5.  ROBOT DE POSTULATION  (INDÉPENDANT — génère ET envoie en une seule action)
# ══════════════════════════════════════════════════════════════════════════════
@agent_bp.route('/api/agent/apply', methods=['POST'])
def agent_apply():
    """🤖 ROBOT — Génère la lettre + email ET les envoie via Gmail. Totalement indépendant."""
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    d = request.get_json() or {}
    offer_title     = (d.get('offer_title')     or '').strip()
    organization    = (d.get('organization')    or '').strip()
    recruiter_email = (d.get('recruiter_email') or '').strip()
    description     = (d.get('description')     or '')[:1200]
    offer_url       = (d.get('offer_url')       or '').strip()
    send_now        = bool(recruiter_email)

    if not offer_title: return jsonify({'error':'❌ Titre du poste requis'}), 400
    if send_now and not re.match(r'^[^@]+@[^@]+\.[^@]+$', recruiter_email):
        return jsonify({'error':'❌ Email du recruteur invalide'}), 400

    try:
        key = _get_api_key(aid); profile = _get_profile(aid)
    except ValueError as e: return jsonify({'error':str(e)}), 400
    if not profile.get('name'):
        return jsonify({'error':'❌ Profil incomplet — renseignez votre nom dans Profil.'}), 400
    if send_now and not profile.get('gmail_connected'):
        return jsonify({'error':'❌ Gmail non connecté.\n→ Connectez votre Gmail dans Configuration.'}), 400

    steps=[]; cover=''; subject=''; body=''; err_msg=''

    # ── Étape 1 : Lettre ──────────────────────────────────────────────────────
    try:
        lm_p = (f"Expert en candidatures Cameroun. Lettre de motivation en français.\n\n"
                f"{_profile_ctx(profile)}\n\n"
                f"OFFRE :\nPoste : {offer_title}\nEntreprise : {organization or 'non précisée'}\nDescription : {description or 'non fournie'}\n\n"
                f"300-360 mots. Ton professionnel. Contexte camerounais. UNIQUEMENT la lettre.")
        cover = _call_claude(key,[{"role":"user","content":lm_p}],max_tokens=1200)
        steps.append({'step':'📝 Lettre de motivation générée','status':'ok'})
    except ValueError as e:
        return jsonify({'error':str(e),'steps':steps}), 400

    # ── Étape 2 : Email ───────────────────────────────────────────────────────
    try:
        em_p = (f"Email candidature français 130 mots max.\n"
                f"Candidat : {profile.get('name','')} — {profile.get('profession','')}\n"
                f"Poste : {offer_title} chez {organization or 'cette entreprise'}\n"
                f"Accroche forte. Mentionne CV + lettre joints.\n"
                f"FORMAT : OBJET: [objet]\n---\n[corps + signature]\nUNIQUEMENT ce format.")
        raw_em  = _call_claude(key,[{"role":"user","content":em_p}],max_tokens=400)
        m       = re.search(r'OBJET\s*:\s*(.+)',raw_em,re.I)
        subject = m.group(1).strip() if m else f'Candidature — {offer_title}'
        parts   = raw_em.split('---',1)
        body    = parts[1].strip() if len(parts)>1 else raw_em
        if profile.get('phone'): body += f"\n\n{profile.get('name','')} | {profile.get('phone','')}"
        steps.append({'step':'📧 Email de candidature généré','status':'ok'})
    except ValueError as e:
        steps.append({'step':'📧 Email','status':'error','error':str(e)})
        subject = f'Candidature au poste de {offer_title}'
        body    = f"Madame, Monsieur,\n\nJe vous adresse ma candidature pour le poste de {offer_title}.\n\nCordialement,\n{profile.get('name','')}"

    # ── Étape 3 : Envoi Gmail ─────────────────────────────────────────────────
    email_sent = False
    if send_now:
        try:
            html = (f'<div style="font-family:Arial,sans-serif;max-width:680px;color:#222">'
                    f'<p>{body.replace(chr(10),"<br>")}</p>'
                    f'<hr style="border:1px solid #eee;margin:24px 0">'
                    f'<h3 style="color:#00A550">LETTRE DE MOTIVATION</h3>'
                    f'<p style="line-height:1.8">{cover.replace(chr(10),"<br>")}</p>'
                    f'{"<hr><p style=font-size:12px;color:#888>Offre : <a href="+offer_url+">"+offer_url+"</a></p>" if offer_url else ""}'
                    f'<hr style="border:1px solid #eee"><p style="font-size:11px;color:#aaa">Envoyé via CamerJob Watch — Agent IA</p>'
                    f'</div>')
            _send_gmail(aid, recruiter_email, subject, body+f"\n\n---\nLETTRE DE MOTIVATION\n---\n{cover}", html)
            email_sent = True
            steps.append({'step':f'✅ Email envoyé à {recruiter_email}','status':'ok'})
        except ValueError as e:
            err_msg = str(e)
            steps.append({'step':'📤 Envoi Gmail','status':'error','error':err_msg})
        except Exception as e:
            err_msg = str(e)[:200]
            steps.append({'step':'📤 Envoi Gmail','status':'error','error':err_msg})
    else:
        steps.append({'step':'📤 Pas d\'email recruteur → documents enregistrés','status':'skip'})

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    status = 'envoyée' if email_sent else ('erreur_envoi' if (send_now and not email_sent) else 'brouillon')
    conn   = _db()
    conn.execute('''INSERT INTO agent_applications
        (account_id,offer_title,organization,offer_url,recruiter_email,
         cover_letter,email_subject,email_body,email_sent,sent_at,status,error_msg,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (aid,offer_title,organization,offer_url,recruiter_email,cover,subject,body,
         1 if email_sent else 0,_now() if email_sent else '',status,err_msg,_now()))
    app_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit(); conn.close()

    return jsonify({'success':True,'application_id':app_id,'cover_letter':cover,
                    'email_subject':subject,'email_body':body,'email_sent':email_sent,
                    'status':status,'steps':steps,'error':err_msg or None})

@agent_bp.route('/api/agent/applications')
def list_applications():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    rows = conn.execute('''SELECT id,offer_title,organization,recruiter_email,email_sent,
        status,sent_at,created_at,error_msg FROM agent_applications WHERE account_id=?
        ORDER BY created_at DESC LIMIT 100''',(aid,)).fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@agent_bp.route('/api/agent/applications/<int:app_id>')
def get_application(app_id):
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db(); row = conn.execute('SELECT * FROM agent_applications WHERE id=? AND account_id=?',(app_id,aid)).fetchone(); conn.close()
    return jsonify(dict(row)) if row else ('not found',404)

@agent_bp.route('/api/agent/applications/<int:app_id>', methods=['DELETE'])
def del_application(app_id):
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db(); conn.execute('DELETE FROM agent_applications WHERE id=? AND account_id=?',(app_id,aid)); conn.commit(); conn.close()
    return jsonify({'success':True})

@agent_bp.route('/api/agent/stats')
def agent_stats():
    aid = session.get('agent_id')
    if not aid: return jsonify({'error':'non_connecte'}), 401
    conn = _db()
    total = conn.execute('SELECT COUNT(*) FROM agent_applications WHERE account_id=?',(aid,)).fetchone()[0]
    sent  = conn.execute("SELECT COUNT(*) FROM agent_applications WHERE account_id=? AND email_sent=1",(aid,)).fetchone()[0]
    docs  = conn.execute('SELECT COUNT(*) FROM agent_documents WHERE account_id=?',(aid,)).fetchone()[0]
    conn.close()
    return jsonify({'applications_total':total,'applications_sent':sent,'documents_total':docs})


# ══════════════════════════════════════════════════════════════════════════════
# 6.  ADMIN MAILER — Envoi d'offres ciblées depuis votre email admin
# ══════════════════════════════════════════════════════════════════════════════
def _check_admin():
    d  = request.get_json(silent=True) or {}
    pw = request.headers.get('X-Admin-Password','') or d.get('admin_password','')
    return pw == ADMIN_PASSWORD

@agent_bp.route('/api/admin/users')
def admin_users():
    """Liste tous les utilisateurs Agent IA (admin seulement)."""
    if not _check_admin(): return jsonify({'error':'Accès refusé'}), 403
    conn = _db()
    rows = conn.execute('''SELECT id,name,email,phone,profession,location,sectors_pref,
        locations_pref,notif_email,gmail_connected,api_valid,created_at,last_login
        FROM agent_accounts WHERE is_active=1 ORDER BY created_at DESC''').fetchall()
    conn.close(); return jsonify({'count':len(rows),'users':[dict(r) for r in rows]})

@agent_bp.route('/api/admin/users/emails')
def admin_user_emails():
    """Liste uniquement les emails (pour export)."""
    if not _check_admin(): return jsonify({'error':'Accès refusé'}), 403
    conn = _db()
    rows = conn.execute("SELECT name,email,sectors_pref,notif_email FROM agent_accounts WHERE is_active=1 AND notif_email=1 ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify({'count':len(rows),'emails':[{'name':r['name'],'email':r['email'],'sectors':r['sectors_pref']} for r in rows]})

@agent_bp.route('/api/admin/send-offers', methods=['POST'])
def admin_send_offers():
    """
    📨 ADMIN — Envoie des offres ciblées aux utilisateurs inscrits.

    Paramètres JSON :
      admin_password       : mot de passe admin (requis)
      subject              : objet de l'email
      offer_ids            : liste d'IDs d'offres [1,2,3]
      target_sector        : filtre par secteur d'intérêt (optionnel)
      target_location      : filtre par ville (optionnel)
      custom_message       : message personnalisé en tête (optionnel)
      admin_gmail_aid      : ID du compte Agent IA admin avec Gmail connecté (pour envoi auto)
    """
    if not _check_admin(): return jsonify({'error':'Accès refusé — mot de passe admin incorrect'}), 403
    d = request.get_json() or {}
    subject         = (d.get('subject') or 'Offres sélectionnées pour vous — CamerJob Watch').strip()
    offer_ids       = d.get('offer_ids',[])
    target_sector   = (d.get('target_sector')   or '').strip().lower()
    target_location = (d.get('target_location') or '').strip().lower()
    custom_msg      = (d.get('custom_message')  or '').strip()
    admin_aid       = d.get('admin_gmail_aid')   # ID du compte admin avec Gmail

    if not offer_ids: return jsonify({'error':'❌ offer_ids requis (liste d\'IDs d\'offres)'}), 400

    conn = _db()

    # Récupère les offres
    ph     = ','.join('?'*len(offer_ids))
    offers = conn.execute(f'SELECT * FROM offers WHERE id IN ({ph}) AND is_active=1',offer_ids).fetchall()
    if not offers: conn.close(); return jsonify({'error':'❌ Aucune offre trouvée avec ces IDs'}), 400

    # Récupère les destinataires avec filtre
    users = conn.execute('SELECT id,name,email,sectors_pref,locations_pref,notif_email FROM agent_accounts WHERE is_active=1 AND notif_email=1').fetchall()

    def matches(u):
        if target_sector:
            sp = (u['sectors_pref'] or '').lower()
            if sp and target_sector not in sp: return False
        if target_location:
            lp = (u['locations_pref'] or '').lower()
            if lp and target_location not in lp: return False
        return True

    recipients = [u for u in users if matches(u)]
    if not recipients: conn.close(); return jsonify({'error':'❌ Aucun destinataire correspondant'}), 400

    # Construit les cartes offres HTML
    def offer_card(o):
        badge = '💼 Emploi' if o['offer_type']=='emploi' else "📋 Appel d'offre"
        desc  = (o['description'] or '')[:220]
        if len(o['description'] or '')>220: desc+='…'
        link  = (f'<a href="{o["url"]}" style="display:inline-block;background:#00A550;color:#fff;'
                 f'padding:8px 18px;border-radius:6px;text-decoration:none;font-size:13px;margin-top:10px">Voir l\'offre →</a>') if o.get('url') else ''
        return (f'<div style="border:1px solid #e5e5e5;border-radius:10px;padding:18px;margin-bottom:18px;background:#fff">'
                f'<div style="font-size:11px;color:#00A550;font-weight:700;margin-bottom:6px;text-transform:uppercase">{badge}</div>'
                f'<h3 style="margin:0 0 8px;font-size:15px;color:#1a1a1a">{o["title"] or ""}</h3>'
                f'<div style="font-size:13px;color:#666;margin-bottom:8px">🏢 {o["organization"] or "—"} &nbsp;|&nbsp; 📍 {o["location"] or "Cameroun"} &nbsp;|&nbsp; 📅 {o["deadline"] or "N/A"}</div>'
                f'{"<div style=font-size:13px;color:#555;margin-bottom:8px>💰 "+o["salary"]+"</div>" if o.get("salary") else ""}'
                f'<p style="font-size:13px;color:#777;margin:0">{desc}</p>'
                f'{link}</div>')

    cards_html = ''.join(offer_card(o) for o in offers)

    def full_email_html(uname):
        cm = (f'<div style="background:#f0faf5;border-left:4px solid #00A550;padding:14px 18px;'
              f'border-radius:0 8px 8px 0;margin-bottom:24px;font-size:14px;color:#333">{custom_msg}</div>') if custom_msg else ''
        return (f'<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
                f'<body style="font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px">'
                f'<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.08)">'
                f'<div style="background:linear-gradient(135deg,#00A550 0%,#007A3D 100%);padding:28px 32px;color:#fff">'
                f'<div style="font-size:24px;font-weight:800">🎯 CamerJob Watch</div>'
                f'<div style="font-size:14px;opacity:.85;margin-top:4px">Offres sélectionnées pour votre profil</div>'
                f'</div>'
                f'<div style="padding:28px 32px">'
                f'<p style="font-size:15px;color:#222;margin-bottom:20px">Bonjour <strong>{uname}</strong>,</p>'
                f'{cm}'
                f'<p style="color:#555;font-size:14px;margin-bottom:22px">Voici les offres sélectionnées correspondant à votre profil :</p>'
                f'{cards_html}'
                f'<div style="text-align:center;margin-top:28px;padding-top:20px;border-top:1px solid #f0f0f0">'
                f'<a href="http://localhost:5000" style="display:inline-block;background:#00A550;color:#fff;'
                f'padding:13px 36px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px">Voir toutes les offres →</a>'
                f'</div></div>'
                f'<div style="background:#f9f9f9;padding:16px 32px;text-align:center;font-size:11px;color:#aaa;border-top:1px solid #eee">'
                f'Envoyé par {ADMIN_NAME} · CamerJob Watch<br>'
                f'Gérez vos notifications dans votre espace Agent IA.</div>'
                f'</div></body></html>')

    # Envoi ou liste selon si admin_aid fourni
    sent_ok=[]; sent_err=[]
    if admin_aid:
        for u in recipients:
            try:
                _send_gmail(admin_aid, u['email'], subject,
                    f"Bonjour {u['name']},\n\nVoici des offres sélectionnées pour vous sur CamerJob Watch.\n\n— {ADMIN_NAME}",
                    full_email_html(u['name']))
                sent_ok.append(u['email'])
            except Exception as e:
                sent_err.append({'email':u['email'],'error':str(e)[:80]})
        mode = 'gmail_sent'
    else:
        sent_ok = [u['email'] for u in recipients]
        mode    = 'list_only'

    # Log
    conn.execute('INSERT INTO admin_mailings(subject,body_html,offer_ids,target_sector,target_location,recipients_count,sent_at,status) VALUES(?,?,?,?,?,?,?,?)',
                 (subject,full_email_html('{{name}}'),json.dumps(offer_ids),target_sector,target_location,len(sent_ok),_now(),mode))
    conn.commit(); conn.close()

    msg = (f'✅ {len(sent_ok)} email(s) envoyé(s)' if admin_aid
           else f'📋 {len(recipients)} destinataire(s) identifié(s) — ajoutez admin_gmail_aid pour l\'envoi auto')
    return jsonify({'success':True,'recipients_total':len(recipients),'sent_ok':len(sent_ok),
                    'sent_error':sent_err,'emails_list':sent_ok,'mode':mode,'message':msg})

@agent_bp.route('/api/admin/mailings')
def admin_mailings():
    if not _check_admin(): return jsonify({'error':'Accès refusé'}), 403
    conn = _db()
    rows = conn.execute('SELECT id,subject,target_sector,target_location,recipients_count,sent_at,status FROM admin_mailings ORDER BY sent_at DESC LIMIT 50').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])
