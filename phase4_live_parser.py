import asyncio
import re
from datetime import datetime

import pytz
from telethon import TelegramClient, events
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError


# ============================================================
# PHASE 4 - LIVE TELEGRAM SIGNAL PARSER
# ============================================================
#
# PURPOSE:
#   Monitor Telegram gold signal channels, parse incoming
#   signals, validate the execution TPs, and send parsed
#   results to the private test channel.
#
# IMPORTANT:
#   THIS VERSION DOES NOT:
#
#       - connect to MetaApi
#       - connect to MT5
#       - place trades
#       - modify trades
#
# PHASE 6 handles DEMO trade execution.
#
# EXECUTION TP MAPPING
#
#   Gold Signal VIP              TP3 + TP6
#   Gold Hunter Trade             TP3 + TP4
#   Gold Signals 98% Sure         TP3 + TP4
#   Gold VIP Signals Insights     TP3 + TP6
#   GUNS THE TRADER               TP3 + TP4
#
# IMPORTANT VALIDATION RULE:
#
#   Only the two TPs that Phase 6 will actually execute
#   are used for TP validation.
#
#   Example:
#
#       SELL 4620/4633
#
#       TP1 4630
#       TP2 4624
#       TP3 4610
#       TP4 4605
#
#       SL 4660
#
#   TP1 and TP2 are inside the entry range, but they are
#   NOT being executed for GUNS THE TRADER.
#
#   TP3 and TP4 are below the SELL entry range, therefore
#   the signal is valid.
#
# ============================================================


# ============================================================
# TELEGRAM CONFIGURATION
# ============================================================

API_ID = 14424659

API_HASH = "5facb0b7b7a6f141da79d9cc460d4e12"

SESSION_NAME = "gold_signal_bot"


# ============================================================
# SOURCE CHANNELS
# ============================================================

SOURCE_CHANNELS = [

    # REAL SIGNAL SOURCES
    "Goldhunterlearnttade3867",
    "GoldSignalVip110",
    "MrHenrys122",
    "AGoldvip_0786",

    # YOUR TEST SOURCE
    -1003170522699,
]


# ============================================================
# TEST OUTPUT CHANNEL
# ============================================================

TEST_OUTPUT_CHANNEL_ID = -1002933896146


# ============================================================
# TIMEZONE
# ============================================================

TIMEZONE = pytz.timezone("Africa/Harare")


# ============================================================
# SOURCE -> EXECUTION TP MAPPING
# ============================================================
#
# These are the SAME mappings used by Phase 6.
#
# The parser validates these TPs specifically.
#
# ============================================================

TP_MAPPING = {

    "GOLD SIGNAL VIP": (3, 6),

    "GOLD HUNTER TRADE": (3, 4),

    "GOLD SIGNALS 98% SURE": (3, 4),

    "GOLD VIP SIGNALS INSIGHTS": (3, 6),

    # Private testing channel
    "GUNS THE TRADER": (3, 4),
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace("\r", "\n")

    text = text.replace("\u00A0", " ")

    # Normalize common Unicode dashes
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )

    # Normalize tabs/spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# NORMALIZE CHANNEL NAME
# ============================================================

def normalize_channel_name(name):

    if not name:
        return ""

    name = str(name).upper()

    # Remove common Telegram bold Unicode characters
    replacements = {

        "𝗚𝗢𝗟𝗗": "GOLD",
        "𝐆𝐎𝐋𝐃": "GOLD",

        "𝗛𝗨𝗡𝗧𝗘𝗥": "HUNTER",
        "𝐇𝐔𝐍𝐓𝐄𝐑": "HUNTER",

        "𝗧𝗥𝗔𝗗𝗘": "TRADE",
        "𝐓𝐑𝐀𝐃𝐄": "TRADE",

        "𝗦𝗜𝗚𝗡𝗔𝗟": "SIGNAL",
        "𝐒𝐈𝐆𝐍𝐀𝐋": "SIGNAL",

        "𝗦𝗜𝗚𝗡𝗔𝗟𝗦": "SIGNALS",
        "𝐒𝐈𝐆𝐍𝐀𝐋𝐒": "SIGNALS",

        "𝗩𝗜𝗣": "VIP",
        "𝐕𝐈𝐏": "VIP",

        "𝗦𝗨𝗥𝗘": "SURE",
        "𝐒𝐔𝐑𝐄": "SURE",

        "𝗜𝗡𝗦𝗜𝗚𝗛𝗧𝗦": "INSIGHTS",
        "𝐈𝐍𝐒𝐈𝐆𝐇𝐓𝐒": "INSIGHTS",

        "𝗚𝗨𝗡𝗦": "GUNS",
        "𝐆𝐔𝐍𝐒": "GUNS",

        "𝗧𝗥𝗔𝗗𝗘𝗥": "TRADER",
        "𝐓𝐑𝐀𝐃𝐄𝐑": "TRADER",

        "😎": "",
    }

    for old, new in replacements.items():

        name = name.replace(
            old,
            new
        )

    name = " ".join(
        name.split()
    )

    return name.strip()


