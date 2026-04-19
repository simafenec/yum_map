#!/usr/bin/env python3
import discord
import os
import datetime
import re
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAP_SHARE_URL_REGEX = r"https://maps.app.goo.gl/[a-zA-Z0-9]+"
TOKEN = os.getenv('DISCORD_TOKEN')

intents=discord.Intents.none()
intents.reactions = True
intents.guilds = True
# discord.py Ver2.0 以降は必要
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print('ログインしました')

@client.event
async def on_raw_reaction_add(payload):
    txt_channel = client.get_channel(payload.channel_id)
    message = await txt_channel.fetch_message(payload.message_id)
    user = payload.member
    reaction = payload.emoji
    CHANNEL_ID = 1419162512200437841
    channel = client.get_channel(CHANNEL_ID)
    msg = f"{message.author.mention} {reaction}\nFrom:{user.display_name} \
          \nMessage:{message.content}\n{message.jump_url}"
    await channel.send(msg)
    
client.run(TOKEN)
