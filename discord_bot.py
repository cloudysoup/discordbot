import discord
from discord.ext import commands
import main  # Your analysis script
import os
from dotenv import load_dotenv
import constants
import time
import logging
from collections import deque
from datetime import datetime, timedelta

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
TOKEN = os.getenv('DISCORD_TOKEN')

# Rate limiting settings
ATTEMPTS_PER_LIMIT = 3  # Allow 3 attempts before rate limit triggers
RATE_LIMIT_SECONDS = 30  # Time window for rate limiting
user_cooldowns = {}  # Track user request timestamps

def is_rate_limited(user_id):
    """Check if a user is rate-limited and return the remaining cooldown time if applicable."""
    now = time.time()
    if user_id not in user_cooldowns:
        user_cooldowns[user_id] = deque()

    queue = user_cooldowns[user_id]

    # Remove expired attempts
    while queue and now - queue[0] > RATE_LIMIT_SECONDS:
        queue.popleft()

    if len(queue) < ATTEMPTS_PER_LIMIT:
        queue.append(now)
        return False, 0  # Not rate-limited

    # Calculate remaining cooldown time
    remaining_time = RATE_LIMIT_SECONDS - (now - queue[0])
    return True, remaining_time

# Test image URL
TEST_IMAGE_URL = 'https://cdn.discordapp.com/attachments/1339054469131927573/1339063273852502107/image.png'

# Store user command usage for daily limit
user_usage = {}
DAILY_LIMIT = 2  # Limit for non-premium users
RESET_TIME = timedelta(days=1)  # Reset every 24 hours

# List of premium users (Replace with actual IDs)
PREMIUM_USERS = {471432445628252160, 987654321098765432}  # Replace with actual user IDs

def can_use_command(user_id):
    """Check if a user can use the command based on their membership and daily limit."""
    now = datetime.utcnow()

    # Premium users have unlimited uses
    if user_id in PREMIUM_USERS:
        return True, 0

    # Initialize user usage if not present
    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "last_used": now}
    
    last_used = user_usage[user_id]["last_used"]
    
    # Reset count if it's a new day
    if now - last_used >= RESET_TIME:
        user_usage[user_id]["count"] = 0
        user_usage[user_id]["last_used"] = now

    # Check if user is within the limit
    if user_usage[user_id]["count"] < DAILY_LIMIT:
        user_usage[user_id]["count"] += 1
        user_usage[user_id]["last_used"] = now
        return True, DAILY_LIMIT - user_usage[user_id]["count"]  # Uses left
    
    return False, 0  # Exceeded limit

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
                embed.add_field(name=f"❌ {player_name}", value="Could not retrieve data.", inline=False)
                continue

            top_heroes = main.get_top_heroes(player_data)
            hero_info = [
                f"{constants.HERO_EMOJI_MAP.get(hero['hero_name'], hero['hero_name'])} {hero['matches']} matches, {hero['winrate']:.1f}% WR"
                for hero in top_heroes
            ]

            rank, tier = main.get_player_rank(player_data.stats.rank.level)

            embed.add_field(
                name=f"{player_name} {constants.RANK_EMOJIS.get(rank)} {tier if tier else ''}",
                value="\n".join(hero_info) if hero_info else "No hero data available",
                inline=False
            )

        # Add ban recommendations
        bans = main.determine_bans(players_data)
        if bans:
            embed.add_field(
                name="🚫 Recommended Bans",
                value="\n".join(bans[:10]) if bans else "No ban recommendations",
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
    embed.add_field(name="!test", value="Runs an image analysis on a test image.", inline=False)
    embed.add_field(name="!stats <player_name>", value="Get stats for a specific player.", inline=False)
    embed.add_field(name="Upload an image", value="Sends player analysis from an uploaded image.", inline=False)
    embed.add_field(name="!shutdown (admin only)", value="Shuts down the bot.", inline=False)
    embed.add_field(name="!restart (admin only)", value="Restarts the bot.", inline=False)
    embed.set_footer(text="Rate limits apply to prevent spam.")
    await ctx.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = message.author.id

    # Rate limiting check
    rate_limited, retry_after = is_rate_limited(user_id)
    if rate_limited:
        await message.channel.send(f"⏳ Slow down! You can use this command again in {retry_after:.2f} seconds.")
        return

    # Daily usage limit check for non-premium users
    allowed, uses_left = can_use_command(user_id)
    if not allowed:
        await message.channel.send(f"🚫 {message.author.mention}, you've reached your daily limit of {DAILY_LIMIT} uses! Upgrade to premium for unlimited access.")
        return
    elif user_id not in PREMIUM_USERS:
        await message.channel.send(f"⚠️ {message.author.mention}, you have {uses_left} uses left today.")

    # Process images if uploaded
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                await process_image_url(attachment.url, message.channel)

    await bot.process_commands(message)

# Run the bot with your token
bot.run(TOKEN)
