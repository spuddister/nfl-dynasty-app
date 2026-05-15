from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class Position(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"
    FLEX = "FLEX"


class DynastyTier(str, Enum):
    """Dynasty value tiers — long-term outlook."""
    ELITE = "Elite"          # Top 5 at position, cornerstone asset
    GREAT = "Great"          # Top 12, reliable starter with upside
    GOOD = "Good"            # Solid starter, positive dynasty value
    FRINGE = "Fringe"        # Borderline starter / strong handcuff
    DEPTH = "Depth"          # Bench/taxi squad value only
    DROP = "Drop"            # No dynasty value, should be traded/dropped


class RedraftTier(str, Enum):
    """Current-season value tiers."""
    MUST_START = "Must Start"
    START = "Start"
    FLEX = "Flex"
    BENCH = "Bench"
    WAIVER = "Waiver"
    DROP = "Drop"


class InjuryStatus(str, Enum):
    HEALTHY = "Healthy"
    QUESTIONABLE = "Questionable"
    DOUBTFUL = "Doubtful"
    OUT = "Out"
    IR = "IR"
    PUP = "PUP"
    UNKNOWN = "Unknown"


class PlayerStats(BaseModel):
    season: int
    games_played: int = 0
    # Passing
    pass_yards: float = 0
    pass_tds: int = 0
    interceptions: int = 0
    # Rushing
    rush_yards: float = 0
    rush_tds: int = 0
    carries: int = 0
    # Receiving
    targets: int = 0
    receptions: int = 0
    rec_yards: float = 0
    rec_tds: int = 0
    # Fantasy
    fantasy_points_total: float = 0
    fantasy_points_avg: float = 0
    finish_rank: int | None = None  # Overall positional rank finish


class Player(BaseModel):
    player_id: str
    name: str
    position: Position
    nfl_team: str = "FA"
    age: int | None = None
    years_pro: int | None = None

    # Status
    injury_status: InjuryStatus = InjuryStatus.UNKNOWN
    injury_note: str = ""

    # Fantasy context
    is_on_my_roster: bool = False
    acquisition_cost: str = ""  # e.g. "Round 3 pick", "Traded for X"

    # Analysis outputs
    dynasty_tier: DynastyTier | None = None
    redraft_tier: RedraftTier | None = None
    dynasty_trade_value: int | None = None  # 0-100 scale
    analysis_summary: str = ""
    analysis_notes: list[str] = Field(default_factory=list)
    reddit_sentiment: str = ""  # raw summary from Reddit
    last_analyzed: datetime | None = None

    # Historical stats
    stats: list[PlayerStats] = Field(default_factory=list)

    @property
    def dynasty_age_factor(self) -> str:
        """Quick human-readable age context for dynasty."""
        if self.age is None:
            return "Unknown age"
        if self.position in (Position.QB,):
            if self.age <= 25:
                return "Young QB — high dynasty upside"
            elif self.age <= 29:
                return "Prime QB window"
            elif self.age <= 33:
                return "Aging QB — monitor"
            else:
                return "Old QB — avoid in dynasty"
        else:  # skill positions age out faster
            if self.age <= 23:
                return "Young — dynasty cornerstone candidate"
            elif self.age <= 26:
                return "Prime — peak value"
            elif self.age <= 28:
                return "Late prime — value plateauing"
            elif self.age <= 30:
                return "Aging — redraft value only"
            else:
                return "Old — dynasty drop candidate"
