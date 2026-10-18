import os
import re
import asyncio
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv

from telethon import TelegramClient, events, utils
from telethon.sessions import StringSession


# ============================================================
# PHASE 4 — LIVE TELEGRAM GOLD SIGNAL PARSER
# ============================================================
#
# PURPOSE:
#
#   Monitor the configured Telegram gold-signal channels,
#   parse incoming gold signals,
#   validate them,
#   determine the correct execution TPs,
#   and publish the parsed result to Guns' Goldbot.
#
# IMPORTANT:
#
#   THIS SERVICE DOES NOT:
#
#       - connect to MetaApi
#       - connect to MT5
#       - place trades
#       - modify trades
#       - close trades
#
#   This is PARSER ONLY.
#
#   The future Phase 6 executor will handle DEMO trading.
#
# ============================================================


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()

API_ID = int(
    os.getenv(
        "TELEGRAM_API_ID",
        "14424659"
    )
)

API_HASH = os.getenv(
    "TELEGRAM_API_HASH"
)

# Render:
#   TELEGRAM_SESSION_STRING
#
# Local:
#   gold_signal_bot.session
#
SESSION_STRING = os.getenv(
    "TELEGRAM_SESSION_STRING"
)

LOCAL_SESSION_NAME = os.getenv(
    "TELEGRAM_LOCAL_SESSION",
    "gold_signal_bot"
)

# Private Telegram queue / monitoring channel
TEST_OUTPUT_CHANNEL_ID = int(
    os.getenv(
        "TELEGRAM_CHANNEL_ID",
        "-1003995895185"
    )
)

TIMEZONE = pytz.timezone(
    "Africa/Harare"
)


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

if not API_HASH:
    raise RuntimeError(
        "TELEGRAM_API_HASH is missing."
    )


# ============================================================
# SOURCE CHANNELS
# ============================================================
#
# THREE REAL SIGNAL SOURCES
# PLUS GUNS THE TRADER AS TEST SOURCE
#
# Numeric IDs are deliberately used instead of usernames.
#
# ============================================================

SOURCE_CHANNELS = [

    # --------------------------------------------------------
    # REAL SOURCE 1
    # --------------------------------------------------------

    -1004316213872,      # Daily Gold Signals

    # --------------------------------------------------------
    # REAL SOURCE 2
    # --------------------------------------------------------

    -1001685029638,      # Trading View

    # --------------------------------------------------------
    # REAL SOURCE 3
    # --------------------------------------------------------

    -1001303958625,      # KING OF XAUUSD

    # --------------------------------------------------------
    # TEST SOURCE
    # --------------------------------------------------------

    -1003170522699,      # GUNS THE TRADER
]


# ============================================================
# EXECUTION TP MAPPING
# ============================================================
#
# Each channel has its own two execution targets.
#
# Daily Gold Signals           -> TP5 + TP7
# Trading View                 -> TP4 + TP8
# KING OF XAUUSD               -> TP3 + TP5
# GUNS THE TRADER              -> TP3 + TP4
#
# ============================================================

TP_MAPPING = {

    -1004316213872: (5, 7),

    -1001685029638: (4, 8),

    -1001303958625: (3, 5),

    -1003170522699: (3, 4),
}


# ============================================================
# CHANNEL DISPLAY NAMES
# ============================================================

CHANNEL_DISPLAY_NAMES = {

    -1004316213872:
        "Daily Gold Signals",

    -1001685029638:
        "Trading View",

    -1001303958625:
        "KING OF XAUUSD",

    -1003170522699:
        "GUNS THE TRADER",
}


# ============================================================
# CHANNEL NAME NORMALIZATION
# ============================================================

