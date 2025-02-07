import discord
from discord.ext import commands
import main  # Your analysis script
import os
TOKEN = os.getenv('DISCORD_TOKEN')
# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

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
                    
                    # Process and send results
                    messages = []
                    
                    # Add player info
                    for player_name, player_data in players_data.items():
                        if not player_data:
                            messages.append(f"Could not retrieve data for player {player_name}.")
                            continue

                        top_heroes = main.get_top_heroes(player_data)
                        messages.append(f"\nTop {len(top_heroes)} most played heroes for {player_name}:")
                        for hero in top_heroes:
                            messages.append(
                                f"• {hero['hero_name']}: {hero['matches']} ranked matches, Winrate: {hero['winrate']:.2f}%")

                    # Add ban recommendations
                    bans = main.determine_bans(players_data)
                    messages.append("\nRecommended bans:")
                    for ban in bans:
                        messages.append(f"• {ban}")

                    # Send results in chunks to avoid Discord's message length limit
                    message_text = "\n".join(messages)
                    chunks = [message_text[i:i+1900] for i in range(0, len(message_text), 1900)]
                    
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            await processing_msg.edit(content=f"```{chunk}```")
                        else:
                            await message.channel.send(f"```{chunk}```")

                except Exception as e:
                    await processing_msg.edit(content=f"An error occurred: {str(e)}")

# Run the bot with your token
bot.run('TOKEN')  # Replace with your actual bot token