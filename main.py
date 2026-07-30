import os
import random
import discord
import threading
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from discord import app_commands
from discord.ext import commands, tasks
from dashboard import run_dashboard
from dashboard import reminders_db

# ── CONFIGURATION DES LOGS ───────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")

# ── FONCTIONS API FICTIVES (À adapter selon ton backend) ─────────────────────

async def api_get_list(endpoint: str) -> list:
    return []

async def api_get_json(endpoint: str) -> Optional[dict]:
    return None

async def api_post(endpoint: str, data: dict) -> None:
    pass

async def api_patch(endpoint: str, data: dict) -> None:
    pass


# ── 1. CONFIGURATION DES INTENTS & DU BOT ──────────────────────────────────────

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── DICTIONNAIRES DE STOCKAGE (EN MÉMOIRE) ────────────────────────────────────
active_guesses = {}
user_balances = {}   # user_id -> {"wallet": int, "bank": int}
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


# ── SYSTÈME DE GIVEAWAY & RÔLES TEMPORAIRES AVANCÉS ──────────────────────────

GIVEAWAY_EMOJI = "🎉"

def _parse_duration(s: str) -> Optional[int]:
    """Parse '7j'/'7d', '24h', '30m', ou un nombre brut en minutes."""
    s = s.strip().lower()
    if not s:
        return None
    if s.endswith("j") or s.endswith("d"):
        return int(s[:-1]) * 1440
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if s.endswith("m"):
        return int(s[:-1])
    return int(s)


def _fmt_duration(minutes: int) -> str:
    """Formate un nombre de minutes en chaîne lisible."""
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 1440:
        h, m = divmod(minutes, 60)
        return f"{h}h{m:02d}" if m else f"{h}h"
    d = minutes // 1440
    return f"{d} jour{'s' if d > 1 else ''}"


async def _filter_eligible(
    users: list[discord.User],
    guild: Optional[discord.Guild],
    giveaway: dict,
) -> list[discord.User]:
    """Retourne les utilisateurs qui respectent les conditions du giveaway."""
    required_role_ids: list[str] = list(giveaway.get("requiredRoleIds") or [])
    legacy_role = giveaway.get("requiredRoleId")
    if legacy_role and legacy_role not in required_role_ids:
        required_role_ids.append(legacy_role)

    forbidden_role_ids: list[str] = list(giveaway.get("forbiddenRoleIds") or [])
    min_balance: Optional[int] = giveaway.get("requiredMinBalance")

    if not required_role_ids and not forbidden_role_ids and not min_balance:
        return users

    eligible: list[discord.User] = []
    for user in users:
        if (required_role_ids or forbidden_role_ids) and guild:
            try:
                member = guild.get_member(user.id) or await guild.fetch_member(user.id)
                role_ids = {str(r.id) for r in member.roles}
                if required_role_ids and not any(rid in role_ids for rid in required_role_ids):
                    continue
                if forbidden_role_ids and any(rid in role_ids for rid in forbidden_role_ids):
                    continue
            except Exception:
                continue

        if min_balance:
            player = await api_get_json(f"/economy/players/{user.id}")
            if not player or (player.get("balance") or 0) < min_balance:
                continue

        eligible.append(user)

    return eligible


