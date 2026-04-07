import hashlib
import html
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

API_URL = "https://skins-table.com/api_v2/items"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"


@dataclass
class Config:
    api_key: str
    telegram_token: str
    telegram_chat_id: str
    mock_api: bool
    run_once: bool
    timezone: str
    poll_minutes: int
    app_id: int
    site: str
    compare_with_market: bool
    market_site: str
    only_below_market: bool
    compare_with_steam_order: bool
    only_below_steam_order: bool
    steam_order_site: str
    compare_with_pirateswap: bool
    pirateswap_site: str
    send_schedule_notices: bool
    analysis_start_notice_time: dt_time
    analysis_end_notice_time: dt_time
    analysis_start_notice_text: str
    analysis_end_notice_text: str
    active_start: dt_time
    active_end: dt_time
    min_steam_n: int
    min_steam_order_n: int
    max_items: int
    min_price: float | None
    max_price: float | None
    request_timeout_seconds: int


def parse_hhmm(value: str) -> dt_time:
    try:
        hour_str, minute_str = value.strip().split(":", 1)
        return dt_time(hour=int(hour_str), minute=int(minute_str))
    except Exception as exc:
        raise ValueError(f"Invalid time format '{value}'. Use HH:MM.") from exc


def parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return float(text)


def parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num < 0:
        return None
    return int(num)


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    load_dotenv(override=True)

    api_key = os.getenv("SKINS_TABLE_API_KEY", "").strip()
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    mock_api = parse_bool(os.getenv("MOCK_API", "0"))

    missing = []
    if not api_key and not mock_api:
        missing.append("SKINS_TABLE_API_KEY")
    if not telegram_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        raise ValueError("Missing required env vars: " + ", ".join(missing))

    return Config(
        api_key=api_key,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        mock_api=mock_api,
        run_once=parse_bool(os.getenv("RUN_ONCE", "0")),
        timezone=os.getenv("TIMEZONE", "Europe/Chisinau").strip(),
        poll_minutes=int(os.getenv("POLL_MINUTES", "10")),
        app_id=int(os.getenv("APP_ID", "730")),
        site=os.getenv("SITE", "STEAM").strip(),
        compare_with_market=parse_bool(os.getenv("COMPARE_WITH_MARKET", "1")),
        market_site=os.getenv("MARKET_SITE", "MARKET").strip(),
        only_below_market=parse_bool(os.getenv("ONLY_BELOW_MARKET", "1")),
        compare_with_steam_order=parse_bool(os.getenv("COMPARE_WITH_STEAM_ORDER", "1")),
        only_below_steam_order=parse_bool(os.getenv("ONLY_BELOW_STEAM_ORDER", "1")),
        steam_order_site=os.getenv("STEAM_ORDER_SITE", "STEAM ORDER").strip(),
        compare_with_pirateswap=parse_bool(os.getenv("COMPARE_WITH_PIRATESWAP", "1")),
        pirateswap_site=os.getenv("PIRATESWAP_SITE", "PIRATESWAP").strip(),
        send_schedule_notices=parse_bool(os.getenv("SEND_SCHEDULE_NOTICES", "1")),
        analysis_start_notice_time=parse_hhmm(os.getenv("ANALYSIS_START_NOTICE_TIME", "09:59")),
        analysis_end_notice_time=parse_hhmm(os.getenv("ANALYSIS_END_NOTICE_TIME", "00:59")),
        analysis_start_notice_text=os.getenv(
            "ANALYSIS_START_NOTICE_TEXT",
            "Market analysis started.",
        ).strip(),
        analysis_end_notice_text=os.getenv(
            "ANALYSIS_END_NOTICE_TEXT",
            "Trading session is finished.",
        ).strip(),
        active_start=parse_hhmm(os.getenv("ACTIVE_START", "10:00")),
        active_end=parse_hhmm(os.getenv("ACTIVE_END", "00:59")),
        min_steam_n=int(os.getenv("MIN_STEAM_N", "1")),
        min_steam_order_n=int(os.getenv("MIN_STEAM_ORDER_N", "1")),
        max_items=int(os.getenv("MAX_ITEMS", "30")),
        min_price=parse_optional_float(os.getenv("MIN_PRICE")),
        max_price=parse_optional_float(os.getenv("MAX_PRICE")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "25")),
    )


def is_active_now(now: datetime, start: dt_time, end: dt_time) -> bool:
    now_t = now.timetz().replace(tzinfo=None)
    if start <= end:
        return start <= now_t <= end
    return now_t >= start or now_t <= end