# ============================================================
# FIND TP MAPPING
# ============================================================

def get_tp_mapping(channel_name):

    normalized = normalize_channel_name(
        channel_name
    )

    # --------------------------------------------------------
    # Direct match
    # --------------------------------------------------------

    if normalized in TP_MAPPING:

        return TP_MAPPING[normalized]

    # --------------------------------------------------------
    # Flexible matching
    # --------------------------------------------------------

    if (
        "GOLD" in normalized
        and "SIGNAL" in normalized
        and "VIP" in normalized
        and "HUNTER" not in normalized
        and "INSIGHTS" not in normalized
    ):

        return (3, 6)

    if (
        "HUNTER" in normalized
        and "TRADE" in normalized
    ):

        return (3, 4)

    if (
        "98%" in normalized
        and "SURE" in normalized
    ):

        return (3, 4)

    if "INSIGHTS" in normalized:

        return (3, 6)

    if (
        "GUNS" in normalized
        and "TRADER" in normalized
    ):

        return (3, 4)

    return None


# ============================================================
# DIRECTION
# ============================================================

def extract_direction(text):

    text_upper = text.upper()

    if re.search(
        r"\bBUY\b",
        text_upper
    ):

        return "BUY"

    if re.search(
        r"\bSELL\b",
        text_upper
    ):

        return "SELL"

    return None


# ============================================================
# ENTRY
# ============================================================

def extract_entry(text):

    # --------------------------------------------------------
    # Entry ranges
    #
    # Examples:
    #
    # 4547/4544
    # 4545_4542
    # 4500-4510
    # 4500 – 4510
    # --------------------------------------------------------

    range_patterns = [

        r"\b(\d+(?:\.\d+)?)\s*[/_]\s*(\d+(?:\.\d+)?)\b",

        r"\b(\d+(?:\.\d+)?)\s*[-]\s*(\d+(?:\.\d+)?)\b",
    ]

    for pattern in range_patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            a = float(
                match.group(1)
            )

            b = float(
                match.group(2)
            )

            return (
                min(a, b),
                max(a, b),
                "RANGE"
            )

    # --------------------------------------------------------
    # Single entry
    # --------------------------------------------------------

    single_patterns = [

        (
            r"\b(?:GOLD|XAUUSD|XAU)\b\s+"
            r"(?:BUY|SELL)\b"
            r"(?:\s+NOW)?\s+"
            r"(\d+(?:\.\d+)?)"
            r"(?:\s+00\b)?"
        ),

        (
            r"\b(?:BUY|SELL)\b\s+"
            r"(?:GOLD|XAUUSD|XAU)\b"
            r"(?:\s+NOW)?\s+"
            r"(\d+(?:\.\d+)?)"
            r"(?:\s+00\b)?"
        ),
    ]

    for pattern in single_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = float(
                match.group(1)
            )

            return (
                value,
                value,
                "SINGLE"
            )

    return (
        None,
        None,
        None
    )


# ============================================================
# STOP LOSS
# ============================================================

def extract_sl(text):

    patterns = [

        r"\bSL\b\s*[:.\-]?\s*(\d+(?:\.\d+)?)",

        r"\bSTOPLOSS\b\s*[:.\-]?\s*(\d+(?:\.\d+)?)",

        r"\bSTOP\s+LOSS\b\s*[:.\-]?\s*(\d+(?:\.\d+)?)",

        r"\bSTOP\b\s*[:.\-]?\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return float(
                match.group(1)
            )

    return None


# ============================================================
# TAKE PROFITS
# ============================================================

def extract_tp_levels(text):

    tp_levels = {}

    pattern = (
        r"\bTP\s*([1-9])"
        r"\s*[:.\-=]?"
        r"\s*(\d+(?:\.\d+)?)"
    )

    matches = re.findall(
        pattern,
        text,
        re.IGNORECASE
    )

    for tp_number, tp_price in matches:

        tp_levels[
            int(tp_number)
        ] = float(tp_price)

    return dict(
        sorted(
            tp_levels.items()
        )
    )


