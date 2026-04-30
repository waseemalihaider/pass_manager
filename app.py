from flask import Flask, render_template, request, jsonify, session
import json, os, base64, hashlib, secrets, time
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

USERS_FILE = "users.json"
VAULTS_DIR = "vaults"
os.makedirs(VAULTS_DIR, exist_ok=True)

# ── CRYPTO ────────────────────────────────────────────────────────────────────
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_data(data: dict, password: str, salt: bytes) -> bytes:
    return Fernet(derive_key(password, salt)).encrypt(json.dumps(data).encode())

def decrypt_data(ct: bytes, password: str, salt: bytes) -> dict:
    return json.loads(Fernet(derive_key(password, salt)).decrypt(ct).decode())

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode()).hexdigest()

# ── USERS DB ──────────────────────────────────────────────────────────────────
def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            return json.load(f)
    return {}

def save_users(users: dict):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

# ── VAULT ─────────────────────────────────────────────────────────────────────
def vault_path(username: str) -> str:
    return os.path.join(VAULTS_DIR, f"{username}.enc")

def load_vault(username: str, password: str, salt: bytes) -> dict:
    p = vault_path(username)
    if not os.path.exists(p):
        return {"accounts": []}
    with open(p, 'rb') as f:
        return decrypt_data(f.read(), password, salt)

def save_vault(username: str, vault: dict, password: str, salt: bytes):
    with open(vault_path(username), 'wb') as f:
        f.write(encrypt_data(vault, password, salt))

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    data     = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    name     = data.get('name', '').strip()

    if not username or not password or not name:
        return jsonify({'ok': False, 'msg': 'Sab fields zaroor bharo!'})
    if len(username) < 3:
        return jsonify({'ok': False, 'msg': 'Username kam se kam 3 characters!'})
    if len(password) < 6:
        return jsonify({'ok': False, 'msg': 'Password kam se kam 6 characters!'})

    users = load_users()
    if username in users:
        return jsonify({'ok': False, 'msg': 'Yeh username already exist karta hai!'})

    salt = secrets.token_hex(16)
    users[username] = {
        'name':    name,
        'username':username,
        'salt':    salt,
        'hash':    hash_password(password, salt),
        'vault_salt': base64.b64encode(os.urandom(16)).decode(),
        'joined':  time.strftime('%d %b %Y'),
    }
    save_users(users)

    # Create empty vault
    vsalt = base64.b64decode(users[username]['vault_salt'])
    save_vault(username, {"accounts": []}, password, vsalt)

    session['user']     = username
    session['name']     = name
    session['password'] = password
    session['vsalt']    = users[username]['vault_salt']
    return jsonify({'ok': True, 'name': name})

@app.route('/login', methods=['POST'])
def login():
    data     = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')

    users = load_users()
    if username not in users:
        return jsonify({'ok': False, 'msg': 'Username nahi mila!'})

    u = users[username]
    if hash_password(password, u['salt']) != u['hash']:
        return jsonify({'ok': False, 'msg': 'Galat password!'})

    try:
        vsalt = base64.b64decode(u['vault_salt'])
        load_vault(username, password, vsalt)
    except:
        return jsonify({'ok': False, 'msg': 'Vault decrypt nahi hua — galat password!'})

    session['user']     = username
    session['name']     = u['name']
    session['password'] = password
    session['vsalt']    = u['vault_salt']
    return jsonify({'ok': True, 'name': u['name']})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/check_auth')
def check_auth():
    if session.get('user'):
        return jsonify({'auth': True, 'name': session.get('name'), 'user': session.get('user')})
    return jsonify({'auth': False})

# ── ACCOUNT ROUTES ────────────────────────────────────────────────────────────
def get_vault():
    return load_vault(session['user'], session['password'], base64.b64decode(session['vsalt']))

def put_vault(vault):
    save_vault(session['user'], vault, session['password'], base64.b64decode(session['vsalt']))

@app.route('/get_accounts')
def get_accounts():
    if not session.get('user'): return jsonify({'ok': False})
    vault = get_vault()
    accounts = [{
        'id':    a['id'], 'label': a.get('label',''), 'email': a.get('email',''),
        'phone': a.get('phone',''), 'platform': a.get('platform',''),
        'notes': a.get('notes',''), 'status': a.get('status','active'),
        'added': a.get('added',''), 'has_pass': bool(a.get('password','')),
        'has_2fa': bool(a.get('twofa_secret','')),
        'backup_codes_count': len(a.get('backup_codes',[])),
    } for a in vault['accounts']]
    return jsonify({'ok': True, 'accounts': accounts})

@app.route('/get_account/<aid>')
def get_account(aid):
    if not session.get('user'): return jsonify({'ok': False})
    for a in get_vault()['accounts']:
        if a['id'] == aid: return jsonify({'ok': True, 'account': a})
    return jsonify({'ok': False})

@app.route('/add_account', methods=['POST'])
def add_account():
    if not session.get('user'): return jsonify({'ok': False})
    data  = request.json
    vault = get_vault()
    acc   = {
        'id':           secrets.token_hex(8),
        'label':        data.get('label',''),
        'email':        data.get('email',''),
        'phone':        data.get('phone',''),
        'password':     data.get('password',''),
        'platform':     data.get('platform','Gmail'),
        'notes':        data.get('notes',''),
        'twofa_secret': data.get('twofa_secret',''),
        'backup_codes': data.get('backup_codes',[]),
        'status':       data.get('status','active'),
        'added':        time.strftime('%d %b %Y %H:%M'),
    }
    vault['accounts'].append(acc)
    put_vault(vault)
    return jsonify({'ok': True, 'id': acc['id']})

@app.route('/update_account/<aid>', methods=['POST'])
def update_account(aid):
    if not session.get('user'): return jsonify({'ok': False})
    data  = request.json
    vault = get_vault()
    for a in vault['accounts']:
        if a['id'] == aid:
            for k in ['label','email','phone','password','platform','notes','twofa_secret','backup_codes','status']:
                if k in data: a[k] = data[k]
            a['updated'] = time.strftime('%d %b %Y %H:%M')
            break
    put_vault(vault)
    return jsonify({'ok': True})

@app.route('/delete_account/<aid>', methods=['POST'])
def delete_account(aid):
    if not session.get('user'): return jsonify({'ok': False})
    vault = get_vault()
    vault['accounts'] = [a for a in vault['accounts'] if a['id'] != aid]
    put_vault(vault)
    return jsonify({'ok': True})

@app.route('/change_password', methods=['POST'])
def change_password():
    if not session.get('user'): return jsonify({'ok': False})
    data     = request.json
    old_pass = data.get('old_password','')
    new_pass = data.get('new_password','')
    users    = load_users()
    u        = users[session['user']]
    if hash_password(old_pass, u['salt']) != u['hash']:
        return jsonify({'ok': False, 'msg': 'Purana password galat hai!'})
    if len(new_pass) < 6:
        return jsonify({'ok': False, 'msg': 'Naya password kam se kam 6 characters!'})

    vault    = get_vault()
    new_salt = os.urandom(16)
    new_vsalt= base64.b64encode(new_salt).decode()
    new_hsalt= secrets.token_hex(16)

    u['salt']       = new_hsalt
    u['hash']       = hash_password(new_pass, new_hsalt)
    u['vault_salt'] = new_vsalt
    save_users(users)
    save_vault(session['user'], vault, new_pass, new_salt)

    session['password'] = new_pass
    session['vsalt']    = new_vsalt
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=7070, threaded=True)
