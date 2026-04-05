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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_voice_members(interaction: discord.Interaction) -> list[discord.Member]:
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or member.voice is None or member.voice.channel is None:
        return []
    return [m for m in member.voice.channel.members if not m.bot]


def assign_leaders(members: list[discord.Member]) -> list[tuple[discord.Member, str, str]]:
    """Randomly assign a unique leader to each member.
    Returns list of (member, civ, leader) tuples."""
    # Flatten all (civ, leader) pairs and shuffle
    all_leaders = [(civ, leader) for civ, leaders in LEADERS_BY_CIV.items() for leader in leaders]
    random.shuffle(all_leaders)
    return [(m, civ, leader) for m, (civ, leader) in zip(members, all_leaders)]


def leader_embeds(assignments: list[tuple[discord.Member, str, str]]) -> list[discord.Embed]:
    """One embed per player: shows their name + leader portrait."""
    embeds = []
    for member, civ, leader in assignments:
        embed = discord.Embed(
            title=member.display_name,
            description=f"**{civ}** — {leader}",
            color=discord.Color.dark_gold(),
        )
        embed.set_thumbnail(url=image_url(civ, leader))
        embeds.append(embed)
    return embeds


def team_embeds(
    teams: list[list[tuple[discord.Member, str, str]]]
) -> list[discord.Embed]:
    """One embed per team, listing players + leaders. First player's leader as thumbnail."""
    team_colors = [
        discord.Color.red(),
        discord.Color.blue(),
        discord.Color.yellow(),
        discord.Color.green(),
        discord.Color.purple(),
        discord.Color.orange(),
    ]
    team_emojis = ["🔴", "🔵", "🟡", "🟢", "🟣", "🟠"]
    embeds = []
    for i, team in enumerate(teams):
        color = team_colors[i % len(team_colors)]
        emoji = team_emojis[i % len(team_emojis)]
        embed = discord.Embed(title=f"{emoji} Takım {i+1}", color=color)
        for member, civ, leader in team:
            embed.add_field(
                name=member.display_name,
                value=f"**{civ}** — {leader}",
                inline=False,
            )
        # Thumbnail = first player's leader portrait
        if team:
            _, civ0, leader0 = team[0]
            embed.set_thumbnail(url=image_url(civ0, leader0))
        embeds.append(embed)
    return embeds


async def send_embeds_in_chunks(
    interaction: discord.Interaction,
    header: discord.Embed,
    player_embeds: list[discord.Embed],
    mentions: str = "",
):
    """Send header + player embeds, chunking into messages of ≤10 embeds."""
    # First message: header + up to 9 player embeds
    first_chunk = [header] + player_embeds[:9]
    await interaction.response.send_message(content=mentions or None, embeds=first_chunk)
    # Remaining chunks
    rest = player_embeds[9:]
    while rest:
        chunk, rest = rest[:10], rest[10:]
        await interaction.followup.send(embeds=chunk)


# ---------------------------------------------------------------------------
# Team count selector
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
                    custom_id=f"team_{n}",
                )
                btn.callback = self._make_callback(n)
                self.add_item(btn)

    def _make_callback(self, n: int):
        async def callback(interaction: discord.Interaction):
            self.stop()
            assignments = assign_leaders(self.members)
            random.shuffle(assignments)
            teams: list[list] = [[] for _ in range(n)]
            for idx, assignment in enumerate(assignments):
                teams[idx % n].append(assignment)

            header = discord.Embed(
                title="🤝 Civilization VI — Takımlı",
                description=f"{len(self.members)} oyuncu, {n} takım",
                color=discord.Color.green(),
            )
            embeds = [header] + team_embeds(teams)
            await interaction.response.edit_message(content=None, embeds=embeds, view=None)
        return callback

    async def on_timeout(self):
        pass


# ---------------------------------------------------------------------------
# Game mode selector
# ---------------------------------------------------------------------------

class GameModeView(discord.ui.View):
    def __init__(self, origin: discord.Interaction):
        super().__init__(timeout=60)
        self.origin = origin

    @discord.ui.button(label="⚔️ FFA", style=discord.ButtonStyle.danger)
    async def ffa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        members = get_voice_members(self.origin)
        if not members:
            await interaction.response.edit_message(
                content="❌ Bir ses kanalında olman gerekiyor!", embeds=[], view=None
            )
            return
        assignments = assign_leaders(members)
        channel_name = interaction.guild.get_member(self.origin.user.id).voice.channel.name
        header = discord.Embed(
            title="⚔️ Civilization VI — FFA",
            description=f"Ses kanalı: **{channel_name}** · {len(members)} oyuncu",
            color=discord.Color.gold(),
        )
        embeds = [header] + leader_embeds(assignments)
        mentions = " ".join(m.mention for m in members)
        await interaction.response.edit_message(content=mentions, embeds=embeds, view=None)

    @discord.ui.button(label="🤝 Takımlı", style=discord.ButtonStyle.success)
    async def teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    async def on_timeout(self):
        pass


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="civ", description="Civ 6 oyun kurulumunu başlatır: FFA veya Takımlı seçimi.")
async def civ_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Civilization VI",
        description="Oyun modunu seçin:",
        color=discord.Color.blurple(),
    )
    view = GameModeView(interaction)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="ffa", description="Ses kanaldaki herkese rastgele lider atar, FFA draft yapar.")
async def ffa_command(interaction: discord.Interaction):
    members = get_voice_members(interaction)
    if not members:
        await interaction.response.send_message("❌ Bir ses kanalında olman gerekiyor!", ephemeral=True)
        return
    assignments = assign_leaders(members)
    channel_name = interaction.guild.get_member(interaction.user.id).voice.channel.name
    header = discord.Embed(
        title="⚔️ Civilization VI — FFA",
        description=f"Ses kanalı: **{channel_name}** · {len(members)} oyuncu",
        color=discord.Color.gold(),
    )
    mentions = " ".join(m.mention for m in members)
    await send_embeds_in_chunks(interaction, header, leader_embeds(assignments), mentions)


@bot.tree.command(name="takim", description="Kaç takım istediğini sorar, oyuncuları ve liderleri rastgele dağıtır.")
async def teams_command(interaction: discord.Interaction):
    members = get_voice_members(interaction)
    if not members:
        await interaction.response.send_message("❌ Bir ses kanalında olman gerekiyor!", ephemeral=True)
        return
    if len(members) < 2:
        await interaction.response.send_message("❌ Takımlı oyun için en az 2 kişi gerekli!", ephemeral=True)
        return
    view = TeamCountView(members)
    await interaction.response.send_message(f"Kaç takım olsun? ({len(members)} oyuncu)", view=view)


@bot.tree.command(name="yardim", description="Civ6 bot komutlarını listeler.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Civ6 Bot Komutları", color=discord.Color.blurple())
    embed.add_field(name="/civ",   value="Oyun modu seçimi (FFA veya Takımlı).", inline=False)
    embed.add_field(name="/ffa",   value="Direkt FFA draft: herkese rastgele lider atar, lider portresiyle gösterir.", inline=False)
    embed.add_field(name="/takim", value="Direkt Takımlı: kaç takım istediğini seç, oyuncular ve liderler rastgele dağıtılır.", inline=False)
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
        raise RuntimeError("DISCORD_TOKEN ortam değişkeni ayarlanmamış! .env dosyasını kontrol et.")
    bot.run(TOKEN)
