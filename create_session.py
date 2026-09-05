from telethon import TelegramClient

API_ID = 14424659
API_HASH = "5facb0b7b7a6f141da79d9cc460d4e12"

SESSION_NAME = "gold_signal_bot"

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH
)


async def main():
    print("Connecting to Telegram...")

    await client.start()

    print()
    print("================================")
    print("TELEGRAM LOGIN SUCCESSFUL")
    print("================================")

    me = await client.get_me()

    print(f"Name: {me.first_name}")

    if me.username:
        print(f"Username: @{me.username}")
    else:
        print("Username: None")

    print(f"Telegram ID: {me.id}")

    print()
    print("Session file created:")
    print("gold_signal_bot.session")

    await client.disconnect()


with client:
    client.loop.run_until_complete(main())