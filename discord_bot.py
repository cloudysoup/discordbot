import discord
from discord.ext import commands
import main  # Your analysis script
import os
from dotenv import load_dotenv
import constants
import logging
import requests
import functools

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
TOKEN = os.getenv('DISCORD_TOKEN')
APPLICATION_ID = 1339034909528035358

# List of premium users (Replace with actual IDs)
PREMIUM_USERS = {471432445628252160, 987654321098765432}  # Replace with actual user IDs


def entitlement_check():
    """Decorator to check if a user has access based on entitlements."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(ctx, *args, **kwargs):
            if ctx.author.id in PREMIUM_USERS:
                return await func(ctx, *args, **kwargs)

            res = requests.get(
                f"https://discord.com/api/v10/applications/{APPLICATION_ID}/entitlements",
                headers={'Authorization': f'Bot {TOKEN}'}
            )

            if res.status_code >= 400:
                return await ctx.send("Error fetching entitlements.")

            has_access = any(int(entitlement['user_id']) == int(
                ctx.author.id) for entitlement in res.json())

            if not has_access:
                return await ctx.send("NO ACCESS")

            return await func(ctx, *args, **kwargs)

        return wrapper
    return decorator


# Test image URL
# TEST_IMAGE_URL = 'https://cdn.discordapp.com/attachments/1339054469131927573/1339063273852502107/image.png'


async def process_image_url(image_url: str, channel: discord.TextChannel):
    """Process an image URL and send results."""
    processing_msg = await channel.send("Processing image... This may take a moment.")

    try:
        # Get usernames from image
        player_names = main.get_usernames_from_image(image_url)
        await processing_msg.edit(content=f"Detected players: {', '.join(player_names)}\nFetching player data...")

        # Get player IDs and detailed data
        player_ids = main.get_player_ids(player_names)
        players_data = main.get_players_data(player_ids)

        # Create the embed
        embed = discord.Embed(
            title="Player Analysis",
            description="Analysis of detected players and their hero pools",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # Add player info to embed
        for player_name, player_data in players_data.items():
            if not player_data:
                embed.add_field(
                    name=f"❌ {player_name}", value="Could not retrieve data.", inline=False)
                continue

            top_heroes = main.get_top_heroes(player_data)
            hero_info = [
                f"{constants.HERO_EMOJI_MAP.get(hero['hero_name'], hero['hero_name'])} {hero['matches']} matches, {hero['winrate']:.1f}% WR"
                for hero in top_heroes
            ]

            rank, tier = main.get_player_rank(player_data.stats.rank.level)

            embed.add_field(
                name=f"{player_name} {constants.RANK_EMOJIS.get(rank)} {tier if tier else ''}",
                value="\n".join(
                    hero_info) if hero_info else "No hero data available",
                inline=False
            )

        # Add ban recommendations
        bans = main.determine_bans(players_data)
        if bans:
            embed.add_field(
                name="🚫 Recommended Bans",
                value="\n".join(
                    bans[:10]) if bans else "No ban recommendations",
                inline=False
            )

        # Delete processing message and send embed
        await processing_msg.delete()
        await channel.send(embed=embed)

    except Exception as e:
        logging.error(f"Error processing image: {e}")
        await processing_msg.edit(content="An error occurred while processing the image.")


@bot.event
async def on_ready():
    logging.info(f'Bot is online as {bot.user}')
    print(f'Bot is ready and logged in as {bot.user}')


@bot.command(name='commands')
async def help_command(ctx):
    """Display available bot commands."""
    embed = discord.Embed(
        title="Available Commands",
        description="Here's what I can do!",
        color=discord.Color.green()
    )
    embed.add_field(
        name="!test", value="Runs an image analysis on a test image.", inline=False)
    embed.add_field(name="!stats <player_name>",
                    value="Get stats for a specific player.", inline=False)
    embed.add_field(name="Upload an image",
                    value="Sends player analysis from an uploaded image.", inline=False)
    embed.add_field(name="!shutdown (admin only)",
                    value="Shuts down the bot.", inline=False)
    embed.add_field(name="!restart (admin only)",
                    value="Restarts the bot.", inline=False)
    embed.set_footer(text="Rate limits apply to prevent spam.")
    await ctx.send(embed=embed)


@bot.command()
@entitlement_check()
@commands.cooldown(3, 30, commands.BucketType.user)
async def bans(ctx):
    message = ctx.message

    if not message.attachments:
        return await ctx.send("Image required")

    attachment = message.attachments[0]
    is_image = any(attachment.filename.lower().endswith(ext)
                   for ext in ['.png', '.jpg', '.jpeg', '.webp'])
    if not is_image:
        return await ctx.send("Attachment must be image")

    await process_image_url(attachment.url, message.channel)


@bans.error
async def handle_bans_errors(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳Slow down! Try again in {error.retry_after:.2f} seconds.")


# Run the bot with your token
bot.run(TOKEN)
