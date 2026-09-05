from telethon import TelegramClient
import asyncio

API_ID = 14424659
API_HASH = "5facb0b7b7a6f141da79d9cc460d4e12"

async def main():
    client = TelegramClient(
        "gold_signal_bot",
        API_ID,
        API_HASH
    )

    print("Connecting to Telegram...")

    await client.connect()

    print("Connected.")

    authorized = await client.is_user_authorized()

    print(f"Authorized: {authorized}")

    if not authorized:
        print("❌ SESSION IS NOT AUTHORIZED")
        await client.disconnect()
        return

    me = await client.get_me()

    print()
    print("==============================")
    print("✅ SESSION WORKS")
    print("==============================")
    print(f"Name: {me.first_name}")
    print(f"Telegram ID: {me.id}")

    if me.username:
        print(f"Username: @{me.username}")
    else:
        print("Username: None")

    await client.disconnect()
    print()
    print("Disconnected successfully.")

asyncio.run(main())