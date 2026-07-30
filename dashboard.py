from flask import Flask, render_template_string, request, redirect, url_for
import threading

app = Flask(__name__)

# Dictionnaire de configuration des permissions (Commande -> "admin" ou "everyone")
# Plus tard, tu pourras stocker ça dans une base de données
command_permissions = {
    "startguess": "admin",
    "higherlower": "everyone",
    "roulette": "everyone",
    "casino": "everyone",
    "balance": "everyone",
    "level": "everyone"
}

# Template HTML simple et moderne intégré directement pour l'exemple
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Dashboard Bot Discord</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 40px; }
        .container { max-width: 800px; margin: auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h1 { color: #38bdf8; text-align: center; }
        table { width: 100%; margin-top: 20px; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { background-color: #334155; color: #38bdf8; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }
        .btn-admin { background-color: #ef4444; color: white; }
        .btn-everyone { background-color: #22c55e; color: white; }
        .btn:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Dashboard de Configuration</h1>
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
                    <form action="/toggle/{{ cmd }}" method="POST" style="display:inline;">
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
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_TEMPLATE, permissions=command_permissions)

@app.route("/toggle/<cmd_name>", methods=["POST"])
def toggle_permission(cmd_name):
    if cmd_name in command_permissions:
        # Alterne entre 'admin' et 'everyone'
        if command_permissions[cmd_name] == "admin":
            command_permissions[cmd_name] = "everyone"
        else:
            command_permissions[cmd_name] = "admin"
    return redirect(url_for("index"))

def run_dashboard():
    # Render écoute généralement sur le port 10000 ou via la variable d'environnement PORT
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
