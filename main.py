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
    if message.content.startswith("https://maps.app.goo.gl/"):
        shop_infos = parser.parse_google_map_share_url(message.content)
        if shop_infos:
            for shop_info in shop_infos:
                result = spreadsheet_client.append_row(shop_info, message.created_at.strftime("%Y/%m/%d %H:%M:%S"))
                if result:
                    await message.channel.send(f"<@{message.author.id}> さんにより {shop_info.name}が追加されました！")
        else:
            await message.channel.send("Googleマップの共有URLから情報を取得できませんでした。")

client.run(TOKEN)