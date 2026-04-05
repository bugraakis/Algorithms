import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
from collections import Counter
import os
from dotenv import load_dotenv

from leaders import CIVS, LEADERS_BY_CIV, image_url
from civ_emojis import CIV_EMOJIS

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ---------------------------------------------------------------------------
# All leaders flat list
# ---------------------------------------------------------------------------
ALL_LEADERS: list[tuple[str, str]] = [
    (civ, leader)
    for civ, leaders in LEADERS_BY_CIV.items()
    for leader in leaders
]

# Civ pages for select menus (max 25 options)
_CIV_PAGES: list[list[str]] = [CIVS[i : i + 25] for i in range(0, len(CIVS), 25)]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAPS = [
    ("Lakes",                      "🏞️"),
    ("Pangea Ultima",              "🌍"),
    ("Rich Highlands",             "⛰️"),
    ("Tilted Axis (Wraparound)",   "🌐"),
    ("Continents and Islands",     "🏝️"),
    ("Seven Seas",                 "🌊"),
    ("Primordial",                 "🌋"),
]

PLAYER_COLORS = [
    discord.Color.gold(),
    discord.Color.blue(),
    discord.Color.red(),
    discord.Color.green(),
    discord.Color.purple(),
    discord.Color.orange(),
    discord.Color.teal(),
    discord.Color.magenta(),
    discord.Color.from_rgb(255, 165, 0),
    discord.Color.from_rgb(0, 206, 209),
    discord.Color.from_rgb(220, 20, 60),
    discord.Color.from_rgb(50, 205, 50),
]

TEAM_COLORS = [
    discord.Color.red(),
    discord.Color.blue(),
    discord.Color.yellow(),
    discord.Color.green(),
    discord.Color.purple(),
    discord.Color.orange(),
]
TEAM_EMOJIS = ["🔴", "🔵", "🟡", "🟢", "🟣", "🟠"]

# Active FFA games per channel
active_ffa_games: dict[int, "FFAGame"] = {}

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_voice_members(interaction: discord.Interaction) -> list[discord.Member]:
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or member.voice is None or member.voice.channel is None:
        return []
    return [m for m in member.voice.channel.members if not m.bot]


def emoji_to_civ(emoji_str: str) -> str | None:
    """Return the civ name that matches this emoji string, or None."""
    for civ, emoji in CIV_EMOJIS.items():
        if emoji and str(emoji) == emoji_str:
            return civ
    return None


def civ_emoji_str(civ: str) -> str:
    """Return the configured emoji string for a civ, or empty string."""
    return CIV_EMOJIS.get(civ) or ""


def build_pool_embed(
    member: discord.Member,
    pool: list[tuple[str, str]],
    color: discord.Color,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎴 {member.display_name}",
        description=f"{len(pool)} lider",
        color=color,
    )
    for civ, leader in pool:
        embed.add_field(name=leader, value=civ, inline=True)
    if pool:
        embed.set_thumbnail(url=image_url(*pool[0]))
    return embed


async def send_embeds(
    channel: discord.TextChannel,
    embeds: list[discord.Embed],
    content: str = "",
):
    """Send embeds in chunks of 10 (Discord limit)."""
    first, rest = embeds[:10], embeds[10:]
    await channel.send(content=content or None, embeds=first)
    for i in range(0, len(rest), 10):
        await channel.send(embeds=rest[i : i + 10])


# ===========================================================================
# FFA GAME — new flow: map vote → per-player civ ban → pool distribution
# ===========================================================================