# ============================================================
# PRICE RANGE VALIDATION
# ============================================================

def validate_gold_price_range(
    entry_low,
    entry_high,
    stoploss,
    tp_levels,
    errors
):

    all_prices = [

        entry_low,

        entry_high,

        stoploss,
    ]

    all_prices.extend(
        tp_levels.values()
    )

    for price in all_prices:

        if price is None:

            continue

        if not 1800 <= price <= 6000:

            errors.append(
                f"Price {price} outside Gold range"
            )


# ============================================================
# EXECUTION TP VALIDATION
# ============================================================

def validate_execution_tps(
    direction,
    entry_low,
    entry_high,
    tp_levels,
    execution_mapping,
    errors
):

    if not execution_mapping:

        errors.append(
            "No execution TP mapping found"
        )

        return

    tp_number_1, tp_number_2 = (
        execution_mapping
    )

    execution_tp_1 = tp_levels.get(
        tp_number_1
    )

    execution_tp_2 = tp_levels.get(
        tp_number_2
    )

    # --------------------------------------------------------
    # Check that required execution TPs exist
    # --------------------------------------------------------

    if execution_tp_1 is None:

        errors.append(
            f"Required TP{tp_number_1} "
            "not found"
        )

    if execution_tp_2 is None:

        errors.append(
            f"Required TP{tp_number_2} "
            "not found"
        )

    if errors:

        return

    # --------------------------------------------------------
    # BUY
    #
    # For BUY:
    #
    # SL < ENTRY < TP
    #
    # Both execution TPs must be ABOVE
    # the entire entry range.
    # --------------------------------------------------------

    if direction == "BUY":

        if execution_tp_1 <= entry_high:

            errors.append(
                f"BUY execution TP{tp_number_1} "
                f"{execution_tp_1} is not above "
                f"entry {entry_high}"
            )

        if execution_tp_2 <= entry_high:

            errors.append(
                f"BUY execution TP{tp_number_2} "
                f"{execution_tp_2} is not above "
                f"entry {entry_high}"
            )

    # --------------------------------------------------------
    # SELL
    #
    # For SELL:
    #
    # TP < ENTRY < SL
    #
    # Both execution TPs must be BELOW
    # the entire entry range.
    # --------------------------------------------------------

    elif direction == "SELL":

        if execution_tp_1 >= entry_low:

            errors.append(
                f"SELL execution TP{tp_number_1} "
                f"{execution_tp_1} is not below "
                f"entry {entry_low}"
            )

        if execution_tp_2 >= entry_low:

            errors.append(
                f"SELL execution TP{tp_number_2} "
                f"{execution_tp_2} is not below "
                f"entry {entry_low}"
            )


# ============================================================
# PRICE / SIGNAL VALIDATION
# ============================================================

def validate_signal(
    direction,
    entry_low,
    entry_high,
    stoploss,
    tp_levels,
    channel_name
):

    errors = []

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    if direction not in (
        "BUY",
        "SELL"
    ):

        errors.append(
            "Missing BUY/SELL direction"
        )

    if entry_low is None:

        errors.append(
            "Missing entry"
        )

    if stoploss is None:

        errors.append(
            "Missing stop loss"
        )

    if not tp_levels:

        errors.append(
            "No TP levels found"
        )

    if errors:

        return False, errors

    # --------------------------------------------------------
    # Entry sanity
    # --------------------------------------------------------

    if entry_low > entry_high:

        errors.append(
            "Invalid entry range"
        )

    # --------------------------------------------------------
    # Gold price range
    # --------------------------------------------------------

    validate_gold_price_range(
        entry_low,
        entry_high,
        stoploss,
        tp_levels,
        errors
    )

    # --------------------------------------------------------
    # Entry range width
    # --------------------------------------------------------

    if (
        entry_high - entry_low
    ) > 100:

        errors.append(
            f"Entry range too wide: "
            f"{entry_low}-{entry_high}"
        )

    # --------------------------------------------------------
    # STOP LOSS validation
    # --------------------------------------------------------

    if direction == "BUY":

        if stoploss >= entry_low:

            errors.append(
                f"BUY SL {stoploss} is not below "
                f"entry {entry_low}"
            )

    elif direction == "SELL":

        if stoploss <= entry_high:

            errors.append(
                f"SELL SL {stoploss} is not above "
                f"entry {entry_high}"
            )

    # --------------------------------------------------------
    # FIND SOURCE TP MAPPING
    # --------------------------------------------------------

    mapping = get_tp_mapping(
        channel_name
    )

    if not mapping:

        errors.append(
            f"No TP mapping configured for "
            f"channel '{channel_name}'"
        )

        return (
            len(errors) == 0,
            errors
        )

    # --------------------------------------------------------
    # VALIDATE ONLY EXECUTION TPs
    # --------------------------------------------------------

    validate_execution_tps(
        direction,
        entry_low,
        entry_high,
        tp_levels,
        mapping,
        errors
    )

    return (
        len(errors) == 0,
        errors
    )


