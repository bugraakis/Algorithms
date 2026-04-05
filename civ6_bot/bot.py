import discord
from discord import app_commands
from discord.ext import commands
import os
import random
from dotenv import load_dotenv

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
    """Return members in the invoker's current voice channel (excluding bots)."""
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or member.voice is None or member.voice.channel is None:
        return []
    return [m for m in member.voice.channel.members if not m.bot]


def build_ffa_embed(members: list[discord.Member], channel_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="⚔️ Civilization VI — FFA",
        description=f"Ses kanalı: **{channel_name}**",
        color=discord.Color.gold(),
    )
    player_list = "\n".join(f"{i+1}. {m.mention}" for i, m in enumerate(members))
    embed.add_field(name=f"Oyuncular ({len(members)})", value=player_list or "Kimse yok", inline=False)
    embed.set_footer(text="İyi oyunlar! 🏆")
    return embed


def build_teams_embed(teams: list[list[discord.Member]]) -> discord.Embed:
    embed = discord.Embed(
        title="🤝 Civilization VI — Takımlı",
        color=discord.Color.green(),
    )
    team_emojis = ["🔴", "🔵", "🟡", "🟢", "🟣", "🟠"]
    for i, team in enumerate(teams):
        emoji = team_emojis[i] if i < len(team_emojis) else f"T{i+1}"
        members_text = "\n".join(m.mention for m in team) or "—"
        embed.add_field(name=f"{emoji} Takım {i+1}", value=members_text, inline=True)
    embed.set_footer(text="İyi oyunlar! 🏆")
    return embed


# ---------------------------------------------------------------------------
# Team count selector (shown after "Takımlı" is chosen)
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
            shuffled = self.members[:]
            random.shuffle(shuffled)
            teams = [[] for _ in range(n)]
            for idx, member in enumerate(shuffled):
                teams[idx % n].append(member)
            embed = build_teams_embed(teams)
            await interaction.response.edit_message(content=None, embed=embed, view=None)
        return callback

    async def on_timeout(self):
        pass


# ---------------------------------------------------------------------------
# Game mode selector (FFA vs Takımlı)
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
                content="❌ Bir ses kanalında olman gerekiyor!", embed=None, view=None
            )
            return
        member = interaction.guild.get_member(self.origin.user.id)
        channel_name = member.voice.channel.name
        embed = build_ffa_embed(members, channel_name)
        mentions = " ".join(m.mention for m in members)
        await interaction.response.edit_message(content=mentions, embed=embed, view=None)

    @discord.ui.button(label="🤝 Takımlı", style=discord.ButtonStyle.success)
    async def teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        members = get_voice_members(self.origin)
        if not members:
            await interaction.response.edit_message(
                content="❌ Bir ses kanalında olman gerekiyor!", embed=None, view=None
            )
            return
        if len(members) < 2:
            await interaction.response.edit_message(
                content="❌ Takımlı oyun için en az 2 kişi gerekli!", embed=None, view=None
            )
            return
        view = TeamCountView(members)
        await interaction.response.edit_message(
            content=f"Kaç takım olsun? ({len(members)} oyuncu)",
            embed=None,
            view=view,
        )

    async def on_timeout(self):
        pass


# ---------------------------------------------------------------------------
# Slash Commands
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


@bot.tree.command(name="ffa", description="Ses kanaldaki herkesi etiketler, FFA oyuncu listesi oluşturur.")
async def ffa_command(interaction: discord.Interaction):
    members = get_voice_members(interaction)
    if not members:
        await interaction.response.send_message("❌ Bir ses kanalında olman gerekiyor!", ephemeral=True)
        return
    member = interaction.guild.get_member(interaction.user.id)
    channel_name = member.voice.channel.name
    embed = build_ffa_embed(members, channel_name)
    mentions = " ".join(m.mention for m in members)
    await interaction.response.send_message(content=mentions, embed=embed)


@bot.tree.command(name="takim", description="Kaç takım istediğini sorar, oyuncuları rastgele takımlara dağıtır.")
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
    embed = discord.Embed(
        title="📖 Civ6 Bot Komutları",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="/civ",
        value="Oyun modu seçimi (FFA veya Takımlı) — ses kanalında olman gerekir.",
        inline=False,
    )
    embed.add_field(
        name="/ffa",
        value="Direkt FFA: ses kanaldaki tüm oyuncuları listeler ve etiketler.",
        inline=False,
    )
    embed.add_field(
        name="/takim",
        value="Direkt Takımlı: kaç takım istediğini seç, oyuncular rastgele dağıtılır.",
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
    print(f"✅ Slash komutları senkronize edildi.")
    await bot.change_presence(activity=discord.Game(name="Civilization VI | /civ"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN ortam değişkeni ayarlanmamış! .env dosyasını kontrol et.")
    bot.run(TOKEN)
