# Import required libraries
from PIL import Image  # For image processing
import google.generativeai as genai  # Google's Generative AI API
import requests  # For making HTTP requests
from io import BytesIO  # For handling image data in memory
import json  # For parsing JSON data
import concurrent.futures  # For parallel processing
from operator import itemgetter  # For sorting operations
from collections import Counter  # For counting occurrences

# Configure Gemini API with authentication
genai.configure(api_key="AIzaSyD0SWihqcTCevwQxzvZXUggcG_tnPBBI6Q")

# Constants for player analysis and API configuration
API_URL = 'https://mrapi.org'
ONE_TRICK_THRESHOLD = 1.5  # Multiplier to identify players who mainly use one hero
COMMON_WINRATE_THRESHOLD = 55  # Minimum winrate % to consider a hero commonly played well
COMMON_MATCH_THRESHOLD = 20  # Minimum matches needed to consider hero experience
GOOD_PLAYER_WINRATE_THRESHOLD = 60  # Minimum winrate % to identify strong players
GOOD_PLAYER_MATCH_THRESHOLD = 30  # Minimum matches needed to identify strong players

def get_usernames_from_image(image_url):
    """
    Extracts usernames from a game screenshot using Google's Gemini Vision API
    Args:
        image_url (str): URL of the image to analyze
    Returns:
        list: List of extracted usernames
    """
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content))
    
    # Use Gemini model to analyze the image
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(
        ["Parse the usernames from this video game image. Return results as an array of strings", 
        image]
    )
    
    # Process the response text to extract the username array
    response_text = response.text
    array_start = response_text.find('[')
    array_end = response_text.find(']') + 1
    usernames_str = response_text[array_start:array_end]
    
    # Convert string array to Python list
    usernames = json.loads(usernames_str)
    return usernames

def get_player_id(player_name):
    """
    Retrieves player ID from the API using player name
    Args:
        player_name (str): Player's username
    Returns:
        str: Player ID if found, None otherwise
    """
    response = requests.get(f"{API_URL}/api/player-id/{player_name}")
    if response.status_code < 400:
        return response.json().get("id")
    return None

def get_player_ids(player_names):
    """
    Gets multiple player IDs concurrently using ThreadPoolExecutor
    Args:
        player_names (list): List of player usernames
    Returns:
        dict: Mapping of player names to their IDs
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(get_player_id, player_names)
    return dict(zip(player_names, results))

def get_player_data(player_id):
    """
    Retrieves detailed player statistics from the API
    Args:
        player_id (str): Player's unique identifier
    Returns:
        dict: Player statistics and data
    """
    response = requests.get(f"{API_URL}/api/player/{player_id}")
    if response.status_code < 400:
        return response.json()
    return None

def get_players_data(player_ids):
    """
    Gets multiple players' data concurrently
    Args:
        player_ids (dict): Dictionary of player names and their IDs
    Returns:
        dict: Mapping of player names to their complete data
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(get_player_data, player_ids.values())
    return dict(zip(player_ids.keys(), results))

def get_top_heroes(player_data, top_n=5):
    """
    Analyzes player data to find their most played heroes
    Args:
        player_data (dict): Player's complete statistics
        top_n (int): Number of top heroes to return
    Returns:
        list: Top N heroes with their match counts and winrates
    """
    hero_stats = player_data.get("hero_stats", {})
    ranked_heroes = []

    # Calculate statistics for each hero
    for hero_id, hero_info in hero_stats.items():
        ranked_data = hero_info.get("ranked", {})
        matches = ranked_data.get("matches", 0)
        wins = ranked_data.get("wins", 0)
        winrate = (wins / matches * 100) if matches > 0 else 0
        if matches > 0:
            ranked_heroes.append({
                "hero_name": hero_info.get("hero_name", "Unknown"),
                "matches": matches,
                "winrate": winrate
            })

    # Sort heroes by number of matches played
    ranked_heroes.sort(key=itemgetter("matches"), reverse=True)
    return ranked_heroes[:top_n]