# ============================================================
# PARSE SIGNAL
# ============================================================

def parse_signal(
    message,
    channel_name
):

    message = normalize_text(
        message
    )

    direction = extract_direction(
        message
    )

    entry_low, entry_high, entry_type = (
        extract_entry(message)
    )

    stoploss = extract_sl(
        message
    )

    tp_levels = extract_tp_levels(
        message
    )

    valid, errors = validate_signal(
        direction,
        entry_low,
        entry_high,
        stoploss,
        tp_levels,
        channel_name
    )

    mapping = get_tp_mapping(
        channel_name
    )

    execution_tp_1 = None
    execution_tp_2 = None

    if mapping:

        tp_number_1, tp_number_2 = mapping

        execution_tp_1 = tp_levels.get(
            tp_number_1
        )

        execution_tp_2 = tp_levels.get(
            tp_number_2
        )

    else:

        tp_number_1 = None
        tp_number_2 = None

    signal = {

        "channel": channel_name,

        "normalized_channel":
            normalize_channel_name(
                channel_name
            ),

        "direction": direction,

        "entry": entry_low,

        "entry_low": entry_low,

        "entry_high": entry_high,

        "entry_type": entry_type,

        "stoploss": stoploss,

        "tp1": tp_levels.get(1),

        "tp2": tp_levels.get(2),

        "tp3": tp_levels.get(3),

        "tp4": tp_levels.get(4),

        "tp5": tp_levels.get(5),

        "tp6": tp_levels.get(6),

        "tp_levels": tp_levels,

        # ----------------------------------------------------
        # Execution mapping
        # ----------------------------------------------------

        "execution_tp_numbers": (
            mapping
            if mapping
            else None
        ),

        "execution_tp1_number":
            tp_number_1,

        "execution_tp2_number":
            tp_number_2,

        "execution_tp1":
            execution_tp_1,

        "execution_tp2":
            execution_tp_2,

        "parse_success": valid,

        "validation_errors": errors,

        "timestamp": datetime.now(
            TIMEZONE
        ),
    }

    return signal


# ============================================================
# FORMAT PARSED SIGNAL
# ============================================================

def format_parsed_signal(signal):

    entry_low = signal["entry_low"]

    entry_high = signal["entry_high"]

    if entry_low == entry_high:

        entry_text = (
            f"{entry_low:.2f}"
        )

    else:

        entry_text = (
            f"{entry_low:.2f} - "
            f"{entry_high:.2f}"
        )

    mapping = (
        signal.get(
            "execution_tp_numbers"
        )
    )

    lines = [

        "🟢 SIGNAL PARSED",

        "────────────────────",

        f"📺 Channel: "
        f"{signal['channel']}",

        f"💎 Asset: XAU/USD",

        f"🎯 Direction: "
        f"{signal['direction']}",

        f"💰 Entry: "
        f"{entry_text}",

        f"🛑 SL: "
        f"{signal['stoploss']:.2f}",
    ]

    # --------------------------------------------------------
    # ALL RECEIVED TPs
    # --------------------------------------------------------

    for number, price in (
        signal["tp_levels"].items()
    ):

        lines.append(
            f"🎯 TP{number}: "
            f"{price:.2f}"
        )

    # --------------------------------------------------------
    # EXECUTION TPs
    # --------------------------------------------------------

    if mapping:

        tp_a, tp_b = mapping

        lines.extend([

            "",

            "📌 EXECUTION TARGETS",

            f"Position 1 → "
            f"TP{tp_a}: "
            f"{signal['tp_levels'].get(tp_a):.2f}",

            f"Position 2 → "
            f"TP{tp_b}: "
            f"{signal['tp_levels'].get(tp_b):.2f}",
        ])

    lines.extend([

        "────────────────────",

        "✅ Parser Status: VALID",

        f"⏰ "
        f"{signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}",
    ])

    return "\n".join(
        lines
    )


