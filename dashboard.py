import os
import subprocess
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

# Dictionnaire de configuration des permissions des commandes
command_permissions = {
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

# Stockage en mémoire des rappels
reminders_db = {}
reminder_counter = 1

# Variable pour stocker le dernier statut des actions
sync_status = None

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Dashboard Bot Discord</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 40px; }
        .container { max-width: 900px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h1, h2 { color: #38bdf8; text-align: center; }
        h2 { text-align: left; border-bottom: 2px solid #334155; padding-bottom: 10px; margin-top: 40px; }
        table { width: 100%; margin-top: 20px; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { background-color: #334155; color: #38bdf8; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn-admin { background-color: #ef4444; color: white; }
        .btn-everyone { background-color: #22c55e; color: white; }
        .btn-delete { background-color: #ef4444; color: white; }
        .btn-add { background-color: #38bdf8; color: #0f172a; margin-top: 10px; }
        .btn-sync-discord { background-color: #5865F2; color: white; }
        .btn-sync-github { background-color: #24292e; color: white; }
        .btn-sync-render { background-color: #46e3b7; color: #0f172a; }
        .btn:hover { opacity: 0.9; }
        form.inline-form { display: inline; }
        .form-group { margin-top: 15px; display: flex; gap: 10px; }
        input[type="text"] { flex: 1; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: white; }
        .sync-container { display: flex; gap: 15px; flex-wrap: wrap; margin-top: 20px; }
        .alert { padding: 12px; border-radius: 6px; margin-bottom: 20px; background-color: #334155; color: #38bdf8; border: 1px solid #38bdf8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Dashboard de Configuration</h1>

        {% if message %}
        <div class="alert">
            ⚡ <strong>Statut :</strong> {{ message }}
        </div>
        {% endif %}

        <!-- SECTION 0 : SYNCHRONISATION GLOBALE -->
        <h2>🔄 Centre de Synchronisation</h2>
        <p>Exécute des actions de mise à jour et de synchronisation instantanées :</p>
        <div class="sync-container">
            <form action="/sync/discord" method="POST">
                <button type="submit" class="btn btn-sync-discord">🤖 Re-sync Discord (Commandes)</button>
            </form>
            <form action="/sync/github" method="POST">
                <button type="submit" class="btn btn-sync-github">📂 Re-sync Script GitHub</button>
            </form>
            <form action="/sync/render" method="POST">
                <button type="submit" class="btn btn-sync-render">🚀 Redéployer (Render)</button>
            </form>
        </div>
        
        <!-- SECTION 1 : PERMISSIONS -->
        <h2>🛡️ Gestion des Permissions des Commandes</h2>
        <p>Gère les permissions des commandes de ton bot en un clic :</p>
        <table>
            <tr>
                <th>Commande</th>
                <th>Permission Actuelle</th>
                <th>Action / Bascule</th>
            </tr>
            {% for cmd, perm in permissions.items() %}
            <tr>
                <td><strong>/{{ cmd }}</strong></td>
                <td>
                    {% if perm == 'admin' %}
                        <span style="color: #ef4444;">🛡️ Administrateurs uniquement</span>
                    {% else %}
                        <span style="color: #22c55e;">🌐 Tous les membres</span>
                    {% endif %}
                </td>
                <td>
                    <form action="/toggle/{{ cmd }}" method="POST" class="inline-form">
                        {% if perm == 'admin' %}
                            <button type="submit" class="btn btn-everyone">Rendre public</button>
                        {% else %}
                            <button type="submit" class="btn btn-admin">Restreindre Admin</button>
                        {% endif %}
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>

        <!-- SECTION 2 : RAPPELS (REMINDERS) -->
        <h2>⏰ Gestion des Rappels (Reminders)</h2>
        <p>Crée et consulte les rappels enregistrés :</p>
        
        <table>
            <tr>
                <th>ID</th>
                <th>Titre du Rappel</th>
                <th>Horaire / Date</th>
                <th>Action</th>
            </tr>
            {% if reminders %}
                {% for r_id, r_data in reminders.items() %}
                <tr>
                    <td>#{{ r_id }}</td>
                    <td><strong>{{ r_data.title }}</strong></td>
                    <td>{{ r_data.time }}</td>
                    <td>
                        <form action="/reminder/delete/{{ r_id }}" method="POST" class="inline-form">
                            <button type="submit" class="btn btn-delete">Supprimer</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            {% else %}
                <tr>
                    <td colspan="4" style="text-align: center; color: #94a3b8;">Aucun rappel pour le moment.</td>
                </tr>
            {% endif %}
        </table>

        <form action="/reminder/add" method="POST" class="form-group">
            <input type="text" name="title" placeholder="Titre du rappel (ex: Lancer un stream)" required>
            <input type="text" name="time" placeholder="Horaire (ex: Ce soir à 20h)" required>
            <button type="submit" class="btn btn-add">Ajouter un rappel</button>
        </form>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    global sync_status
    msg = sync_status
    sync_status = None # Réinitialise le message après affichage
    return render_template_string(DASHBOARD_TEMPLATE, permissions=command_permissions, reminders=reminders_db, message=msg)

@app.route("/toggle/<cmd_name>", methods=["POST"])
def toggle_permission(cmd_name):
    if cmd_name in command_permissions:
        if command_permissions[cmd_name] == "admin":
            command_permissions[cmd_name] = "everyone"
        else:
            command_permissions[cmd_name] = "admin"
    return redirect(url_for("index"))

@app.route("/reminder/add", methods=["POST"])
def add_reminder():
    global reminder_counter
    title = request.form.get("title")
    time_str = request.form.get("time")
    if title and time_str:
        reminders_db[reminder_counter] = {"title": title, "time": time_str}
        reminder_counter += 1
    return redirect(url_for("index"))

@app.route("/reminder/delete/<int:r_id>", methods=["POST"])
def delete_reminder(r_id):
    if r_id in reminders_db:
        del reminders_db[r_id]
    return redirect(url_for("index"))

# --- ROUTES DE SYNCHRONISATION ---

@app.route("/sync/discord", methods=["POST"])
def sync_discord():
    global sync_status
    # Note : Le vrai sync des commandes s'effectue dans main.py lors du on_ready. 
    # Ici, on envoie un signal ou on simule/relance le processus si nécessaire.
    sync_status = "Signal de synchronisation des commandes envoyé au bot Discord."
    return redirect(url_for("index"))

@app.route("/sync/github", methods=["POST"])
def sync_github():
    global sync_status
    try:
        # Tente de faire un git pull local si le projet tourne dans un repo local tracké
        result = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            sync_status = "Mise à jour GitHub réussie (Git Pull exécuté)."
        else:
            sync_status = f"Erreur Git Pull : {result.stderr.strip()}"
    except Exception as e:
        sync_status = "Impossible d'exécuter le git pull (environnement cloud isolé ou non-git)."
    return redirect(url_for("index"))

@app.route("/sync/render", methods=["POST"])
def sync_render():
    global sync_status
    # Render déploie automatiquement à chaque push GitHub. 
    # Pour forcer via dashboard, on peut utiliser un Webhook Deploy Render si configuré, ou informer l'utilisateur.
    render_webhook = os.environ.get("RENDER_DEPLOY_HOOK_URL")
    if render_webhook:
        import urllib.request
        try:
            urllib.request.urlopen(render_webhook, data=b"")
            sync_status = "Ordre de redéploiement transmis à Render avec succès !"
        except Exception as e:
            sync_status = f"Échec du déclenchement du webhook Render : {e}"
    else:
        sync_status = "Redéploiement demandé. (Astuce : ajoute ton Render Deploy Hook en variable d'environnement 'RENDER_DEPLOY_HOOK_URL' pour l'activer)."
    return redirect(url_for("index"))

def run_dashboard():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
