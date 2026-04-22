import discord
import os
import datetime
from spreadsheet import GoogleSpreadsheetClient
from url_parser import URLParser
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

intents=discord.Intents.none()
intents.reactions = True
intents.guilds = True
intents.message_content = True
intents.messages = True
client = discord.Client(intents=intents)
spreadsheet_client = GoogleSpreadsheetClient()
parser = URLParser()

@client.event
async def on_ready():
    print("おいしいものbotが起動しました。現在時刻 : " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

@client.event
async def on_message(message : discord.Message):
    if message.author.bot:
        return
    if message.content == "!update_history":
        await message.channel.send("履歴からマップデータを更新します...")
        await update_history(message.channel.id)
        await message.channel.send("履歴の更新が完了しました！")
    await add_shop_info_from_message(message)

async def add_shop_info_from_message(message : discord.Message):
    if "https://maps.app.goo.gl/" in message.content:
        shop_infos = parser.parse_google_map_share_url(message.content)
        if shop_infos:
            for shop_info in shop_infos:
                result = spreadsheet_client.append_row(shop_info, message.created_at.strftime("%Y/%m/%d %H:%M:%S"))
                if result:
                    print(f"{shop_info.name} を追加しました！")
        else:
            print("Googleマップの共有URLから情報を取得できませんでした。")

async def update_history(channel_id : int):
    channel = client.get_channel(channel_id)
    if channel is None:
        print(f"チャンネルID {channel_id} が見つかりませんでした。")
        return

    async for message in channel.history(limit=100):
        await add_shop_info_from_message(message)

client.run(TOKEN)