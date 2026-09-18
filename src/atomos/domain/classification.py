"""
Atomos Classification Rules (Novice vs Open)

Implements Novice and Open classification for debaters and teams.

All rules sourced directly from:
- docs/debating/DEBATING_RULEBOOK.md (Section 10)

No rule in this module should be invented by the coding agent.
"""

from enum import Enum
from typing import Sequence


class Category(str, Enum):
    NOVICE = "NOVICE"
    OPEN = "OPEN"


class TournamentFormat(str, Enum):
    PURE_OPEN = "PURE_OPEN"
    PURE_NOVICE = "PURE_NOVICE"
    NOVICE_AND_OPEN = "NOVICE_AND_OPEN"


# [CONFIRMED] 7 or more qualifying tournaments to become Open
OPEN_THRESHOLD_TOURNAMENTS = 7


def counts_toward_open_status(
    is_dc_endorsed: bool,
    tournament_format: TournamentFormat,
    team_category_in_tournament: Category,
    was_speaker_tab_eligible: bool,
) -> bool:
    """
    Determine if a tournament participation counts toward an individual's Open threshold.

    [CONFIRMED]
    - Must be a DC-endorsed tournament.
    - Debater must have been eligible for Speaker Tab in that tournament.
    - The debater's team in that tournament must have been classified as OPEN.
    - Pure Novice tournaments never count.
    - In Novice&Open tournaments, only participation in an Open team counts.
    """
    if not is_dc_endorsed:
        return False
    if not was_speaker_tab_eligible:
        return False
    if tournament_format == TournamentFormat.PURE_NOVICE:
        return False
    return team_category_in_tournament == Category.OPEN


def classify_debater(qualifying_open_tournaments_count: int) -> Category:
    """
    Classify an individual debater as NOVICE or OPEN.

    [CONFIRMED]
    - >= 7 qualifying tournaments: OPEN
    - <= 6 qualifying tournaments: NOVICE (including 0)
    """
    if qualifying_open_tournaments_count >= OPEN_THRESHOLD_TOURNAMENTS:
        return Category.OPEN
    return Category.NOVICE


def classify_team(member_categories: Sequence[Category]) -> Category:
    """
    Classify a team as NOVICE or OPEN.

    [CONFIRMED]
    - A team is Novice ONLY if ALL members are Novice.
    - If at least one member is Open, the entire team is classified as Open.
    """
    if not member_categories:
        raise ValueError("Cannot classify a team with no members")

    for cat in member_categories:
        if cat == Category.OPEN:
            return Category.OPEN
    return Category.NOVICE