def determine_bans(players_data):
    """
    Analyzes all players' data to determine optimal hero bans
    Args:
        players_data (dict): Complete data for all players
    Returns:
        list: Recommended bans with detailed reasoning
    """
    # Initialize counters and tracking dictionaries
    hero_usage = Counter()
    one_tricks = {}  # Players who mainly play one hero
    good_players = {}  # Players who perform well with specific heroes

    # Analyze each player's hero pool
    for player_name, player_data in players_data.items():
        top_heroes = get_top_heroes(player_data)
        
        # Identify one-trick players
        if len(top_heroes) > 0 and top_heroes[0]["matches"] > sum(hero["matches"] for hero in top_heroes[1:]) * ONE_TRICK_THRESHOLD:
            one_tricks[top_heroes[0]["hero_name"]] = (
                player_name, top_heroes[0]["matches"], top_heroes[0]["winrate"])

        # Track hero usage and identify strong players
        for hero in top_heroes:
            if hero["winrate"] >= COMMON_WINRATE_THRESHOLD and hero["matches"] >= COMMON_MATCH_THRESHOLD:
                hero_usage[hero["hero_name"]] += 1
            if hero["winrate"] >= GOOD_PLAYER_WINRATE_THRESHOLD and hero["matches"] >= GOOD_PLAYER_MATCH_THRESHOLD:
                if hero["hero_name"] in good_players:
                    good_players[hero["hero_name"]].append(
                        (player_name, top_heroes[0]["matches"], top_heroes[0]["winrate"]))
                else:
                    good_players[hero["hero_name"]] = (
                        (player_name, top_heroes[0]["matches"], top_heroes[0]["winrate"]))

    # Generate list of ban candidates
    sorted_heroes = hero_usage.most_common()
    ban_candidates = set(list(one_tricks.keys()) + list(good_players.keys()) +
                         [hero for hero, count in sorted_heroes if count > 1])
    bans = list(ban_candidates)

    # Create detailed ban recommendations
    ban_info = []
    for hero in bans:
        if hero in one_tricks:
            ban_info.append(
                f"{hero} (One-trick: {one_tricks[hero][0]}, {one_tricks[hero][1]} matches, {one_tricks[hero][2]:.2f}%)")
        else:
            if hero in good_players:
                ban_info.append(
                    f"{hero} (Good-player: {good_players[hero][0]}, {good_players[hero][1]} matches, {good_players[hero][2]:.2f}%)")
                common_players = []
            if hero_usage[hero] > 1:
                for player, data in players_data.items():
                    top_heroes = get_top_heroes(data)
                    for hero_data in top_heroes:
                        if hero_data["hero_name"] == hero:
                            common_players.append(
                                (player, hero_data["matches"], hero_data["winrate"]))
                            break
                ban_info.append(
                    f"{hero} (Common hero: {', '.join(f'{player}: {matches} matches, {winrate:.2f}% winrate' for player, matches, winrate in common_players)})"
                )

    return ban_info

def fetch_data(player_names):
    """
    Main function to fetch and analyze data for all players
    Args:
        player_names (list): List of player usernames to analyze
    """
    # Get player IDs for all players
    player_ids = get_player_ids(player_names)
    print("Player IDs:", player_ids)

    # Get detailed data for all players
    players_data = get_players_data(player_ids)

    # Analyze and display results for each player
    for player_name, player_data in players_data.items():
        if not player_data:
            print(f"Could not retrieve data for player {player_name}.")
            continue

        top_heroes = get_top_heroes(player_data)
        print(f"Top {len(top_heroes)} most played heroes for {player_name}:")
        for hero in top_heroes:
            print(
                f"{hero['hero_name']}: {hero['matches']} ranked matches, Winrate: {hero['winrate']:.2f}%")

    # Generate and display ban recommendations
    bans = determine_bans(players_data)
    print("Recommended bans:", bans)

def main():
    """
    Entry point of the script
    Handles image processing and initiates data analysis
    """
    # Discord image URL containing player names
    image_url = 'https://media.discordapp.net/attachments/1266915114322231330/1337309415367376896/image.png?ex=67a7a2b2&is=67a65132&hm=d77e7c2af072265616ff9c2e66282c40c0542717a6f13ab140e8ad23b97a0650&format=webp&quality=lossless'
    
    # Extract usernames from the image
    player_names = get_usernames_from_image(image_url)
    print("Detected players:", player_names)
    
    # Analyze the players' data
    fetch_data(player_names)

# Script entry point
if __name__ == "__main__":
    main()