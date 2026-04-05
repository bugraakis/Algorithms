import discord
from discord.ext import commands
import os
import random
from dotenv import load_dotenv
from leaders import CIVS, LEADERS_BY_CIV, image_url

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

ALL_LEADERS: list[tuple[str, str]] = [
    (civ, leader)
    for civ, leaders in LEADERS_BY_CIV.items()
    for leader in leaders
]
# Civ pages for select menus (max 25 options each)
_CIV_PAGES: list[list[str]] = [CIVS[i : i + 25] for i in range(0, len(CIVS), 25)]

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_voice_members(interaction: discord.Interaction) -> list[discord.Member]:
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or member.voice is None or member.voice.channel is None:
        return []
    return [m for m in member.voice.channel.members if not m.bot]


def distribute_leaders(
    members: list[discord.Member], banned: set[tuple[str, str]]
) -> dict[discord.Member, list[tuple[str, str]]]:
    """Shuffle remaining leaders and deal them as evenly as possible."""
    remaining = [pair for pair in ALL_LEADERS if pair not in banned]
    random.shuffle(remaining)
    n = len(members)
    per_player = len(remaining) // n
    pools: dict[discord.Member, list] = {m: [] for m in members}
    for i, member in enumerate(members):
        pools[member] = remaining[i * per_player : (i + 1) * per_player]
    # Distribute leftover leaders one each to random players
    leftover = remaining[n * per_player :]
    for i, pair in enumerate(leftover):
        pools[members[i]].append(pair)
    return pools


def build_pool_embed(
    member: discord.Member,
    pool: list[tuple[str, str]],
    color: discord.Color = discord.Color.dark_gold(),
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
    interaction: discord.Interaction,
    embeds: list[discord.Embed],
    content: str = "",
    edit: bool = False,
):
    """Send a list of embeds, chunking to ≤10 per message."""
    first, rest = embeds[:10], embeds[10:]
    if edit:
        await interaction.response.edit_message(
            content=content or None, embeds=first, view=None
        )
    else:
        await interaction.response.send_message(
            content=content or None, embeds=first
        )
    while rest:
        chunk, rest = rest[:10], rest[10:]
        await interaction.followup.send(embeds=chunk)


# ---------------------------------------------------------------------------
# Draft session — holds state through the ban phase
# ---------------------------------------------------------------------------

class DraftSession:
    def __init__(
        self,
        members: list[discord.Member],
        mode: str,  # "ffa" | "teams"
        team_count: int = 0,
    ):
        self.members = members
        self.mode = mode
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
        pools = distribute_leaders(self.members, self.banned)
        mentions = " ".join(m.mention for m in self.members)

        if self.mode == "ffa":
            header = discord.Embed(
                title="⚔️ Civilization VI — FFA Draft",
                description=(
                    f"{len(self.members)} oyuncu · "
                    f"{len(self.banned)} ban · "
                    f"kişi başı ~{len(ALL_LEADERS) - len(self.banned)} / {len(self.members)} lider"
                ),
                color=discord.Color.gold(),
            )
            player_embeds = [
                build_pool_embed(m, pools[m], PLAYER_COLORS[i % len(PLAYER_COLORS)])
                for i, m in enumerate(self.members)
            ]
            await send_embeds(interaction, [header] + player_embeds, mentions, edit=True)

        else:
            # Assign teams
            shuffled = self.members[:]
            random.shuffle(shuffled)
            teams: list[list[discord.Member]] = [[] for _ in range(self.team_count)]
            for i, m in enumerate(shuffled):
                teams[i % self.team_count].append(m)

            header = discord.Embed(
                title="🤝 Civilization VI — Takımlı Draft",
                description=(
                    f"{len(self.members)} oyuncu · "
                    f"{self.team_count} takım · "
                    f"{len(self.banned)} ban"
                ),
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
                        build_pool_embed(member, pools[member], TEAM_COLORS[i % len(TEAM_COLORS)])
                    )
            await send_embeds(interaction, all_embeds, mentions, edit=True)


# ---------------------------------------------------------------------------
# Leader ban selector (shown after a civ is chosen)
# ---------------------------------------------------------------------------

