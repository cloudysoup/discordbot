# Import required libraries
from typing import Tuple
from PIL import Image  # For image processing
from google import genai
import requests  # For making HTTP requests
from io import BytesIO  # For handling image data in memory
import json  # For parsing JSON data
import concurrent.futures  # For parallel processing
from operator import itemgetter  # For sorting operations
from collections import Counter  # For counting occurrences
import os
from dotenv import load_dotenv
import constants
from models import PlayerIDResponse, PlayerInfoResponse

load_dotenv()


# Constants for player analysis and API configuration
API_URL = 'https://mrapi.org'
ONE_TRICK_THRESHOLD = 1.5  # Multiplier to identify players who mainly use one hero
# Minimum winrate % to consider a hero commonly played well
COMMON_WINRATE_THRESHOLD = 55
COMMON_MATCH_THRESHOLD = 20  # Minimum matches needed to consider hero experience
GOOD_PLAYER_WINRATE_THRESHOLD = 60  # Minimum winrate % to identify strong players
# Minimum matches needed to identify strong players
GOOD_PLAYER_MATCH_THRESHOLD = 30
# Minimum matches needed to be considered a one-trick
ONE_TRICK_MINIMUM_MATCHES = 50
PRIMARY_HERO_THRESHOLD = 0.4    # 40% of total matches on main hero
PLAY_RATE_DECAY_THRESHOLD = 2.0  # Main hero played 2x more than second hero
# HHI threshold for hero pool concentration
HERO_POOL_CONCENTRATION_THRESHOLD = 0.25


def get_usernames_from_image(image_url: str) -> list[str]:
    """
    Extracts usernames from a game screenshot using Google's Gemini Vision API
    and filters out specific unwanted phrases
    Args:
        image_url (str): URL of the image to analyze
    Returns:
        list: List of filtered usernames
    """
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content))

    # Configure Gemini API with authentication
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[image, "Parse the usernames from this video game image."],
        config={
            'response_mime_type': 'application/json',
            'response_schema': list[str],
        }
    )
    usernames = json.loads(response.text)

    filtered_usernames = list(filter(
        lambda name: name not in constants.EXCLUDED_PHRASES, usernames))

    return filtered_usernames[-6:]


def get_player_id(player_name: str) -> str | None:
    """
    Retrieves player ID from the API using player name
    Args:
        player_name (str): Player's username
    Returns:
        str: Player ID if found, None otherwise
    """
    response = requests.get(f"{API_URL}/api/player-id/{player_name}")
    if response.status_code < 400:
        try:
            return PlayerIDResponse(**response.json()).id
        except ValueError:
            return None
    print("Error getting player id:", response)
    return None


def get_player_ids(player_names: list[str]) -> dict[str, str | None]:
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


def get_player_data(player_id: str) -> (PlayerInfoResponse | None):
    """
    Retrieves detailed player statistics from the API
    Args:
        player_id (str): Player's unique identifier
    Returns:
        dict: Player statistics and data
    """
    response = requests.get(f"{API_URL}/api/player/{player_id}")
    if response.status_code < 400:
        try:
            return PlayerInfoResponse(**response.json())
        except ValueError:
            return None
    print("Error getting player data:", response)
    return None


def get_players_data(player_ids: dict[str, str | None]) -> dict[str, PlayerInfoResponse | None]:
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


def get_top_heroes(player_data: PlayerInfoResponse, top_n=5) -> list[dict]:
    """
    Analyzes player data to find their most played heroes
    Args:
        player_data (dict): Player's complete statistics
        top_n (int): Number of top heroes to return
    Returns:
        list: Top N heroes with their match counts and winrates
    """
    hero_stats = player_data.hero_stats
    if not hero_stats:
        return []
    ranked_heroes = []

    # Calculate statistics for each hero
    for _, hero_info in hero_stats.items():
        ranked_data = hero_info.ranked
        if not ranked_data:
            continue
        matches = ranked_data.matches
        wins = ranked_data.wins
        winrate = (wins / matches * 100) if matches > 0 else 0
        if matches > 0:
            ranked_heroes.append({
                "hero_name": hero_info.hero_name,
                "matches": matches,
                "winrate": winrate
            })

    # Sort heroes by number of matches played
    ranked_heroes.sort(key=itemgetter("matches"), reverse=True)
    return ranked_heroes[:top_n]


