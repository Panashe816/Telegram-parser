import os
import re
import asyncio
from datetime import datetime

import pytz
from dotenv import load_dotenv

from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "14424659"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

# Render will use TELEGRAM_SESSION_STRING.
# Local development can fall back to the .session file.
SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING")
LOCAL_SESSION_NAME = os.getenv("TELEGRAM_LOCAL_SESSION", "gold_signal_bot")

# Private Telegram queue/output channel
TEST_OUTPUT_CHANNEL_ID = int(
    os.getenv("TELEGRAM_CHANNEL_ID", "-1002933896146")
)


# ============================================================
# SOURCE CHANNELS
# ============================================================
# These are the ONLY channels monitored by the parser.
#
# IMPORTANT:
# The IDs are deliberately used instead of usernames.
# ============================================================

SOURCE_CHANNELS = [
    -1001920682501,  # Gold Signals 98% Sure
    -1002000548854,  # GOLD HUNTER TRADE
    -1001859361786,  # GOLD SIGNAL VIP
    -1001392009006,  # SCALPING MARKET TRADING
    -1001509147302,  # Smart Money Trader
    -1003170522699,  # GUNS THE TRADER - TEST SOURCE
]


# ============================================================
# EXECUTION TP MAPPING
# ============================================================
#
# Each source has its own execution targets.
#
# Format:
# channel_id: (first_execution_tp, second_execution_tp)
# ============================================================

TP_MAPPING = {
    -1001920682501: (3, 4),  # Gold Signals 98% Sure
    -1002000548854: (3, 4),  # GOLD HUNTER TRADE
    -1001859361786: (3, 6),  # GOLD SIGNAL VIP
    -1001392009006: (4, 7),  # SCALPING MARKET TRADING
    -1001509147302: (4, 6),  # Smart Money Trader
    -1003170522699: (3, 4),  # GUNS THE TRADER
}


# ============================================================
# CHANNEL NAME NORMALIZATION
# ============================================================

