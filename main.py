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

intents = discord.Intents.none()
intents.reactions = True
intents.guilds = True
intents.message_content = True
intents.messages = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)
spreadsheet_client = GoogleSpreadsheetClient()
parser = URLParser(geocoding_api_key=GOOGLE_MAPS_API_KEY)

@client.event
async def on_ready():
    try:
        # ① まずグローバル同期（全サーバー対象、反映に最大1時間かかる）
        await tree.sync()

        # ② 即時反映させたいギルドには個別同期も実施
        for guild in client.guilds:
            try:
                tree.copy_global_to(guild=guild)
                synced = await tree.sync(guild=guild)
                print(f"ギルド '{guild.name}' に {len(synced)}個のコマンドを同期しました")
            except discord.Forbidden:
                print(f"ギルド '{guild.name}' への同期権限がありません")
            except Exception as e:
                print(f"ギルド '{guild.name}' の同期中にエラー: {e}")

    except Exception as e:
        print(f"コマンド同期に失敗しました: {e}")

    print("おいしいものbotが起動しました。現在時刻 : " + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))

@tree.command(name="update_history", description="チャンネルの履歴からお店情報を更新します")
async def slash_update_history(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await update_history(interaction.channel_id)
    await interaction.followup.send("✅ 更新が完了しました。", ephemeral=True)

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await add_shop_info_from_message(message)

async def add_shop_info_from_message(message: discord.Message):
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

async def update_history(channel_id: int):
    channel = client.get_channel(channel_id)
    if channel is None:
        print(f"チャンネルID {channel_id} が見つかりませんでした。")
        return
    async for message in channel.history(limit=100):
        if message.author.bot:
            continue
        if "https://maps.app.goo.gl/" not in message.content:
            continue
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