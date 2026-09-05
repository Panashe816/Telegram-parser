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

    if not await client.is_user_authorized():
        print("❌ SESSION NOT AUTHORIZED")
        await client.disconnect()
        return

    print("✅ SESSION AUTHORIZED")
    print()
    print("Searching for your Guns test channels...")
    print()

    dialogs = await client.get_dialogs()

    found = 0

    for dialog in dialogs:

        title = dialog.name or ""
        title_lower = title.lower()

        if "guns" in title_lower or "goldbot" in title_lower:

            entity = dialog.entity

            print("=" * 60)
            print(f"NAME: {title}")
            print(f"ID: {entity.id}")

            username = getattr(entity, "username", None)

            if username:
                print(f"USERNAME: @{username}")
            else:
                print("USERNAME: None")

            print(f"TYPE: {type(entity).__name__}")

            found += 1

    print()
    print("=" * 60)
    print(f"FOUND: {found} matching channels")
    print("=" * 60)

    await client.disconnect()

asyncio.run(main())