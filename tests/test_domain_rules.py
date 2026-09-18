"""
Unit tests for Atomos domain debating rules.

These tests serve as executable verification of the rules confirmed in:
- docs/debating/DEBATING_RULEBOOK.md
- docs/debating/Scoring Scale.txt
- docs/debating/Tab rules.txt
"""

import pytest

from atomos.domain.scoring import (
    SUBSTANTIVE_SCORE_MIN,
    SUBSTANTIVE_SCORE_MAX,
    REPLY_SCORE_MIN,
    REPLY_SCORE_MAX,
    SUBSTANTIVE_CONTENT_MIN,
    SUBSTANTIVE_CONTENT_MAX,
    SUBSTANTIVE_STYLE_MIN,
    SUBSTANTIVE_STYLE_MAX,
    SUBSTANTIVE_STRATEGY_MIN,
    SUBSTANTIVE_STRATEGY_MAX,
    REPLY_CONTENT_MIN,
    REPLY_CONTENT_MAX,
    REPLY_STYLE_MIN,
    REPLY_STYLE_MAX,
    REPLY_STRATEGY_MIN,
    REPLY_STRATEGY_MAX,
    TEAM_ROUND_SCORE_MIN,
    TEAM_ROUND_SCORE_MAX,
    WALKOVER_SUBSTANTIVE_WINNER,
    WALKOVER_SUBSTANTIVE_LOSER,
    WALKOVER_REPLY,
    WALKOVER_MARGIN,
    WALKOVER_TEAM_TOTAL_WINNER,
    WALKOVER_TEAM_TOTAL_LOSER,
    is_valid_substantive_score,

    is_valid_reply_score,
    is_valid_substantive_components,
    is_valid_reply_components,
    substantive_total,
    reply_total,
    team_round_score,
    round_winner,
    win_margin,
    average_win_margin,
)
from atomos.domain.eligibility import (
    is_valid_team_registration_size,
    is_speaker_tab_eligible,
    is_reply_tab_eligible,
    is_team_tab_eligible,
    is_team_knockout_eligible,
    resolve_iron_man_substantive_score,
    is_master_team_tab_eligible,
)
from atomos.domain.classification import (
    Category,
    TournamentFormat,
    counts_toward_open_status,
    classify_debater,
    classify_team,
)
from atomos.domain.ranking import (
    TeamTabEntry,
    SpeakerTabEntry,
    calculate_atss,
    rank_teams_for_tab,
    calculate_speaker_tab_average,
    rank_speakers_for_tab,
    calculate_reply_tab_average,
    calculate_master_speaker_tab_score,
    calculate_cumulative_speech_average,
    calculate_master_speaker_tab_cumulative_score,
    calculate_master_speaker_score,
    calculate_master_reply_tab_score,
    calculate_non_round1_walkover_scores,
    round_down_to_half,
)