def determine_bans(players_data: dict[str, PlayerInfoResponse | None]):
    """
    Analyzes all players' data to determine optimal hero bans
    Args:
        players_data (dict): Complete data for all players
    Returns:
        list: Recommended bans with detailed reasoning
    """
    # Initialize tracking dictionaries
    hero_usage = Counter()
    one_tricks = {}
    good_players = {}
    player_top_heroes = {}
    player_metrics = {}

    # Process each player's hero data
    for player_name, player_data in players_data.items():
        if not player_data:
            continue

        top_heroes = get_top_heroes(player_data)
        if not top_heroes:
            continue

        player_top_heroes[player_name] = top_heroes

        # Calculate advanced metrics
        metrics = calculate_hero_pool_metrics(top_heroes)
        player_metrics[player_name] = metrics

        # Identify one-tricks using new metrics
        if metrics["is_one_trick"]:
            primary_hero = top_heroes[0]
            one_tricks.setdefault(primary_hero["hero_name"], []).append({
                "player": player_name,
                "matches": primary_hero["matches"],
                "winrate": primary_hero["winrate"],
                "dominance": metrics["primary_hero_dominance"],
                "diversity": metrics["diversity_score"]
            })

        # Track hero usage and strong players
        for hero in top_heroes:
            hero_name = hero["hero_name"]
            matches = hero["matches"]
            winrate = hero["winrate"]

            if winrate >= COMMON_WINRATE_THRESHOLD and matches >= COMMON_MATCH_THRESHOLD:
                hero_usage[hero_name] += 1

            if winrate >= GOOD_PLAYER_WINRATE_THRESHOLD and matches >= GOOD_PLAYER_MATCH_THRESHOLD:
                good_players.setdefault(hero_name, []).append(
                    (player_name, matches, winrate)
                )

    # Compile ban candidates
    one_trick_set = set(one_tricks.keys())
    good_player_set = set(good_players.keys())
    common_hero_set = {hero for hero, count in hero_usage.items() if count > 1}

    ban_candidates = one_trick_set | good_player_set | common_hero_set

    return compile_ban_recommendations(ban_candidates, one_tricks, good_players, hero_usage, player_top_heroes)


def get_common_hero_players(hero, player_top_heroes):
    """
    Finds players who frequently use a given hero.
    """
    common_players = [
        f"{player}: {hero_data['matches']} matches, {hero_data['winrate']:.2f}% winrate"
        for player, top_heroes in player_top_heroes.items()
        for hero_data in top_heroes
        if hero_data["hero_name"] == hero
    ]
    return common_players


def compile_ban_recommendations(ban_candidates, one_tricks, good_players, hero_usage, player_top_heroes) -> list[str]:
    """
    Creates a detailed list of ban recommendations with improved one-trick detection
    """
    one_trick_bans, good_player_bans, common_hero_bans = [], [], []

    for hero in ban_candidates:
        hero_display = constants.HERO_EMOJI_MAP.get(hero, hero)

        if hero in one_tricks:
            for player_data in one_tricks[hero]:
                one_trick_bans.append(
                    f"{hero_display} (One-trick: {player_data['player']}, "
                    f"{player_data['matches']} matches, {player_data['winrate']:.2f}%, "
                    f"Hero dominance: {player_data['dominance']*100:.1f}%)"
                )

        elif hero in good_players:
            for player, matches, winrate in good_players[hero]:
                good_player_bans.append(
                    f"{hero_display} (Good-player: {player}, {matches} matches, {winrate:.2f}%)"
                )

        elif hero_usage[hero] > 1:
            common_players = get_common_hero_players(hero, player_top_heroes)
            if common_players:
                common_hero_bans.append(
                    f"{hero_display} (Common hero: {', '.join(common_players)})"
                )

    # Sort bans by priority (one-tricks first, then good players, then common heroes)
    sorted_bans = one_trick_bans + good_player_bans + common_hero_bans
    return sorted_bans


