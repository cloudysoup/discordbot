from typing import Dict, Optional
from pydantic import BaseModel


class PlayerIDResponse(BaseModel):
    name: str
    id: str


class RankDetails(BaseModel):
    level: int
    rank: str
    score: int
    win_count: int


class PlayerStats(BaseModel):
    level: int  # Convert from string to int
    rank: RankDetails


class RankedStats(BaseModel):
    matches: Optional[int] = 0
    wins: Optional[int] = 0
    mvp: int
    svp: int
    kills: int
    deaths: int
    assists: int
    kdr: float  # Convert from string for numerical operations
    kda: float  # Convert from string for numerical operations
    damage_given: int
    damage_received: int
    heal: int


class HeroStats(BaseModel):
    hero_name: Optional[str] = "Unknown"
    ranked: Optional[RankedStats] = None


class PlayerInfoResponse(BaseModel):
    player_name: str
    hero_stats: Optional[Dict[int, HeroStats]] = None
