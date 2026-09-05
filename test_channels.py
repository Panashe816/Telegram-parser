from telethon import TelegramClient
import asyncio

API_ID = 14424659
API_HASH = "5facb0b7b7a6f141da79d9cc460d4e12"

CHANNELS = [
    "Day_TradingAcademy",
    "Gary_TheTrader",
    "fabioforex",
    "HugoTradingxGOLD",
    -1003170522699,
    "HANEEFTRADER00",
    "FxTradingProfessor12",
    "FxAnalysisTeam_541",
    "gold_1900_pro_trader",
    "fxpower2200",
    "XAUUSDMARKETEXPERTS",
    "forexstar13",
    "Fxpipso0",
]


async def main():

    client = TelegramClient(
        "gold_signal_bot",
        API_ID,
        API_HASH
    )

    print("Connecting to Telegram...")

    await client.connect()

    if not await client.is_user_authorized():
        print("❌ SESSION NOT AUTHORIZED")
        await client.disconnect()
        return

    print("✅ SESSION AUTHORIZED")
    print()

    for channel in CHANNELS:

        print(f"🔍 Testing: {channel}")

        try:
            entity = await client.get_entity(channel)

            title = getattr(entity, "title", None)
            username = getattr(entity, "username", None)

            print("   ✅ ACCESSIBLE")

            if title:
                print(f"   Name: {title}")

            print(f"   ID: {entity.id}")

            if username:
                print(f"   Username: @{username}")

        except Exception as e:

            print("   ❌ NOT ACCESSIBLE")
            print(f"   Error: {type(e).__name__}: {e}")

        print()

    await client.disconnect()

    print("Finished.")


asyncio.run(main())