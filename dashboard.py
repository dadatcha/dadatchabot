import os
import json
import base64
import urllib.request
import urllib.error
import subprocess
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

# Configuration GitHub & Render
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_NAME = "dadatcha/dadatchabot"  # Ton dépôt GitHub
FILE_PATH = "data.json"            # Fichier de stockage persistant

default_data = {
    "permissions": {
        "startguess": "admin",
        "higherlower": "everyone",
        "roulette": "everyone",
        "casino": "everyone",
        "balance": "everyone",
        "level": "everyone",
        "addmoney": "admin",
        "removemoney": "admin",
        "setlevel": "admin",
        "reminders": "admin",
        "add": "admin",
        "delete": "admin",
        "toggle": "admin",
        "sync": "admin",
        "custom_command": "admin",
        "levels": "admin"
    },
    "banned_roles": [],
    "reminders": {},
    "level_config": {
        "xp_per_message": 15,
        "xp_multiplier": 1.0,
        "money_per_level": 100
    },
    "custom_commands": {}
}

# --- CHARGEMENT ET SAUVEGARDE VIA GITHUB ---
def load_data():
    if not GITHUB_TOKEN:
        print("[INFO] GITHUB_TOKEN manquant, utilisation des données par défaut.")
        return default_data
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req) as response:
            res_json = json.loads(response.read().decode())
            file_content = base64.b64decode(res_json["content"]).decode("utf-8")
            print("[SUCCES] Données chargées depuis GitHub !")
            return json.loads(file_content)
    except Exception as e:
        print(f"[INFO] Fichier data.json non trouvé sur GitHub ou erreur ({e}), création initiale...")
        return default_data

def save_data(data):
    if not GITHUB_TOKEN:
        print("[ERREUR] Impossible de sauvegarder : GITHUB_TOKEN manquant.")
        return
    try:
        url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
        sha = None
        try:
            req_get = urllib.request.Request(url, headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req_get) as resp:
                sha = json.loads(resp.read().decode()).get("sha")
        except Exception:
            pass

        json_str = json.dumps(data, indent=4, ensure_ascii=False)
        content_encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "Mise à jour des configurations du dashboard",
            "content": content_encoded
        }
        if sha:
            payload["sha"] = sha

        req_put = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v3+json"
        }, method="PUT")

        with urllib.request.urlopen(req_put) as response:
            print("[SUCCES] Données sauvegardées et commitées sur GitHub avec succès !")
    except Exception as e:
        print(f"[ERREUR] Échec de la sauvegarde sur GitHub : {e}")

db = load_data()
command_permissions = db.get("permissions", default_data["permissions"])
banned_roles = db.get("banned_roles", [])
raw_reminders = db.get("reminders", {})
reminders_db = {int(k): v for k, v in raw_reminders.items() if str(k).isdigit()}
level_config = db.get("level_config", default_data["level_config"])
custom_commands = db.get("custom_commands", {})

if reminders_db:
    reminder_counter = max(reminders_db.keys()) + 1
else:
    reminder_counter = 1