class TestScoringRules:
    def test_score_ranges_constants(self):
        assert SUBSTANTIVE_SCORE_MIN == 60
        assert SUBSTANTIVE_SCORE_MAX == 80
        assert REPLY_SCORE_MIN == 30
        assert REPLY_SCORE_MAX == 40

    def test_substantive_score_validation(self):
        assert is_valid_substantive_score(60) is True
        assert is_valid_substantive_score(74.5) is True
        assert is_valid_substantive_score(80) is True
        assert is_valid_substantive_score(59.9) is False
        assert is_valid_substantive_score(80.1) is False

    def test_reply_score_validation(self):
        assert is_valid_reply_score(30) is True
        assert is_valid_reply_score(37.5) is True
        assert is_valid_reply_score(40) is True
        assert is_valid_reply_score(29.5) is False
        assert is_valid_reply_score(40.5) is False

    def test_substantive_component_validation(self):
        # Valid bounds: Content 24-32, Style 24-32, Strategy 12-16
        assert is_valid_substantive_components(28, 28, 14) is True
        assert is_valid_substantive_components(32, 32, 16) is True
        assert is_valid_substantive_components(24, 24, 12) is True
        assert is_valid_substantive_components(23.5, 28, 14) is False
        assert is_valid_substantive_components(28, 32.5, 14) is False
        assert is_valid_substantive_components(28, 28, 16.5) is False

    def test_reply_component_validation(self):
        # Valid bounds: Content 12-16, Style 12-16, Strategy 6-8
        assert is_valid_reply_components(14, 14, 7) is True
        assert is_valid_reply_components(16, 16, 8) is True
        assert is_valid_reply_components(12, 12, 6) is True
        assert is_valid_reply_components(11.5, 14, 7) is False
        assert is_valid_reply_components(14, 16.5, 7) is False
        assert is_valid_reply_components(14, 14, 8.5) is False

    def test_substantive_and_reply_totals(self):
        assert substantive_total(28, 28, 14) == 70
        assert substantive_total(30, 31, 15) == 76
        assert reply_total(14, 15, 7) == 36

    def test_team_round_score_and_bounds(self):
        assert TEAM_ROUND_SCORE_MIN == 210  # 60*3 + 30
        assert TEAM_ROUND_SCORE_MAX == 280  # 80*3 + 40
        score = team_round_score(72, 74, 71, 35)
        assert score == 252

    def test_round_winner_and_margins(self):
        assert round_winner(252, 248) == "A"
        assert round_winner(245, 250) == "B"
        assert round_winner(250, 250) == "TIE"

        assert win_margin(252, 248) == 4.0
        assert win_margin(245, 250) == -5.0

    def test_average_win_margin(self):
        # A team with margins across 4 rounds: +4, +2, -8, +1 -> average = -1/4 = -0.25
        margins = [4.0, 2.0, -8.0, 1.0]
        assert average_win_margin(margins) == -0.25


class TestEligibilityRules:
    def test_team_registration_size(self):
        assert is_valid_team_registration_size(2) is False  # Cannot register with 2
        assert is_valid_team_registration_size(3) is True   # Standard 3
        assert is_valid_team_registration_size(4) is True   # With 4th member
        assert is_valid_team_registration_size(5) is False  # Max 4

    def test_speaker_tab_eligibility(self):
        # [CONFIRMED] Must have spoken in at least 3 preliminary rounds
        assert is_speaker_tab_eligible(0) is False
        assert is_speaker_tab_eligible(2) is False
        assert is_speaker_tab_eligible(3) is True
        assert is_speaker_tab_eligible(5) is True

    def test_reply_tab_eligibility(self):
        # [CONFIRMED] No minimum round requirement; at least 1 reply speech
        assert is_reply_tab_eligible(0) is False
        assert is_reply_tab_eligible(1) is True
        assert is_reply_tab_eligible(3) is True

    def test_team_tab_and_knockout_eligibility(self):
        # Team tab requires >= 3 rounds
        assert is_team_tab_eligible(2) is False
        assert is_team_tab_eligible(3) is True

        # Knockout eligibility requires >= 3 rounds AND <= 2 iron man rounds
        assert is_team_knockout_eligible(rounds_debated=4, iron_man_rounds=0) is True
        assert is_team_knockout_eligible(rounds_debated=4, iron_man_rounds=1) is True
        assert is_team_knockout_eligible(rounds_debated=4, iron_man_rounds=2) is True
        # > 2 Iron Man rounds: disqualified from knockouts
        assert is_team_knockout_eligible(rounds_debated=4, iron_man_rounds=3) is False

    def test_iron_man_higher_substantive_represented(self):
        # [CONFIRMED] Higher substantive speech score counts
        assert resolve_iron_man_substantive_score(72.0, 75.5) == 75.5
        assert resolve_iron_man_substantive_score(76.0, 71.0) == 76.0

    def test_master_team_tab_eligibility(self):
        # [CONFIRMED] Must be eligible in at least 3 tournaments
        assert is_master_team_tab_eligible(2) is False
        assert is_master_team_tab_eligible(3) is True
        assert is_master_team_tab_eligible(5) is True


