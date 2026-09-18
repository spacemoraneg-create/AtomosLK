"""
Atomos Tab and Ranking Rules

Implements ranking calculations for tournament and master tabs:
- Team Tab (Wins -> ATSS -> Average Margin)
- Speaker Tab (Substantive Average for eligible debaters)
- Reply Tab (Reply Average)
- Master Speaker Tab (Average of tournament averages)
- Master Reply Tab (Average of tournament reply averages)

All rules sourced directly from:
- docs/debating/DEBATING_RULEBOOK.md (Sections 8, 9, 13)
- docs/debating/Tab rules.txt

No rule in this module should be invented by the coding agent.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence
import math

from atomos.domain.eligibility import is_speaker_tab_eligible, is_reply_tab_eligible, is_team_tab_eligible


@dataclass(frozen=True)
class TeamTabEntry:
    team_name: str
    rounds_debated: int
    wins: int
    total_speaker_points: float  # sum of all 4 speeches across all rounds
    atss: float                 # average total speaker score per round
    average_margin: float       # average net margin across all rounds
    is_eligible: bool


@dataclass(frozen=True)
class SpeakerTabEntry:
    debater_name: str
    rounds_spoken: int
    substantive_scores: Sequence[float]
    average_score: float
    is_eligible: bool


@dataclass(frozen=True)
class ReplyTabEntry:
    debater_name: str
    replies_given: int
    reply_scores: Sequence[float]
    average_score: float
    is_eligible: bool


def calculate_atss(round_team_scores: Sequence[float]) -> float:
    """
    Calculate Average Total Speaker Score (ATSS).
    [CONFIRMED] The average of the team round scores across all preliminary rounds.
    """
    if not round_team_scores:
        raise ValueError("Cannot calculate ATSS with no rounds")
    return sum(round_team_scores) / len(round_team_scores)


def rank_teams_for_tab(entries: Sequence[TeamTabEntry]) -> List[TeamTabEntry]:
    """
    Rank teams for the tournament Team Tab.

    [CONFIRMED] Criteria in order of priority:
    1. Wins (descending)
    2. ATSS (Average Total Speaker Score) (descending)
    3. Average win margin (descending)
    """
    # Filter or sort; note that non-eligible teams are kept at the bottom or flagged.
    # We sort all teams using the tuple key:
    # (is_eligible, wins, atss, average_margin)
    return sorted(
        entries,
        key=lambda e: (e.is_eligible, e.wins, e.atss, e.average_margin),
        reverse=True,
    )


def calculate_speaker_tab_average(substantive_scores: Sequence[float]) -> float:
    """
    Calculate a debater's Speaker Tab score.
    [CONFIRMED] Average of their substantive scores across preliminary rounds.
    """
    if not substantive_scores:
        raise ValueError("Cannot calculate average without scores")
    return sum(substantive_scores) / len(substantive_scores)


def rank_speakers_for_tab(entries: Sequence[SpeakerTabEntry]) -> List[SpeakerTabEntry]:
    """
    Rank debaters for the tournament Speaker Tab.
    [CONFIRMED] Ranked by average substantive score descending.
    Eligible debaters appear first.
    """
    return sorted(
        entries,
        key=lambda e: (e.is_eligible, e.average_score),
        reverse=True,
    )


def calculate_reply_tab_average(reply_scores: Sequence[float]) -> float:
    """
    Calculate a debater's Reply Tab score.
    [CONFIRMED] Average of their reply speech scores.
    """
    if not reply_scores:
        raise ValueError("Cannot calculate average without scores")
    return sum(reply_scores) / len(reply_scores)


def rank_replies_for_tab(entries: Sequence[ReplyTabEntry]) -> List[ReplyTabEntry]:
    """
    Rank debaters for the tournament Reply Tab.
    [CONFIRMED] Ranked by average reply score descending.
    """
    return sorted(
        entries,
        key=lambda e: (e.is_eligible, e.average_score),
        reverse=True,
    )


def calculate_cumulative_speech_average(scores: Sequence[float]) -> float:
    """
    Calculate debater's cumulative speech average.
    [NEW REGULATION - PRIORITY]
    Adds up all speech scores and divides by the total number of speeches.
    """
    if not scores:
        raise ValueError("Cannot calculate average without speech scores")
    return sum(scores) / len(scores)


def calculate_master_speaker_tab_cumulative_score(all_qualifying_scores: Sequence[float]) -> float:
    """
    Calculate Master Speaker Tab score across qualifying tournaments using speech weighting.
    [NEW REGULATION - PRIORITY]
    Adds up all substantive speech scores from qualifying tournaments and divides by total qualifying speeches.
    """
    return calculate_cumulative_speech_average(all_qualifying_scores)


def calculate_master_speaker_tab_score(tournament_averages: Sequence[float]) -> float:
    """
    Calculate Master Speaker Tab score across multiple tournaments.
    [LEGACY REGULATION] Average of the debater's tournament averages (each tournament weighted equally).
    Only tournaments where debater was eligible for Speaker Tab should be passed in.
    """
    if not tournament_averages:
        raise ValueError("No eligible tournaments provided for Master Speaker Tab")
    return sum(tournament_averages) / len(tournament_averages)


def calculate_master_speaker_score(
    tournament_scores_map: Sequence[Sequence[float]],
    regulation: str = "new",
) -> float:
    """
    Unified master speaker calculation supporting both regulations.
    - regulation="new" (Priority): sums all speeches across qualifying tournaments and divides by total speeches.
    - regulation="legacy": computes each tournament average and returns the mean of tournament averages.
    """
    if not tournament_scores_map:
        raise ValueError("No tournament scores provided")

    if regulation in ("legacy", "avg_of_avgs"):
        tour_avgs = [sum(scores) / len(scores) for scores in tournament_scores_map if scores]
        return calculate_master_speaker_tab_score(tour_avgs)

    # Default to new regulation (priority)
    all_scores = [score for tour in tournament_scores_map for score in tour]
    return calculate_master_speaker_tab_cumulative_score(all_scores)


def calculate_master_reply_tab_score(tournament_reply_averages: Sequence[float]) -> float:
    """
    Calculate Master Reply Tab score across multiple tournaments.
    [CONFIRMED] Average of the debater's tournament reply averages (each tournament weighted equally).
    """
    if not tournament_reply_averages:
        raise ValueError("No tournament reply averages provided for Master Reply Tab")
    return sum(tournament_reply_averages) / len(tournament_reply_averages)


def round_down_to_half(val: float) -> float:
    """Helper to round down to the nearest 0.5 (e.g. 248.7 -> 248.5, 248.4 -> 248.0)."""
    return math.floor(val * 2.0) / 2.0


def calculate_non_round1_walkover_scores(
    winner_other_rounds_scores: Sequence[float],
) -> tuple[float, float, float, float]:
    """
    Calculate walkover team scores for non-round-1 walkovers per Tab rules 3.4.

    Returns:
    (winner_awarded_score, loser_awarded_score, winner_margin, loser_margin)

    [CONFIRMED]:
    - Winner: 6-point margin win, score = average of other rounds rounded down to nearest 0.5.
    - Loser: 6-point defeat, score = opponent's average score - 6.
    """
    if not winner_other_rounds_scores:
        raise ValueError("Cannot calculate without participated rounds for winner")

    avg_winner = sum(winner_other_rounds_scores) / len(winner_other_rounds_scores)
    winner_score = round_down_to_half(avg_winner)
    loser_score = winner_score - 6.0
    return winner_score, loser_score, 6.0, -6.0
