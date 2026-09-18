"""
Atomos Eligibility Rules

Implements the eligibility rules for Sri Lankan DC-endorsed WSDC debating.

All rules in this module are sourced directly from:
- docs/debating/DEBATING_RULEBOOK.md (Section 7, Section 4, Section 9)

No rule in this module should be invented by the coding agent.
"""

from dataclasses import dataclass
from typing import Optional


# --- Team Registration Constraints ---
# [CONFIRMED] Team registered members: min 3, max 4
TEAM_MEMBERS_MIN = 3
TEAM_MEMBERS_MAX = 4

# [CONFIRMED] Active speakers required in an ordinary round: 3
ACTIVE_SPEAKERS_STANDARD = 3

# [CONFIRMED] Active speakers in an Iron Man round: 2
ACTIVE_SPEAKERS_IRON_MAN = 2

# --- Thresholds ---
# [CONFIRMED] Debater must speak in at least 3 preliminary rounds for Speaker Tab
SPEAKER_TAB_MIN_ROUNDS = 3

# [CONFIRMED] Reply Tab has NO minimum round requirement (at least 1 reply speech)
REPLY_TAB_MIN_ROUNDS = 1

# [CONFIRMED] Team must debate in at least 3 preliminary rounds for Team Tab & Knockouts
TEAM_TAB_MIN_ROUNDS = 3

# [CONFIRMED] Max Iron Man rounds allowed before knockout disqualification: 2
# (> 2 means disqualified from knockouts, though still eligible for Team Tab)
MAX_IRON_MAN_ROUNDS_FOR_KNOCKOUT = 2

# [CONFIRMED] Master Team Tab requires eligibility in at least 3 tournaments
MASTER_TEAM_TAB_MIN_TOURNAMENTS = 3


def is_valid_team_registration_size(member_count: int) -> bool:
    """
    Check if a team has a valid number of registered members (3 to 4).
    [CONFIRMED] A team cannot register with fewer than 3 members.
    """
    return TEAM_MEMBERS_MIN <= member_count <= TEAM_MEMBERS_MAX


def is_speaker_tab_eligible(rounds_spoken: int) -> bool:
    """
    Determine if a debater is eligible for the tournament Speaker Tab.
    [CONFIRMED] Must have spoken in at least 3 preliminary rounds.
    """
    return rounds_spoken >= SPEAKER_TAB_MIN_ROUNDS


def is_reply_tab_eligible(replies_given: int) -> bool:
    """
    Determine if a debater is eligible for the tournament Reply Tab.
    [CONFIRMED] No minimum round requirement; anyone who gave at least 1 reply is listed.
    """
    return replies_given >= REPLY_TAB_MIN_ROUNDS


def is_team_tab_eligible(rounds_debated: int) -> bool:
    """
    Determine if a team is eligible for the tournament Team Tab.
    [CONFIRMED] Must have debated in at least 3 preliminary rounds.
    """
    return rounds_debated >= TEAM_TAB_MIN_ROUNDS


def is_team_knockout_eligible(rounds_debated: int, iron_man_rounds: int) -> bool:
    """
    Determine if a team is eligible for knockout rounds.
    [CONFIRMED] Must have debated at least 3 preliminary rounds AND
    iron-manned in at most 2 rounds.
    """
    if not is_team_tab_eligible(rounds_debated):
        return False
    return iron_man_rounds <= MAX_IRON_MAN_ROUNDS_FOR_KNOCKOUT


def resolve_iron_man_substantive_score(score_1: float, score_2: float) -> float:
    """
    In an Iron Man round, one debater delivers two substantive speeches.
    [CONFIRMED] The speech that recorded the higher speaker score represents
    them in the Speaker Tab.
    """
    return max(score_1, score_2)


def is_master_team_tab_eligible(eligible_tournaments_count: int) -> bool:
    """
    Determine if a team qualifies to appear on the Master Team Tab.
    [CONFIRMED] Must have been eligible for Team Tab in at least 3 tournaments.
    """
    return eligible_tournaments_count >= MASTER_TEAM_TAB_MIN_TOURNAMENTS
