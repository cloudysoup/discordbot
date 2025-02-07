import discord
from discord.ext import commands
import main  # Your analysis script
import os
from dotenv import load_dotenv

load_dotenv()

# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
TOKEN = os.getenv('DISCORD_TOKEN')

@bot.event
async def on_ready():
    print(f'Bot is ready and logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if message has an image attachment
    if message.attachments:
        for attachment in message.attachments:
            # Verify it's an image
            if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                # Send initial response
                processing_msg = await message.channel.send("Processing image... This may take a moment.")

                try:
                    # Get usernames from image
                    player_names = main.get_usernames_from_image(attachment.url)
                    await processing_msg.edit(content=f"Detected players: {', '.join(player_names)}\nFetching player data...")

                    # Get player IDs
                    player_ids = main.get_player_ids(player_names)

                    # Get detailed data
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
                                name=f"❌ {player_name}",
                                value="Could not retrieve data for this player.",
                                inline=False
                            )
                            continue

                        top_heroes = main.get_top_heroes(player_data)
                        hero_info = []
                        for hero in top_heroes:
                            hero_info.append(
                                f"• {hero['hero_name']}: {hero['matches']} matches, {hero['winrate']:.1f}% WR"
                            )
                        
                        # Add field for each player
                        embed.add_field(
                            name=f"👤 {player_name}'s Hero Pool",
                            value="\n".join(hero_info) if hero_info else "No hero data available",
                            inline=False
                        )

                    # Add ban recommendations
                    bans = main.determine_bans(players_data)
                    if bans:
                        ban_text = []
                        for ban in bans:
                            if len(ban_text) + len(ban) > 1000:  # Discord field value limit
                                break
                            ban_text.append(f"• {ban}")
                        
                        embed.add_field(
                            name="🚫 Recommended Bans",
                            value="\n".join(ban_text) if ban_text else "No ban recommendations",
                            inline=False
                        )

                    # Add footer with timestamp
                    embed.set_footer(text="Analysis completed at")

                    # Delete processing message and send embed
                    await processing_msg.delete()
                    await message.channel.send(embed=embed)

                    # If there are too many bans for the embed, send them separately
                    if bans and len("\n".join(bans)) > 1000:
                        chunks = [bans[i:i + 10] for i in range(0, len(bans), 10)]
                        for chunk in chunks[1:]:  # Skip first chunk as it's in the embed
                            ban_chunk_text = "\n".join(f"• {ban}" for ban in chunk)
                            await message.channel.send(f"```Additional Ban Recommendations:\n{ban_chunk_text}```")

                except Exception as e:
                    await processing_msg.edit(content=f"An error occurred: {str(e)}")

# Run the bot with your token
bot.run(TOKEN)
