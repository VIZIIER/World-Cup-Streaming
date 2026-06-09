# 🏆 Discord IPTV World Cup Bot

A Discord bot that streams live World Cup / football matches from an IPTV provider directly into your voice channels, using slash commands.

---

## Features

- `/matches` — Lists all live football/World Cup channels from your IPTV provider; pick one from a dropdown
- `/stop` — Stops the stream and disconnects the bot
- `/nowplaying` — Shows what's currently streaming
- `/ping` — Check bot latency
- **Auto-reconnect** — FFmpeg is restarted automatically on network drops (up to `MAX_RECONNECTS` times)
- **Multi-guild** — Each Discord server gets its own independent stream session
- **Auto-disconnect** — Bot leaves voice automatically when no listeners remain

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| FFmpeg | Any recent (4.x+) |
| discord.py[voice] | 2.4+ |

---

## Setup

### 1. Install FFmpeg

**Linux (Ubuntu/Debian)**
```bash
sudo apt update && sudo apt install -y ffmpeg
```

**macOS**
```bash
brew install ffmpeg
```

**Windows**
Download from https://ffmpeg.org/download.html and add `ffmpeg.exe` to your PATH (or set `FFMPEG_PATH` in `.env`).

---

### 2. Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → name it
3. Go to **Bot** → click **Add Bot**
4. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Voice States** (already default)
5. Copy your **Bot Token**
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Connect`, `Speak`, `Send Messages`, `Embed Links`, `Use Slash Commands`
7. Open the generated URL and invite the bot to your server

---

### 3. Configure the Bot

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
DISCORD_TOKEN=your_bot_token_here
IPTV_M3U_URL=https://your-iptv-provider.com/playlist.m3u
```

**Or for Xtream Codes providers:**
```env
XTREAM_HOST=http://yourprovider.com:8080
XTREAM_USER=your_username
XTREAM_PASS=your_password
```

---

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

### 5. Run the Bot

```bash
python bot.py
```

---

## IPTV Provider Notes

### Free / Test Source
The default `IPTV_M3U_URL` points to `iptv-org`'s public sports playlist. These streams may be unstable or geo-blocked. **For reliable World Cup streams, use a paid provider.**

### Paid Provider Options (IPTV Smarters compatible)
Most paid IPTV services give you either:
- An **M3U URL** → paste into `IPTV_M3U_URL`
- **Xtream Codes credentials** (host/user/pass) → use the `XTREAM_*` variables

### Keyword Filtering
The bot filters channels by keywords in `MATCH_KEYWORDS`. Customize this to match your provider's channel names:
```env
MATCH_KEYWORDS=world cup,fifa,bein sports,fox sports,espn,sport
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | *(required)* | Your Discord bot token |
| `IPTV_M3U_URL` | iptv-org sports | M3U playlist URL |
| `XTREAM_HOST` | | Xtream Codes host URL |
| `XTREAM_USER` | | Xtream Codes username |
| `XTREAM_PASS` | | Xtream Codes password |
| `MATCH_KEYWORDS` | world cup,fifa,… | Filter keywords (comma-separated) |
| `FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |
| `AUDIO_BITRATE` | `128k` | Audio bitrate for Discord |
| `MAX_RECONNECTS` | `5` | Max auto-reconnect attempts |
| `RECONNECT_DELAY` | `5` | Base delay (seconds) between retries |
| `HTTP_TIMEOUT` | `15` | HTTP request timeout (seconds) |

---

## Troubleshooting

**"No matches found"**
- Check that your `IPTV_M3U_URL` is accessible
- Adjust `MATCH_KEYWORDS` to match your provider's channel names
- Try `curl -I "your_m3u_url"` to test connectivity

**"Failed to start stream"**
- Make sure FFmpeg is installed: `ffmpeg -version`
- Verify the stream URL plays in VLC first
- Check `bot.log` for detailed error messages

**Bot joins but no audio**
- Ensure you gave the bot `Speak` permission in the voice channel
- Check your Discord voice region (switch to a closer region)
- Try lowering `AUDIO_BITRATE` to `64k`

**Slash commands not showing**
- Wait up to 1 hour for global sync, or use `guild_id` for instant sync during testing
- Re-invite the bot with `applications.commands` scope

---

## File Structure

```
discord_iptv_bot/
├── bot.py            # Main bot, slash commands, UI views
├── config.py         # Configuration loader (.env)
├── iptv_client.py    # IPTV playlist fetcher & parser
├── stream_manager.py # Voice connection & FFmpeg streaming
├── requirements.txt
├── .env.example
└── README.md
```

---

## Running as a Service (Linux)

Create `/etc/systemd/system/iptv-bot.service`:

```ini
[Unit]
Description=Discord IPTV Bot
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/discord_iptv_bot
ExecStart=/usr/bin/python3 bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now iptv-bot
sudo journalctl -u iptv-bot -f
```