class FFAGame:
    def __init__(self, players: list[discord.Member]):
        self.players = players
        self.map_votes: dict[int, str] = {}   # player_id -> map_name
        self.selected_map: str | None = None
        self.bans: dict[int, str] = {}        # player_id -> civ_name

    # ---- map phase ----

    def record_map_vote(self, player_id: int, map_name: str):
        self.map_votes[player_id] = map_name

    def all_map_votes_done(self) -> bool:
        return len(self.map_votes) == len(self.players)

    def get_winning_map(self) -> str:
        counts = Counter(self.map_votes.values())
        max_votes = max(counts.values())
        tied = [m for m, v in counts.items() if v == max_votes]
        return random.choice(tied)

    # ---- ban phase ----

    def record_ban(self, player_id: int, civ: str):
        self.bans[player_id] = civ

    def all_bans_done(self) -> bool:
        return len(self.bans) == len(self.players)

    def get_banned_civs(self) -> set[str]:
        return set(self.bans.values())

    # ---- pool distribution ----

    def distribute_pools(self) -> dict[discord.Member, list[tuple[str, str]]]:
        banned_civs = self.get_banned_civs()
        remaining = [(c, l) for c, l in ALL_LEADERS if c not in banned_civs]
        random.shuffle(remaining)
        n = len(self.players)
        per_player = len(remaining) // n
        pools: dict[discord.Member, list] = {}
        for i, member in enumerate(self.players):
            pools[member] = remaining[i * per_player : (i + 1) * per_player]
        for i, pair in enumerate(remaining[n * per_player :]):
            pools[self.players[i]].append(pair)
        return pools


# ---------------------------------------------------------------------------
# Map Selection View
# ---------------------------------------------------------------------------

