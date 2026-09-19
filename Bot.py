import os

import urllib.request

import json

import discord

from discord import app_commands

from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)

def get_token_data(mint):

    url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"

    req = urllib.request.Request(

        url,

        headers={"User-Agent": "Mozilla/5.0"}

    )

    with urllib.request.urlopen(req, timeout=10) as response:

        data = json.loads(response.read().decode())

    pairs = data.get("pairs", [])

    if not pairs:

        return None

    # Prefer Solana pair

    solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]

    pair = solana_pairs[0] if solana_pairs else pairs[0]

    return {

        "name": pair.get("baseToken", {}).get("name", "Unknown"),

        "symbol": pair.get("baseToken", {}).get("symbol", "???"),

        "price": pair.get("priceUsd"),

        "market_cap": pair.get("marketCap") or pair.get("fdv"),

        "liquidity": (pair.get("liquidity") or {}).get("usd"),

        "volume": (pair.get("volume") or {}).get("h24"),

        "change": (pair.get("priceChange") or {}).get("h24"),

        "url": pair.get("url", "")

    }

@bot.event

async def on_ready():

    try:

        synced = await bot.tree.sync()

        print(f"Logged in as {bot.user}")

        print(f"Synced {len(synced)} commands")

    except Exception as e:

        print("Command sync error:", e)

@bot.tree.command(

    name="token",

    description="Look up a Solana token"

)

@app_commands.describe(

    mint="Paste the token's Solana contract/mint address"

)

async def token(interaction: discord.Interaction, mint: str):

    await interaction.response.defer()

    try:

        data = get_token_data(mint)

        if not data:

            await interaction.followup.send(

                "❌ I couldn't find market data for that token."

            )

            return

        def money(value):

            if value is None:

                return "N/A"

            try:

                return f"${float(value):,.2f}"

            except:

                return "N/A"

        price = money(data["price"])

        mc = money(data["market_cap"])

        liquidity = money(data["liquidity"])

        volume = money(data["volume"])

        change = data["change"]

        change_text = "N/A"

        if change is not None:

            try:

                change_text = f"{float(change):+.2f}%"

            except:

                pass

        embed = discord.Embed(

            title=f"{data['name']} (${data['symbol']})",

            description="Solana token market data",

            url=data["url"] if data["url"] else None

        )

        embed.add_field(

            name="💵 Price",

            value=price,

            inline=True

        )

        embed.add_field(

            name="📈 Market Cap",

            value=mc,

            inline=True

        )

        embed.add_field(

            name="💧 Liquidity",

            value=liquidity,

            inline=True

        )

        embed.add_field(

            name="📊 24h Volume",

            value=volume,

            inline=True

        )

        embed.add_field(

            name="📉 24h Change",

            value=change_text,

            inline=True

        )

        embed.add_field(

            name="🔗 Mint",

            value=f"`{mint}`",

            inline=False

        )

        await interaction.followup.send(embed=embed)

    except Exception as e:

        print("Token lookup error:", e)

        await interaction.followup.send(

            "❌ Couldn't retrieve that token right now. "

            "Check the mint address and try again."

        )

@bot.tree.command(

    name="ping",

    description="Check whether the bot is online"

)

async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(

        "🟢 Pump tracker is online!"

    )

if not TOKEN:

    raise RuntimeError(

        "Missing DISCORD_TOKEN environment variable."

    )

bot.run(TOKEN)