def normalize_channel_name(name):

    if not name:
        return ""

    text = str(name).upper()

    replacements = {

        # Bold Unicode letters
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
        "𝗔": "A",
        "𝗩": "V",
        "𝗣": "P",
        "𝗠": "M",
        "𝗞": "K",

        # Mathematical bold
        "𝐆": "G",
        "𝐎": "O",
        "𝐋": "L",
        "𝐃": "D",
        "𝐇": "H",
        "𝐔": "U",
        "𝐍": "N",
        "𝐓": "T",
        "𝐄": "E",
        "𝐑": "R",
        "𝐒": "S",
        "𝐈": "I",
        "𝐀": "A",
        "𝐕": "V",
        "𝐏": "P",
        "𝐌": "M",
        "𝐊": "K",

        "®": " ",
        "™": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    # Remove emoji/symbols
    text = re.sub(
        r"[^A-Z0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


# ============================================================
# TP MAPPING LOOKUP
# ============================================================

def get_tp_mapping(
    channel_id=None,
    channel_name=None
):

    # --------------------------------------------------------
    # PRIMARY METHOD:
    # NUMERIC CHANNEL ID
    # --------------------------------------------------------

    if channel_id is not None:

        try:

            channel_id = int(
                channel_id
            )

            if channel_id in TP_MAPPING:

                return TP_MAPPING[
                    channel_id
                ]

        except (
            ValueError,
            TypeError
        ):

            pass

    # --------------------------------------------------------
    # FALLBACK:
    # CHANNEL NAME
    # --------------------------------------------------------

    normalized = normalize_channel_name(
        channel_name
    )

    if "DAILY GOLD SIGNALS" in normalized:

        return 5, 7

    if "TRADING VIEW" in normalized:

        return 4, 8

    if "KING OF XAUUSD" in normalized:

        return 3, 5

    if "GUNS THE TRADER" in normalized:

        return 3, 4

    return None


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if not text:

        return ""

    text = str(text)

    # Normalize line endings
    text = text.replace(
        "\r",
        "\n"
    )

    # Non-breaking space
    text = text.replace(
        "\u00A0",
        " "
    )

    # Normalize dashes
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )

    # Normalize tabs
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# DIRECTION
# ============================================================

def extract_direction(text):

    if not text:
        return None

    text_upper = text.upper()

    # Standard separated forms:
    # BUY, SELL
    if re.search(r"\bBUY\b", text_upper):
        return "BUY"

    if re.search(r"\bSELL\b", text_upper):
        return "SELL"

    # Some source channels use compact instrument+direction forms:
    # XAUUSDSELL
    # XAUUSDBUY
    # XAUSELL
    # XAUBUY
    if re.search(r"\bXAUUSD\s*(?:SELL|BUY)\b", text_upper):
        return (
            "SELL"
            if re.search(r"\bXAUUSD\s*SELL\b", text_upper)
            else "BUY"
        )

    if re.search(r"\bXAU\s*(?:SELL|BUY)\b", text_upper):
        return (
            "SELL"
            if re.search(r"\bXAU\s*SELL\b", text_upper)
            else "BUY"
        )

    # Compact forms can have no word boundary between XAUUSD and
    # the direction, e.g. XAUUSDSELL.
    if "XAUUSDSELL" in text_upper:
        return "SELL"

    if "XAUUSDBUY" in text_upper:
        return "BUY"

    if "XAUSELL" in text_upper:
        return "SELL"

    if "XAUBUY" in text_upper:
        return "BUY"

    return None


# ============================================================
# ENTRY EXTRACTION
# ============================================================
#
# Supports:
#
# BUY 4642/4650
# BUY 4642 - 4650
# BUY 4642-4650
#
# ENTRY 4642/4650
# ENTRY: 4642/4650
#
# GOLD BUY 4642
# GOLD SELL 4642
#
# XAUUSD BUY 4642
# XAU BUY 4642
#
# BUY GOLD NOW 4642
# SELL GOLD NOW 4642
#
# ============================================================

def extract_entry(text):

    if not text:
        return None

    # --------------------------------------------------------
    # RANGE PATTERNS
    # --------------------------------------------------------

    range_patterns = [

        # Daily Gold Signals:
        # GOLD SELL 4332
        # OTHER SELL 4335
        # GOLD BUY 4332
        # OTHER BUY 4335
        (
            r"\bGOLD\b\s+(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
            r"[\s\S]*?"
            r"\bOTHER\b\s+(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
        ),

        # Trading View:
        # GOLD SELL 4374
        # MORE SELL 4377
        # GOLD BUY 4374
        # MORE BUY 4377
        (
            r"\bGOLD\b\s+(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
            r"[\s\S]*?"
            r"\bMORE\b\s+(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
        ),

        # Standard BUY/SELL followed by range:
        # BUY 4642/4650
        # SELL 4642/4650
        # BUY 4642 - 4650
        # BUY 4642-4650
        (
            r"\b(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
            r"\s*[/_]\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        (
            r"\b(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
            r"\s*-\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # Compact XAUUSD/XAU direction followed by range:
        # XAUUSDSELL 4407/4416
        # XAUUSDBUY 4429/4426
        # XAU SELL 4410/4413
        (
            r"\b(?:XAUUSD|XAU)\s*(?:BUY|SELL)\s*(?:LIMIT|LIMT)?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*[/_]\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        (
            r"\b(?:XAUUSD|XAU)\s*(?:BUY|SELL)\s*(?:LIMIT|LIMT)?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*-\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # Fully compact forms without a word boundary:
        # XAUUSDSELL4407/4416
        # XAUUSDBUY4429/4426
        (
            r"XAUUSD(?:BUY|SELL)\s*(?:LIMIT|LIMT)?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*[/_]\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        (
            r"XAUUSD(?:BUY|SELL)\s*(?:LIMIT|LIMT)?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*-\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # ENTRY followed by range
        (
            r"\bENTRY\b\s*[:.\-]?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*[/_]\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        (
            r"\bENTRY\b\s*[:.\-]?\s*"
            r"(\d+(?:\.\d+)?)"
            r"\s*-\s*"
            r"(\d+(?:\.\d+)?)"
        ),
    ]

    for pattern in range_patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
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
    # SINGLE PRICE PATTERNS
    # --------------------------------------------------------

    single_patterns = [

        # GOLD BUY 4642
        (
            r"\b(?:GOLD|XAUUSD|XAU)\b\s+"
            r"(?:BUY|SELL)\b"
            r"(?:\s+NOW)?\s+"
            r"(\d+(?:\.\d+)?)"
            r"(?:\s+00\b)?"
        ),

        # Compact XAUUSDSELL 4407
        # XAUUSDBUY 4426
        (
            r"XAUUSD(?:BUY|SELL)\s*(?:LIMIT|LIMT)?\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # Compact XAU SELL 4407
        (
            r"\bXAU\s*(?:BUY|SELL)\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # BUY GOLD 4642
        (
            r"\b(?:BUY|SELL)\b\s+"
            r"(?:GOLD|XAUUSD|XAU)\b"
            r"(?:\s+NOW)?\s+"
            r"(\d+(?:\.\d+)?)"
            r"(?:\s+00\b)?"
        ),

        # ENTRY: 4642
        (
            r"\bENTRY\b\s*[:.\-]?\s*"
            r"(\d+(?:\.\d+)?)"
        ),

        # BUY 4642
        (
            r"\b(?:BUY|SELL)\b\s+"
            r"(\d+(?:\.\d+)?)"
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

    return None


# ============================================================
# STOP LOSS
# ============================================================

def extract_sl(text):

    if not text:
        return None

    patterns = [

        # SL 4640
        # SL: 4640
        # SL. 4640
        # SL - 4640
        # SL @ 4640
        r"\bSL(?:\b|_)\s*[@:._\-]?\s*"
        r"(\d+(?:\.\d+)?)",

        # STOPLOSS 4640
        r"\bSTOPLOSS\b\s*[@:.\-]?\s*"
        r"(\d+(?:\.\d+)?)",

        # STOP LOSS 4640
        r"\bSTOP\s+LOSS\b\s*[@:.\-]?\s*"
        r"(\d+(?:\.\d+)?)",

        # STOP 4640
        r"\bSTOP\b\s*[@:.\-]?\s*"
        r"(\d+(?:\.\d+)?)",
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
# TAKE PROFIT EXTRACTION
# ============================================================
#
# Supports TP1 through TP9.
#
# Examples:
#
# TP1 4655
# TP1: 4655
# TP1 - 4655
# TP1=4655
# TP1. 4655
#
# ============================================================

def extract_tp_levels(text):

    if not text:
        return {}

    tp_levels = {}

    # --------------------------------------------------------
    # UNICODE SUPERSCRIPT TP NUMBERS
    # --------------------------------------------------------
    #
    # Some channels use:
    #
    # TP¹ 4398
    # TP² 4401
    # TP³ 4404
    # TP⁴ 4407
    # TP⁵ 4410
    # TP⁶ 4413
    #
    # Convert the superscript number to the normal TP number.
    #
    superscript_map = {
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
    }

    normalized_tp_text = text

    for superscript, normal in superscript_map.items():

        normalized_tp_text = normalized_tp_text.replace(
            f"TP{superscript}",
            f"TP{normal}"
        )

    # --------------------------------------------------------
    # STANDARD TP FORMATS
    # --------------------------------------------------------
    #
    # Supports:
    #
    # TP1 4655
    # TP1: 4655
    # TP1 - 4655
    # TP1=4655
    # TP1. 4655
    # TP1. @ 4655
    # TP1 @ 4655
    #
    # The @ is deliberately optional because some source
    # channels use it before the target price.
    #
    pattern = (
        r"\bTP\s*([1-9])"
        r"(?=\s|[:.\-=]|$)"
        r"\s*[:.\-=]?"
        r"\s*@?\s*"
        r"(\d+(?:\.\d+)?)"
    )

    matches = re.findall(
        pattern,
        normalized_tp_text,
        re.IGNORECASE
    )

    for tp_number, price in matches:

        tp_levels[
            int(tp_number)
        ] = float(price)

    # --------------------------------------------------------
    # UNNUMBERED TP FORMAT
    # --------------------------------------------------------
    #
    # Some channels send TPs positionally, for example:
    #
    # TP 4220
    # TP 4215
    # TP 4210
    # TP 4205
    # TP 4200
    #
    # These are interpreted in order as TP1, TP2, TP3, ...
    # This is a fallback only, so explicitly numbered TP1, TP2,
    # etc. continue to work exactly as before.
    #
    if not matches:

        unnumbered_pattern = (
            r"\bTP\b\s+"
            r"(\d+(?:\.\d+)?)"
        )

        unnumbered_matches = re.findall(
            unnumbered_pattern,
            normalized_tp_text,
            re.IGNORECASE
        )

        for index, price in enumerate(
            unnumbered_matches,
            start=1
        ):

            if index > 9:
                break

            tp_levels[index] = float(price)

    return dict(
        sorted(
            tp_levels.items()
        )
    )


# ============================================================
# PRICE VALIDATION
# ============================================================

def validate_gold_price_range(
    price
):

    if price is None:

        return False

    return (
        1800 <= price <= 6000
    )


# ============================================================
# FULL SIGNAL VALIDATION
# ============================================================

def validate_signal(
    direction,
    entry_low,
    entry_high,
    stoploss,
    tp_levels,
    execution_tps
):

    errors = []

    # --------------------------------------------------------
    # DIRECTION
    # --------------------------------------------------------

    if direction not in (
        "BUY",
        "SELL"
    ):

        errors.append(
            "Missing or invalid BUY/SELL direction"
        )

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    if entry_low is None:

        errors.append(
            "Missing entry"
        )

    if entry_high is None:

        errors.append(
            "Missing entry"
        )

    if (
        entry_low is not None
        and entry_high is not None
    ):

        if entry_low > entry_high:

            errors.append(
                "Invalid entry range"
            )

        if (
            entry_high - entry_low
        ) > 100:

            errors.append(
                f"Entry range too wide: "
                f"{entry_low}-{entry_high}"
            )

        if not validate_gold_price_range(
            entry_low
        ):

            errors.append(
                f"Entry price {entry_low} "
                f"is outside XAUUSD range"
            )

        if not validate_gold_price_range(
            entry_high
        ):

            errors.append(
                f"Entry price {entry_high} "
                f"is outside XAUUSD range"
            )

    # --------------------------------------------------------
    # STOP LOSS
    # --------------------------------------------------------

    if stoploss is None:

        errors.append(
            "Missing stop loss"
        )

    else:

        if not validate_gold_price_range(
            stoploss
        ):

            errors.append(
                f"SL {stoploss} "
                f"is outside XAUUSD range"
            )

    # --------------------------------------------------------
    # SL DIRECTION
    # --------------------------------------------------------

    if (
        direction == "BUY"
        and entry_low is not None
        and stoploss is not None
    ):

        if stoploss >= entry_low:

            errors.append(
                f"BUY SL {stoploss} "
                f"is not below entry "
                f"{entry_low}"
            )

    if (
        direction == "SELL"
        and entry_high is not None
        and stoploss is not None
    ):

        if stoploss <= entry_high:

            errors.append(
                f"SELL SL {stoploss} "
                f"is not above entry "
                f"{entry_high}"
            )

    # --------------------------------------------------------
    # EXECUTION TP MAPPING
    # --------------------------------------------------------

    if not execution_tps:

        errors.append(
            "No execution TP mapping found"
        )

        return (
            False,
            errors
        )

    tp_number_1, tp_number_2 = (
        execution_tps
    )

    # --------------------------------------------------------
    # REQUIRED EXECUTION TPs
    # --------------------------------------------------------

    execution_tp_1 = tp_levels.get(
        tp_number_1
    )

    execution_tp_2 = tp_levels.get(
        tp_number_2
    )

    if execution_tp_1 is None:

        errors.append(
            f"Required TP{tp_number_1} "
            f"not found"
        )

    if execution_tp_2 is None:

        errors.append(
            f"Required TP{tp_number_2} "
            f"not found"
        )

    # --------------------------------------------------------
    # VALIDATE ALL PRESENT TP PRICES
    # --------------------------------------------------------

    for tp_number, price in tp_levels.items():

        if not validate_gold_price_range(
            price
        ):

            errors.append(
                f"TP{tp_number} price "
                f"{price} is outside "
                f"XAUUSD range"
            )

    # --------------------------------------------------------
    # EXECUTION TP DIRECTION
    # --------------------------------------------------------

    if (
        direction == "BUY"
        and entry_high is not None
    ):

        if (
            execution_tp_1 is not None
            and execution_tp_1 <= entry_high
        ):

            errors.append(
                f"BUY execution TP"
                f"{tp_number_1} "
                f"{execution_tp_1} "
                f"is not above entry "
                f"{entry_high}"
            )

        if (
            execution_tp_2 is not None
            and execution_tp_2 <= entry_high
        ):

            errors.append(
                f"BUY execution TP"
                f"{tp_number_2} "
                f"{execution_tp_2} "
                f"is not above entry "
                f"{entry_high}"
            )

    elif (
        direction == "SELL"
        and entry_low is not None
    ):

        if (
            execution_tp_1 is not None
            and execution_tp_1 >= entry_low
        ):

            errors.append(
                f"SELL execution TP"
                f"{tp_number_1} "
                f"{execution_tp_1} "
                f"is not below entry "
                f"{entry_low}"
            )

        if (
            execution_tp_2 is not None
            and execution_tp_2 >= entry_low
        ):

            errors.append(
                f"SELL execution TP"
                f"{tp_number_2} "
                f"{execution_tp_2} "
                f"is not below entry "
                f"{entry_low}"
            )

    if errors:

        return (
            False,
            errors
        )

    return (
        True,
        []
    )


# ============================================================
# PARSE SIGNAL
# ============================================================

def parse_signal(
    message,
    channel_name,
    channel_id=None,
    message_id=None
):

    # --------------------------------------------------------
    # SIGNAL METADATA
    # --------------------------------------------------------

    signal_time = datetime.now(
        TIMEZONE
    )

    # Telegram message IDs are unique within each source channel.
    # Combining the channel ID and message ID gives the signal
    # a stable unique identifier for the executor.
    if message_id is not None:
        signal_id = (
            f"SIG-{abs(int(channel_id))}"
            f"-{message_id}"
            if channel_id is not None
            else f"SIG-{message_id}"
        )
    else:
        signal_id = (
            f"SIG-{abs(int(channel_id))}"
            f"-{signal_time.strftime('%Y%m%d%H%M%S%f')}"
            if channel_id is not None
            else f"SIG-{signal_time.strftime('%Y%m%d%H%M%S%f')}"
        )

    valid_until = signal_time + timedelta(
        hours=2
    )

    message = normalize_text(
        message
    )

    direction = extract_direction(
        message
    )

    entry = extract_entry(
        message
    )

    stoploss = extract_sl(
        message
    )

    tp_levels = extract_tp_levels(
        message
    )

    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    entry_low = None
    entry_high = None
    entry_type = None

    if entry:

        entry_low = entry[0]
        entry_high = entry[1]
        entry_type = entry[2]

    # --------------------------------------------------------
    # TP MAPPING
    # --------------------------------------------------------

    mapping = get_tp_mapping(
        channel_id=channel_id,
        channel_name=channel_name
    )

    # --------------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------------

    if mapping is None:

        return {
            "valid": False,
            "reason":
                "Unknown source channel / "
                "TP mapping",
            "channel": channel_name,
            "channel_id": channel_id,
            "message_id": message_id,
            "signal_id": signal_id,
            "signal_time": signal_time,
            "valid_until": valid_until,
            "direction": direction,
            "entry_low": entry_low,
            "entry_high": entry_high,
            "entry_type": entry_type,
            "sl": stoploss,
            "stoploss": stoploss,
            "tp_levels": tp_levels,
            "execution_tps": None,
            "execution_tp_numbers": None,
            "execution_tp1": None,
            "execution_tp2": None,
            "validation_errors": [
                "Unknown source channel / TP mapping"
            ],
        }

    # --------------------------------------------------------
    # FULL VALIDATION
    # --------------------------------------------------------

    valid, errors = validate_signal(
        direction=direction,
        entry_low=entry_low,
        entry_high=entry_high,
        stoploss=stoploss,
        tp_levels=tp_levels,
        execution_tps=mapping
    )

    tp_number_1 = mapping[0]
    tp_number_2 = mapping[1]

    execution_tp_1 = tp_levels.get(
        tp_number_1
    )

    execution_tp_2 = tp_levels.get(
        tp_number_2
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result = {

        "valid": valid,

        "reason": (
            None
            if valid
            else (
                "; ".join(errors)
                if errors
                else "Signal rejected"
            )
        ),

        "channel": channel_name,

        "channel_id": channel_id,

        "message_id": message_id,

        "signal_id": signal_id,

        "signal_time": signal_time,

        "valid_until": valid_until,

        "normalized_channel":
            normalize_channel_name(
                channel_name
            ),

        "direction": direction,

        "entry": (
            entry_low
            if entry_low == entry_high
            else (
                (
                    entry_low,
                    entry_high
                )
                if entry_low is not None
                else None
            )
        ),

        "entry_low": entry_low,

        "entry_high": entry_high,

        "entry_type": entry_type,

        "sl": stoploss,

        "stoploss": stoploss,

        "tp_levels": tp_levels,

        "tp1": tp_levels.get(1),

        "tp2": tp_levels.get(2),

        "tp3": tp_levels.get(3),

        "tp4": tp_levels.get(4),

        "tp5": tp_levels.get(5),

        "tp6": tp_levels.get(6),

        "tp7": tp_levels.get(7),

        "tp8": tp_levels.get(8),

        "tp9": tp_levels.get(9),

        "execution_tps": mapping,

        "execution_tp_numbers": mapping,

        "execution_tp1_number":
            tp_number_1,

        "execution_tp2_number":
            tp_number_2,

        "execution_tp1":
            execution_tp_1,

        "execution_tp2":
            execution_tp_2,

        "execution_price_1":
            execution_tp_1,

        "execution_price_2":
            execution_tp_2,

        "parse_success": valid,

        "validation_errors": errors,

        "timestamp":
            datetime.now(
                TIMEZONE
            ),
    }

    return result


# ============================================================
# FORMAT VALID SIGNAL
# ============================================================

def format_parsed_signal(
    signal
):

    direction = signal.get(
        "direction"
    )

    entry_low = signal.get(
        "entry_low"
    )

    entry_high = signal.get(
        "entry_high"
    )

    stoploss = signal.get(
        "stoploss"
    )

    channel_name = signal.get(
        "channel"
    )

    tp_levels = signal.get(
        "tp_levels",
        {}
    )

    mapping = signal.get(
        "execution_tp_numbers"
    )

    execution_tp_1 = signal.get(
        "execution_tp1"
    )

    execution_tp_2 = signal.get(
        "execution_tp2"
    )

    timestamp = signal.get(
        "timestamp"
    )

    signal_id = signal.get(
        "signal_id"
    )

    signal_time = signal.get(
        "signal_time"
    )

    valid_until = signal.get(
        "valid_until"
    )

    if timestamp:

        timestamp_text = timestamp.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    else:

        timestamp_text = (
            datetime.now(
                TIMEZONE
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

    if signal_time:
        signal_time_text = signal_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        signal_time_text = timestamp_text

    if valid_until:
        valid_until_text = valid_until.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        valid_until_text = ""

    # --------------------------------------------------------
    # ENTRY DISPLAY
    # --------------------------------------------------------

    if (
        entry_low is not None
        and entry_high is not None
    ):

        if entry_low == entry_high:

            entry_text = (
                f"{entry_low:.2f}"
            )

        else:

            entry_text = (
                f"{entry_low:.2f}"
                f" - "
                f"{entry_high:.2f}"
            )

    else:

        entry_text = "N/A"

    # --------------------------------------------------------
    # BUILD MESSAGE
    # --------------------------------------------------------

    lines = [

        "🟢 SIGNAL PARSED",

        "────────────────────",

        f"📺 Channel: {channel_name}",

        "💎 Asset: XAU/USD",

        f"🎯 Direction: {direction}",

        f"💰 Entry: {entry_text}",

        (
            f"🛑 SL: "
            f"{stoploss:.2f}"
            if stoploss is not None
            else "🛑 SL: N/A"
        ),

    ]

    # --------------------------------------------------------
    # ALL TPs
    # --------------------------------------------------------

    for tp_number in sorted(
        tp_levels
    ):

        lines.append(
            f"🎯 TP{tp_number}: "
            f"{tp_levels[tp_number]:.2f}"
        )

    # --------------------------------------------------------
    # EXECUTION TARGETS
    # --------------------------------------------------------

    lines.extend([

        "",

        "📌 EXECUTION TARGETS",

    ])

    if mapping:

        lines.append(
            f"Position 1 → "
            f"TP{mapping[0]} "
            f"({execution_tp_1:.2f})"
        )

        lines.append(
            f"Position 2 → "
            f"TP{mapping[1]} "
            f"({execution_tp_2:.2f})"
        )

    else:

        lines.append(
            "No execution mapping"
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    lines.extend([

        "",

        f"🆔 Signal ID: {signal_id}",

        f"🕒 Signal Time: "
        f"{signal_time_text}",

        f"⏳ Valid Until: "
        f"{valid_until_text}",

        "✅ Parser Status: VALID",

        f"🕒 Timestamp: "
        f"{timestamp_text}",

        "────────────────────",

        "⚠️ DEMO PIPELINE ONLY",

        "No trade executed by Phase 4.",

    ])

    return "\n".join(
        lines
    )


# ============================================================
# FORMAT REJECTED SIGNAL
# ============================================================

def format_rejected_signal(
    signal,
    raw_text
):

    channel_name = signal.get(
        "channel"
    )

    direction = signal.get(
        "direction"
    )

    entry_low = signal.get(
        "entry_low"
    )

    entry_high = signal.get(
        "entry_high"
    )

    stoploss = signal.get(
        "stoploss"
    )

    tp_levels = signal.get(
        "tp_levels",
        {}
    )

    mapping = signal.get(
        "execution_tp_numbers"
    )

    errors = signal.get(
        "validation_errors",
        []
    )

    timestamp = signal.get(
        "timestamp"
    )

    if timestamp:

        timestamp_text = timestamp.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    else:

        timestamp_text = (
            datetime.now(
                TIMEZONE
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

    lines = [

        "🔴 SIGNAL REJECTED",

        "────────────────────",

        f"📺 Channel: {channel_name}",

    ]

    if direction:

        lines.append(
            f"🎯 Direction: {direction}"
        )

    if (
        entry_low is not None
        and entry_high is not None
    ):

        if entry_low == entry_high:

            lines.append(
                f"💰 Entry: "
                f"{entry_low:.2f}"
            )

        else:

            lines.append(
                f"💰 Entry: "
                f"{entry_low:.2f} - "
                f"{entry_high:.2f}"
            )

    else:

        lines.append(
            "💰 Entry: NOT FOUND"
        )

    if stoploss is not None:

        lines.append(
            f"🛑 SL: {stoploss:.2f}"
        )

    else:

        lines.append(
            "🛑 SL: NOT FOUND"
        )

    # --------------------------------------------------------
    # ALL DETECTED TPs
    # --------------------------------------------------------

    for tp_number in sorted(
        tp_levels
    ):

        lines.append(
            f"🎯 TP{tp_number}: "
            f"{tp_levels[tp_number]:.2f}"
        )

    # --------------------------------------------------------
    # EXECUTION MAPPING
    # --------------------------------------------------------

    lines.append("")

    if mapping:

        lines.append(
            f"📌 Required execution TPs: "
            f"TP{mapping[0]} + TP{mapping[1]}"
        )

    else:

        lines.append(
            "📌 Required execution TPs: "
            "NO MAPPING"
        )

    # --------------------------------------------------------
    # REJECTION REASONS
    # --------------------------------------------------------

    lines.extend([

        "",

        "❌ REJECTION REASONS",

    ])

    if errors:

        for error in errors:

            lines.append(
                f"• {error}"
            )

    else:

        reason = signal.get(
            "reason"
        )

        lines.append(
            f"• {reason or 'Signal rejected'}"
        )

    # --------------------------------------------------------
    # RAW MESSAGE
    # --------------------------------------------------------

    lines.extend([

        "",

        "📝 RAW MESSAGE",

        "────────────────────",

        raw_text,

        "",

        f"🕒 Timestamp: "
        f"{timestamp_text}",

        "────────────────────",

        "⚠️ No trade was executed.",

    ])

    return "\n".join(
        lines
    )


# ============================================================
# TELEGRAM CLIENT
# ============================================================

def create_telegram_client():

    # --------------------------------------------------------
    # RENDER AUTHENTICATION
    # --------------------------------------------------------

    if SESSION_STRING:

        print(
            "🔐 Using TELEGRAM_SESSION_STRING"
        )

        return TelegramClient(
            StringSession(
                SESSION_STRING
            ),
            API_ID,
            API_HASH
        )

    # --------------------------------------------------------
    # LOCAL AUTHENTICATION
    # --------------------------------------------------------

    print(
        "🔐 Using local Telegram session:"
        f" {LOCAL_SESSION_NAME}"
    )

    return TelegramClient(
        LOCAL_SESSION_NAME,
        API_ID,
        API_HASH
    )


# ============================================================
# RESOLVE SOURCE CHANNELS
# ============================================================

async def resolve_source_channels(
    client
):

    print()
    print("=" * 70)
    print(
        "🔎 VERIFYING TELEGRAM SOURCE CHANNELS"
    )
    print("=" * 70)

    resolved_channels = []

    accessible = []

    failed = []

    # --------------------------------------------------------
    # CHECK EACH SOURCE
    # --------------------------------------------------------

    for channel_id in SOURCE_CHANNELS:

        print()

        print(
            f"Checking channel ID: "
            f"{channel_id}"
        )

        try:

            entity = await client.get_entity(
                channel_id
            )

            # Convert entity to Telegram peer ID
            resolved_id = utils.get_peer_id(
                entity
            )

            title = getattr(
                entity,
                "title",
                None
            )

            username = getattr(
                entity,
                "username",
                None
            )

            mapping = get_tp_mapping(
                channel_id=channel_id,
                channel_name=title
            )

            display_name = (
                title
                or CHANNEL_DISPLAY_NAMES.get(
                    channel_id,
                    str(channel_id)
                )
            )

            print(
                f"  ✅ {display_name}"
            )

            print(
                f"     ID: {resolved_id}"
            )

            if username:

                print(
                    f"     Username: "
                    f"@{username}"
                )

            if mapping:

                print(
                    f"     TP Mapping: "
                    f"TP{mapping[0]} + "
                    f"TP{mapping[1]}"
                )

            else:

                print(
                    "     TP Mapping: NONE"
                )

            accessible.append(
                channel_id
            )

            resolved_channels.append(
                entity
            )

        except Exception as exc:

            print(
                f"  ❌ FAILED: "
                f"{channel_id}"
            )

            print(
                f"     Reason: {exc}"
            )

            failed.append(
                channel_id
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        f"Accessible sources: "
        f"{len(accessible)}/{len(SOURCE_CHANNELS)}"
    )

    if failed:

        print(
            f"❌ Failed sources: "
            f"{len(failed)}"
        )

        for channel_id in failed:

            print(
                f"   • {channel_id}"
            )

    else:

        print(
            "✅ ALL SOURCE CHANNELS ACCESSIBLE"
        )

    print("=" * 70)

    return resolved_channels


# ============================================================
# VERIFY TP MAPPINGS
# ============================================================

def print_tp_mappings():

    print()
    print("=" * 70)
    print(
        "📌 EXECUTION TP MAPPINGS"
    )
    print("=" * 70)

    for channel_id in SOURCE_CHANNELS:

        mapping = TP_MAPPING.get(
            channel_id
        )

        name = CHANNEL_DISPLAY_NAMES.get(
            channel_id,
            str(channel_id)
        )

        if mapping:

            print(
                f"  • {name}"
            )

            print(
                f"    {channel_id}"
                f" → TP{mapping[0]}"
                f" + TP{mapping[1]}"
            )

        else:

            print(
                f"  • {name}"
                f" → NO MAPPING"
            )

    print("=" * 70)


# ============================================================
# VERIFY OUTPUT CHANNEL
# ============================================================

async def verify_output_channel(
    client
):

    print()
    print("=" * 70)
    print(
        "📤 VERIFYING OUTPUT CHANNEL"
    )
    print("=" * 70)

    try:

        output_entity = await client.get_entity(
            TEST_OUTPUT_CHANNEL_ID
        )

        output_name = getattr(
            output_entity,
            "title",
            None
        )

        output_peer_id = utils.get_peer_id(
            output_entity
        )

        print(
            f"✅ Output channel accessible: "
            f"{output_name}"
        )

        print(
            f"   ID: {output_peer_id}"
        )

        return output_entity

    except Exception as exc:

        print(
            "❌ OUTPUT CHANNEL IS NOT ACCESSIBLE"
        )

        print(
            f"   Channel ID: "
            f"{TEST_OUTPUT_CHANNEL_ID}"
        )

        print(
            f"   Reason: {exc}"
        )

        raise


# ============================================================
# MESSAGE HANDLER
# ============================================================

async def process_message(
    client,
    event
):

    try:

        # Capture diagnostic timestamps for this message.
        handler_received_time = datetime.now(TIMEZONE)
        source_message_time = (
            event.date.astimezone(TIMEZONE)
            if event.date is not None
            else None
        )

        # ----------------------------------------------------
        # GET RAW MESSAGE
        # ----------------------------------------------------

        raw_text = event.raw_text or ""

        if not raw_text.strip():

            print(
                "\n⚠️ Empty Telegram message ignored."
            )

            return

        # ----------------------------------------------------
        # GET SOURCE ENTITY
        # ----------------------------------------------------

        chat = await event.get_chat()

        channel_name = getattr(
            chat,
            "title",
            None
        )

        if not channel_name:

            channel_name = str(
                event.chat_id
            )

        # ----------------------------------------------------
        # TELEGRAM PEER ID
        # ----------------------------------------------------

        channel_id = utils.get_peer_id(
            chat
        )

        # ----------------------------------------------------
        # NORMALIZE SOURCE ID
        # ----------------------------------------------------

        try:

            channel_id = int(
                channel_id
            )

        except (
            TypeError,
            ValueError
        ):

            channel_id = event.chat_id

        # ----------------------------------------------------
        # PARSE
        # ----------------------------------------------------

        result = parse_signal(
            message=raw_text,
            channel_name=channel_name,
            channel_id=channel_id,
            message_id=event.id
        )

        # ----------------------------------------------------
        # PRINT PROCESSING LOG
        # ----------------------------------------------------

        print()
        print("=" * 70)

        print(
            "📥 NEW TELEGRAM MESSAGE"
        )

        print(
            f"📺 Channel: {channel_name}"
        )

        print(
            f"🆔 Channel ID: {channel_id}"
        )

        print(
            f"📝 Message ID: "
            f"{event.id}"
        )

        print(
            f"🎯 Direction: "
            f"{result.get('direction')}"
        )

        print(
            f"💰 Entry: "
            f"{result.get('entry_low')} - "
            f"{result.get('entry_high')}"
        )

        print(
            f"🛑 SL: "
            f"{result.get('stoploss')}"
        )

        print(
            f"🎯 TPs: "
            f"{result.get('tp_levels')}"
        )

        print(
            f"📌 Execution TPs: "
            f"{result.get('execution_tps')}"
        )

        # ----------------------------------------------------
        # VALID SIGNAL
        # ----------------------------------------------------

        if result.get("valid"):

            print(
                "✅ SIGNAL VALID"
            )

            output = format_parsed_signal(
                result
            )

            # Add source and handler-received timestamps to the private output.
            source_time_text = (
                source_message_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                if source_message_time is not None
                else "Unavailable"
            )
            output += (
                "\\n\\n🕒 Source message time: " + source_time_text
                + "\\n🕒 Handler received time: "
                + handler_received_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )

            # Send, then record and display the actual publish time.
            sent_message = await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                output
            )
            published_time = datetime.now(TIMEZONE)
            await client.edit_message(
                TEST_OUTPUT_CHANNEL_ID,
                sent_message.id,
                sent_message.message
                + "\\n🕒 Published time: "
                + published_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )

            print(
                "📤 Parsed signal sent to "
                "Guns' Goldbot"
            )

        # ----------------------------------------------------
        # REJECTED SIGNAL
        # ----------------------------------------------------

        else:

            print(
                "❌ SIGNAL REJECTED"
            )

            errors = result.get(
                "validation_errors",
                []
            )

            for error in errors:

                print(
                    f"   • {error}"
                )

            rejection_message = (
                format_rejected_signal(
                    signal=result,
                    raw_text=raw_text
                )
            )

            source_time_text = (
                source_message_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                if source_message_time is not None
                else "Unavailable"
            )
            rejection_message += (
                "\\n\\n🕒 Source message time: " + source_time_text
                + "\\n🕒 Handler received time: "
                + handler_received_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )

            sent_message = await client.send_message(
                TEST_OUTPUT_CHANNEL_ID,
                rejection_message
            )
            published_time = datetime.now(TIMEZONE)
            await client.edit_message(
                TEST_OUTPUT_CHANNEL_ID,
                sent_message.id,
                sent_message.message
                + "\\n🕒 Published time: "
                + published_time.strftime("%Y-%m-%d %H:%M:%S %Z")
            )

            print(
                "📤 Rejection report sent to "
                "Guns' Goldbot"
            )

        print("=" * 70)

    except Exception as exc:

        # ----------------------------------------------------
        # NEVER LET ONE MESSAGE KILL LISTENER
        # ----------------------------------------------------

        print()
        print(
            "❌ ERROR PROCESSING TELEGRAM MESSAGE"
        )

        print(
            f"Reason: {exc}"
        )

        print(
            "Listener remains active."
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("=" * 70)
    print(
        "🚀 PHASE 4 — LIVE TELEGRAM GOLD SIGNAL PARSER"
    )
    print("=" * 70)

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
        "Purpose:"
    )

    print(
        "Telegram → Parse → Validate → "
        "Guns' Goldbot"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # CREATE CLIENT
    # --------------------------------------------------------

    client = create_telegram_client()

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    print()
    print(
        "Connecting to Telegram..."
    )

    try:

        # Do not use interactive login on Render.
        #
        # The StringSession must already be authorized.

        await client.connect()

    except Exception as exc:

        print()
        print(
            "❌ TELEGRAM CONNECTION FAILED"
        )

        print(
            f"Reason: {exc}"
        )

        raise

    # --------------------------------------------------------
    # AUTHORIZATION CHECK
    # --------------------------------------------------------

    if not await client.is_user_authorized():

        print()
        print(
            "❌ TELEGRAM SESSION IS NOT AUTHORIZED"
        )

        print(
            "The TELEGRAM_SESSION_STRING "
            "is invalid or expired."
        )

        await client.disconnect()

        return

    print()
    print(
        "✅ TELEGRAM SESSION AUTHORIZED"
    )

    # --------------------------------------------------------
    # ACCOUNT INFORMATION
    # --------------------------------------------------------

    try:

        me = await client.get_me()

        if me:

            first_name = (
                getattr(
                    me,
                    "first_name",
                    ""
                )
                or ""
            )

            last_name = (
                getattr(
                    me,
                    "last_name",
                    ""
                )
                or ""
            )

            phone = (
                getattr(
                    me,
                    "phone",
                    None
                )
            )

            full_name = (
                f"{first_name} "
                f"{last_name}"
            ).strip()

            print()
            print(
                "👤 Telegram account:"
            )

            print(
                f"   Name: "
                f"{full_name or 'Unknown'}"
            )

            if phone:

                print(
                    f"   Phone: "
                    f"{phone}"
                )

    except Exception as exc:

        print(
            f"⚠️ Could not read account info: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # SHOW CONFIGURED CHANNELS
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "📡 CONFIGURED SOURCE CHANNELS"
    )

    print("=" * 70)

    for channel_id in SOURCE_CHANNELS:

        name = CHANNEL_DISPLAY_NAMES.get(
            channel_id,
            str(channel_id)
        )

        mapping = TP_MAPPING.get(
            channel_id
        )

        if mapping:

            print(
                f"  • {name}"
            )

            print(
                f"    ID: {channel_id}"
            )

            print(
                f"    Execution: "
                f"TP{mapping[0]} + "
                f"TP{mapping[1]}"
            )

        else:

            print(
                f"  • {name}"
            )

            print(
                f"    ID: {channel_id}"
            )

            print(
                "    Execution: NO MAPPING"
            )

    print("=" * 70)

    # --------------------------------------------------------
    # TP MAPPINGS
    # --------------------------------------------------------

    print_tp_mappings()

    # --------------------------------------------------------
    # RESOLVE SOURCES
    # --------------------------------------------------------

    resolved_channels = (
        await resolve_source_channels(
            client
        )
    )

    # --------------------------------------------------------
    # REQUIRE ALL 6 SOURCES
    # --------------------------------------------------------

    if len(
        resolved_channels
    ) != len(
        SOURCE_CHANNELS
    ):

        print()
        print(
            "❌ NOT ALL SOURCE CHANNELS "
            "ARE ACCESSIBLE."
        )

        print(
            f"Accessible: "
            f"{len(resolved_channels)}/"
            f"{len(SOURCE_CHANNELS)}"
        )

        print()
        print(
            "Parser will NOT start."
        )

        print(
            "Fix Telegram access before "
            "continuing."
        )

        await client.disconnect()

        return

    # --------------------------------------------------------
    # VERIFY OUTPUT CHANNEL
    # --------------------------------------------------------

    await verify_output_channel(
        client
    )

    # --------------------------------------------------------
    # FINAL CONFIGURATION SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "✅ TELEGRAM CONFIGURATION VERIFIED"
    )

    print(
        f"✅ Source channels: "
        f"{len(resolved_channels)}/"
        f"{len(SOURCE_CHANNELS)}"
    )

    print(
        "✅ Output channel accessible"
    )

    print(
        "✅ TP mappings loaded"
    )

    print(
        "✅ Signal parser loaded"
    )

    print(
        "✅ Signal validation loaded"
    )

    print(
        "✅ Rejection reporting loaded"
    )

    print(
        "✅ No trading functionality enabled"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # REGISTER MESSAGE HANDLER
    # --------------------------------------------------------

    @client.on(
        events.NewMessage(
            chats=resolved_channels
        )
    )
    async def new_message_handler(
        event
    ):

        await process_message(
            client,
            event
        )

    # --------------------------------------------------------
    # LIVE LISTENER
    # --------------------------------------------------------

    print()
    print("=" * 70)

    print(
        "🟢 LIVE PARSER LISTENER ACTIVE"
    )

    print("=" * 70)

    print()

    print(
        "Monitoring:"
    )

    for channel_id in SOURCE_CHANNELS:

        name = CHANNEL_DISPLAY_NAMES.get(
            channel_id,
            str(channel_id)
        )

        mapping = TP_MAPPING.get(
            channel_id
        )

        if mapping:

            print(
                f"  • {name}"
                f" → TP{mapping[0]}"
                f" + TP{mapping[1]}"
            )

        else:

            print(
                f"  • {name}"
                f" → NO MAPPING"
            )

    print()

    print(
        "📤 Output:"
    )

    print(
        "   Guns' Goldbot"
    )

    print(
        f"   ID: "
        f"{TEST_OUTPUT_CHANNEL_ID}"
    )

    print()

    print(
        "Waiting for Telegram signals..."
    )

    print("=" * 70)

    # --------------------------------------------------------
    # KEEP RUNNING
    # --------------------------------------------------------

    try:

        await client.run_until_disconnected()

    except KeyboardInterrupt:

        print()
        print(
            "🛑 Parser stopped manually."
        )

    except Exception as exc:

        print()
        print(
            "❌ Telegram listener stopped:"
        )

        print(
            f"{exc}"
        )

        raise

    finally:

        if client.is_connected():

            await client.disconnect()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "🛑 PHASE 4 PARSER STOPPED."
        )

    except Exception as exc:

        print()
        print(
            "❌ PHASE 4 PARSER FAILED."
        )

        print(
            f"Reason: {exc}"
        )

        raise