def fetch_data(player_names: list[str]):
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


def get_player_rank(level: int) -> Tuple[str, int]:
    """
    Maps a player's level to their rank and sub-tier (1-3).

    Args:
        level (int): Player's rank level (0-23).

    Returns:
        Tuple[str, int]: Rank name and sub-tier (3 = highest, 1 = lowest).
    """
    rank_tiers = {
        "Bronze": range(0, 4),
        "Silver": range(4, 7),
        "Gold": range(7, 10),
        "Platinum": range(10, 13),
        "Diamond": range(13, 16),
        "Grandmaster": range(16, 19),
        "Celestial": range(19, 22),
        "Eternity": [22],
        "One Above All": [23]
    }

    # Find the rank and calculate the sub-tier (3, 2, 1)
    for rank, levels in rank_tiers.items():
        if level in levels:
            if rank in ["Eternity", "One Above All"]:
                return (rank, None)  # No sub-tier for these ranks
            sub_tier = 3 - (level - min(levels))
            return (rank, sub_tier)

    return ("Unknown", None)  # Fallback for invalid levels


# def main():
#     """
#     Entry point of the script
#     Handles image processing and initiates data analysis
#     """
#     # Discord image URL containing player names
#     # image_url = 'https://media.discordapp.net/attachments/1266915114322231330/1337309415367376896/image.png?ex=67a7a2b2&is=67a65132&hm=d77e7c2af072265616ff9c2e66282c40c0542717a6f13ab140e8ad23b97a0650&format=webp&quality=lossless'
#     image_url = 'https://media.discordapp.net/attachments/1337523234945372193/1337607708043644979/image.png?ex=67a80fc1&is=67a6be41&hm=d5fcd33f0f0a69064ac1c7111d739a4835172ed2645079a354286e0c3bf03124&=&format=webp&quality=lossless'
#     # Extract usernames from the image
#     player_names = get_usernames_from_image(image_url)
#     print("Detected players:", player_names)


#     fetch_data(player_names)
def calculate_hero_pool_metrics(top_heroes: list[dict]) -> dict:
    """
    Calculates advanced metrics for hero pool analysis
    Returns dictionary with diversity score and one-trick indicators
    """
    if not top_heroes:
        return {
            "diversity_score": 0,
            "primary_hero_dominance": 0,
            "is_one_trick": False,
            "total_matches": 0
        }

    total_matches = sum(hero["matches"] for hero in top_heroes)
    if total_matches == 0:
        return {
            "diversity_score": 0,
            "primary_hero_dominance": 0,
            "is_one_trick": False,
            "total_matches": 0
        }

    # Calculate play rate distribution
    play_rates = [hero["matches"] / total_matches for hero in top_heroes]

    # Calculate Herfindahl-Hirschman Index (HHI) for hero pool concentration
    hhi = sum(rate * rate for rate in play_rates)

    # Calculate primary hero dominance
    primary_hero_dominance = play_rates[0] if play_rates else 0

    # Calculate play rate decay between primary and secondary heroes
    play_rate_decay = play_rates[0] / \
        play_rates[1] if len(play_rates) > 1 else float('inf')

    # Determine if player is a one-trick using multiple criteria
    is_one_trick = (
        total_matches >= ONE_TRICK_MINIMUM_MATCHES and  # Enough total matches
        primary_hero_dominance > PRIMARY_HERO_THRESHOLD and  # Plays main hero enough
        play_rate_decay > PLAY_RATE_DECAY_THRESHOLD and     # Sharp dropoff after main hero
        hhi > HERO_POOL_CONCENTRATION_THRESHOLD             # Concentrated hero pool
    )

    return {
        "diversity_score": 1 - hhi,  # Convert HHI to diversity score
        "primary_hero_dominance": primary_hero_dominance,
        "play_rate_decay": play_rate_decay,
        "is_one_trick": is_one_trick,
        "total_matches": total_matches
    }

# # Script entry point
# if __name__ == "__main__":
#     main()
