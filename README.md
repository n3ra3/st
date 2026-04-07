# Steam knives bot (Skins-Table API + Telegram)

Bot requests data from skins-table.com, filters only knives by symbol `★`, builds Steam Market links, and sends results to Telegram.

## Features

- Poll every N minutes (default: 10)
- Active only in selected time window (default: 10:00-00:59)
- Moldova timezone by default (`Europe/Chisinau`)
- Knife filter by symbol `★`
- Optional price range filters
- Steam order comparison: uses second `/items` request (`SITE=STEAM` vs `STEAM_ORDER_SITE=STEAM ORDER`) and shows spread in $ and %
- PirateSwap comparison: optional extra comparison (`SITE=STEAM` vs `PIRATESWAP_SITE=PIRATESWAP`) with spread in $ and %
- MARKET comparison: optional extra comparison in $ and %
- Optional filter to keep only knives below MARKET
- Duplicate protection (won't resend same list every cycle)
- Telegram command `/status` with pretty bot state output

## Setup

1. Install Python 3.10+.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create `.env` from `.env.example` and fill required values:

   - `SKINS_TABLE_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

4. Run:

   ```bash
   python bot.py
   ```

## Important settings (`.env`)

- `TIMEZONE=Europe/Chisinau`
- `POLL_MINUTES=10`
- `ACTIVE_START=10:00`
- `ACTIVE_END=00:59`
- `SEND_SCHEDULE_NOTICES=1`
- `ANALYSIS_START_NOTICE_TIME=09:59`
- `ANALYSIS_END_NOTICE_TIME=00:59`
- `ANALYSIS_START_NOTICE_TEXT=Market analysis started.`
- `ANALYSIS_END_NOTICE_TEXT=Trading session is finished.`
- `ENABLE_TELEGRAM_COMMANDS=1`
- `COMMAND_POLL_SECONDS=30`
- `MIN_STEAM_N=1`
- `MIN_STEAM_ORDER_N=1`
- `SITE=STEAM`
- `COMPARE_WITH_STEAM_ORDER=1`
- `ONLY_BELOW_STEAM_ORDER=1`
- `STEAM_ORDER_SITE=STEAM ORDER`
- `COMPARE_WITH_PIRATESWAP=1`
- `PIRATESWAP_SITE=PIRATESWAP`
- `COMPARE_WITH_MARKET=1`
- `MARKET_SITE=MARKET`
- `ONLY_BELOW_MARKET=1`
- `APP_ID=730`
- `MAX_ITEMS=30`
- `MIN_PRICE=` (optional)
- `MAX_PRICE=` (optional)

## Notes on request usage

At a 10-minute interval during 10:00-00:59, the bot performs around 90 cycles/day. Over 30 days this is around 2700 requests.

If `COMPARE_WITH_MARKET=1`, the bot performs one additional `/items` request each cycle for `MARKET_SITE`.

If `COMPARE_WITH_STEAM_ORDER=1`, the bot performs an additional `/items` request for `STEAM_ORDER_SITE` and matches items by Market Hash Name.

## Quick test without paid API

If your Skins-Table API plan is inactive, you can still validate the bot end-to-end (startup, filtering, Telegram delivery) using mock data.

1. In `.env` set:
   - `MOCK_API=1`
   - `RUN_ONCE=1`
2. Keep valid Telegram values:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Run:

   ```bash
   python bot.py
   ```

The bot will send one test knives update and exit.

## How to find Telegram group chat id

If you cannot get the group chat id manually, use the helper script.

1. Put your token into `.env`:
   - `TELEGRAM_BOT_TOKEN=...`
2. Add the bot to your target group.
3. Send any message in that group (for example `/id`).
4. Run:

   ```bash
   python find_chat_id.py
   ```

The script will print all detected chats and their chat_id values.
Use the needed group id in `TELEGRAM_CHAT_ID` inside `.env`.

## Deploy on Render

This project is configured for Render Worker deployment via Docker (`render.yaml` + `Dockerfile`).

1. Push project to GitHub.
2. In Render, choose **New +** -> **Blueprint** and connect the repository.
3. Render will detect `render.yaml` and create a worker service.
4. Set required secret env vars in Render dashboard:

   - `SKINS_TABLE_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

## Docker local run

Build image:

```bash
docker build -t steamnote-bot .
```

Run container with your env file:

```bash
docker run --rm --env-file .env steamnote-bot
```

## Quick status command

You can check whether the bot is currently active or sleeping and see time until next start:

```bash
python bot.py status
```

## Telegram status command

When the bot is running, send this command in your Telegram group/chat:

```text
/status
```

Bot replies with a formatted status card: current state (ACTIVE/SLEEPING), next start countdown, and notice countdowns.

Requirements:

- `ENABLE_TELEGRAM_COMMANDS=1`
- Bot must be in the same chat as `TELEGRAM_CHAT_ID`
- Bot needs permission to read messages in that chat

### Main Render env vars

- `TIMEZONE=Europe/Chisinau`
- `POLL_MINUTES=10`
- `SITE=STEAM`
- `COMPARE_WITH_STEAM_ORDER=1`
- `STEAM_ORDER_SITE=STEAM ORDER`
- `ONLY_BELOW_STEAM_ORDER=1`
- `COMPARE_WITH_PIRATESWAP=1`
- `PIRATESWAP_SITE=PIRATESWAP`
- `COMPARE_WITH_MARKET=0`
- `ACTIVE_START=10:00`
- `ACTIVE_END=00:59`
- `SEND_SCHEDULE_NOTICES=1`
- `ANALYSIS_START_NOTICE_TIME=09:59`
- `ANALYSIS_END_NOTICE_TIME=00:59`
- `MIN_STEAM_N=1`
- `MIN_STEAM_ORDER_N=1`
- `MAX_ITEMS=30`
- `REQUEST_TIMEOUT_SECONDS=25`
- `MOCK_API=0`
- `RUN_ONCE=0`
