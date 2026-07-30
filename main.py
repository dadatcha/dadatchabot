import os
import random
import discord
from discord import app_commands
from discord.ext import commands

# ── 1. CONFIGURATION DES INTENTS & DU BOT ──────────────────────────────────────

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── DICTIONNAIRES DE STOCKAGE (EN MÉMOIRE) ────────────────────────────────────
# Pour un vrai projet persistant, tu pourras les lier à une base de données (SQLite/MongoDB)
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

    # Gain aléatoire d'XP par message (entre 15 et 25)
    xp_gain = random.randint(15, 25)
    user_levels[user_id]["xp"] += xp_gain

    current_data = user_levels[user_id]
    current_level = current_data["level"]
    current_xp = current_data["xp"]

    # Seuil d'XP nécessaire pour passer au niveau supérieur (ex: niveau * 100)
    xp_needed = current_level * 100

    if current_xp >= xp_needed:
        current_data["level"] += 1
        current_data["xp"] = 0  # Remet l'XP à 0 ou conserve le surplus
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
        user_balances[user_id] = {"wallet": 200, "bank": 0}  # 200 pièces offertes au départ

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
    # 1. Traite le jeu Guess the Number
    await GuessGameView.handle_guess_message(message)
    
    # 2. Traite l'attribution d'XP pour les niveaux
    await handle_leveling(message)
    
    # Laisse passer les autres commandes
    await bot.process_commands(message)
@bot.tree.command(name="higherlower", description="Parie des coins sur un jeu de Higher/Lower")
@app_commands.describe(bet="Montant de ta mise", choice="Choisis 'higher' (plus haut) ou 'lower' (plus bas)")
@app_commands.choices(choice=[
    app_commands.Choice(name="Plus haut (Higher)", value="higher"),
    app_commands.Choice(name="Plus bas (Lower)", value="lower")
])
async def higher_lower(interaction: discord.Interaction, bet: int, choice: str):
    user_id = interaction.user.id

    # Vérification du solde
    if user_id not in user_balances:
        user_balances[user_id] = {"wallet": 200, "bank": 0}

    if bet <= 0:
        await interaction.response.send_message("❌ La mise doit être supérieure à 0.", ephemeral=True)
        return

    if user_balances[user_id]["wallet"] < bet:
        await interaction.response.send_message("❌ Tu n'as pas assez d'argent dans ton portefeuille !", ephemeral=True)
        return

    # Déduction de la mise
    user_balances[user_id]["wallet"] -= bet

    # Génération des nombres (entre 1 et 100)
    base_number = random.randint(1, 50)
    secret_number = random.randint(1, 100)

    # Résolution
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

# ── 6. LANCEMENT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(os.environ.get("DISCORD_TOKEN"))
    
