import asyncio
import logging
import shutil
from typing import Optional, TYPE_CHECKING

import discord
from discord import FFmpegPCMAudio, PCMVolumeTransformer

if TYPE_CHECKING:
    from bot import IPTVBot

log = logging.getLogger("stream_manager")


# ── FFmpeg options ────────────────────────────────────────────────────────────
def _ffmpeg_options(stream_url: str, ffmpeg_path: str, bitrate: str) -> dict:

    before_options = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-reconnect_on_network_error 1 "
        "-reconnect_on_http_error 4xx,5xx "
        "-fflags +nobuffer+discardcorrupt "
        "-flags low_delay "
        "-timeout 15000000 "          # 15 s probe timeout (µs)
        "-analyzeduration 5000000 "   # 5 s
        "-probesize 5000000"
    )
    options = (
        f"-vn "
        f"-acodec pcm_s16le "
        f"-ar 48000 "
        f"-ac 2 "
        f"-b:a {bitrate} "
        f"-bufsize 512k"
    )
    return {
        "executable": ffmpeg_path,
        "before_options": before_options,
        "options": options,
    }


class StreamManager:


    def __init__(self, bot: "IPTVBot", guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_match: Optional[dict] = None
        self.is_playing: bool = False
        self._reconnect_count: int = 0
        self._stop_event = asyncio.Event()
        self._stream_task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────────
    async def start(self, channel: discord.VoiceChannel, match: dict):
        self.current_match = match
        self._stop_event.clear()
        self._reconnect_count = 0

        await self._connect(channel)
        self._stream_task = asyncio.create_task(
            self._stream_loop(), name=f"stream-{self.guild_id}"
        )

    async def stop(self):
        log.info(f"[Guild {self.guild_id}] Stopping stream.")
        self._stop_event.set()
        self.is_playing = False

        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        await self._disconnect()

    # ── Internal ──────────────────────────────────────────────────────────────
    async def _connect(self, channel: discord.VoiceChannel):
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
            return

        log.info(f"[Guild {self.guild_id}] Connecting to {channel.name}")
        self.voice_client = await channel.connect(
            timeout=30.0,
            reconnect=True,
            self_deaf=True,   # bot deafens itself to save bandwidth
        )

    async def _disconnect(self):
        if self.voice_client:
            try:
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                if self.voice_client.is_connected():
                    await self.voice_client.disconnect(force=True)
            except Exception as exc:
                log.warning(f"[Guild {self.guild_id}] Disconnect error: {exc}")
            finally:
                self.voice_client = None

    def _make_source(self) -> PCMVolumeTransformer:
        cfg = self.bot.config
        ffmpeg_bin = shutil.which(cfg.FFMPEG_PATH) or cfg.FFMPEG_PATH
        opts = _ffmpeg_options(
            self.current_match["url"], ffmpeg_bin, cfg.AUDIO_BITRATE
        )
        raw_source = FFmpegPCMAudio(
            self.current_match["url"],
            executable=opts["executable"],
            before_options=opts["before_options"],
            options=opts["options"],
        )
        return PCMVolumeTransformer(raw_source, volume=0.8)

    async def _stream_loop(self):
        """
        Core loop: play audio and reconnect on failure.
        Uses an asyncio.Event to detect when FFmpeg finishes or errors.
        """
        cfg = self.bot.config
        title = self.current_match.get("title", "Unknown")

        while not self._stop_event.is_set():
            try:
                # Ensure we're still connected
                if not self.voice_client or not self.voice_client.is_connected():
                    log.warning(f"[{title}] Voice client gone – reconnecting …")
                    guild = self.bot.get_guild(self.guild_id)
                    channel = None
                    if guild:
                        for vc in guild.voice_channels:
                            if any(m.id == self.bot.user.id for m in vc.members):
                                channel = vc
                                break
                    if channel:
                        await self._connect(channel)
                    else:
                        log.error(f"[{title}] Cannot find voice channel – giving up.")
                        break

                if self.voice_client.is_playing():
                    self.voice_client.stop()

                done_event = asyncio.Event()

                def _after(error: Optional[Exception]):
                    if error:
                        log.error(f"[{title}] FFmpeg error: {error}")
                    done_event.set()

                source = self._make_source()
                self.voice_client.play(source, after=_after)
                self.is_playing = True
                self._reconnect_count = 0  # reset counter after successful start
                log.info(f"[{title}] Stream started.")

                # Wait until FFmpeg finishes OR we're told to stop
                await asyncio.wait(
                    [
                        asyncio.create_task(done_event.wait()),
                        asyncio.create_task(self._stop_event.wait()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if self._stop_event.is_set():
                    break

                # FFmpeg ended unexpectedly
                log.warning(f"[{title}] Stream ended unexpectedly.")

            except discord.errors.ClientException as exc:
                log.error(f"[{title}] Discord client error: {exc}")
            except Exception as exc:
                log.error(f"[{title}] Unexpected error: {exc}", exc_info=True)

            # ── Reconnect logic ───────────────────────────────────────────────
            self.is_playing = False
            if self._stop_event.is_set():
                break

            self._reconnect_count += 1
            if self._reconnect_count > cfg.MAX_RECONNECTS:
                log.error(
                    f"[{title}] Max reconnects ({cfg.MAX_RECONNECTS}) reached – stopping."
                )
                await self._notify_failure(title)
                break

            delay = min(cfg.RECONNECT_DELAY * self._reconnect_count, 60)
            log.info(
                f"[{title}] Reconnect {self._reconnect_count}/{cfg.MAX_RECONNECTS} "
                f"in {delay}s …"
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                break  # stop was requested during wait
            except asyncio.TimeoutError:
                pass  # normal – continue reconnect loop

        self.is_playing = False
        log.info(f"[{title}] Stream loop exited.")

    async def _notify_failure(self, title: str):
        """Try to post a failure message to the text channel where the command originated."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        # Find the first text channel we can write to
        for ch in guild.text_channels:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages:
                try:
                    await ch.send(
                        f"❌ Lost connection to **{title}** after "
                        f"{self.bot.config.MAX_RECONNECTS} retries. "
                        f"Use `/matches` to restart."
                    )
                except Exception:
                    pass
                break
