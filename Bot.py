import os
import json
import asyncio
import urllib.request

import discord
from discord import app_commands
from discord.ext import commands
import websockets


TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
SOLANA_WSS_URL = os.getenv("SOLANA_WSS_URL")

# Pump.fun program
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

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

    solana_pairs = [
        p for p in pairs
        if p.get("chainId") == "solana"
    ]

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


def money(value):
    if value is None:
        return "N/A"

    try:
        return f"${float(value):,.2f}"
    except:
        return "N/A"


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()

        print(f"Logged in as {bot.user}")
        print(f"Synced {len(synced)} commands")

        if CHANNEL_ID and SOLANA_WSS_URL:
            asyncio.create_task(watch_pump_fun())
            print("Pump.fun watcher started.")
        else:
            print("Pump.fun watcher NOT started.")
            print("Missing DISCORD_CHANNEL_ID or SOLANA_WSS_URL.")

    except Exception as e:
        print("Startup error:", e)


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

        change = data["change"]

        if change is not None:
            try:
                change_text = f"{float(change):+.2f}%"
            except:
                change_text = "N/A"
        else:
            change_text = "N/A"

        embed = discord.Embed(
            title=f"{data['name']} (${data['symbol']})",
            description="Solana token market data",
            url=data["url"] if data["url"] else None,
            color=discord.Color.green()
        )

        embed.add_field(
            name="💵 Price",
            value=money(data["price"]),
            inline=True
        )

        embed.add_field(
            name="📈 Market Cap",
            value=money(data["market_cap"]),
            inline=True
        )

        embed.add_field(
            name="💧 Liquidity",
            value=money(data["liquidity"]),
            inline=True
        )

        embed.add_field(
            name="📊 24h Volume",
            value=money(data["volume"]),
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
            "❌ Couldn't retrieve that token right now."
        )


@bot.tree.command(
    name="ping",
    description="Check whether the bot is online"
)
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🟢 Pump tracker is online!"
    )


async def send_new_token_alert(mint):
    try:
        channel = bot.get_channel(int(CHANNEL_ID))

        if channel is None:
            print("Could not find Discord channel:", CHANNEL_ID)
            return

        data = get_token_data(mint)

        if data:
            name = data["name"]
            symbol = data["symbol"]
            url = data["url"]
        else:
            name = "New Pump.fun Token"
            symbol = "???"
            url = ""

        embed = discord.Embed(
            title=f"🚨 New Pump.fun Token",
            description=f"**{name} (${symbol})**",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="🔗 Mint Address",
            value=f"`{mint}`",
            inline=False
        )

        if url:
            embed.add_field(
                name="📊 DexScreener",
                value=f"[View Token]({url})",
                inline=False
            )

        await channel.send(
            content="@here",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=True
            )
        )

        print("Alert sent for:", mint)

    except Exception as e:
        print("Alert error:", e)


async def watch_pump_fun():
    """
    Watches Solana logs for transactions involving Pump.fun.
    When a new Pump.fun transaction is detected, we inspect it
    for a newly-created token mint.
    """

    while True:
        try:
            async with websockets.connect(
                SOLANA_WSS_URL,
                ping_interval=20,
                ping_timeout=20
            ) as ws:

                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {
                            "mentions": [PUMP_PROGRAM]
                        },
                        {
                            "commitment": "confirmed"
                        }
                    ]
                }

                await ws.send(json.dumps(request))

                print("Connected to Solana WebSocket.")

                while True:
                    message = await ws.recv()
                    data = json.loads(message)

                    if "params" not in data:
                        continue

                    result = data["params"].get("result", {})
                    value = result.get("value", {})

                    signature = value.get("signature")

                    if not signature:
                        continue

                    # Get the transaction and inspect it.
                    mint = await find_created_mint(signature)

                    if mint:
                        await send_new_token_alert(mint)

        except Exception as e:
            print("Watcher disconnected:", e)
            print("Reconnecting in 10 seconds...")
            await asyncio.sleep(10)


async def find_created_mint(signature):
    """
    Retrieves a Pump.fun transaction and attempts to find
    the newly-created token mint.
    """

    rpc_url = SOLANA_WSS_URL.replace("wss://", "https://")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0
            }
        ]
    }

    try:
        request = urllib.request.Request(
            rpc_url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            result = json.loads(
                response.read().decode()
            )

        transaction = result.get("result")

        if not transaction:
            return None

        instructions = (
            transaction
            .get("transaction", {})
            .get("message", {})
            .get("instructions", [])
        )

        for instruction in instructions:

            program = instruction.get("program")

            if program != "pump":
                continue

            parsed = instruction.get("parsed")

            if not parsed:
                continue

            info = parsed.get("info", {})

            mint = info.get("mint")

            if mint:
                return mint

    except Exception as e:
        print("Transaction lookup error:", e)

    return None


if not TOKEN:
    raise RuntimeError(
        "Missing DISCORD_TOKEN environment variable."
    )

bot.run(TOKEN)