def seconds_until_next_start(now: datetime, start: dt_time) -> int:
    next_start = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if now >= next_start:
        next_start = next_start + timedelta(days=1)
    return max(60, int((next_start - now).total_seconds()))


def seconds_until_next_notice(now: datetime, target: dt_time, sent_today: bool) -> int:
    candidate = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
    if sent_today or now >= candidate:
        candidate = candidate + timedelta(days=1)
    return max(1, int((candidate - now).total_seconds()))


def maybe_send_schedule_notices(
    config: Config,
    previous_now: datetime,
    now: datetime,
    sent_dates: dict[str, str],
) -> None:
    if not config.send_schedule_notices:
        return

    schedule = [
        (
            "analysis_start",
            config.analysis_start_notice_time,
            config.analysis_start_notice_text,
        ),
        (
            "analysis_end",
            config.analysis_end_notice_time,
            config.analysis_end_notice_text,
        ),
    ]

    tz = now.tzinfo
    date_cursor = previous_now.date() - timedelta(days=1)
    end_date = now.date() + timedelta(days=1)

    while date_cursor <= end_date:
        for key, target_time, message in schedule:
            target_dt = datetime.combine(date_cursor, target_time, tzinfo=tz)
            marker = f"{date_cursor.isoformat()}|{target_time.strftime('%H:%M')}"

            if previous_now < target_dt <= now and sent_dates.get(key) != marker:
                send_telegram(config, message)
                sent_dates[key] = marker
                logging.info("Schedule notice sent: %s", key)

        date_cursor = date_cursor + timedelta(days=1)


def build_steam_link(app_id: int, market_hash_name: str) -> str:
    encoded_name = quote(market_hash_name, safe="")
    return f"https://steamcommunity.com/market/listings/{app_id}/{encoded_name}"


def fetch_items(config: Config, site: str) -> tuple[dict[str, Any], int | None]:
    params = {
        "apikey": config.api_key,
        "app": config.app_id,
        "site": site,
    }

    response = requests.get(API_URL, params=params, timeout=config.request_timeout_seconds)
    response.raise_for_status()

    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Skins-table API error: {data['error']}")

    items = data.get("items")
    if not isinstance(items, dict):
        raise RuntimeError("Unexpected API response: 'items' is missing or invalid")

    requests_left = data.get("requests")
    return items, requests_left if isinstance(requests_left, int) else None


def get_mock_items(site: str) -> tuple[dict[str, Any], int | None]:
    if site.upper() == "PIRATESWAP":
        items: dict[str, Any] = {
            "★ Karambit | Doppler (Factory New)": {
                "n": "★ Karambit | Doppler (Factory New)",
                "p": 915.0,
                "c": 2,
            },
            "★ Gut Knife | Lore (Field-Tested)": {
                "n": "★ Gut Knife | Lore (Field-Tested)",
                "p": 170.0,
                "c": 4,
            },
        }
        return items, None

    if site.upper() == "STEAM ORDER":
        items: dict[str, Any] = {
            "★ Karambit | Doppler (Factory New)": {
                "n": "★ Karambit | Doppler (Factory New)",
                "p": 940.0,
                "c": 3,
            },
            "★ Gut Knife | Lore (Field-Tested)": {
                "n": "★ Gut Knife | Lore (Field-Tested)",
                "p": 160.0,
                "c": 8,
            },
        }
        return items, None

    if site.upper() == "MARKET":
        items: dict[str, Any] = {
            "★ Karambit | Doppler (Factory New)": {
                "n": "★ Karambit | Doppler (Factory New)",
                "p": 980.0,
                "c": 1,
            },
            "★ Gut Knife | Lore (Field-Tested)": {
                "n": "★ Gut Knife | Lore (Field-Tested)",
                "p": 150.0,
                "c": 5,
            },
        }
        return items, None

    items = {
        "★ Karambit | Doppler (Factory New)": {
            "n": "★ Karambit | Doppler (Factory New)",
            "p": 899.99,
            "c": 2,
        },
        "★ Gut Knife | Lore (Field-Tested)": {
            "n": "★ Gut Knife | Lore (Field-Tested)",
            "p": 165.5,
            "c": 6,
        },
        "AK-47 | Slate (Field-Tested)": {
            "n": "AK-47 | Slate (Field-Tested)",
            "p": 4.2,
            "c": 120,
        },
    }
    return items, None


