import random
import discord
from discord import app_commands
from discord.ext import commands

# Dictionnaire pour stocker l'état du jeu par salon (channel_id -> état)
active_guesses = {}

class GuessGameView:
    @staticmethod
    async def handle_guess_message(message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id
        if channel_id not in active_guesses:
            return

        game = active_guesses[channel_id]
        
        # Vérifie si le message est un nombre valide
        try:
            guess = int(message.content.strip())
        except ValueError:
            return  # Ce n'est pas un nombre, on ignore (ou on laisse les gens spammer)

        # Enregistre le participant
        game["participants"].add(message.author.id)
        game["attempts"] += 1

        if guess == game["target"]:
            # Le nombre a été trouvé !
            winner = message.author
            target_num = game["target"]
            total_attempts = game["attempts"]
            total_participants = len(game["participants"])

            # Nettoyage de l'état
            del active_guesses[channel_id]

            # Verrouillage du salon (retire la permission d'écrire pour @everyone)
            try:
                await message.channel.set_permissions(
                    message.guild.default_role, send_messages=False
                )
            except discord.Forbidden:
                pass  # Si le bot n'a pas les permissions nécessaires

            # Création de l'embed récapitulatif
            embed = discord.Embed(
                title="🎯 Nombre Mystère Trouvé !",
                color=discord.Color.green(),
                description=f"Le jeu est terminé, le salon a été verrouillé."
            )
            embed.add_field(name="Nombre mystère", value=f"**{target_num}**", inline=False)
            embed.add_field(name="Gagnant", value=winner.mention, inline=False)
            embed.add_field(name="Participants", value=f"**{total_participants}** membre(s)", inline=True)
            embed.add_field(name="Tentatives totales", value=f"**{total_attempts}** essai(s)", inline=True)

            await message.channel.send(embed=embed)

        elif guess < game["target"]:
            # Optionnel : réagir ou donner un indice si tu veux, 
            # mais tu as demandé un mode spam libre, donc on peut être silencieux ou réagir discrètement.
            pass
        else:
            pass


# Commande Slash pour lancer le jeu (Admin ou selon configuration)
@app_commands.command(name="startguess", description="Lance une partie de Guess the Number dans le salon")
@app_commands.describe(min_num="Nombre minimum", max_num="Nombre maximum")
async def start_guess(interaction: discord.Interaction, min_num: int = 1, max_num: int = 100):
    # Vérification admin rapide (à lier plus tard avec ton dashboard)
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

    # Initialisation de la partie
    active_guesses[channel_id] = {
        "target": secret_number,
        "attempts": 0,
        "participants": set()
    }

    # S'assurer que les membres peuvent parler (déverrouillage au cas où)
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
