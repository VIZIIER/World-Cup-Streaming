import asyncio
import logging
import re
from typing import Optional

import aiohttp

from config import Config

log = logging.getLogger("iptv_client")

# ── M3U Parser ────────────────────────────────────────────────────────────────
_EXTINF_RE = re.compile(
    r'#EXTINF:-?\d+(?:\s[^,]*)?,\s*(?P<title>.+)',
    re.IGNORECASE,
)
_ATTR_RE = re.compile(r'(?P<key>[\w-]+)="(?P<val>[^"]*)"')


def _parse_m3u(text: str) -> list[dict]:
    """
    Parse an M3U/M3U8 playlist into a list of channel dicts:
        { title, url, group, logo, description }
    """
    channels: list[dict] = []
    lines = text.splitlines()
    pending: Optional[dict] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("#EXTINF"):
            m = _EXTINF_RE.search(line)
            title = m.group("title").strip() if m else "Unknown"
            attrs = dict(_ATTR_RE.findall(line))
            pending = {
                "title": title,
                "url": "",
                "group": attrs.get("group-title", ""),
                "logo": attrs.get("tvg-logo", ""),
                "description": attrs.get("tvg-name", title),
            }

        elif line.startswith("#"):
            continue  # other directives

        else:
            # This is the stream URL
            if pending is not None:
                pending["url"] = line
                channels.append(pending)
                pending = None

    return channels


class IPTVClient:
    def __init__(self, config: Config):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.HTTP_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    # ── Public API ────────────────────────────────────────────────────────────
    async def get_live_matches(self) -> list[dict]:
        """
        Return filtered list of channels that look like World Cup / football.
        Tries Xtream Codes first (if configured), falls back to M3U.
        """
        channels: list[dict] = []

        if self.config.XTREAM_HOST and self.config.XTREAM_USER:
            try:
                channels = await self._fetch_xtream()
                log.info(f"Xtream: fetched {len(channels)} live channels")
            except Exception as exc:
                log.warning(f"Xtream fetch failed ({exc}), falling back to M3U")

        if not channels and self.config.IPTV_M3U_URL:
            channels = await self._fetch_m3u()
            log.info(f"M3U: fetched {len(channels)} channels")

        return self._filter_football(channels)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Fetchers ──────────────────────────────────────────────────────────────
    async def _fetch_m3u(self) -> list[dict]:
        session = await self._get_session()
        async with session.get(self.config.IPTV_M3U_URL) as resp:
            resp.raise_for_status()
            text = await resp.text(encoding="utf-8", errors="replace")
        return _parse_m3u(text)

    async def _fetch_xtream(self) -> list[dict]:
        """
        Fetch live streams from an Xtream Codes / Stalker portal.
        Endpoint: /player_api.php?username=…&password=…&action=get_live_streams
        """
        session = await self._get_session()
        host = self.config.XTREAM_HOST.rstrip("/")
        url = (
            f"{host}/player_api.php"
            f"?username={self.config.XTREAM_USER}"
            f"&password={self.config.XTREAM_PASS}"
            f"&action=get_live_streams"
        )
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        channels = []
        for item in data:
            stream_id = item.get("stream_id")
            if not stream_id:
                continue
            stream_url = (
                f"{host}/live/{self.config.XTREAM_USER}"
                f"/{self.config.XTREAM_PASS}/{stream_id}.m3u8"
            )
            channels.append(
                {
                    "title": item.get("name", "Unknown"),
                    "url": stream_url,
                    "group": item.get("category_name", ""),
                    "logo": item.get("stream_icon", ""),
                    "description": item.get("name", "Live"),
                }
            )
        return channels

    # ── Filter ────────────────────────────────────────────────────────────────
    def _filter_football(self, channels: list[dict]) -> list[dict]:
        keywords = self.config.MATCH_KEYWORDS
        results = []
        for ch in channels:
            searchable = (
                (ch.get("title") or "")
                + " "
                + (ch.get("group") or "")
                + " "
                + (ch.get("description") or "")
            ).lower()
            if any(kw in searchable for kw in keywords):
                results.append(ch)

        log.info(f"Filtered {len(results)} football/World Cup channels")
        return results