# ============================================================
# FORMAT INVALID SIGNAL
# ============================================================

def format_invalid_signal(
    signal,
    raw_message
):

    mapping = signal.get(
        "execution_tp_numbers"
    )

    lines = [

        "🔴 SIGNAL REJECTED",

        "────────────────────",

        f"📺 Channel: "
        f"{signal['channel']}",

        f"🎯 Direction: "
        f"{signal['direction']}",

        f"💰 Entry: "
        f"{signal['entry_low']} - "
        f"{signal['entry_high']}",

        f"🛑 SL: "
        f"{signal['stoploss']}",
    ]

    if mapping:

        tp_a, tp_b = mapping

        lines.extend([

            "",

            "📌 Required execution TPs:",

            f"TP{tp_a}: "
            f"{signal['tp_levels'].get(tp_a)}",

            f"TP{tp_b}: "
            f"{signal['tp_levels'].get(tp_b)}",
        ])

    lines.extend([

        "",

        "❌ REASON:",
    ])

    for error in (
        signal["validation_errors"]
    ):

        lines.append(
            f"• {error}"
        )

    lines.extend([

        "",

        "Raw message:",

        raw_message[:1000],
    ])

    return "\n".join(
        lines
    )


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH
)


# ============================================================
# RESOLVE SOURCE CHANNELS
# ============================================================

async def resolve_sources():

    valid_sources = []

    print()
    print("=" * 70)
    print("RESOLVING SOURCE CHANNELS")
    print("=" * 70)

    for username in SOURCE_CHANNELS:

        print()
        print(
            f"🔍 {username}"
        )

        try:

            entity = await client.get_entity(
                username
            )

            valid_sources.append(
                entity
            )

            title = getattr(
                entity,
                "title",
                username
            )

            entity_id = getattr(
                entity,
                "id",
                "Unknown"
            )

            print(
                "   ✅ ACCESSIBLE"
            )

            print(
                f"   Name: {title}"
            )

            print(
                f"   ID: {entity_id}"
            )

        except (
            UsernameInvalidError,
            UsernameNotOccupiedError,
            ValueError
        ) as e:

            print(
                f"   ❌ NOT ACCESSIBLE: {e}"
            )

    print()

    print(
        f"Accessible sources: "
        f"{len(valid_sources)}/"
        f"{len(SOURCE_CHANNELS)}"
    )

    return valid_sources


# ============================================================
# VERIFY TEST OUTPUT CHANNEL
# ============================================================

async def verify_output_channel():

    print()
    print("=" * 70)
    print("VERIFYING TEST OUTPUT CHANNEL")
    print("=" * 70)

    try:

        entity = await client.get_entity(
            TEST_OUTPUT_CHANNEL_ID
        )

        title = getattr(
            entity,
            "title",
            "Unknown"
        )

        print(
            f"✅ Output channel accessible: "
            f"{title}"
        )

        print(
            f"   ID: "
            f"{TEST_OUTPUT_CHANNEL_ID}"
        )

        return entity

    except Exception as e:

        print(
            f"❌ Could not access output channel: "
            f"{e}"
        )

        return None


# ============================================================
# MESSAGE HANDLER
# ============================================================