def select_knives(items: dict[str, Any], config: Config) -> list[dict[str, Any]]:
    knives: list[dict[str, Any]] = []

    for item_name, raw in items.items():
        if not isinstance(raw, dict):
            continue

        name = str(raw.get("n") or item_name)
        if "★" not in name:
            continue

        try:
            price = float(raw.get("p", 0))
        except (TypeError, ValueError):
            continue

        if config.min_price is not None and price < config.min_price:
            continue
        if config.max_price is not None and price > config.max_price:
            continue

        steam_n = parse_optional_int(raw.get("c"))
        if steam_n is None:
            steam_n = 0
        if steam_n < config.min_steam_n:
            continue

        knives.append(
            {
                "name": name,
                "price": price,
                "steam_n": steam_n,
                "steam_link": build_steam_link(config.app_id, name),
                "steam_order": None,
                "steam_order_n": None,
                "below_steam_order_abs": None,
                "below_steam_order_pct": None,
                "pirateswap_price": None,
                "steam_vs_pirateswap_abs": None,
                "steam_vs_pirateswap_pct": None,
                "market_price": None,
                "below_market_abs": None,
                "below_market_pct": None,
            }
        )

    knives.sort(key=lambda x: (x["price"], x["name"]))
    return knives


def apply_steam_order_diff(
    knives: list[dict[str, Any]],
    steam_order_data: dict[str, dict[str, Any]],
    only_below_steam_order: bool,
    min_steam_order_n: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for knife in knives:
        steam_order_row = steam_order_data.get(knife["name"], {})
        steam_order = steam_order_row.get("price")
        steam_order_n = steam_order_row.get("count")
        knife_copy = dict(knife)

        if not isinstance(steam_order_n, int):
            steam_order_n = 0
        if steam_order_n < min_steam_order_n:
            continue

        if isinstance(steam_order, (int, float)) and steam_order > 0:
            knife_copy["steam_order"] = steam_order
            knife_copy["steam_order_n"] = steam_order_n
            diff_abs = steam_order - knife_copy["price"]
            diff_pct = (diff_abs / steam_order) * 100.0
            knife_copy["below_steam_order_abs"] = diff_abs
            knife_copy["below_steam_order_pct"] = diff_pct

            if only_below_steam_order and diff_abs <= 0:
                continue
        elif only_below_steam_order:
            continue

        result.append(knife_copy)

    result.sort(
        key=lambda x: (
            -(x["below_steam_order_abs"] if isinstance(x["below_steam_order_abs"], (int, float)) else -1e9),
            x["price"],
            x["name"],
        )
    )
    return result


def build_site_map(items: dict[str, Any]) -> dict[str, dict[str, Any]]:
    site_map: dict[str, dict[str, Any]] = {}
    for item_name, raw in items.items():
        if not isinstance(raw, dict):
            continue

        name = str(raw.get("n") or item_name)
        try:
            price = float(raw.get("p", 0))
        except (TypeError, ValueError):
            continue

        if price > 0:
            site_map[name] = {
                "price": price,
                "count": parse_optional_int(raw.get("c")),
            }
    return site_map


def build_price_map(items: dict[str, Any]) -> dict[str, float]:
    site_map = build_site_map(items)
    return {name: float(data["price"]) for name, data in site_map.items() if "price" in data}


def apply_pirateswap_diff(
    knives: list[dict[str, Any]],
    pirateswap_prices: dict[str, float],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for knife in knives:
        knife_copy = dict(knife)
        pirateswap_price = pirateswap_prices.get(knife_copy["name"])

        if isinstance(pirateswap_price, (int, float)) and pirateswap_price > 0:
            diff_abs = pirateswap_price - knife_copy["price"]
            diff_pct = (diff_abs / pirateswap_price) * 100.0
            knife_copy["pirateswap_price"] = pirateswap_price
            knife_copy["steam_vs_pirateswap_abs"] = diff_abs
            knife_copy["steam_vs_pirateswap_pct"] = diff_pct

        result.append(knife_copy)

    return result


def apply_market_diff(
    knives: list[dict[str, Any]],
    market_prices: dict[str, float],
    only_below_market: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for knife in knives:
        market_price = market_prices.get(knife["name"])
        knife_copy = dict(knife)

        if market_price is not None and market_price > 0:
            diff_abs = market_price - knife_copy["price"]
            diff_pct = (diff_abs / market_price) * 100.0
            knife_copy["market_price"] = market_price
            knife_copy["below_market_abs"] = diff_abs
            knife_copy["below_market_pct"] = diff_pct

            if only_below_market and diff_abs <= 0:
                continue

        elif only_below_market:
            # No MARKET price to compare means no actionable edge.
            continue

        result.append(knife_copy)

    result.sort(
        key=lambda x: (
            -(x["below_market_abs"] if isinstance(x["below_market_abs"], (int, float)) else -1e9),
            x["price"],
            x["name"],
        )
    )
    return result


def make_signature(knives: list[dict[str, Any]]) -> str:
    serialized = json.dumps(knives, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def chunk_text(lines: list[str], limit: int = 3500) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        add_len = len(line) + (1 if current else 0)
        if current and current_len + add_len > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += add_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def build_messages(knives: list[dict[str, Any]], now: datetime, requests_left: int | None) -> list[str]:
    ts = now.strftime("%Y-%m-%d %H:%M")
    header = f"Skins-Table knives update ({ts})"
    if requests_left is not None:
        header += f" | requests left: {requests_left}"

    if not knives:
        return [header + "\nNo knives found by current filters."]

    lines = [header, f"Total knives in message: {len(knives)}", ""]
    for idx, item in enumerate(knives, start=1):
        safe_name = html.escape(item["name"])
        safe_link = html.escape(item["steam_link"])
        market_price = item.get("market_price")
        below_market_abs = item.get("below_market_abs")
        below_market_pct = item.get("below_market_pct")
        pirateswap_price = item.get("pirateswap_price")
        steam_vs_pirateswap_abs = item.get("steam_vs_pirateswap_abs")
        steam_vs_pirateswap_pct = item.get("steam_vs_pirateswap_pct")
        steam_order = item.get("steam_order")
        steam_n = item.get("steam_n")
        steam_order_n = item.get("steam_order_n")
        below_steam_order_abs = item.get("below_steam_order_abs")
        below_steam_order_pct = item.get("below_steam_order_pct")

        steam_n_text = str(steam_n) if isinstance(steam_n, int) else "-"

        card_lines = [
            f"<b>{idx}. {safe_name}</b>",
            f"Steam: <b>${item['price']:.2f}</b> | N: <b>{steam_n_text}</b> | <a href=\"{safe_link}\">Open</a>",
        ]

        if isinstance(steam_order, (int, float)):
            order_n_text = str(steam_order_n) if isinstance(steam_order_n, int) else "-"
            card_lines.append(f"Steam order: <b>${steam_order:.2f}</b> | N: <b>{order_n_text}</b>")

            if isinstance(below_steam_order_abs, (int, float)) and isinstance(below_steam_order_pct, (int, float)):
                if below_steam_order_abs >= 0:
                    card_lines.append(
                        f"🔵 Steam vs Steam order: <b>+${below_steam_order_abs:.2f}</b> ({below_steam_order_pct:.2f}%)"
                    )
                else:
                    card_lines.append(
                        f"🔵 Steam vs Steam order: <b>-${abs(below_steam_order_abs):.2f}</b> ({abs(below_steam_order_pct):.2f}%)"
                    )

        if isinstance(pirateswap_price, (int, float)):
            pirateswap_line = f"PirateSwap: <b>${pirateswap_price:.2f}</b>"
            if isinstance(steam_vs_pirateswap_abs, (int, float)) and isinstance(steam_vs_pirateswap_pct, (int, float)):
                sign = "+" if steam_vs_pirateswap_abs >= 0 else "-"
                pirateswap_line += (
                    f" | 🟠 Steam vs PirateSwap: <b>{sign}${abs(steam_vs_pirateswap_abs):.2f}</b> "
                    f"({abs(steam_vs_pirateswap_pct):.2f}%)"
                )
            card_lines.append(pirateswap_line)

        if isinstance(market_price, (int, float)):
            market_line = f"Market: <b>${market_price:.2f}</b>"
            if isinstance(below_market_abs, (int, float)) and isinstance(below_market_pct, (int, float)):
                if below_market_abs >= 0:
                    market_line += f" | Spread: <b>+${below_market_abs:.2f}</b> ({below_market_pct:.2f}%)"
                else:
                    market_line += f" | Spread: <b>-${abs(below_market_abs):.2f}</b> ({abs(below_market_pct):.2f}%)"
            card_lines.append(market_line)

        lines.append("\n".join(card_lines))
        lines.append("")

    return chunk_text(lines)


def send_telegram(config: Config, message: str) -> None:
    url = TELEGRAM_URL.format(token=config.telegram_token)
    payload = {
        "chat_id": config.telegram_chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=config.request_timeout_seconds)
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    config = load_config()
    try:
        tz = ZoneInfo(config.timezone)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            "Timezone database is missing for zone "
            f"'{config.timezone}'. Install tzdata: pip install tzdata"
        ) from exc

    logging.info(
        "Bot started. Timezone=%s Poll=%s min MockAPI=%s RunOnce=%s CompareWithMarket=%s CompareWithSteamOrder=%s Notices=%s",
        config.timezone,
        config.poll_minutes,
        config.mock_api,
        config.run_once,
        config.compare_with_market,
        config.compare_with_steam_order,
        config.send_schedule_notices,
    )

    last_signature: str | None = None
    last_loop_now = datetime.now(tz) - timedelta(seconds=1)
    schedule_sent_dates: dict[str, str] = {}

    while True:
        now = datetime.now(tz)
        try:
            maybe_send_schedule_notices(config, last_loop_now, now, schedule_sent_dates)
        except Exception as exc:
            logging.exception("Failed to send schedule notice: %s", exc)

        if not is_active_now(now, config.active_start, config.active_end):
            sleep_seconds = seconds_until_next_start(now, config.active_start)
            if config.send_schedule_notices:
                start_sent_today = schedule_sent_dates.get("analysis_start", "").startswith(now.date().isoformat())
                end_sent_today = schedule_sent_dates.get("analysis_end", "").startswith(now.date().isoformat())
                sleep_to_start_notice = seconds_until_next_notice(now, config.analysis_start_notice_time, start_sent_today)
                sleep_to_end_notice = seconds_until_next_notice(now, config.analysis_end_notice_time, end_sent_today)
                sleep_seconds = min(sleep_seconds, sleep_to_start_notice, sleep_to_end_notice)

            logging.info("Quiet hours. Sleeping until active window for %s sec", sleep_seconds)
            last_loop_now = now
            time.sleep(sleep_seconds)
            continue

        try:
            if config.mock_api:
                items, requests_left = get_mock_items(config.site)
            else:
                items, requests_left = fetch_items(config, config.site)

            knives = select_knives(items, config)

            if config.compare_with_steam_order and config.steam_order_site.upper() != config.site.upper():
                if config.mock_api:
                    steam_order_items, steam_order_requests_left = get_mock_items(config.steam_order_site)
                else:
                    steam_order_items, steam_order_requests_left = fetch_items(config, config.steam_order_site)

                if isinstance(steam_order_requests_left, int):
                    requests_left = steam_order_requests_left

                steam_order_prices = build_site_map(steam_order_items)
                knives = apply_steam_order_diff(
                    knives,
                    steam_order_prices,
                    config.only_below_steam_order,
                    config.min_steam_order_n,
                )

            if config.compare_with_pirateswap and config.pirateswap_site.upper() != config.site.upper():
                if config.mock_api:
                    pirateswap_items, pirateswap_requests_left = get_mock_items(config.pirateswap_site)
                else:
                    pirateswap_items, pirateswap_requests_left = fetch_items(config, config.pirateswap_site)

                if isinstance(pirateswap_requests_left, int):
                    requests_left = pirateswap_requests_left

                pirateswap_prices = build_price_map(pirateswap_items)
                knives = apply_pirateswap_diff(knives, pirateswap_prices)

            if config.compare_with_market and config.market_site.upper() != config.site.upper():
                if config.mock_api:
                    market_items, market_requests_left = get_mock_items(config.market_site)
                else:
                    market_items, market_requests_left = fetch_items(config, config.market_site)

                if isinstance(market_requests_left, int):
                    requests_left = market_requests_left

                market_prices = build_price_map(market_items)
                knives = apply_market_diff(knives, market_prices, config.only_below_market)

            if config.max_items > 0:
                knives = knives[: config.max_items]

            current_signature = make_signature(knives)

            if current_signature != last_signature:
                messages = build_messages(knives, now, requests_left)
                for msg in messages:
                    send_telegram(config, msg)
                last_signature = current_signature
                logging.info("Update sent: %s knives", len(knives))
            else:
                logging.info("No changes since last update. Skip send.")

            if config.run_once:
                logging.info("Run once is enabled. Exiting after one cycle.")
                return

        except Exception as exc:
            logging.exception("Cycle failed: %s", exc)

        sleep_seconds = max(60, config.poll_minutes * 60)
        if config.send_schedule_notices:
            start_sent_today = schedule_sent_dates.get("analysis_start", "").startswith(now.date().isoformat())
            end_sent_today = schedule_sent_dates.get("analysis_end", "").startswith(now.date().isoformat())
            sleep_to_start_notice = seconds_until_next_notice(now, config.analysis_start_notice_time, start_sent_today)
            sleep_to_end_notice = seconds_until_next_notice(now, config.analysis_end_notice_time, end_sent_today)
            sleep_seconds = min(sleep_seconds, sleep_to_start_notice, sleep_to_end_notice)

        last_loop_now = now
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
