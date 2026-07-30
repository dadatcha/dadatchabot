import os
import subprocess
from flask import Flask, render_template_string, request, redirect, url_for
import json
import subprocess

app = Flask(__name__)

# Fichiers de sauvegarde persistante
PERMS_FILE = "permissions.json"

# Dictionnaire par défaut
default_permissions = {
    "startguess": "admin",
    "higherlower": "everyone",
    "roulette": "everyone",
    "casino": "everyone",
    "balance": "everyone",
    "level": "everyone",
    "addmoney": "admin",
    "removemoney": "admin",
    "setlevel": "admin",
    "reminders": "everyone"
}

# Fonction pour charger les permissions (depuis le fichier s'il existe, sinon par défaut)
def load_permissions():
    if os.path.exists(PERMS_FILE):
        try:
            with open(PERMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_permissions.copy()

# Fonction pour sauvegarder les permissions dans le fichier
def save_permissions(perms):
    try:
        with open(PERMS_FILE, "w", encoding="utf-8") as f:
            json.dump(perms, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des permissions : {e}")

# Charger les permissions au démarrage
command_permissions = load_permissions()

# Stockage des rappels : id -> {"title": str, "channel_id": int, "role_name": str, "interval_minutes": int}
reminders_db = {}
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
        
        <h2>🛡️ Gestion des Permissions des Commandes</h2>
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
    return render_template_string(DASHBOARD_TEMPLATE, permissions=command_permissions, reminders=reminders_db, message=msg)

@app.route("/toggle/<cmd_name>", methods=["POST"])
def toggle_permission(cmd_name):
    if cmd_name in command_permissions:
        command_permissions[cmd_name] = "everyone" if command_permissions[cmd_name] == "admin" else "admin"
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
        except ValueError:
            pass
    return redirect(url_for("index"))

@app.route("/reminder/delete/<int:r_id>", methods=["POST"])
def delete_reminder(r_id):
    if r_id in reminders_db:
        del reminders_db[r_id]
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
            # Vérifie si 'origin' existe déjà, sinon l'ajoute, sinon met à jour son URL
            remotes = subprocess.run(["git", "remote"], capture_output=True, text=True)
            if "origin" not in remotes.stdout:
                subprocess.run(["git", "remote", "add", "origin", repo_url], capture_output=True, text=True)
            else:
                subprocess.run(["git", "remote", "set-url", "origin", repo_url], capture_output=True, text=True)

        # Force la récupération et le pull
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
        import urllib.request
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