def _build_giveaway_embed(giveaway: dict, ends_ts: int) -> discord.Embed:
    lines = [f"Réagis avec {GIVEAWAY_EMOJI} pour participer !"]

    if giveaway.get("hostId"):
        lines.append(f"\n👤 **Organisé par** <@{giveaway['hostId']}>")

    conds: list[str] = []
    req_role_ids: list[str] = list(giveaway.get("requiredRoleIds") or [])
    if giveaway.get("requiredRoleId") and giveaway["requiredRoleId"] not in req_role_ids:
        req_role_ids.append(giveaway["requiredRoleId"])
    if req_role_ids:
        conds.append("✅ Rôles autorisés : " + " ".join(f"<@&{rid}>" for rid in req_role_ids))
    for rid in giveaway.get("forbiddenRoleIds") or []:
        conds.append(f"🚫 Rôle interdit : <@&{rid}>")
    if giveaway.get("requiredMinBalance"):
        conds.append(f"💰 Solde minimum : {giveaway['requiredMinBalance']:,}")
    if conds:
        lines.append("\n**Conditions**\n" + "\n".join(conds))

    rewards: list[dict] = giveaway.get("rewards") or []
    if rewards:
        reward_lines: list[str] = []
        for r in rewards:
            if r["type"] == "money":
                reward_lines.append(f"💰 {r['amount']:,} pièces")
            elif r["type"] == "role":
                dur = r.get("roleDurationMinutes")
                dur_str = f" ⏱ {_fmt_duration(dur)}" if dur else ""
                reward_lines.append(f"🎭 <@&{r['roleId']}>{dur_str}")
            elif r["type"] == "item":
                item_label = r.get("itemName") or f"Item #{r.get('itemId', '?')}"
                reward_lines.append(f"📦 {item_label}")
        lines.append("\n**Récompenses supplémentaires**\n" + "\n".join(reward_lines))

    lines.append(f"\n**Fin :** <t:{ends_ts}:R>  (<t:{ends_ts}:f>)")
    lines.append(f"**🏆 Gagnants :** {giveaway['winnersCount']}")

    embed = discord.Embed(
        title=f"{GIVEAWAY_EMOJI}  GIVEAWAY  {GIVEAWAY_EMOJI}",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Giveaway #{giveaway['id']}")
    return embed


async def _post_giveaway_embed(giveaway: dict) -> None:
    channel_id = int(giveaway["channelId"])
    giveaway_id = giveaway["id"]

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as exc:
            logger.error("Giveaway #%d: cannot find channel %s: %s", giveaway_id, channel_id, exc)
            return

    ends_at = datetime.fromisoformat(giveaway["endsAt"].replace("Z", "+00:00"))
    ends_ts = int(ends_at.timestamp())
    embed = _build_giveaway_embed(giveaway, ends_ts)

    mentioned = giveaway.get("mentionedRoleIds") or []
    mention_ping = " ".join(f"<@&{rid}>" for rid in mentioned) if mentioned else ""

    try:
        if mention_ping:
            await channel.send(mention_ping)
        msg = await channel.send(embed=embed)
        await msg.add_reaction(GIVEAWAY_EMOJI)
        await api_patch(
            f"/giveaways/{giveaway_id}",
            {
                "messageId": str(msg.id),
                "guildId": str(channel.guild.id),
            },
        )
    except Exception as exc:
        logger.error("Giveaway #%d: failed to post: %s", giveaway_id, exc)


async def _deliver_rewards(winners: list[discord.User], giveaway: dict, guild: Optional[discord.Guild]) -> None:
    rewards: list[dict] = giveaway.get("rewards") or []
    if not rewards:
        return
    for winner in winners:
        for reward in rewards:
            try:
                if reward["type"] == "money" and reward.get("amount"):
                    eco = await api_get_json(f"/economy/players/{winner.id}")
                    if eco is not None:
                        new_wallet = (eco.get("wallet") or 0) + reward["amount"]
                        await api_patch(f"/economy/players/{winner.id}", {"wallet": new_wallet})
                elif reward["type"] == "role" and reward.get("roleId") and guild:
                    member = guild.get_member(winner.id) or await guild.fetch_member(winner.id)
                    role = guild.get_role(int(reward["roleId"]))
                    if role and member:
                        await member.add_roles(role, reason=f"Giveaway #{giveaway['id']} reward")
                        dur_min = reward.get("roleDurationMinutes")
                        if dur_min and isinstance(dur_min, (int, float)):
                            expires = datetime.now(timezone.utc) + timedelta(minutes=dur_min)
                            await api_post(
                                "/temporary-roles",
                                {
                                    "userId": str(winner.id),
                                    "guildId": str(guild.id),
                                    "roleId": str(role.id),
                                    "expiresAt": expires.isoformat(),
                                    "reason": f"Giveaway #{giveaway['id']} — {_fmt_duration(dur_min)}",
                                },
                            )
                elif reward["type"] == "item" and reward.get("itemId"):
                    item_id = reward["itemId"]
                    await api_post(
                        "/inventory",
                        {
                            "userId": str(winner.id),
                            "itemId": item_id,
                            "quantity": 1,
                            "source": "giveaway",
                        },
                    )
            except Exception as exc:
                logger.error("Giveaway reward delivery error for %s: %s", winner.id, exc)


async def _end_giveaway(giveaway: dict) -> None:
    giveaway_id = giveaway["id"]
    channel_id = int(giveaway["channelId"])
    message_id = int(giveaway["messageId"])
    winners_count = giveaway["winnersCount"]

    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
    except Exception as exc:
        logger.error("Giveaway #%d: cannot fetch message: %s", giveaway_id, exc)
        await api_post(f"/giveaways/{giveaway_id}/end", {"winners": []})
        return

    raw_reactors: list[discord.User] = []
    for reaction in message.reactions:
        if str(reaction.emoji) == GIVEAWAY_EMOJI:
            async for user in reaction.users():
                if not user.bot:
                    raw_reactors.append(user)
            break

    reactors = await _filter_eligible(raw_reactors, message.guild, giveaway)

    winners: list[discord.User] = []
    if reactors:
        winners = random.sample(reactors, min(winners_count, len(reactors)))

    winner_ids = [str(w.id) for w in winners]
    await api_post(f"/giveaways/{giveaway_id}/end", {"winners": winner_ids})
    await _deliver_rewards(winners, giveaway, message.guild)

    ends_ts = int(datetime.fromisoformat(giveaway["endsAt"].replace("Z", "+00:00")).timestamp())
    
    ended_embed = discord.Embed(
        title="🎊  GIVEAWAY TERMINÉ  🎊",
        description=(
            f"**Prix :** {giveaway.get('prize', 'Lot')}\n\n"
            + (
                "**🏆 Gagnant(s) :** " + ", ".join(w.mention for w in winners)
                if winners
                else "😔 Aucun participant éligible"
            )
            + f"\n\n**Fin :** <t:{ends_ts}:f>"
        ),
        color=discord.Color.greyple(),
    )
    try:
        await message.edit(embed=ended_embed)
    except Exception:
        pass

    host_ping = f"<@{giveaway['hostId']}> " if giveaway.get("hostId") else ""
    prize_name = giveaway.get('prize', 'le lot')
    if winners:
        mention_str = " ".join(w.mention for w in winners)
        await channel.send(f"{host_ping}🎉 Félicitations {mention_str} ! Vous avez gagné **{prize_name}** !")
    else:
        await channel.send(f"{host_ping}Le giveaway **{prize_name}** s'est terminé sans participants éligibles.")


# Modals et Vues de Giveaway Interactif existants
class GiveawayParticipationView(discord.ui.View):
    def __init__(self, db_data, prize, prize_type, allowed_roles):
        super().__init__(timeout=None)
        self.db_data = db_data
        self.prize = prize
        self.prize_type = prize_type
        self.allowed_roles = allowed_roles
        self.participants = set()

    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.green, custom_id="giveaway_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_role_names = [role.name for role in interaction.user.roles]
        user_role_ids = [role.id for role in interaction.user.roles]

        banned_roles = self.db_data.get("banned_roles", [])
        for banned in banned_roles:
            if banned in user_role_names:
                await interaction.response.send_message(f"❌ Tu possèdes le rôle interdit **@{banned}** et ne peux pas participer.", ephemeral=True)
                return

        if self.allowed_roles:
            has_allowed_role = any(r in user_role_names or r in user_role_ids for r in self.allowed_roles)
            if not has_allowed_role:
                await interaction.response.send_message("❌ Tu ne possèdes pas l'un des rôles requis pour participer.", ephemeral=True)
                return

        if interaction.user.id in self.participants:
            await interaction.response.send_message("Tu participes déjà à ce giveaway !", ephemeral=True)
        else:
            self.participants.add(interaction.user.id)
            await interaction.response.send_message("✅ Ta participation a bien été enregistrée !", ephemeral=True)


class GiveawayEditModal(discord.ui.Modal, title="Modifier le Lot et la Durée"):
    prize_input = discord.ui.TextInput(label="Lot à gagner", default="Nitro Classic")
    duration_input = discord.ui.TextInput(label="Durée (en minutes)", default="5")

    def __init__(self, panel_view):
        super().__init__()
        self.panel_view = panel_view

    async def on_submit(self, interaction: discord.Interaction):
        self.panel_view.prize = self.prize_input.value
        try:
            self.panel_view.duration = int(self.duration_input.value)
        except ValueError:
            self.panel_view.duration = 5
        await self.panel_view.update_panel(interaction)


class GiveawayPanel(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.prize = "Nitro Classic"
        self.duration = 5
        self.prize_type = "Argent (Coins)"
        self.ping_role = None
        self.allowed_role = None

    async def update_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ Panneau de Configuration - Giveaway",
            description="Personnalisez les paramètres, puis cliquez sur **Lancer**.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="🎁 Lot", value=f"`{self.prize}`", inline=True)
        embed.add_field(name="⏱️ Durée", value=f"`{self.duration} minute(s)`", inline=True)
        embed.add_field(name="📌 Type de prix", value=f"`{self.prize_type}`", inline=True)
        embed.add_field(name="🔔 Rôle mentionné", value=self.ping_role.mention if self.ping_role else "`Aucun`", inline=True)
        embed.add_field(name="🛡️ Rôle requis", value=self.allowed_role.mention if self.allowed_role else "`Aucun`", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✏️ Modifier Lot & Durée", style=discord.ButtonStyle.primary, row=0)
    async def edit_modal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayEditModal(self))

    @discord.ui.select(
        placeholder="Choisir le type de prix...",
        row=1,
        options=[
            discord.SelectOption(label="Argent (Coins)", description="Donne des coins automatiquement"),
            discord.SelectOption(label="Rôle Permanent", description="Attribution d'un rôle fixe"),
            discord.SelectOption(label="Rôle Temporaire", description="Rôle temporaire"),
            discord.SelectOption(label="Niveau / XP", description="Augmente le niveau"),
            discord.SelectOption(label="Item / Autre", description="Autre type de lot")
        ]
    )
    async def select_prize_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.prize_type = select.values[0]
        await self.update_panel(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Choisir un rôle à mentionner...", row=2, min_values=0, max_values=1)
    async def select_ping_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.ping_role = select.values[0] if select.values else None
        await self.update_panel(interaction)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Choisir un rôle requis...", row=3, min_values=0, max_values=1)
    async def select_allowed_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.allowed_role = select.values[0] if select.values else None
        await self.update_panel(interaction)

    @discord.ui.button(label="🚀 Lancer le Giveaway", style=discord.ButtonStyle.green, row=4)
    async def launch_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                db_data = json.load(f)
        except FileNotFoundError:
            db_data = {"permissions": {}, "banned_roles": []}

        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"🎁 **Lot :** {self.prize}\n"
                        f"📌 **Type :** {self.prize_type}\n"
                        f"⏱️ **Durée :** {self.duration} minute(s)\n"
                        f"{f'🛡️ **Rôle requis :** {self.allowed_role.mention}' if self.allowed_role else ''}\n\n"
                        f"Clique sur le bouton **🎉 Participer** ci-dessous !",
            color=discord.Color.blue()
        )

        allowed_roles_list = [self.allowed_role.name] if self.allowed_role else []
        view = GiveawayParticipationView(db_data, self.prize, self.prize_type, allowed_roles_list)
        content_to_send = self.ping_role.mention if self.ping_role else None
        
        await interaction.message.delete()
        message = await interaction.channel.send(content=content_to_send, embed=embed, view=view)


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

@bot.tree.command(name="startguess", description="Lance une partie de Guess the Number")
@app_commands.describe(min_num="Nombre minimum", max_num="Nombre maximum")
async def start_guess(interaction: discord.Interaction, min_num: int = 1, max_num: int = 100):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tu dois être admin.", ephemeral=True)
        return

    channel_id = interaction.channel.id
    if channel_id in active_guesses:
        await interaction.response.send_message("⚠️ Une partie est déjà en cours !", ephemeral=True)
        return

    secret_number = random.randint(min_num, max_num)
    active_guesses[channel_id] = {"target": secret_number, "attempts": 0, "participants": set()}

    embed = discord.Embed(title="🔢 Devine le nombre !", description=f"Entre {min_num} et {max_num}.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="giveaway", description="Ouvre le panneau de configuration du Giveaway")
async def giveaway_command(interaction: discord.Interaction):
    panel_view = GiveawayPanel(interaction)
    embed = discord.Embed(title="⚙️ Panneau de Configuration - Giveaway", color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, view=panel_view, ephemeral=True)


@bot.tree.command(name="balance", description="Vérifie ton solde")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    bal = user_balances.setdefault(target.id, {"wallet": 200, "bank": 0})
    embed = discord.Embed(title=f"💰 Solde de {target.display_name}", color=discord.Color.gold())
    embed.add_field(name="Portefeuille", value=f"{bal['wallet']} coins")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="level", description="Vérifie ton niveau")
async def level(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    lvl = user_levels.setdefault(target.id, {"xp": 0, "level": 1})
    embed = discord.Embed(title=f"📊 Niveau de {target.display_name}", color=discord.Color.purple())
    embed.add_field(name="Niveau", value=str(lvl["level"]))
    await interaction.response.send_message(embed=embed)


# ── BOUCLES D'ARRIÈRE-PLAN ───────────────────────────────────────────────────

@tasks.loop(seconds=30)
async def giveaway_poll_loop() -> None:
    active = await api_get_list("/giveaways?status=active")
    if not active:
        return
    now = datetime.now(timezone.utc)
    for giveaway in active:
        if not giveaway.get("messageId"):
            await _post_giveaway_embed(giveaway)
            continue
        ends_at = datetime.fromisoformat(giveaway["endsAt"].replace("Z", "+00:00"))
        if now >= ends_at:
            await _end_giveaway(giveaway)


@tasks.loop(minutes=1)
async def temp_role_poll_loop() -> None:
    pending = await api_get_list("/temporary-roles/pending")
    if not pending:
        return
    for entry in pending:
        try:
            guild = bot.get_guild(int(entry["guildId"])) or await bot.fetch_guild(int(entry["guildId"]))
            member = guild.get_member(int(entry["userId"])) or await guild.fetch_member(int(entry["userId"]))
            role = guild.get_role(int(entry["roleId"]))
            if role and member and role in member.roles:
                await member.remove_roles(role, reason="Rôle temporaire expiré")
        except Exception as exc:
            logger.warning("Erreur suppression rôle temporaire: %s", exc)
        await api_patch(f"/temporary-roles/{entry['id']}/removed", {})


@tasks.loop(seconds=60)
async def background_reminder_task():
    for r_id, data in list(reminders_db.items()):
        channel = bot.get_channel(data["channel_id"])
        if not channel:
            continue
        embed = discord.Embed(title="⏰ Rappel Automatique", description=data["title"], color=discord.Color.gold())
        try:
            await channel.send(embed=embed)
        except Exception:
            pass


# ── 5. ÉVÉNEMENTS DU BOT ──────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commandes slash.")
    except Exception as e:
        print(e)
    
    if not background_reminder_task.is_running():
        background_reminder_task.start()
    if not giveaway_poll_loop.is_running():
        giveaway_poll_loop.start()
    if not temp_role_poll_loop.is_running():
        temp_role_poll_loop.start()


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