class MapSelectionView(discord.ui.View):
    def __init__(self, game: FFAGame):
        super().__init__(timeout=None)
        self.game = game
        for map_name, emoji in MAPS:
            btn = discord.ui.Button(
                label=map_name,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
            )
            btn.callback = self._make_vote_cb(map_name)
            self.add_item(btn)

    def build_embed(self) -> discord.Embed:
        counts = Counter(self.game.map_votes.values())
        n = len(self.game.players)
        lines = []
        for map_name, emoji in MAPS:
            c = counts.get(map_name, 0)
            bar = "█" * c + "░" * (n - c)
            lines.append(f"{emoji} **{map_name}** — {c} oy  `{bar}`")

        embed = discord.Embed(
            title="🗺️ Harita Seçimi",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        not_voted = [p for p in self.game.players if p.id not in self.game.map_votes]
        if not_voted:
            embed.add_field(
                name="⏳ Oy Bekleniyorlar",
                value=" ".join(m.mention for m in not_voted),
                inline=False,
            )
        return embed

    def _make_vote_cb(self, map_name: str):
        async def callback(interaction: discord.Interaction):
            if not any(p.id == interaction.user.id for p in self.game.players):
                await interaction.response.send_message(
                    "Bu oyuna dahil değilsin!", ephemeral=True
                )
                return

            self.game.record_map_vote(interaction.user.id, map_name)
            embed = self.build_embed()

            if self.game.all_map_votes_done():
                self.game.selected_map = self.game.get_winning_map()
                for item in self.children:
                    item.disabled = True
                embed.color = discord.Color.green()
                embed.title = f"✅ Harita Seçildi: **{self.game.selected_map}**"
                await interaction.response.edit_message(embed=embed, view=self)
                await _start_ban_phase(interaction.channel, self.game)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        return callback


# ---------------------------------------------------------------------------
# Shared Ban Phase View  (tek mesaj, herkes aynı butona basar)
# ---------------------------------------------------------------------------

class BanPhaseView(discord.ui.View):
    """Single message shared by all players. Each reacts with a civ emoji then clicks Confirm."""

    def __init__(self, game: FFAGame):
        super().__init__(timeout=None)
        self.game = game
        self.message: discord.Message | None = None  # set after send

    def build_embed(self) -> discord.Embed:
        status_lines = []
        for player in self.game.players:
            if player.id in self.game.bans:
                civ = self.game.bans[player.id]
                status_lines.append(f"✅ {player.mention} → {civ_emoji_str(civ)} **{civ}**")
            else:
                status_lines.append(f"⏳ {player.mention}")

        civ_ref = "  ".join(
            f"{civ_emoji_str(c)}`{c}`" for c in CIVS if CIV_EMOJIS.get(c)
        ) or "*(civ_emojis.py henüz doldurulmadı)*"

        embed = discord.Embed(
            title="🚫 Medeniyet Ban Aşaması",
            description=(
                "Banlamak istediğin medeniyetin emojisini **bu mesaja** ekle, "
                "ardından **✅ Onayla**'ya bas. Herkes aynı anda yapabilir."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Durum", value="\n".join(status_lines), inline=False)
        embed.add_field(name="Medeniyet Emojileri", value=civ_ref[:1024], inline=False)
        return embed

    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.green)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = next((p for p in self.game.players if p.id == interaction.user.id), None)
        if not player:
            await interaction.response.send_message("Bu oyuna dahil değilsin!", ephemeral=True)
            return

        if player.id in self.game.bans:
            await interaction.response.send_message("Zaten ban yaptın!", ephemeral=True)
            return

        # Read this specific player's reactions on the shared message
        message = await interaction.channel.fetch_message(interaction.message.id)
        banned_civ: str | None = None
        for reaction in message.reactions:
            async for user in reaction.users():
                if user.id == player.id:
                    banned_civ = emoji_to_civ(str(reaction.emoji))
                    break
            if banned_civ:
                break

        if not banned_civ:
            await interaction.response.send_message(
                "Önce banlamak istediğin medeniyetin emojisini bu mesaja ekle, sonra Onayla'ya bas.",
                ephemeral=True,
            )
            return

        self.game.record_ban(player.id, banned_civ)
        embed = self.build_embed()

        if self.game.all_bans_done():
            await interaction.response.edit_message(embed=embed, view=self)
            await _finalize_ffa_pools(interaction.channel, self.game, ban_message=self.message)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ---------------------------------------------------------------------------
# FFA phase helpers
# ---------------------------------------------------------------------------

async def _start_ban_phase(channel: discord.TextChannel, game: FFAGame):
    view = BanPhaseView(game)
    msg = await channel.send(embed=view.build_embed(), view=view)
    view.message = msg


async def _finalize_ffa_pools(
    channel: discord.TextChannel,
    game: FFAGame,
    ban_message: discord.Message | None = None,
):
    banned = game.get_banned_civs()
    pools = game.distribute_pools()
    mentions = " ".join(m.mention for m in game.players)

    ban_summary = "  ·  ".join(
        f"{civ_emoji_str(c)} **{c}**" for c in sorted(banned)
    ) or "Yok"

    header = discord.Embed(
        title=f"🗺️ {game.selected_map}  ·  ⚔️ FFA Draft Tamamlandı!",
        description=f"**Banlanan Medeniyetler:** {ban_summary}",
        color=discord.Color.gold(),
    )
    await channel.send(content=mentions, embed=header)

    for i, player in enumerate(game.players):
        embed = build_pool_embed(player, pools[player], PLAYER_COLORS[i % len(PLAYER_COLORS)])
        await channel.send(content=player.mention, embed=embed)

    # Delete the ban phase message to keep the channel clean
    if ban_message:
        try:
            await ban_message.delete()
        except discord.HTTPException:
            pass

    active_ffa_games.pop(channel.id, None)


# ===========================================================================
# TEAM DRAFT — unchanged from original
# ===========================================================================

class TeamDraftSession:
    def __init__(self, members: list[discord.Member], team_count: int):
        self.members = members
        self.team_count = team_count
        self.banned: set[tuple[str, str]] = set()

    def ban_status(self) -> str:
        banned_text = (
            ", ".join(f"{c} — {l}" for c, l in sorted(self.banned))
            if self.banned
            else "Henüz ban yok"
        )
        return (
            f"🚫 **Ban Aşaması**\n"
            f"Toplam lider: **{len(ALL_LEADERS)}**  |  "
            f"Banlanan: **{len(self.banned)}**  |  "
            f"Kalan: **{len(ALL_LEADERS) - len(self.banned)}**\n"
            f"Banlananlar: {banned_text}"
        )

    async def finalize(self, interaction: discord.Interaction):
        remaining = [p for p in ALL_LEADERS if p not in self.banned]
        random.shuffle(remaining)
        shuffled_members = self.members[:]
        random.shuffle(shuffled_members)

        teams: list[list[discord.Member]] = [[] for _ in range(self.team_count)]
        for i, m in enumerate(shuffled_members):
            teams[i % self.team_count].append(m)

        n = len(self.members)
        per_player = len(remaining) // n
        player_pools: dict[discord.Member, list] = {}
        for i, m in enumerate(self.members):
            player_pools[m] = remaining[i * per_player : (i + 1) * per_player]
        for i, pair in enumerate(remaining[n * per_player :]):
            player_pools[self.members[i]].append(pair)

        mentions = " ".join(m.mention for m in self.members)
        header = discord.Embed(
            title="🤝 Civilization VI — Takımlı Draft",
            description=f"{len(self.members)} oyuncu · {self.team_count} takım · {len(self.banned)} ban",
            color=discord.Color.green(),
        )
        all_embeds: list[discord.Embed] = [header]
        for i, team in enumerate(teams):
            team_header = discord.Embed(
                title=f"{TEAM_EMOJIS[i % len(TEAM_EMOJIS)]} Takım {i + 1}",
                color=TEAM_COLORS[i % len(TEAM_COLORS)],
            )
            all_embeds.append(team_header)
            for member in team:
                all_embeds.append(
                    build_pool_embed(member, player_pools[member], TEAM_COLORS[i % len(TEAM_COLORS)])
                )

        first, rest = all_embeds[:10], all_embeds[10:]
        await interaction.response.edit_message(content=mentions, embeds=first, view=None)
        for chunk in [rest[i : i + 10] for i in range(0, len(rest), 10)]:
            await interaction.followup.send(embeds=chunk)


class LeaderBanView(discord.ui.View):
    def __init__(self, session: TeamDraftSession, civ: str, ban_view: "TeamBanPhaseView"):
        super().__init__(timeout=120)
        self.session = session
        self.civ = civ
        self.ban_view = ban_view

        options = [
            discord.SelectOption(
                label=l,
                value=l,
                description="BANLI" if (civ, l) in session.banned else "",
                default=(civ, l) in session.banned,
            )
            for l in LEADERS_BY_CIV[civ]
        ]
        sel = discord.ui.Select(
            placeholder=f"{civ} — ban etmek istediklerini seç",
            options=options,
            min_values=0,
            max_values=len(options),
        )
        sel.callback = self._on_select
        self.add_item(sel)

        back = discord.ui.Button(label="◀ Geri", style=discord.ButtonStyle.secondary)
        back.callback = self._go_back
        self.add_item(back)

    async def _on_select(self, interaction: discord.Interaction):
        selected = set(interaction.data["values"])
        self.session.banned = {p for p in self.session.banned if p[0] != self.civ}
        for l in selected:
            self.session.banned.add((self.civ, l))
        self.ban_view._rebuild()
        await interaction.response.edit_message(content=self.session.ban_status(), view=self.ban_view)

    async def _go_back(self, interaction: discord.Interaction):
        self.ban_view._rebuild()
        await interaction.response.edit_message(content=self.session.ban_status(), view=self.ban_view)


class TeamBanPhaseView(discord.ui.View):
    def __init__(self, session: TeamDraftSession):
        super().__init__(timeout=600)
        self.session = session
        self.page = 0
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        civs = _CIV_PAGES[self.page]
        sel = discord.ui.Select(
            placeholder=f"Medeniyet seç — Sayfa {self.page + 1}/{len(_CIV_PAGES)}",
            options=[discord.SelectOption(label=c, value=c) for c in civs],
        )
        sel.callback = self._civ_chosen
        self.add_item(sel)

        if self.page > 0:
            prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary)
            prev.callback = self._prev
            self.add_item(prev)

        if self.page < len(_CIV_PAGES) - 1:
            nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary)
            nxt.callback = self._next
            self.add_item(nxt)

        remaining = len(ALL_LEADERS) - len(self.session.banned)
        start = discord.ui.Button(
            label=f"✅ Draftı Başlat ({remaining} lider)",
            style=discord.ButtonStyle.success,
        )
        start.callback = self._start
        self.add_item(start)

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        await interaction.response.edit_message(content=self.session.ban_status(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(content=self.session.ban_status(), view=self)

    async def _civ_chosen(self, interaction: discord.Interaction):
        civ = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"**{civ}** liderlerinden ban etmek istediklerini seç:",
            view=LeaderBanView(self.session, civ, self),
        )

    async def _start(self, interaction: discord.Interaction):
        self.stop()
        await self.session.finalize(interaction)


class TeamCountView(discord.ui.View):
    def __init__(self, members: list[discord.Member]):
        super().__init__(timeout=60)
        self.members = members
        for n in [2, 3, 4, 5, 6]:
            if n <= len(members):
                btn = discord.ui.Button(label=f"{n} Takım", style=discord.ButtonStyle.primary)
                btn.callback = self._make_cb(n)
                self.add_item(btn)

    def _make_cb(self, n: int):
        async def cb(interaction: discord.Interaction):
            self.stop()
            session = TeamDraftSession(self.members, team_count=n)
            view = TeamBanPhaseView(session)
            await interaction.response.edit_message(content=session.ban_status(), view=view)
        return cb


# ===========================================================================
# Slash Commands
# ===========================================================================

@bot.tree.command(name="ffa", description="FFA: Harita oylaması → Civ ban → Lider havuzu dağıtımı")
async def ffa_command(interaction: discord.Interaction):
    if interaction.channel_id in active_ffa_games:
        await interaction.response.send_message(
            "Bu kanalda zaten aktif bir FFA oyunu var!", ephemeral=True
        )
        return

    players = get_voice_members(interaction)
    if not players:
        await interaction.response.send_message(
            "❌ Bir ses kanalında olman gerekiyor!", ephemeral=True
        )
        return

    game = FFAGame(players)
    active_ffa_games[interaction.channel_id] = game

    view = MapSelectionView(game)
    embed = view.build_embed()
    embed.description = "Oynamak istediğin haritaya oy ver!\n\n" + (embed.description or "")

    await interaction.response.send_message(
        content=" ".join(p.mention for p in players),
        embed=embed,
        view=view,
    )


@bot.tree.command(name="takim", description="Takımlı ban + draft başlatır.")
async def teams_command(interaction: discord.Interaction):
    members = get_voice_members(interaction)
    if not members:
        await interaction.response.send_message(
            "❌ Bir ses kanalında olman gerekiyor!", ephemeral=True
        )
        return
    if len(members) < 2:
        await interaction.response.send_message(
            "❌ Takımlı oyun için en az 2 kişi gerekli!", ephemeral=True
        )
        return
    await interaction.response.send_message(
        content=f"Kaç takım olsun? ({len(members)} oyuncu)",
        view=TeamCountView(members),
    )


@bot.tree.command(name="yardim", description="Civ6 bot komutlarını listeler.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Civ6 Bot Komutları", color=discord.Color.blurple())
    embed.add_field(
        name="/ffa",
        value=(
            "Ses kanalındaki oyuncularla FFA başlatır.\n"
            "1️⃣ Harita oylaması (butonlar, canlı güncelleme)\n"
            "2️⃣ Herkes kendi mesajına civ emojisi koyar → Onayla\n"
            "3️⃣ Kalan liderler eşit havuzlara bölünür"
        ),
        inline=False,
    )
    embed.add_field(
        name="/takim",
        value="Takımlı draft: takım sayısını seç → lider ban → dağıtım.",
        inline=False,
    )
    embed.add_field(
        name="⚙️ Emoji Ayarı",
        value="`civ_emojis.py` dosyasına her medeniyetin Discord emojisini ekle.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ===========================================================================
# Events
# ===========================================================================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} olarak giriş yapıldı.")
    print("✅ Slash komutları senkronize edildi.")
    await bot.change_presence(activity=discord.Game(name="Civilization VI | /ffa"))


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(TOKEN)