sync_status = None

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Dashboard Bot Discord</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 40px; }
        .container { max-width: 1000px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h1, h2 { color: #38bdf8; text-align: center; }
        h2 { text-align: left; border-bottom: 2px solid #334155; padding-bottom: 10px; margin-top: 40px; }
        table { width: 100%; margin-top: 20px; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { background-color: #334155; color: #38bdf8; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn-admin { background-color: #ef4444; color: white; }
        .btn-everyone { background-color: #22c55e; color: white; }
        .btn-delete { background-color: #ef4444; color: white; }
        .btn-add { background-color: #38bdf8; color: #0f172a; margin-top: 15px; width: 100%; }
        .btn-sync-discord { background-color: #5865F2; color: white; }
        .btn-sync-github { background-color: #24292e; color: white; }
        .btn-sync-render { background-color: #46e3b7; color: #0f172a; }
        .btn:hover { opacity: 0.9; }
        form.inline-form { display: inline; }
        .form-grid { margin-top: 15px; display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; }
        .form-grid-2 { margin-top: 15px; display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr; gap: 10px; }
        .form-grid-role { margin-top: 15px; display: grid; grid-template-columns: 3fr 1fr; gap: 10px; }
        input, select { padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: white; width: 100%; box-sizing: border-box; }
        .sync-container { display: flex; gap: 15px; flex-wrap: wrap; margin-top: 20px; }
        .alert { padding: 12px; border-radius: 6px; margin-bottom: 20px; background-color: #334155; color: #38bdf8; border: 1px solid #38bdf8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Dashboard de Configuration</h1>

        {% if message %}
        <div class="alert">⚡ <strong>Statut :</strong> {{ message }}</div>
        {% endif %}

        <h2>🔄 Centre de Synchronisation</h2>
        <div class="sync-container">
            <form action="/sync/discord" method="POST"><button type="submit" class="btn btn-sync-discord">🤖 Re-sync Discord</button></form>
            <form action="/sync/github" method="POST"><button type="submit" class="btn btn-sync-github">📂 Re-sync Script GitHub</button></form>
            <form action="/sync/render" method="POST"><button type="submit" class="btn btn-sync-render">🚀 Redéployer (Render)</button></form>
        </div>
        
        <h2>📊 Fonctionnement des Niveaux (XP)</h2>
        <form action="/levels/config" method="POST">
            <div class="form-grid">
                <div>
                    <label>XP gagné par message :</label>
                    <input type="number" name="xp_per_message" value="{{ level_config.xp_per_message }}" required>
                </div>
                <div>
                    <label>Multiplicateur d'XP :</label>
                    <input type="number" step="0.1" name="xp_multiplier" value="{{ level_config.xp_multiplier }}" required>
                </div>
                <div>
                    <label>Argent par niveau :</label>
                    <input type="number" name="money_per_level" value="{{ level_config.money_per_level }}" required>
                </div>
                <div style="display: flex; align-items: flex-end;">
                    <button type="submit" class="btn btn-add" style="margin-top:0;">💾 Sauvegarder</button>
                </div>
            </div>
        </form>

        <h2>🎁 Commandes Personnalisées de Récompense</h2>
        <table>
            <tr><th>Nom de la commande</th><th>Rôle attribué</th><th>Niveaux ajoutés</th><th>Argent ajouté</th><th>Action</th></tr>
            {% if custom_commands %}
                {% for cmd_name, cmd_data in custom_commands.items() %}
                <tr>
                    <td><strong>/{{ cmd_name }}</strong></td>
                    <td>@{{ cmd_data.role_name if cmd_data.role_name else 'Aucun' }}</td>
                    <td>+{{ cmd_data.add_levels }} Niveaux</td>
                    <td>+{{ cmd_data.add_money }} 🪙</td>
                    <td>
                        <form action="/custom-command/delete/{{ cmd_name }}" method="POST" class="inline-form">
                            <button type="submit" class="btn btn-delete">Supprimer</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            {% else %}
                <tr><td colspan="5" style="text-align: center; color: #94a3b8;">Aucune commande personnalisée créée.</td></tr>
            {% endif %}
        </table>

        <form action="/custom-command/add" method="POST">
            <div class="form-grid-2">
                <input type="text" name="cmd_name" placeholder="Nom de la commande (ex: bonus)" required>
                <input type="text" name="role_name" placeholder="Rôle à donner (optionnel)">
                <input type="number" name="add_levels" placeholder="Niveaux à ajouter" value="0" required>
                <input type="number" name="add_money" placeholder="Argent à ajouter" value="0" required>
                <button type="submit" class="btn btn-add" style="margin-top:0;">➕ Créer</button>
            </div>
        </form>

        <h2>🚫 Rôles Interdits à l'Usage des Commandes</h2>
        <table>
            <tr><th>Nom du Rôle Interdit</th><th>Action</th></tr>
            {% if banned_roles %}
                {% for role in banned_roles %}
                <tr>
                    <td><strong>@{{ role }}</strong></td>
                    <td>
                        <form action="/banned-role/delete" method="POST" class="inline-form">
                            <input type="hidden" name="role_name" value="{{ role }}">
                            <button type="submit" class="btn btn-delete">Autoriser à nouveau</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            {% else %}
                <tr><td colspan="2" style="text-align: center; color: #94a3b8;">Aucun rôle interdit configuré.</td></tr>
            {% endif %}
        </table>

        <form action="/banned-role/add" method="POST">
            <div class="form-grid-role">
                <input type="text" name="role_name" placeholder="Nom du rôle à interdire (ex: Mute, Visiteur)" required>
                <button type="submit" class="btn btn-add" style="margin-top:0;">🚫 Interdire ce Rôle</button>
            </div>
        </form>

        <h2>🛡️ Gestion des Permissions des Commandes (Actuelles et Futures)</h2>
        <table>
            <tr><th>Commande</th><th>Permission Actuelle</th><th>Action / Bascule</th></tr>
            {% for cmd, perm in permissions.items() %}
            <tr>
                <td><strong>/{{ cmd }}</strong></td>
                <td>{% if perm == 'admin' %}<span style="color: #ef4444;">🛡️ Admin uniquement</span>{% else %}<span style="color: #22c55e;">🌐 Tous</span>{% endif %}</td>
                <td>
                    <form action="/toggle/{{ cmd }}" method="POST" class="inline-form">
                        {% if perm == 'admin' %}<button type="submit" class="btn btn-everyone">Rendre public</button>
                        {% else %}<button type="submit" class="btn btn-admin">Restreindre Admin</button>{% endif %}
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>

        <h2>⏰ Configuration des Rappels Automatiques</h2>
        <table>
            <tr><th>ID</th><th>Message / Titre</th><th>ID du Salon</th><th>Rôle visé</th><th>Intervalle</th><th>Action</th></tr>
            {% if reminders %}
                {% for r_id, r_data in reminders.items() %}
                <tr>
                    <td>#{{ r_id }}</td>
                    <td><strong>{{ r_data.title }}</strong></td>
                    <td><code>{{ r_data.channel_id }}</code></td>
                    <td>@{{ r_data.role_name }}</td>
                    <td>Toutes les <strong>{{ r_data.interval_minutes }} min</strong></td>
                    <td>
                        <form action="/reminder/delete/{{ r_id }}" method="POST" class="inline-form">
                            <button type="submit" class="btn btn-delete">Supprimer</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            {% else %}
                <tr><td colspan="6" style="text-align: center; color: #94a3b8;">Aucun rappel configuré.</td></tr>
            {% endif %}
        </table>

        <form action="/reminder/add" method="POST">
            <div class="form-grid">
                <input type="text" name="title" placeholder="Message du rappel" required>
                <input type="text" name="channel_id" placeholder="ID du salon Discord" required>
                <input type="text" name="role_name" placeholder="Nom du rôle à mentionner" required>
                <input type="number" name="interval_minutes" placeholder="Intervalle (en minutes)" min="1" required>
            </div>
            <button type="submit" class="btn btn-add">➕ Ajouter et Activer le Rappel</button>
        </form>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    global sync_status
    msg = sync_status
    sync_status = None
    return render_template_string(
        DASHBOARD_TEMPLATE, 
        permissions=command_permissions,
        banned_roles=banned_roles,
        reminders=reminders_db, 
        level_config=level_config,
        custom_commands=custom_commands,
        message=msg
    )

@app.route("/levels/config", methods=["POST"])
def update_levels_config():
    global level_config
    try:
        xp_msg = int(request.form.get("xp_per_message", 15))
        xp_mult = float(request.form.get("xp_multiplier", 1.0))
        money_lvl = int(request.form.get("money_per_level", 100))
        level_config["xp_per_message"] = xp_msg
        level_config["xp_multiplier"] = xp_mult
        level_config["money_per_level"] = money_lvl
        db["level_config"] = level_config
        save_data(db)
    except ValueError:
        pass
    return redirect(url_for("index"))

@app.route("/custom-command/add", methods=["POST"])
def add_custom_command():
    global custom_commands
    cmd_name = request.form.get("cmd_name", "").strip().lower().lstrip("/")
    role_name = request.form.get("role_name", "").strip().lstrip("@")
    try:
        add_levels = int(request.form.get("add_levels", 0))
        add_money = int(request.form.get("add_money", 0))
        
        if cmd_name:
            custom_commands[cmd_name] = {
                "role_name": role_name,
                "add_levels": add_levels,
                "add_money": add_money
            }
            db["custom_commands"] = custom_commands
            # S'assurer que la nouvelle commande a une permission par défaut
            if cmd_name not in command_permissions:
                command_permissions[cmd_name] = "admin"
                db["permissions"] = command_permissions
            save_data(db)
    except ValueError:
        pass
    return redirect(url_for("index"))

@app.route("/custom-command/delete/<cmd_name>", methods=["POST"])
def delete_custom_command(cmd_name):
    if cmd_name in custom_commands:
        del custom_commands[cmd_name]
        db["custom_commands"] = custom_commands
        if cmd_name in command_permissions:
            del command_permissions[cmd_name]
            db["permissions"] = command_permissions
        save_data(db)
    return redirect(url_for("index"))

@app.route("/banned-role/add", methods=["POST"])
def add_banned_role():
    global banned_roles
    role_name = request.form.get("role_name", "").strip().lstrip("@")
    if role_name and role_name not in banned_roles:
        banned_roles.append(role_name)
        db["banned_roles"] = banned_roles
        save_data(db)
    return redirect(url_for("index"))

@app.route("/banned-role/delete", methods=["POST"])
def delete_banned_role():
    global banned_roles
    role_name = request.form.get("role_name", "").strip().lstrip("@")
    if role_name in banned_roles:
        banned_roles.remove(role_name)
        db["banned_roles"] = banned_roles
        save_data(db)
    return redirect(url_for("index"))

@app.route("/toggle/<cmd_name>", methods=["POST"])
def toggle_permission(cmd_name):
    if cmd_name in command_permissions:
        command_permissions[cmd_name] = "everyone" if command_permissions[cmd_name] == "admin" else "admin"
        db["permissions"] = command_permissions
        save_data(db)
    return redirect(url_for("index"))

@app.route("/reminder/add", methods=["POST"])
def add_reminder():
    global reminder_counter
    title = request.form.get("title")
    channel_id = request.form.get("channel_id")
    role_name = request.form.get("role_name")
    interval = request.form.get("interval_minutes")
    
    if title and channel_id and role_name and interval:
        try:
            reminders_db[reminder_counter] = {
                "title": title,
                "channel_id": int(channel_id),
                "role_name": role_name.strip("@"),
                "interval_minutes": int(interval)
            }
            reminder_counter += 1
            db["reminders"] = {str(k): v for k, v in reminders_db.items()}
            save_data(db)
        except ValueError:
            pass
    return redirect(url_for("index"))

@app.route("/reminder/delete/<int:r_id>", methods=["POST"])
def delete_reminder(r_id):
    if r_id in reminders_db:
        del reminders_db[r_id]
        db["reminders"] = {str(k): v for k, v in reminders_db.items()}
        save_data(db)
    return redirect(url_for("index"))

@app.route("/sync/discord", methods=["POST"])
def sync_discord():
    global sync_status
    sync_status = "Signal de synchronisation des commandes envoyé."
    return redirect(url_for("index"))

@app.route("/sync/github", methods=["POST"])
def sync_github():
    global sync_status
    repo_url = "https://github.com/dadatcha/dadatchabot.git"
    try:
        if not os.path.isdir(".git"):
            subprocess.run(["git", "init"], capture_output=True, text=True, check=True)
            subprocess.run(["git", "remote", "add", "origin", repo_url], capture_output=True, text=True)
        else:
            remotes = subprocess.run(["git", "remote"], capture_output=True, text=True)
            if "origin" not in remotes.stdout:
                subprocess.run(["git", "remote", "add", "origin", repo_url], capture_output=True, text=True)
            else:
                subprocess.run(["git", "remote", "set-url", "origin", repo_url], capture_output=True, text=True)

        subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, timeout=10)
        subprocess.run(["git", "branch", "-M", "main"], capture_output=True, text=True)
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            sync_status = "Mise à jour GitHub réussie (Git Pull effectué)."
        else:
            sync_status = f"Erreur Git : {result.stderr.strip()}"
    except Exception as e:
        sync_status = f"Impossible d'exécuter la synchro GitHub : {e}"
    return redirect(url_for("index"))

@app.route("/sync/render", methods=["POST"])
def sync_render():
    global sync_status
    webhook = os.environ.get("RENDER_DEPLOY_HOOK_URL")
    if webhook:
        try:
            urllib.request.urlopen(webhook, data=b"")
            sync_status = "Redéploiement Render déclenché !"
        except Exception as e:
            sync_status = f"Erreur webhook : {e}"
    else:
        sync_status = "Variable RENDER_DEPLOY_HOOK_URL non configurée."
    return redirect(url_for("index"))

def run_dashboard():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
