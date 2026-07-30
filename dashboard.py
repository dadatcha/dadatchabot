import os
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
    "setlevel": "admin"
}

# Stockage en mémoire des rappels (id -> {"title": str, "time": str})
reminders_db = {}
reminder_counter = 1

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
        .btn:hover { opacity: 0.9; }
        form.inline-form { display: inline; }
        .form-group { margin-top: 15px; display: flex; gap: 10px; }
        input[type="text"] { flex: 1; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Dashboard de Configuration</h1>
        
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
    return render_template_string(DASHBOARD_TEMPLATE, permissions=command_permissions, reminders=reminders_db)

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

def run_dashboard():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
