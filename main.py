import asyncio
import discord
import os
import datetime
from spreadsheet import GoogleSpreadsheetClient
from url_parser import URLParser
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

intents=discord.Intents.none()
intents.reactions = True
intents.guilds = True
intents.message_content = True
intents.messages = True
client = discord.Client(intents=intents)
spreadsheet_client = GoogleSpreadsheetClient()
parser = URLParser(geocoding_api_key=GOOGLE_MAPS_API_KEY)

@client.event
async def on_ready():
    print("おいしいものbotが起動しました。現在時刻 : " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

@client.event
async def on_message(message : discord.Message):
    if message.author.bot:
        return
    if message.content == "!update_history":
        try:
            await message.delete()
        except discord.errors.Forbidden:
            pass
        await update_history(message.channel.id)
    await add_shop_info_from_message(message)

async def add_shop_info_from_message(message : discord.Message):
    if "https://maps.app.goo.gl/" in message.content:
        shop_infos = await asyncio.to_thread(
            parser.parse_google_map_share_url,
            message.content,
            spreadsheet_client.is_cached
        )
        if shop_infos:
            for shop_info in shop_infos:
                result = await asyncio.to_thread(
                    spreadsheet_client.append_row,
                    shop_info,
                    message.created_at.strftime("%Y/%m/%d %H:%M:%S")
                )
                if result:
                    print(f"{shop_info.name} を追加しました！")
        else:
            print("Googleマップの共有URLから情報を取得できませんでした。 URL: " + message.content)

async def update_history(channel_id : int):
    channel = client.get_channel(channel_id)
    if channel is None:
        print(f"チャンネルID {channel_id} が見つかりませんでした。")
        return

    async for message in channel.history(limit=100):
        if message.author.bot:
            continue
        if "https://maps.app.goo.gl/" not in message.content:
            continue
        # キャッシュチェックなしでパースし、新規追加 or URL更新を行う
        shop_infos = await asyncio.to_thread(
            parser.parse_google_map_share_url, message.content
        )
        for shop_info in shop_infos:
            result = await asyncio.to_thread(
                spreadsheet_client.append_row,
                shop_info,
                message.created_at.strftime("%Y/%m/%d %H:%M:%S")
            )
            if result:
                print(f"{shop_info.name} を追加しました！")
            elif shop_info.url or shop_info.genre:
                updated = await asyncio.to_thread(
                    spreadsheet_client.update_missing_fields, shop_info
                )
                if updated:
                    print(f"{shop_info.name} のフィールドを更新しました。")

client.run(TOKEN)