def normalize_channel_name(name):
    """
    Normalize Telegram channel names so that title-based
    fallback matching is more reliable.
    """

    if not name:
        return ""

    text = str(name).upper()

    replacements = {
        "𝗚": "G",
        "𝗢": "O",
        "𝗟": "L",
        "𝗗": "D",
        "𝗛": "H",
        "𝗨": "U",
        "𝗡": "N",
        "𝗧": "T",
        "𝗘": "E",
        "𝗥": "R",
        "𝗦": "S",
        "𝗜": "I",
        "𝗚": "G",
        "𝗡": "N",
        "𝗔": "A",
        "𝗟": "L",
        "𝗩": "V",
        "𝗣": "P",
        "𝗠": "M",
        "𝗞": "K",
        "𝗧": "T",
        "𝗥": "R",
        "𝗔": "A",
        "𝗗": "D",
        "𝗘": "E",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove common symbols / emoji
    text = text.replace("®", " ")
    text = text.replace("™", " ")

    # Keep alphanumeric characters and spaces
    text = re.sub(r"[^A-Z0-9]+", " ", text)

    return " ".join(text.split())


# ============================================================
# TP MAPPING LOOKUP
# ============================================================

def get_tp_mapping(channel_id=None, channel_name=None):
    """
    Return the two execution TP numbers for a source channel.

    Numeric channel ID is the primary method.
    Channel name is only a fallback.
    """

    # --------------------------------------------------------
    # PRIMARY: NUMERIC CHANNEL ID
    # --------------------------------------------------------

    if channel_id is not None:
        try:
            channel_id = int(channel_id)

            if channel_id in TP_MAPPING:
                return TP_MAPPING[channel_id]

        except (ValueError, TypeError):
            pass

    # --------------------------------------------------------
    # FALLBACK: CHANNEL NAME
    # --------------------------------------------------------

    normalized = normalize_channel_name(channel_name)

    if "GOLD SIGNALS 98 SURE" in normalized:
        return 3, 4

    if "GOLD HUNTER TRADE" in normalized:
        return 3, 4

    if "GOLD SIGNAL VIP" in normalized:
        return 3, 6

    if "SCALPING MARKET TRADING" in normalized:
        return 4, 7

    if "SMART MONEY TRADER" in normalized:
        return 4, 6

    if "GUNS THE TRADER" in normalized:
        return 3, 4

    return None


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize signal text while preserving the numerical data.
    """

    if not text:
        return ""

    text = text.replace(",", "")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    return text.strip()


# ============================================================
# DIRECTION
# ============================================================

def extract_direction(text):
    """
    Detect BUY or SELL.
    """

    match = re.search(r"\b(BUY|SELL)\b", text, re.IGNORECASE)

    if not match:
        return None

    return match.group(1).upper()


# ============================================================
# ENTRY
# ============================================================

def extract_entry(text):
    """
    Extract entry range.

    Supported examples:

    BUY 4642/4650
    BUY 4642 - 4650
    BUY 4642-4650
    """

    patterns = [
        r"\b(?:BUY|SELL)\s+(\d+(?:\.\d+)?)\s*[/\-]\s*(\d+(?:\.\d+)?)",
        r"\bENTRY\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*[/\-]\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            price_a = float(match.group(1))
            price_b = float(match.group(2))

            return min(price_a, price_b), max(price_a, price_b)

    return None


# ============================================================
# STOP LOSS
# ============================================================

def extract_sl(text):
    """
    Extract stop loss.
    """

    patterns = [
        r"\bSL\s*[:\-]?\s*(\d+(?:\.\d+)?)",
        r"\bSTOP\s*LOSS\s*[:\-]?\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return float(match.group(1))

    return None


# ============================================================
# TAKE PROFIT LEVELS
# ============================================================

def extract_tp_levels(text):
    """
    Extract TP1 through TP9.

    Example:

    TP1 4655
    TP2 4660
    TP3 4670
    TP4 4680
    """

    tp_levels = {}

    pattern = r"\bTP\s*([1-9])\s*[:\-]?\s*(\d+(?:\.\d+)?)"

    matches = re.findall(pattern, text, re.IGNORECASE)

    for tp_number, price in matches:
        tp_levels[int(tp_number)] = float(price)

    return tp_levels


# ============================================================
# GOLD PRICE VALIDATION
# ============================================================

def validate_gold_price_range(price):
    """
    Basic sanity check for XAU/USD prices.
    """

    if price is None:
        return False

    return 1800 <= price <= 6000


# ============================================================
# SIGNAL VALIDATION
# ============================================================

def validate_signal(
    direction,
    entry_low,
    entry_high,
    sl,
    tp_levels,
    execution_tps
):
    """
    Validate all required fields and the execution targets.
    """

    if direction not in ("BUY", "SELL"):
        return False, "Invalid direction"

    if entry_low is None or entry_high is None:
        return False, "Entry price/range not found"

    if not validate_gold_price_range(entry_low):
        return False, f"Entry price {entry_low} is outside XAUUSD range"

    if not validate_gold_price_range(entry_high):
        return False, f"Entry price {entry_high} is outside XAUUSD range"

    if entry_low > entry_high:
        return False, "Entry range is invalid"

    # Prevent accidentally enormous ranges
    if entry_high - entry_low > 100:
        return False, "Entry range is wider than 100 points"

    if sl is None:
        return False, "Stop loss not found"

    if not validate_gold_price_range(sl):
        return False, f"SL {sl} is outside XAUUSD range"

    # --------------------------------------------------------
    # SL DIRECTION
    # --------------------------------------------------------

    if direction == "BUY":
        if sl >= entry_low:
            return False, (
                f"BUY SL {sl} is not below entry {entry_low}"
            )

    elif direction == "SELL":
        if sl <= entry_high:
            return False, (
                f"SELL SL {sl} is not above entry {entry_high}"
            )

    # --------------------------------------------------------
    # EXECUTION TP REQUIREMENTS
    # --------------------------------------------------------

    tp1_number, tp2_number = execution_tps

    if tp1_number not in tp_levels:
        return False, f"Required TP{tp1_number} not found"

    if tp2_number not in tp_levels:
        return False, f"Required TP{tp2_number} not found"

    execution_price_1 = tp_levels[tp1_number]
    execution_price_2 = tp_levels[tp2_number]

    # --------------------------------------------------------
    # TP DIRECTION VALIDATION
    # --------------------------------------------------------

    if direction == "BUY":

        if execution_price_1 <= entry_high:
            return False, (
                f"BUY execution TP{tp1_number} "
                f"{execution_price_1} is not above entry "
                f"{entry_high}"
            )

        if execution_price_2 <= entry_high:
            return False, (
                f"BUY execution TP{tp2_number} "
                f"{execution_price_2} is not above entry "
                f"{entry_high}"
            )

    elif direction == "SELL":

        if execution_price_1 >= entry_low:
            return False, (
                f"SELL execution TP{tp1_number} "
                f"{execution_price_1} is not below entry "
                f"{entry_low}"
            )

        if execution_price_2 >= entry_low:
            return False, (
                f"SELL execution TP{tp2_number} "
                f"{execution_price_2} is not below entry "
                f"{entry_low}"
            )

    return True, None


# ============================================================
# PARSE SIGNAL
# ============================================================

def parse_signal(text, channel_id=None, channel_name=None):
    """
    Parse and validate one Telegram signal.
    """

    text = normalize_text(text)

    direction = extract_direction(text)
    entry = extract_entry(text)
    sl = extract_sl(text)
    tp_levels = extract_tp_levels(text)

    # --------------------------------------------------------
    # TP MAPPING
    # --------------------------------------------------------

    execution_tps = get_tp_mapping(
        channel_id=channel_id,
        channel_name=channel_name
    )

    if execution_tps is None:
        return {
            "valid": False,
            "reason": "Unknown source channel / TP mapping",
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp_levels": tp_levels,
            "execution_tps": None,
        }

    # --------------------------------------------------------
    # BASIC EXTRACTION VALIDATION
    # --------------------------------------------------------

    if direction is None:
        return {
            "valid": False,
            "reason": "BUY/SELL direction not found",
            "direction": None,
            "entry": entry,
            "sl": sl,
            "tp_levels": tp_levels,
            "execution_tps": execution_tps,
        }

    if entry is None:
        return {
            "valid": False,
            "reason": "Entry range not found",
            "direction": direction,
            "entry": None,
            "sl": sl,
            "tp_levels": tp_levels,
            "execution_tps": execution_tps,
        }

    entry_low, entry_high = entry

    # --------------------------------------------------------
    # FULL VALIDATION
    # --------------------------------------------------------

    valid, reason = validate_signal(
        direction=direction,
        entry_low=entry_low,
        entry_high=entry_high,
        sl=sl,
        tp_levels=tp_levels,
        execution_tps=execution_tps
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result = {
        "valid": valid,
        "reason": reason,
        "direction": direction,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": sl,
        "tp_levels": tp_levels,
        "execution_tps": execution_tps,
    }

    if valid:
        result["execution_price_1"] = tp_levels[execution_tps[0]]
        result["execution_price_2"] = tp_levels[execution_tps[1]]

    return result


# ============================================================
# FORMAT VALID SIGNAL
# ============================================================

def format_parsed_signal(
    result,
    channel_name,
    timestamp
):
    """
    Format a valid parsed signal for Guns' Goldbot.
    """

    direction = result["direction"]
    entry_low = result["entry_low"]
    entry_high = result["entry_high"]
    sl = result["sl"]

    tp_levels = result["tp_levels"]
    execution_tps = result["execution_tps"]

    execution_price_1 = result["execution_price_1"]
    execution_price_2 = result["execution_price_2"]

    lines = [
        "🟢 SIGNAL PARSED",
        "────────────────────",
        f"📺 Channel: {channel_name}",
        "💎 Asset: XAU/USD",
        f"🎯 Direction: {direction}",
        f"💰 Entry: {entry_low:.2f} - {entry_high:.2f}",
        f"🛑 SL: {sl:.2f}",
    ]

    # --------------------------------------------------------
    # ALL TPs
    # --------------------------------------------------------

    for tp_number in sorted(tp_levels):
        lines.append(
            f"🎯 TP{tp_number}: {tp_levels[tp_number]:.2f}"
        )

    # --------------------------------------------------------
    # EXECUTION TARGETS
    # --------------------------------------------------------

    lines.extend([
        "",
        "📌 EXECUTION TARGETS",
        (
            f"Position 1 → TP{execution_tps[0]}: "
            f"{execution_price_1:.2f}"
        ),
        (
            f"Position 2 → TP{execution_tps[1]}: "
            f"{execution_price_2:.2f}"
        ),
        "────────────────────",
        "✅ Parser Status: VALID",
        f"⏰ {timestamp}",
    ])

    return "\n".join(lines)


# ============================================================
# FORMAT REJECTED SIGNAL
# ============================================================

def format_rejected_signal(
    result,
    channel_name,
    raw_text
):
    """
    Format a rejected signal for Guns' Goldbot.
    """

    direction = result.get("direction")
    entry_low = result.get("entry_low")
    entry_high = result.get("entry_high")
    sl = result.get("sl")
    tp_levels = result.get("tp_levels", {})
    execution_tps = result.get("execution_tps")

    lines = [
        "🔴 SIGNAL REJECTED",
        "────────────────────",
        f"📺 Channel: {channel_name}",
    ]

    if direction:
        lines.append(f"🎯 Direction: {direction}")

    if entry_low is not None and entry_high is not None:
        lines.append(
            f"💰 Entry: {entry_low} - {entry_high}"
        )

    if sl is not None:
        lines.append(f"🛑 SL: {sl}")

    # --------------------------------------------------------
    # REQUIRED EXECUTION TPs
    # --------------------------------------------------------

    if execution_tps:
        tp_a, tp_b = execution_tps

        lines.extend([
            "",
            "📌 Required execution TPs:",
            f"TP{tp_a}: {tp_levels.get(tp_a)}",
            f"TP{tp_b}: {tp_levels.get(tp_b)}",
        ])

    lines.extend([
        "",
        "❌ REASON:",
        f"• {result.get('reason')}",
        "",
        "Raw message:",
        raw_text,
    ])

    return "\n".join(lines)


# ============================================================
# CREATE TELEGRAM CLIENT
# ============================================================

def create_telegram_client():
    """
    Create TelegramClient.

    Priority:
        1. TELEGRAM_SESSION_STRING
        2. Local .session file

    Render:
        Uses StringSession.

    Local:
        Falls back to gold_signal_bot.session.
    """

    if SESSION_STRING:
        print("🔐 Using TELEGRAM_SESSION_STRING")
        return TelegramClient(
            StringSession(SESSION_STRING),
            API_ID,
            API_HASH
        )

    print(
        f"🔐 TELEGRAM_SESSION_STRING not found. "
        f"Using local session: {LOCAL_SESSION_NAME}.session"
    )

    return TelegramClient(
        LOCAL_SESSION_NAME,
        API_ID,
        API_HASH
    )


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = create_telegram_client()


# ============================================================
# RESOLVE AND VERIFY SOURCE CHANNELS
# ============================================================

async def resolve_sources():
    """
    Resolve all configured source channels and verify access.
    """

    print("\n" + "=" * 70)
    print("🔎 VERIFYING TELEGRAM SOURCE CHANNELS")
    print("=" * 70)

    accessible = []

    for channel_id in SOURCE_CHANNELS:

        try:
            entity = await client.get_entity(channel_id)

            entity_id = utils.get_peer_id(entity)

            # get_peer_id should produce the signed -100... ID
            signed_id = int(entity_id)

            channel_name = getattr(
                entity,
                "title",
                None
            ) or getattr(
                entity,
                "first_name",
                None
            ) or "Unknown"

            mapping = get_tp_mapping(
                channel_id=signed_id,
                channel_name=channel_name
            )

            print(f"\n📺 {channel_name}")
            print(f"   ID: {signed_id}")

            if mapping:
                print(
                    f"   Execution TPs: "
                    f"TP{mapping[0]} + TP{mapping[1]}"
                )
            else:
                print("   ⚠️ NO TP MAPPING")

            accessible.append(
                {
                    "id": signed_id,
                    "name": channel_name,
                    "mapping": mapping,
                }
            )

        except Exception as e:
            print(
                f"\n❌ Could not access channel "
                f"{channel_id}: {e}"
            )

    print("\n" + "-" * 70)
    print(
        f"Accessible sources: "
        f"{len(accessible)}/{len(SOURCE_CHANNELS)}"
    )
    print("-" * 70)

    return accessible


# ============================================================
# HANDLE NEW TELEGRAM MESSAGE
# ============================================================

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_message(event):
    """
    Process every new message received from a monitored channel.
    """

    try:

        message = event.message
        raw_text = message.message or ""

        # ----------------------------------------------------
        # GET CHANNEL INFORMATION
        # ----------------------------------------------------

        chat = await event.get_chat()

        channel_name = (
            getattr(chat, "title", None)
            or getattr(chat, "first_name", None)
            or "Unknown"
        )

        entity_id = utils.get_peer_id(chat)

        # Ensure the signed Telegram channel ID
        channel_id = int(entity_id)

        # ----------------------------------------------------
        # TIMESTAMP
        # ----------------------------------------------------

        tz = pytz.timezone("Africa/Harare")

        if message.date:
            timestamp = message.date.astimezone(tz).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        else:
            timestamp = datetime.now(tz).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        # ----------------------------------------------------
        # PRINT RAW MESSAGE
        # ----------------------------------------------------

        print("\n" + "=" * 70)
        print("📨 NEW MESSAGE")
        print("=" * 70)
        print(f"Time: {timestamp}")
        print(f"Channel: {channel_name}")
        print(f"Channel ID: {channel_id}")
        print(f"Message ID: {message.id}")

        print("\nRAW MESSAGE:")
        print("-" * 70)
        print(raw_text)
        print("-" * 70)

        # ----------------------------------------------------
        # SHOW TP MAPPING
        # ----------------------------------------------------

        mapping = get_tp_mapping(
            channel_id=channel_id,
            channel_name=channel_name
        )

        if mapping:
            print(
                f"\nExecution TP mapping: "
                f"TP{mapping[0]} + TP{mapping[1]}"
            )
        else:
            print("\n⚠️ No execution TP mapping found")

        # ----------------------------------------------------
        # PARSE
        # ----------------------------------------------------

        result = parse_signal(
            raw_text,
            channel_id=channel_id,
            channel_name=channel_name
        )

        # ----------------------------------------------------
        # VALID SIGNAL
        # ----------------------------------------------------

        if result["valid"]:

            print("\n🟢 SIGNAL PARSED SUCCESSFULLY")

            print(
                f"Direction: {result['direction']}"
            )

            print(
                f"Entry: "
                f"{result['entry_low']} - "
                f"{result['entry_high']}"
            )

            print(
                f"SL: {result['sl']}"
            )

            print(
                f"All TPs: {result['tp_levels']}"
            )

            print(
                f"Execution TPs: "
                f"TP{result['execution_tps'][0]} + "
                f"TP{result['execution_tps'][1]}"
            )

            print(
                f"Execution prices: "
                f"{result['execution_price_1']} + "
                f"{result['execution_price_2']}"
            )

            # ------------------------------------------------
            # FORMAT OUTPUT
            # ------------------------------------------------

            output_message = format_parsed_signal(
                result=result,
                channel_name=channel_name,
                timestamp=timestamp
            )

            # ------------------------------------------------
            # SEND TO PRIVATE QUEUE
            # ------------------------------------------------

            await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                output_message
            )

            print(
                "\n✅ Parsed signal sent to Guns' Goldbot"
            )

        # ----------------------------------------------------
        # REJECTED SIGNAL
        # ----------------------------------------------------

        else:

            print("\n🔴 MESSAGE REJECTED BY PARSER")
            print(
                f"   ❌ {result['reason']}"
            )

            rejection_message = format_rejected_signal(
                result=result,
                channel_name=channel_name,
                raw_text=raw_text
            )

            await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                rejection_message
            )

            print(
                "\n📤 Rejection report sent to Guns' Goldbot"
            )

    except Exception as e:

        print("\n" + "=" * 70)
        print("🔥 ERROR PROCESSING MESSAGE")
        print("=" * 70)
        print(str(e))

        # Do not allow one bad message to kill the listener.
        return


# ============================================================
# MAIN
# ============================================================

async def main():

    print("\n" + "=" * 70)
    print("🚀 PHASE 4 — LIVE TELEGRAM GOLD SIGNAL PARSER")
    print("=" * 70)

    print("\n⚠️ NO TRADING IS ENABLED")
    print("⚠️ NO METAAPI IS CONNECTED")
    print("⚠️ NO MT5 ORDERS CAN BE PLACED")

    print("\nConfigured source channels:")

    for channel_id in SOURCE_CHANNELS:

        mapping = TP_MAPPING.get(channel_id)

        if mapping:
            print(
                f"  • {channel_id} "
                f"→ TP{mapping[0]} + TP{mapping[1]}"
            )
        else:
            print(
                f"  • {channel_id} "
                f"→ NO MAPPING"
            )

    print(
        f"\nOutput channel: "
        f"{TEST_OUTPUT_CHANNEL_ID}"
    )

    print("\nConnecting to Telegram...")

    await client.start()

    print("✅ TELEGRAM SESSION AUTHORIZED")

    # --------------------------------------------------------
    # VERIFY SOURCES
    # --------------------------------------------------------

    accessible_sources = await resolve_sources()

    if len(accessible_sources) != len(SOURCE_CHANNELS):

        print(
            "\n⚠️ WARNING: Not all configured "
            "sources are accessible."
        )

    # --------------------------------------------------------
    # VERIFY OUTPUT CHANNEL
    # --------------------------------------------------------

    try:

        output_entity = await client.get_entity(
            TEST_OUTPUT_CHANNEL_ID
        )

        output_name = (
            getattr(output_entity, "title", None)
            or "Unknown"
        )

        print(
            f"\n📤 Output channel accessible: "
            f"{output_name}"
        )

    except Exception as e:

        print(
            "\n❌ Could not access output channel:"
        )
        print(str(e))

    # --------------------------------------------------------
    # LISTENER
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("LIVE PARSER LISTENER ACTIVE")
    print("=" * 70)

    print("\nMonitoring:")

    for source in accessible_sources:
        mapping = source["mapping"]

        if mapping:
            print(
                f"  • {source['name']} "
                f"({source['id']}) "
                f"→ TP{mapping[0]} + TP{mapping[1]}"
            )
        else:
            print(
                f"  • {source['name']} "
                f"({source['id']}) "
                f"→ NO MAPPING"
            )

    print("\nOutput:")
    print("  • Guns' Goldbot")

    print("\n⚠️ NO TRADING IS ENABLED")
    print("⚠️ NO METAAPI IS CONNECTED")
    print("⚠️ NO MT5 ORDERS CAN BE PLACED")

    print("\nOnly the mapped execution TPs are validated.")

    print("\nWaiting for Telegram signals...")
    print("\nPress CTRL+C to stop.")

    # --------------------------------------------------------
    # KEEP PROCESS ALIVE
    # --------------------------------------------------------

    await client.run_until_disconnected()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        print("\n")
        print("🛑 Parser stopped by user.")

    except Exception as e:

        print("\n")
        print("=" * 70)
        print("🔥 PARSER STOPPED DUE TO ERROR")
        print("=" * 70)
        print(str(e))
