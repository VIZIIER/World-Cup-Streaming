import asyncio
import logging
import os
import signal
import sys
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from iptv_client import IPTVClient
from stream_manager import StreamManager

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("iptv_bot")


# ── Bot Setup ─────────────────────────────────────────────────────────────────
class IPTVBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

        self.config = Config()
        self.iptv = IPTVClient(self.config)
        self.stream_managers: dict[int, StreamManager] = {}  # guild_id → manager

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    async def setup_hook(self):
        await self.tree.sync()
        log.info("Slash commands synced globally.")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🏆 World Cup Live",
            )
        )
        cleanup_idle.start(self)

    async def close(self):
        log.info("Shutting down — disconnecting all voice clients …")
        for manager in list(self.stream_managers.values()):
            await manager.stop()
        await super().close()

    # ── Helpers ───────────────────────────────────────────────────────────────
    def get_manager(self, guild_id: int) -> Optional[StreamManager]:
        return self.stream_managers.get(guild_id)

    def set_manager(self, guild_id: int, manager: StreamManager):
        self.stream_managers[guild_id] = manager

    async def remove_manager(self, guild_id: int):
        manager = self.stream_managers.pop(guild_id, None)
        if manager:
            await manager.stop()


# ── Task: clean up empty voice channels ──────────────────────────────────────
@tasks.loop(minutes=2)
async def cleanup_idle(bot: IPTVBot):
    for guild_id, manager in list(bot.stream_managers.items()):
        vc = manager.voice_client
        if vc and len(vc.channel.members) <= 1:
            log.info(f"Auto-disconnect: no listeners in guild {guild_id}")
            await bot.remove_manager(guild_id)


# ── Match Select View ─────────────────────────────────────────────────────────
class MatchSelect(discord.ui.Select):
    def __init__(self, matches: list[dict], bot: IPTVBot):
        self.bot = bot
        self._matches = matches
        options = [
            discord.SelectOption(
                label=m["title"][:100],
                description=m.get("description", "Live")[:100],
                value=str(i),
                emoji="⚽",
            )
            for i, m in enumerate(matches[:25])
        ]
        super().__init__(
            placeholder="⚽  Choose a World Cup match …",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=True)

        # Must be in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                "تكفى خش صوت اول", ephemeral=True
            )
            return

        match = self._matches[int(self.values[0])]
        channel = interaction.user.voice.channel
        guild_id = interaction.guild_id

        # Stop any existing stream in this guild
        existing = self.bot.get_manager(guild_id)
        if existing:
            await existing.stop()

        manager = StreamManager(self.bot, guild_id)
        self.bot.set_manager(guild_id, manager)

        try:
            await manager.start(channel, match)
            embed = discord.Embed(
                title="📺  Now Streaming",
                description=f"**{match['title']}**\n{match.get('description', '')}",
                color=discord.Color.green(),
            )
            embed.set_footer(text="Use /stop to end the stream • /matches to switch")
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            log.error(f"Failed to start stream: {exc}", exc_info=True)
            await self.bot.remove_manager(guild_id)
            await interaction.followup.send(
                f"❌ Failed to start stream: `{exc}`\n"
                "Check your IPTV URL and FFmpeg installation.",
                ephemeral=True,
            )


class MatchSelectView(discord.ui.View):
    def __init__(self, matches: list[dict], bot: IPTVBot):
        super().__init__(timeout=120)
        self.add_item(MatchSelect(matches, bot))


# ── Slash Commands ────────────────────────────────────────────────────────────
bot = IPTVBot()


@bot.tree.command(name="matches", description="Show live World Cup matches and stream one")
async def matches_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=False)

    try:
        live_matches = await bot.iptv.get_live_matches()
    except Exception as exc:
        log.error(f"IPTV fetch error: {exc}", exc_info=True)
        await interaction.followup.send(
            "❌ Could not fetch matches from IPTV provider. "
            "Check your `IPTV_M3U_URL` in `.env`.",
            ephemeral=True,
        )
        return

    if not live_matches:
        await interaction.followup.send(
            "📭 No World Cup matches found right now. Try again later!",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="🏆  World Cup Live Matches",
        description=f"**{len(live_matches)} match(es) available.** Pick one below:",
        color=discord.Color.gold(),
    )
    for m in live_matches[:10]:
        embed.add_field(
            name=f"⚽ {m['title']}",
            value=m.get("description", "Live now"),
            inline=False,
        )

    view = MatchSelectView(live_matches, bot)
    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="stop", description="Stop the current stream and leave voice")
async def stop_cmd(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    manager = bot.get_manager(guild_id)
    if not manager:
        await interaction.response.send_message(
            "ℹ️ Nothing is currently streaming.", ephemeral=True
        )
        return

    await bot.remove_manager(guild_id)
    await interaction.response.send_message("⏹️  Stream stopped. Goodbye! 👋")


@bot.tree.command(name="nowplaying", description="Show what's currently streaming")
async def nowplaying_cmd(interaction: discord.Interaction):
    manager = bot.get_manager(interaction.guild_id)
    if not manager or not manager.current_match:
        await interaction.response.send_message(
            "📭 Nothing is streaming right now. Use `/matches` to start!", ephemeral=True
        )
        return

    m = manager.current_match
    embed = discord.Embed(
        title="📺  Now Playing",
        description=f"**{m['title']}**\n{m.get('description', '')}",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Channel", value=manager.voice_client.channel.mention)
    embed.add_field(name="Status", value="🟢 Live" if manager.is_playing else "🔴 Reconnecting…")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ping", description="Check bot latency")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🏓 Pong! `{round(bot.latency * 1000)}ms`", ephemeral=True
    )


# ── Entry Point ───────────────────────────────────────────────────────────────
def handle_exit(signum, frame):
    log.info(f"Signal {signum} received — shutting down.")
    asyncio.get_event_loop().stop()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    token = os.getenv("DISCORD_TOKEN") or bot.config.DISCORD_TOKEN
    if not token:
        log.critical("DISCORD_TOKEN not set. Add it to your .env file.")
        sys.exit(1)

    bot.run(token, log_handler=None)