async def handle_message(event):

    try:

        message_text = (
            event.message.message
        )

        if not message_text:

            return

        chat = await event.get_chat()

        channel_name = (

            getattr(
                chat,
                "title",
                None
            )

            or

            getattr(
                chat,
                "username",
                None
            )

            or

            "Unknown"
        )

        print()
        print("=" * 70)
        print("📨 NEW MESSAGE")
        print("=" * 70)

        print(
            f"Time: "
            f"{datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print(
            f"Channel: "
            f"{channel_name}"
        )

        print(
            f"Message ID: "
            f"{event.message.id}"
        )

        print()
        print("RAW MESSAGE:")
        print("-" * 70)

        print(
            message_text
        )

        print("-" * 70)

        # ----------------------------------------------------
        # SHOW SOURCE TP MAPPING
        # ----------------------------------------------------

        mapping = get_tp_mapping(
            channel_name
        )

        if mapping:

            print()
            print(
                f"Execution TP mapping: "
                f"TP{mapping[0]} + TP{mapping[1]}"
            )

        else:

            print()
            print(
                "⚠️ No execution TP mapping found"
            )

        # ----------------------------------------------------
        # PARSE
        # ----------------------------------------------------

        signal = parse_signal(
            message_text,
            channel_name
        )

        # ----------------------------------------------------
        # VALID SIGNAL
        # --------------------------------------------------------

        if signal["parse_success"]:

            print()
            print(
                "🟢 SIGNAL PARSED SUCCESSFULLY"
            )

            print(
                f"Direction: "
                f"{signal['direction']}"
            )

            print(
                f"Entry: "
                f"{signal['entry_low']} - "
                f"{signal['entry_high']}"
            )

            print(
                f"SL: "
                f"{signal['stoploss']}"
            )

            print(
                f"All TPs: "
                f"{signal['tp_levels']}"
            )

            print(
                f"Execution TPs: "
                f"TP{signal['execution_tp1_number']} "
                f"+ "
                f"TP{signal['execution_tp2_number']}"
            )

            print(
                f"Execution prices: "
                f"{signal['execution_tp1']} "
                f"+ "
                f"{signal['execution_tp2']}"
            )

            output = format_parsed_signal(
                signal
            )

            await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                output
            )

            print()

            print(
                "✅ Parsed signal sent to "
                "Guns' Goldbot"
            )

        # ----------------------------------------------------
        # INVALID SIGNAL
        # ----------------------------------------------------

        else:

            print()
            print(
                "🔴 MESSAGE REJECTED BY PARSER"
            )

            for error in (
                signal["validation_errors"]
            ):

                print(
                    f"   ❌ {error}"
                )

            output = format_invalid_signal(
                signal,
                message_text
            )

            await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                output
            )

            print()

            print(
                "📤 Rejection report sent to "
                "Guns' Goldbot"
            )

    except Exception as e:

        print()
        print(
            f"❌ ERROR PROCESSING MESSAGE: "
            f"{e}"
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("=" * 70)
    print("PHASE 4 - LIVE TELEGRAM SIGNAL PARSER")
    print("=" * 70)

    print()
    print(
        "Connecting to Telegram..."
    )

    await client.connect()

    if not await client.is_user_authorized():

        print(
            "❌ SESSION IS NOT AUTHORIZED"
        )

        await client.disconnect()

        return

    print(
        "✅ TELEGRAM SESSION AUTHORIZED"
    )

    # --------------------------------------------------------
    # Resolve sources
    # --------------------------------------------------------

    valid_sources = (
        await resolve_sources()
    )

    if not valid_sources:

        print()
        print(
            "❌ NO SOURCE CHANNELS ARE ACCESSIBLE"
        )

        await client.disconnect()

        return

    # --------------------------------------------------------
    # Verify output
    # --------------------------------------------------------

    output_channel = (
        await verify_output_channel()
    )

    if output_channel is None:

        await client.disconnect()

        return

    # --------------------------------------------------------
    # Print mappings
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("EXECUTION TP MAPPINGS")
    print("=" * 70)

    for channel, mapping in (
        TP_MAPPING.items()
    ):

        print(
            f"  • {channel}: "
            f"TP{mapping[0]} + TP{mapping[1]}"
        )

    # --------------------------------------------------------
    # Register listener
    # --------------------------------------------------------

    client.add_event_handler(
        handle_message,
        events.NewMessage(
            chats=valid_sources
        )
    )

    print()
    print("=" * 70)
    print("LIVE PARSER LISTENER ACTIVE")
    print("=" * 70)

    print()
    print("Monitoring:")

    for source in valid_sources:

        print(
            f"  • "
            f"{getattr(source, 'title', source)}"
        )

    print()

    print(
        "Output:"
    )

    print(
        "  • Guns' Goldbot"
    )

    print()
    print(
        "⚠️ NO TRADING IS ENABLED"
    )

    print(
        "⚠️ NO METAAPI IS CONNECTED"
    )

    print(
        "⚠️ NO MT5 ORDERS CAN BE PLACED"
    )

    print()
    print(
        "Only the mapped execution TPs "
        "are validated."
    )

    print()
    print(
        "Waiting for Telegram signals..."
    )

    print()
    print(
        "Press CTRL+C to stop."
    )

    try:

        await client.run_until_disconnected()

    finally:

        await client.disconnect()

        print(
            "Telegram client disconnected."
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "🛑 Phase 4 stopped by user."
        )