class LeaderBanView(discord.ui.View):
    def __init__(self, session: DraftSession, civ: str, ban_view: "BanPhaseView"):
        super().__init__(timeout=120)
        self.session = session
        self.civ = civ
        self.ban_view = ban_view

        leaders = LEADERS_BY_CIV[civ]
        options = [
            discord.SelectOption(
                label=l,
                value=l,
                description="BANLI" if (civ, l) in session.banned else "",
                default=(civ, l) in session.banned,
            )
            for l in leaders
        ]
        sel = discord.ui.Select(
            placeholder=f"{civ} — ban etmek istediklerini seç (boş = ban yok)",
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
        # Remove all bans for this civ then re-add selected
        self.session.banned = {p for p in self.session.banned if p[0] != self.civ}
        for l in selected:
            self.session.banned.add((self.civ, l))
        self.ban_view._rebuild()
        await interaction.response.edit_message(
            content=self.session.ban_status(), view=self.ban_view
        )

    async def _go_back(self, interaction: discord.Interaction):
        self.ban_view._rebuild()
        await interaction.response.edit_message(
            content=self.session.ban_status(), view=self.ban_view
        )


# ---------------------------------------------------------------------------
# Ban phase view — paginated civ list + Start Draft button
# ---------------------------------------------------------------------------

class BanPhaseView(discord.ui.View):
    def __init__(self, session: DraftSession):
        super().__init__(timeout=600)
        self.session = session
        self.page = 0
        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        civs = _CIV_PAGES[self.page]
        civ_sel = discord.ui.Select(
            placeholder=f"Medeniyet seç — Sayfa {self.page + 1}/{len(_CIV_PAGES)}",
            options=[discord.SelectOption(label=c, value=c) for c in civs],
        )
        civ_sel.callback = self._civ_chosen
        self.add_item(civ_sel)

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
        await interaction.response.edit_message(
            content=self.session.ban_status(), view=self
        )

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(
            content=self.session.ban_status(), view=self
        )

    async def _civ_chosen(self, interaction: discord.Interaction):
        civ = interaction.data["values"][0]
        view = LeaderBanView(self.session, civ, self)
        await interaction.response.edit_message(
            content=f"**{civ}** liderlerinden ban etmek istediklerini seç:",
            view=view,
        )

    async def _start(self, interaction: discord.Interaction):
        self.stop()
        await self.session.finalize(interaction)


# ---------------------------------------------------------------------------
# Team count selector → ban phase
# ---------------------------------------------------------------------------

class TeamCountView(discord.ui.View):
    def __init__(self, members: list[discord.Member]):
        super().__init__(timeout=60)
        self.members = members
        for n in [2, 3, 4, 5, 6]:
            if n <= len(members):
                btn = discord.ui.Button(
                    label=f"{n} Takım",
                    style=discord.ButtonStyle.primary,
                )
                btn.callback = self._make_cb(n)
                self.add_item(btn)

    def _make_cb(self, n: int):
        async def cb(interaction: discord.Interaction):
            self.stop()
            session = DraftSession(self.members, "teams", team_count=n)
            view = BanPhaseView(session)
            await interaction.response.edit_message(
                content=session.ban_status(), view=view
            )
        return cb


# ---------------------------------------------------------------------------
# Game mode selector
# ---------------------------------------------------------------------------

class GameModeView(discord.ui.View):
    def __init__(self, origin: discord.Interaction):
        super().__init__(timeout=60)
        self.origin = origin

    @discord.ui.button(label="⚔️ FFA", style=discord.ButtonStyle.danger)
    async def ffa_btn(self, interaction: discord.Interaction, _btn):
        self.stop()
        members = get_voice_members(self.origin)
        if not members:
            await interaction.response.edit_message(
                content="❌ Bir ses kanalında olman gerekiyor!", embeds=[], view=None
            )
            return
        session = DraftSession(members, "ffa")
        view = BanPhaseView(session)
        await interaction.response.edit_message(
            content=session.ban_status(), embeds=[], view=view
        )

    @discord.ui.button(label="🤝 Takımlı", style=discord.ButtonStyle.success)
    async def teams_btn(self, interaction: discord.Interaction, _btn):
        self.stop()
        members = get_voice_members(self.origin)
        if not members:
            await interaction.response.edit_message(
                content="❌ Bir ses kanalında olman gerekiyor!", embeds=[], view=None
            )
            return
        if len(members) < 2:
            await interaction.response.edit_message(
                content="❌ Takımlı oyun için en az 2 kişi gerekli!", embeds=[], view=None
            )
            return
        view = TeamCountView(members)
        await interaction.response.edit_message(
            content=f"Kaç takım olsun? ({len(members)} oyuncu)",
            embeds=[],
            view=view,
        )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="civ", description="Civ 6 oyun kurulumu: FFA veya Takımlı seçimi.")
async def civ_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Civilization VI",
        description="Oyun modunu seçin:",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(embed=embed, view=GameModeView(interaction))


@bot.tree.command(name="ffa", description="FFA ban + draft başlatır.")
async def ffa_command(interaction: discord.Interaction):
    members = get_voice_members(interaction)
    if not members:
        await interaction.response.send_message(
            "❌ Bir ses kanalında olman gerekiyor!", ephemeral=True
        )
        return
    session = DraftSession(members, "ffa")
    view = BanPhaseView(session)
    await interaction.response.send_message(content=session.ban_status(), view=view)


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
    embed.add_field(name="/civ",   value="Oyun modu seçimi (FFA veya Takımlı).", inline=False)
    embed.add_field(
        name="/ffa",
        value="FFA drafti başlatır: ban aşaması → kalan liderler oyuncular arasında eşit dağıtılır.",
        inline=False,
    )
    embed.add_field(
        name="/takim",
        value="Takımlı draft: takım sayısını seç → ban aşaması → liderler eşit dağıtılır.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} olarak giriş yapıldı.")
    print("✅ Slash komutları senkronize edildi.")
    await bot.change_presence(activity=discord.Game(name="Civilization VI | /civ"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN ortam değişkeni ayarlanmamış!")
    bot.run(TOKEN)