class TestClassificationRules:
    def test_qualifying_toward_open_threshold(self):
        # Must be DC-endorsed
        assert counts_toward_open_status(
            is_dc_endorsed=False,
            tournament_format=TournamentFormat.PURE_OPEN,
            team_category_in_tournament=Category.OPEN,
            was_speaker_tab_eligible=True,
        ) is False

        # Must be speaker tab eligible
        assert counts_toward_open_status(
            is_dc_endorsed=True,
            tournament_format=TournamentFormat.PURE_OPEN,
            team_category_in_tournament=Category.OPEN,
            was_speaker_tab_eligible=False,
        ) is False

        # Pure novice tournament never counts
        assert counts_toward_open_status(
            is_dc_endorsed=True,
            tournament_format=TournamentFormat.PURE_NOVICE,
            team_category_in_tournament=Category.NOVICE,
            was_speaker_tab_eligible=True,
        ) is False

        # Novice&Open on a Novice team does NOT count
        assert counts_toward_open_status(
            is_dc_endorsed=True,
            tournament_format=TournamentFormat.NOVICE_AND_OPEN,
            team_category_in_tournament=Category.NOVICE,
            was_speaker_tab_eligible=True,
        ) is False

        # Novice&Open on an Open team DOES count
        assert counts_toward_open_status(
            is_dc_endorsed=True,
            tournament_format=TournamentFormat.NOVICE_AND_OPEN,
            team_category_in_tournament=Category.OPEN,
            was_speaker_tab_eligible=True,
        ) is True

        # Pure Open on an Open team DOES count
        assert counts_toward_open_status(
            is_dc_endorsed=True,
            tournament_format=TournamentFormat.PURE_OPEN,
            team_category_in_tournament=Category.OPEN,
            was_speaker_tab_eligible=True,
        ) is True

    def test_classify_debater(self):
        assert classify_debater(0) == Category.NOVICE
        assert classify_debater(6) == Category.NOVICE
        assert classify_debater(7) == Category.OPEN
        assert classify_debater(10) == Category.OPEN

    def test_classify_team(self):
        # All members Novice -> NOVICE
        assert classify_team([Category.NOVICE, Category.NOVICE, Category.NOVICE]) == Category.NOVICE
        # At least one Open member -> OPEN
        assert classify_team([Category.NOVICE, Category.NOVICE, Category.OPEN]) == Category.OPEN
        assert classify_team([Category.OPEN, Category.OPEN, Category.OPEN]) == Category.OPEN


