import os
import random
import discord
import threading
from discord import app_commands
from discord.ext import commands
from dashboard import run_dashboard
from discord.ext import tasks
from dashboard import reminders_db

# ── 1. CONFIGURATION DES INTENTS & DU BOT ──────────────────────────────────────

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── DICTIONNAIRES DE STOCKAGE (EN MÉMOIRE) ────────────────────────────────────
active_guesses = {}
user_balances = {}  # user_id -> {"wallet": int, "bank": int}
user_levels = {}    # user_id -> {"xp": int, "level": int}


# ── 2. LOGIQUE DU JEU "GUESS THE NUMBER" ───────────────────────────────────────

class GuessGameView:
    @staticmethod
    async def handle_guess_message(message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id
        if channel_id not in active_guesses:
            return

        game = active_guesses[channel_id]
        
        try:
            guess = int(message.content.strip())
        except ValueError:
            return

        game["participants"].add(message.author.id)
        game["attempts"] += 1

        if guess == game["target"]:
            winner = message.author
            target_num = game["target"]
            total_attempts = game["attempts"]
            total_participants = len(game["participants"])

            del active_guesses[channel_id]

            try:
                await message.channel.set_permissions(
                    message.guild.default_role, send_messages=False
                )
            except discord.Forbidden:
                pass

            embed = discord.Embed(
                title="🎯 Nombre Mystère Trouvé !",
                color=discord.Color.green(),
                description="Le jeu est terminé, le salon a été verrouillé."
            )
            embed.add_field(name="Nombre mystère", value=f"**{target_num}**", inline=False)
            embed.add_field(name="Gagnant", value=winner.mention, inline=False)
            embed.add_field(name="Participants", value=f"**{total_participants}** membre(s)", inline=True)
            embed.add_field(name="Tentatives totales", value=f"**{total_attempts}** essai(s)", inline=True)

            await message.channel.send(embed=embed)


# ── 3. SYSTÈME DE NIVEAUX (XP) ────────────────────────────────────────────────

async def handle_leveling(message: discord.Message):
    if message.author.bot:
        return

    user_id = message.author.id
    if user_id not in user_levels:
        user_levels[user_id] = {"xp": 0, "level": 1}

    xp_gain = random.randint(15, 25)
    user_levels[user_id]["xp"] += xp_gain

    current_data = user_levels[user_id]
    current_level = current_data["level"]
    current_xp = current_data["xp"]
    xp_needed = current_level * 100

    if current_xp >= xp_needed:
        current_data["level"] += 1
        current_data["xp"] = 0
        await message.channel.send(
            f"🎉 Félicitations {message.author.mention} ! Tu passes au niveau **{current_data['level']}** !"
        )


# ── 4. COMMANDES SLASH (JEUX & ÉCONOMIE & NIVEAUX) ───────────────────────────

@bot.tree.command(name="startguess", description="Lance une partie de Guess the Number dans le salon")
@app_commands.describe(min_num="Nombre minimum", max_num="Nombre maximum")
async def start_guess(interaction: discord.Interaction, min_num: int = 1, max_num: int = 100):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu dois être admin pour lancer ce jeu.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    if channel_id in active_guesses:
        await interaction.response.send_message("⚠️ Une partie est déjà en cours dans ce salon !", ephemeral=True)
        return

    if min_num >= max_num:
        await interaction.response.send_message("❌ Le nombre minimum doit être inférieur au maximum.", ephemeral=True)
        return

    secret_number = random.randint(min_num, max_num)

    active_guesses[channel_id] = {
        "target": secret_number,
        "attempts": 0,
        "participants": set()
    }

    try:
        await interaction.channel.set_permissions(
            interaction.guild.default_role, send_messages=True
        )
    except discord.Forbidden:
        pass

    embed = discord.Embed(
        title="🔢 Devine le nombre !",
        description=f"Un nombre mystère entre **{min_num}** et **{max_num}** a été choisi !\n"
                    f"Envoyez vos propositions directement dans ce salon.\n"
                    f"Le salon sera verrouillé dès que quelqu'un aura trouvé !",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="balance", description="Vérifie ton solde ou celui d'un autre membre")
@app_commands.describe(member="Le membre à consulter")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user_id = target.id

    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    bal = user_balances[user_id]
    embed = discord.Embed(
        title=f"💰 Portefeuille de {target.display_name}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Portefeuille", value=f"**{bal['wallet']}** coins", inline=True)
    embed.add_field(name="Banque", value=f"**{bal['bank']}** coins", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="level", description="Vérifie ton niveau actuel ou celui d'un membre")
@app_commands.describe(member="Le membre à consulter")
async def level(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user_id = target.id

    if user_id not in user_levels:
        user_levels[user_id] = {"xp": 0, "level": 1}

    lvl_data = user_levels[user_id]
    xp_needed = lvl_data["level"] * 100

    embed = discord.Embed(
        title=f"📊 Niveau de {target.display_name}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Niveau", value=f"**{lvl_data['level']}**", inline=True)
    embed.add_field(name="XP", value=f"**{lvl_data['xp']} / {xp_needed}**", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="higherlower", description="Parie des coins sur un jeu de Higher/Lower")
@app_commands.describe(bet="Montant de ta mise", choice="Choisis 'higher' (plus haut) ou 'lower' (plus bas)")
@app_commands.choices(choice=[
    app_commands.Choice(name="Plus haut (Higher)", value="higher"),
    app_commands.Choice(name="Plus bas (Lower)", value="lower")
])
async def higher_lower(interaction: discord.Interaction, bet: int, choice: str):
    user_id = interaction.user.id

    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    if bet <= 0:
        await interaction.response.send_message("❌ La mise doit être supérieure à 0.", ephemeral=True)
        return

    if user_balances[user_id]["wallet"] < bet:
        await interaction.response.send_message("❌ Tu n'as pas assez d'argent dans ton portefeuille !", ephemeral=True)
        return

    user_balances[user_id]["wallet"] -= bet

    base_number = random.randint(1, 50)
    secret_number = random.randint(1, 100)

    won = False
    if choice == "higher" and secret_number > base_number:
        won = True
    elif choice == "lower" and secret_number < base_number:
        won = True

    embed = discord.Embed(
        title="🎲 Higher / Lower",
        color=discord.Color.orange()
    )
    embed.add_field(name="Nombre de base", value=f"**{base_number}**", inline=True)
    embed.add_field(name="Ton choix", value=f"**{choice.upper()}**", inline=True)
    embed.add_field(name="Nombre mystère", value=f"**{secret_number}**", inline=False)

    if won:
        winnings = bet * 2
        user_balances[user_id]["wallet"] += winnings
        embed.description = f"🎉 Gagné ! Tu remportes **{winnings}** coins !"
        embed.color = discord.Color.green()
    else:
        embed.description = f"😢 Perdu ! Tu as perdu ta mise de **{bet}** coins."
        embed.color = discord.Color.red()

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roulette", description="Parie des coins à la roulette (red, black ou green)")
@app_commands.describe(bet="Montant de ta mise", choice="Choisis red, black ou green")
@app_commands.choices(choice=[
    app_commands.Choice(name="Rouge (x2)", value="red"),
    app_commands.Choice(name="Noir (x2)", value="black"),
    app_commands.Choice(name="Vert / Zéro (x14)", value="green")
])
async def roulette(interaction: discord.Interaction, bet: int, choice: str):
    user_id = interaction.user.id

    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    if bet <= 0:
        await interaction.response.send_message("❌ La mise doit être supérieure à 0.", ephemeral=True)
        return

    if user_balances[user_id]["wallet"] < bet:
        await interaction.response.send_message("❌ Tu n'as pas assez d'argent dans ton portefeuille !", ephemeral=True)
        return

    user_balances[user_id]["wallet"] -= bet

    roll = random.choices(["red", "black", "green"], weights=[45, 45, 10])[0]

    embed = discord.Embed(title="🎰 Roulette Casino", color=discord.Color.dark_embed())
    embed.add_field(name="Ta mise", value=f"**{bet}** coins sur **{choice.upper()}**", inline=False)
    embed.add_field(name="Résultat de la roue", value=f"**{roll.upper()}**", inline=False)

    if roll == choice:
        multiplier = 14 if roll == "green" else 2
        winnings = bet * multiplier
        user_balances[user_id]["wallet"] += winnings
        embed.description = f"🎉 Jackpot ! C'est tombé sur **{roll.upper()}**. Tu gagnes **{winnings}** coins !"
        embed.color = discord.Color.green()
    else:
        embed.description = f"😢 Perdu ! C'est tombé sur **{roll.upper()}**. Tu perds ta mise."
        embed.color = discord.Color.red()

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="casino", description="Joue à la machine à sous (Slot Machine)")
@app_commands.describe(bet="Montant de ta mise")
async def casino(interaction: discord.Interaction, bet: int):
    user_id = interaction.user.id

    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    if bet <= 0:
        await interaction.response.send_message("❌ La mise doit être supérieure à 0.", ephemeral=True)
        return

    if user_balances[user_id]["wallet"] < bet:
        await interaction.response.send_message("❌ Tu n'as pas assez d'argent dans ton portefeuille !", ephemeral=True)
        return

    user_balances[user_id]["wallet"] -= bet

    symbols = ["🍒", "🍋", "🍊", "🔔", "⭐", "💎"]
    weights = [35, 30, 20, 10, 4, 1]

    result = random.choices(symbols, weights=weights, k=3)

    embed = discord.Embed(title="🎰 Machine à Sous", color=discord.Color.blue())
    embed.add_field(name="Tirage", value=f"| {result[0]} | {result[1]} | {result[2]} |", inline=False)

    if result[0] == result[1] == result[2]:
        multiplier_dict = {"🍒": 5, "🍋": 10, "🍊": 15, "🔔": 25, "⭐": 50, "💎": 100}
        mult = multiplier_dict.get(result[0], 5)
        winnings = bet * mult
        user_balances[user_id]["wallet"] += winnings
        embed.description = f"🎉 TRIPLÉ ! 3 symboles **{result[0]}** ! Tu remportes **{winnings}** coins (x{mult}) !"
        embed.color = discord.Color.green()
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        winnings = int(bet * 1.5)
        user_balances[user_id]["wallet"] += winnings
        embed.description = f"✨ Pas mal ! 2 symboles identiques. Tu récupères **{winnings}** coins."
        embed.color = discord.Color.gold()
    else:
        embed.description = f"😢 Rien du tout ! Tu perds ta mise de **{bet}** coins."
        embed.color = discord.Color.red()

    await interaction.response.send_message(embed=embed)

# ── COMMANDES ADMINISTRATEUR (ÉCONOMIE & NIVEAUX) ─────────────────────────────

@bot.tree.command(name="addmoney", description="[ADMIN] Ajoute des coins à l'argent d'un membre")
@app_commands.describe(member="Le membre ciblé", amount="Le montant à ajouter")
async def add_money(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    user_id = member.id
    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    user_balances[user_id]["wallet"] += amount

    embed = discord.Embed(
        title="💰 Gestion de l'argent (Ajout)",
        description=f"✅ **{amount}** coins ont été ajoutés au portefeuille de {member.mention}.\n"
                    f"Nouveau solde : **{user_balances[user_id]['wallet']}** coins.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="removemoney", description="[ADMIN] Retire des coins à l'argent d'un membre")
@app_commands.describe(member="Le membre ciblé", amount="Le montant à retirer")
async def remove_money(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    user_id = member.id
    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    # Empêche le portefeuille de passer en négatif
    if user_balances[user_id]["wallet"] < amount:
        user_balances[user_id]["wallet"] = 0
    else:
        user_balances[user_id]["wallet"] -= amount

    embed = discord.Embed(
        title="💰 Gestion de l'argent (Retrait)",
        description=f"⚠️ **{amount}** coins ont été retirés du portefeuille de {member.mention}.\n"
                    f"Nouveau solde : **{user_balances[user_id]['wallet']}** coins.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setlevel", description="[ADMIN] Modifie directement le niveau d'un membre")
@app_commands.describe(member="Le membre ciblé", level_num="Le nouveau niveau")
async def set_level(interaction: discord.Interaction, member: discord.Member, level_num: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
        return

    if level_num < 1:
        await interaction.response.send_message("❌ Le niveau minimum est 1.", ephemeral=True)
        return

    user_id = member.id
    if user_id not in user_levels:
        user_levels[user_id] = {"xp": 0, "level": 1}

    user_levels[user_id]["level"] = level_num
    user_levels[user_id]["xp"] = 0  # Remet l'XP à 0 pour repartir sur de bonnes bases

    embed = discord.Embed(
        title="📊 Gestion des Niveaux",
        description=f"✅ Le niveau de {member.mention} a été défini à **{level_num}** (XP réinitialisée à 0).",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# ── BOUCLE D'ENVOI AUTOMATIQUE DES RAPPELS ──────────────────────────────────

@tasks.loop(minutes=1)
async def check_and_send_reminders():
    if not reminders_db:
        return
    
    # On utilise une vérification par minute. Pour gérer des intervalles précis, 
    # on s'appuie sur le compteur de temps ou on simplifie en vérifiant si le temps s'est écoulé.
    # Alternative plus robuste : exécuter une boucle globale ou stocker les objets tasks.
    pass

# Alternative avec une boucle dynamique par rappel ou vérification simple :
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commandes slash.")
    except Exception as e:
        print(e)
    
    # Lancement de la tâche de fond des rappels si elle n'est pas déjà lancée
    if not background_reminder_task.is_running():
        background_reminder_task.start()

@tasks.loop(seconds=60)
async def background_reminder_task():
    for r_id, data in list(reminders_db.items()):
        channel = bot.get_channel(data["channel_id"])
        if not channel:
            continue
        
        # Recherche du rôle dans toutes les guildes où le bot est présent
        target_role = None
        for guild in bot.guilds:
            role = discord.utils.get(guild.roles, name=data["role_name"])
            if role:
                target_role = role
                break
        
        mention_str = target_role.mention if target_role else f"@{data['role_name']}"
        
        embed = discord.Embed(
            title="⏰ Rappel Automatique",
            description=f"{mention_str} {data['title']}",
            color=discord.Color.gold()
        )
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

# N'oublie pas de gérer le timing exact des intervalles si besoin, 
# cette boucle envoie ici un signal de test toutes les X minutes selon la logique de ton choix.

# ── 5. ÉVÉNEMENTS DU BOT ──────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commandes slash.")
    except Exception as e:
        print(e)

@bot.event
async def on_message(message: discord.Message):
    await GuessGameView.handle_guess_message(message)
    await handle_leveling(message)
    await bot.process_commands(message)


# ── 6. LANCEMENT GLOBAL ──────────────────────────────────────────────────────

if __name__ == "__main__":
    dashboard_thread = threading.Thread(target=run_dashboard)
    dashboard_thread.daemon = True
    dashboard_thread.start()
    print("🌐 Dashboard web démarré en arrière-plan.")

    bot.run(os.environ.get("DISCORD_TOKEN"))
