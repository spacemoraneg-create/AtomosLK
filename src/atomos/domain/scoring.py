"""
Atomos Scoring Rules

Implements the scoring rules for Sri Lankan DC-endorsed WSDC-format debating.

All rules in this module are sourced from:
- docs/debating/DEBATING_RULEBOOK.md
- docs/debating/Scoring Scale.txt
- docs/debating/Tab rules.txt

No rule in this module should be invented by the coding agent.
"""


# --- Score Ranges ---
# [CONFIRMED] Substantive speech: 60-80
SUBSTANTIVE_SCORE_MIN = 60
SUBSTANTIVE_SCORE_MAX = 80

# [CONFIRMED] Reply speech: 30-40
REPLY_SCORE_MIN = 30
REPLY_SCORE_MAX = 40

# --- Component Weights ---
# [CONFIRMED] Content: 40%, Style: 40%, Strategy: 20%
CONTENT_WEIGHT = 0.40
STYLE_WEIGHT = 0.40
STRATEGY_WEIGHT = 0.20

# --- Substantive Component Ranges ---
# [CONFIRMED] Content: 24-32, Style: 24-32, Strategy: 12-16
SUBSTANTIVE_CONTENT_MIN = 24
SUBSTANTIVE_CONTENT_MAX = 32
SUBSTANTIVE_STYLE_MIN = 24
SUBSTANTIVE_STYLE_MAX = 32
SUBSTANTIVE_STRATEGY_MIN = 12
SUBSTANTIVE_STRATEGY_MAX = 16

# --- Reply Component Ranges ---
# [CONFIRMED] Same percentages scaled to 30-40 range
REPLY_CONTENT_MIN = 12
REPLY_CONTENT_MAX = 16
REPLY_STYLE_MIN = 12
REPLY_STYLE_MAX = 16
REPLY_STRATEGY_MIN = 6
REPLY_STRATEGY_MAX = 8

# --- Team Score Range ---
# [CONFIRMED] Team round score = sum of 3 substantive + 1 reply
TEAM_ROUND_SCORE_MIN = (3 * SUBSTANTIVE_SCORE_MIN) + REPLY_SCORE_MIN  # 210
TEAM_ROUND_SCORE_MAX = (3 * SUBSTANTIVE_SCORE_MAX) + REPLY_SCORE_MAX  # 280

# --- Walkover Scores ---
# [CONFIRMED] First-round walkover default scores (60-80 scale)
WALKOVER_SUBSTANTIVE_WINNER = 70.0
WALKOVER_SUBSTANTIVE_LOSER = 68.0
WALKOVER_REPLY = 35.0
WALKOVER_MARGIN = 6.0
WALKOVER_TEAM_TOTAL_WINNER = (3 * WALKOVER_SUBSTANTIVE_WINNER) + WALKOVER_REPLY  # 245.0
WALKOVER_TEAM_TOTAL_LOSER = WALKOVER_TEAM_TOTAL_WINNER - WALKOVER_MARGIN  # 239.0


def is_valid_substantive_score(score: float) -> bool:
    """Check if a substantive speech score is within the valid range (60-80)."""
    return SUBSTANTIVE_SCORE_MIN <= score <= SUBSTANTIVE_SCORE_MAX


def is_valid_reply_score(score: float) -> bool:
    """Check if a reply speech score is within the valid range (30-40)."""
    return REPLY_SCORE_MIN <= score <= REPLY_SCORE_MAX


def is_valid_substantive_components(
    content: float, style: float, strategy: float
) -> bool:
    """Check if substantive speech component scores are within valid ranges."""
    return (
        SUBSTANTIVE_CONTENT_MIN <= content <= SUBSTANTIVE_CONTENT_MAX
        and SUBSTANTIVE_STYLE_MIN <= style <= SUBSTANTIVE_STYLE_MAX
        and SUBSTANTIVE_STRATEGY_MIN <= strategy <= SUBSTANTIVE_STRATEGY_MAX
    )


def is_valid_reply_components(
    content: float, style: float, strategy: float
) -> bool:
    """Check if reply speech component scores are within valid ranges."""
    return (
        REPLY_CONTENT_MIN <= content <= REPLY_CONTENT_MAX
        and REPLY_STYLE_MIN <= style <= REPLY_STYLE_MAX
        and REPLY_STRATEGY_MIN <= strategy <= REPLY_STRATEGY_MAX
    )


def substantive_total(content: float, style: float, strategy: float) -> float:
    """Calculate the total score for a substantive speech from its components."""
    return content + style + strategy


def reply_total(content: float, style: float, strategy: float) -> float:
    """Calculate the total score for a reply speech from its components."""
    return content + style + strategy


def team_round_score(
    substantive_1: float,
    substantive_2: float,
    substantive_3: float,
    reply: float,
) -> float:
    """
    Calculate a team's total score for a round.

    [CONFIRMED] Team round score = sum of all 4 speeches
    (3 substantive + 1 reply).
    """
    return substantive_1 + substantive_2 + substantive_3 + reply


def round_winner(team_a_score: float, team_b_score: float) -> str:
    """
    Determine the winner of a round based on team scores.

    Returns 'A', 'B', or 'TIE'.
    [CONFIRMED] The team with the higher total wins.
    """
    if team_a_score > team_b_score:
        return "A"
    elif team_b_score > team_a_score:
        return "B"
    else:
        return "TIE"


def win_margin(team_score: float, opponent_score: float) -> float:
    """
    Calculate the win margin for a team in a round.

    [CONFIRMED] Margin = team score - opponent score.
    Can be positive (win) or negative (loss).
    """
    return team_score - opponent_score


def average_win_margin(margins: list[float]) -> float:
    """
    Calculate the average win margin across all preliminary rounds.

    [CONFIRMED] This is the average of all margins (wins and losses).
    Can be negative overall.
    """
    if not margins:
        raise ValueError("Cannot calculate average of empty margins list")
    return sum(margins) / len(margins)