class TestRankingAndTabs:
    def test_atss_calculation(self):
        scores = [248.0, 252.0, 250.0, 246.0]
        assert calculate_atss(scores) == 249.0

    def test_team_tab_ranking_tiebreakers(self):
        """
        [CONFIRMED] Priority:
        1. Wins
        2. ATSS
        3. Average Win Margin
        """
        # Team A: 4 wins, ATSS 250, Margin +5
        # Team B: 4 wins, ATSS 249, Margin +10 (Lower ATSS than A)
        # Team C: 4 wins, ATSS 249, Margin -1 (Same ATSS as B, but margin -1 vs -1.5)
        # Team D: 4 wins, ATSS 249, Margin -1.5 (Example from founder interview!)
        # Team E: 3 wins, ATSS 255, Margin +15 (Fewer wins)
        t_a = TeamTabEntry("Team A", 5, 4, 1250, 250.0, 5.0, True)
        t_b = TeamTabEntry("Team B", 5, 4, 1245, 249.0, 10.0, True)
        t_c = TeamTabEntry("Team C", 5, 4, 1245, 249.0, -1.0, True)
        t_d = TeamTabEntry("Team D", 5, 4, 1245, 249.0, -1.5, True)
        t_e = TeamTabEntry("Team E", 5, 3, 1275, 255.0, 15.0, True)

        ranked = rank_teams_for_tab([t_e, t_c, t_a, t_d, t_b])
        names = [t.team_name for t in ranked]

        # Expected order:
        # Team A (4 wins, 250 ATSS)
        # Team B (4 wins, 249 ATSS, margin +10)
        # Team C (4 wins, 249 ATSS, margin -1.0)
        # Team D (4 wins, 249 ATSS, margin -1.5)
        # Team E (3 wins)
        assert names == ["Team A", "Team B", "Team C", "Team D", "Team E"]

    def test_speaker_tab_ranking(self):
        s1 = SpeakerTabEntry("Debater 1", 4, [75, 76, 74, 75], 75.0, True)
        s2 = SpeakerTabEntry("Debater 2", 4, [73, 74, 72, 73], 73.0, True)
        s3 = SpeakerTabEntry("Debater 3", 2, [78, 78], 78.0, False)  # Ineligible (only 2 rounds)

        ranked = rank_speakers_for_tab([s2, s3, s1])
        assert ranked[0].debater_name == "Debater 1"
        assert ranked[1].debater_name == "Debater 2"
        assert ranked[2].debater_name == "Debater 3"  # Ineligible ranked lower

    def test_master_speaker_tab_score(self):
        # [CONFIRMED] Average of tournament averages (equal weight)
        tournament_averages = [74.5, 72.0, 76.0]
        # (74.5 + 72.0 + 76.0) / 3 = 222.5 / 3 = 74.1666...
        master_avg = calculate_master_speaker_tab_score(tournament_averages)
        assert pytest.approx(master_avg, 0.001) == 74.167

    def test_cumulative_speech_average(self):
        # [NEW REGULATION - PRIORITY] Add up all speeches and divide by count
        speeches = [74.0, 75.0, 76.0, 72.0, 73.0]
        # (74 + 75 + 76 + 72 + 73) / 5 = 370 / 5 = 74.0
        assert calculate_cumulative_speech_average(speeches) == 74.0

    def test_parallel_master_speaker_score_regulations(self):
        # Tournament 1: 5 speeches at 75.0 (sum 375, avg 75.0)
        # Tournament 2: 3 speeches at 71.0 (sum 213, avg 71.0)
        tour_scores = [
            [75.0, 75.0, 75.0, 75.0, 75.0],
            [71.0, 71.0, 71.0],
        ]
        # Legacy (avg of avgs): (75.0 + 71.0) / 2 = 73.0
        legacy_score = calculate_master_speaker_score(tour_scores, regulation="legacy")
        assert legacy_score == 73.0

        # New Regulation (Priority - Cumulative): (375 + 213) / 8 = 588 / 8 = 73.5
        new_score = calculate_master_speaker_score(tour_scores, regulation="new")
        assert new_score == 73.5
        assert new_score != legacy_score

    def test_master_reply_tab_score(self):
        tournament_replies = [36.0, 37.0, 35.0]
        assert calculate_master_reply_tab_score(tournament_replies) == 36.0

    def test_walkover_rules(self):
        # Round 1 default constants (modern 60-80 scale)
        assert WALKOVER_SUBSTANTIVE_WINNER == 70.0
        assert WALKOVER_SUBSTANTIVE_LOSER == 68.0
        assert WALKOVER_REPLY == 35.0
        assert WALKOVER_MARGIN == 6.0
        assert WALKOVER_TEAM_TOTAL_WINNER == 245.0
        assert WALKOVER_TEAM_TOTAL_LOSER == 239.0


        # Helper round down to 0.5
        assert round_down_to_half(248.7) == 248.5
        assert round_down_to_half(248.4) == 248.0
        assert round_down_to_half(248.5) == 248.5

        # Later round walkover
        winner_participated_scores = [248.0, 251.0, 247.0]  # avg = 746/3 = 248.666...
        w_score, l_score, w_m, l_m = calculate_non_round1_walkover_scores(winner_participated_scores)
        assert w_score == 248.5
        assert l_score == 242.5  # 248.5 - 6
        assert w_m == 6.0
        assert l_m == -6.0
