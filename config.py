import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # ── Required ──────────────────────────────────────────────────────────────
    DISCORD_TOKEN: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))

    # ── IPTV Source ───────────────────────────────────────────────────────────
    # Option A: Direct M3U playlist URL (preferred)
    IPTV_M3U_URL: str = field(
        default_factory=lambda: os.getenv(
            "IPTV_M3U_URL",
            # Public free IPTV list (sports) – replace with your paid provider
            "https://iptv-org.github.io/iptv/categories/sports.m3u",
        )
    )

    # Option B: Xtream Codes / stalker-portal credentials
    XTREAM_HOST: str = field(default_factory=lambda: os.getenv("XTREAM_HOST", ""))
    XTREAM_USER: str = field(default_factory=lambda: os.getenv("XTREAM_USER", ""))
    XTREAM_PASS: str = field(default_factory=lambda: os.getenv("XTREAM_PASS", ""))

    # ── Stream Filtering ──────────────────────────────────────────────────────
    # Keywords used to identify World Cup / football channels
    MATCH_KEYWORDS: list[str] = field(
        default_factory=lambda: [
            kw.strip().lower()
            for kw in os.getenv(
                "MATCH_KEYWORDS",
                "world cup,fifa,football,soccer,sport,beinsport,bein,espn,fox sport",
            ).split(",")
            if kw.strip()
        ]
    )

    # ── FFmpeg / Audio ────────────────────────────────────────────────────────
    FFMPEG_PATH: str = field(
        default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg")
    )
    AUDIO_BITRATE: str = field(
        default_factory=lambda: os.getenv("AUDIO_BITRATE", "128k")
    )
    # Reconnect attempts before giving up
    MAX_RECONNECTS: int = field(
        default_factory=lambda: int(os.getenv("MAX_RECONNECTS", "5"))
    )
    RECONNECT_DELAY: int = field(
        default_factory=lambda: int(os.getenv("RECONNECT_DELAY", "5"))
    )

    # ── Timeouts ──────────────────────────────────────────────────────────────
    HTTP_TIMEOUT: int = field(
        default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "15"))
    )
    STREAM_PROBE_TIMEOUT: int = field(
        default_factory=lambda: int(os.getenv("STREAM_PROBE_TIMEOUT", "10"))
    )
