from __future__ import annotations
from pydantic import BaseModel, Field
from .player import Player, Position


class RosterSlot(BaseModel):
    slot_type: str  # "QB", "RB", "WR", "TE", "FLEX", "BN", "IR", "TAXI"
    player: Player | None = None


class Team(BaseModel):
    team_id: str
    name: str
    owner: str = ""
    is_mine: bool = False
    record_wins: int = 0
    record_losses: int = 0
    record_ties: int = 0
    waiver_priority: int | None = None
    roster: list[Player] = Field(default_factory=list)

    def players_by_position(self, position: Position) -> list[Player]:
        return [p for p in self.roster if p.position == position]


class TradeOffer(BaseModel):
    """Represents a trade under evaluation."""
    i_give: list[Player] = Field(default_factory=list)
    i_receive: list[Player] = Field(default_factory=list)
    context_notes: str = ""  # Any extra context, e.g. "they need a QB"


class WaiverTarget(BaseModel):
    player: Player
    waiver_priority_needed: int | None = None
    faab_bid: int | None = None  # Free Agent Acquisition Budget
    reason: str = ""


class LeagueInfo(BaseModel):
    league_id: str
    name: str
    platform: str  # "espn" or "yahoo"
    season: int
    format: str = "dynasty"  # "dynasty" or "redraft"
    scoring_type: str = "PPR"  # "PPR", "Half-PPR", "Standard"
    num_teams: int = 12
    roster_spots: dict[str, int] = Field(default_factory=dict)
    teams: list[Team] = Field(default_factory=list)
    my_team: Team | None = None
    current_week: int = 1
    faab_budget: int | None = None

    def get_free_agents(self) -> list[Player]:
        """Players not on any roster."""
        rostered_ids = {
            p.player_id
            for team in self.teams
            for p in team.roster
        }
        # Free agents populated by league connector
        return []
