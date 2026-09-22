"""
Atomos LLM Readiness & Function Calling Verification Suite

Verifies that the database, query facades, search algorithms, and tool dispatchers
are 100% stable, JSON-serializable, and ready for downstream LLM agent integration.
"""

import json
import sqlite3
import pytest

from atomos.database.connection import get_connection
from atomos.analytics.search import UnifiedSearchEngine
from atomos.query import AtomosQuery
from atomos.tools import TOOL_SCHEMAS, dispatch_tool


@pytest.fixture
def conn():
    c = get_connection()
    yield c
    c.close()


@pytest.fixture
def query_engine():
    aq = AtomosQuery()
    yield aq
    aq.close()


def test_tool_schemas_validity():
    """Verify that all tool schemas conform to standard OpenAI/Gemini function calling specs."""
    assert len(TOOL_SCHEMAS) == 18
    expected_tools = {
        "search_entities",
        "get_debater_profile",
        "get_head_to_head",
        "compare_institutions",
        "get_institutional_leaderboard",
        "get_speaker_leaderboard",
        "get_circuit_summary",
        "get_tournament_finals",
        "get_motion_analytics",
        "get_debate_ballot",
        "get_team_record",
        "get_tier_matchup_stats",
        "get_national_pool",
        "get_tournament_bracket",
        "get_judge_profile",
        "get_judge_leaderboard",
        "predict_matchup",
        "execute_sql",
    }
    found_tools = set()
    for s in TOOL_SCHEMAS:
        assert s["type"] == "function"
        fn = s["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        found_tools.add(fn["name"])

    assert found_tools == expected_tools


def test_search_engine_debaters(conn):
    """Verify debater entity searching by exact name and alias."""
    se = UnifiedSearchEngine(conn)
    results = se.search_debaters("Balishta", limit=3)
    assert len(results) >= 1
    top = results[0]
    assert top["entity_type"] == "debater"
    assert "Balishta" in top["name"]
    assert top["person_id"] > 0
    assert top["similarity"] >= 0.8


def test_search_engine_institutions(conn):
    """Verify school entity searching by name and acronym code."""
    se = UnifiedSearchEngine(conn)
    # Acronym search
    rc = se.search_institutions("RC", limit=1)
    assert len(rc) == 1
    assert rc[0]["name"] == "Royal College"
    assert rc[0]["code"] == "RC"
    assert rc[0]["similarity"] == 1.0

    # Name search
    wc = se.search_institutions("Wesley", limit=1)
    assert len(wc) == 1
    assert wc[0]["name"] == "Wesley College"


def test_search_engine_motions(conn):
    """Verify motion searching by keyword."""
    se = UnifiedSearchEngine(conn)
    results = se.search_motions("AI", limit=5)
    assert len(results) >= 1
    for m in results:
        assert m["entity_type"] == "motion"
        assert m["theme"] is not None
        assert len(m["motion"]) > 0


def test_atomos_query_debater(query_engine):
    """Verify get_debater returns valid structured profile."""
    prof = query_engine.get_debater("Balishta", compact=True)
    assert "error" not in prof
    assert prof["canonical_name"] == "Balishta Wijesinghe"
    assert prof["person_id"] > 0
    assert "overall_substantive_avg" in prof
    assert "win_rate" in prof
    # Ensure JSON serializable
    serialized = json.dumps(prof)
    assert len(serialized) > 0


def test_atomos_query_head_to_head(query_engine):
    """Verify get_head_to_head across schools and debaters."""
    school_h2h = query_engine.get_head_to_head("Royal", "Ananda", mode="school")
    assert "error" not in school_h2h
    assert "direct_debates" in school_h2h

    deb_h2h = query_engine.get_head_to_head("Balishta Wijesinghe", "Vidath Marasinghe", mode="debater")
    assert "error" not in deb_h2h
    assert "debater_a" in deb_h2h
    assert "debater_b" in deb_h2h


def test_atomos_query_institutions_and_leaderboard(query_engine):
    """Verify compare_institutions and get_institutional_leaderboard."""
    cmp_res = query_engine.compare_institutions("RC", "WC")
    assert "error" not in cmp_res
    assert cmp_res["inst_a"]["name"] == "Royal College"
    assert cmp_res["inst_b"]["name"] == "Wesley College"

    lb = query_engine.get_institutional_leaderboard(min_debates=5)
    assert isinstance(lb, list)
    assert len(lb) >= 5
    for rank_entry in lb[:3]:
        assert 0.0 <= rank_entry["ipi"] <= 100.0


def test_atomos_query_motion_analytics(query_engine):
    """Verify motion analytics, themes, and side biases."""
    analytics = query_engine.get_motion_analytics(extreme_only=True)
    assert "overall_side_balance" in analytics
    assert "thematic_analysis" in analytics
    assert "extreme_and_balanced" in analytics
    assert analytics["overall_side_balance"]["total_decisions"] > 0


def test_dispatch_tool_resilience(query_engine):
    """Verify dispatch_tool handles all tools and unknown tool names gracefully."""
    # Test valid tool
    res = dispatch_tool("get_circuit_summary", {}, query_engine=query_engine)
    assert "total_persons" in res
    assert res["total_persons"] > 0

    # Test unknown tool
    err_res = dispatch_tool("non_existent_tool", {}, query_engine=query_engine)
    assert "error" in err_res
    assert "Unknown tool" in err_res["error"]


def test_atomos_query_tournament_finals(query_engine):
    """Verify get_tournament_finals identifies all Grand Finals and same-school closeouts."""
    all_finals = query_engine.get_tournament_finals()
    assert all_finals["total_finals"] >= 7
    assert all_finals["same_institution_finals_count"] == 2

    # Verify alias resolution for Law Fac -> SLSDC 2026
    law_fac_final = query_engine.get_tournament_finals("Law Fac")
    assert law_fac_final["total_finals"] == 1
    assert law_fac_final["same_institution_finals_count"] == 1
    f = law_fac_final["finals"][0]
    assert "SLSDC" in f["tournament_name"]
    assert f["is_same_institution_final"] is True
    assert f["institution_name"] == "Royal College"

    # Test via dispatch_tool
    dispatched = dispatch_tool("get_tournament_finals", {"tournament": "Chaps"}, query_engine=query_engine)
    assert dispatched["total_finals"] == 1
    assert dispatched["finals"][0]["is_same_institution_final"] is True
    assert dispatched["finals"][0]["institution_name"] == "D. S. Senanayake College"


def test_atomos_query_speaker_leaderboard(query_engine):
    """Verify get_speaker_leaderboard returns correct prelim counts and distinct debate volumes."""
    # 1. Prelims leaderboard
    prelim_lb = query_engine.get_speaker_leaderboard(metric="prelims", limit=10)
    assert prelim_lb["metric"] == "prelim_rounds_debated"
    assert prelim_lb["total_returned"] == 10
    top_entry = prelim_lb["leaderboard"][0]
    # Max prelims across 9 tournaments is 41
    assert top_entry["prelim_rounds_debated"] == 41
    assert "national_level" in top_entry

    # 2. Debates leaderboard
    deb_lb = query_engine.get_speaker_leaderboard(metric="debates", limit=5)
    assert deb_lb["metric"] == "total_debates"
    assert len(deb_lb["leaderboard"]) == 5
    assert deb_lb["leaderboard"][0]["total_debates"] == 41
    assert "national_level" in deb_lb["leaderboard"][0]

    # 3. Master Tab & Critical Stats leaderboards
    mtab_lb = query_engine.get_speaker_leaderboard(metric="master_tab", limit=5)
    assert "national_level" in mtab_lb["leaderboard"][0]
    cstats_lb = query_engine.get_speaker_leaderboard(metric="critical_stats", limit=5)
    assert "national_level" in cstats_lb["leaderboard"][0]

    # 4. Via dispatch_tool
    dispatched = dispatch_tool("get_speaker_leaderboard", {"metric": "prelims", "limit": 5}, query_engine=query_engine)
    assert "leaderboard" in dispatched
    assert len(dispatched["leaderboard"]) == 5
    assert "national_level" in dispatched["leaderboard"][0]


def test_atomos_query_debate_ballot(query_engine):
    """Verify get_debate_ballot accurately retrieves full scoresheet, lineups, and winner."""
    # 1. Query Chap's 2026 Round 5 DS B vs DS A
    ballot = query_engine.get_debate_ballot(tournament="Chaps", round_number=5, team="DS B")
    assert "error" not in ballot
    assert ballot["debate_id"] == 3411
    assert "Chap" in ballot["tournament"]["name"]
    assert ballot["round"]["round_number"] == 5

    # Check proposition is DS B
    prop = ballot["proposition"]
    assert prop["team_name"] == "DS B"
    assert prop["total_score"] == 252.0
    prop_speaker_names = [s["speaker_name"] for s in prop["lineup"]]
    assert "Aadithya Abeysundara" in prop_speaker_names
    assert "Balishta Wijesinghe" in prop_speaker_names
    assert "Didumika Peiris" in prop_speaker_names

    # Check opposition is DS A
    opp = ballot["opposition"]
    assert opp["team_name"] == "DS A"
    assert opp["total_score"] == 254.0
    opp_speaker_names = [s["speaker_name"] for s in opp["lineup"]]
    assert "Sadew Muthuhetti" in opp_speaker_names
    assert "Vidath Marasinghe" in opp_speaker_names
    assert "Nuhan Gunasekara" in opp_speaker_names

    # Check winner
    res = ballot["result"]
    assert res["winner_side"] == "Opposition"
    assert res["winner_team"] == "DS A"
    assert res["margin"] == 2.0

    # Adjudicator
    assert len(ballot["adjudicators"]) == 1
    assert ballot["adjudicators"][0]["name"] == "Rudhesh Ram"

    # 2. Test via dispatch_tool
    dispatched = dispatch_tool("get_debate_ballot", {"debate_id": 3411}, query_engine=query_engine)
    assert "error" not in dispatched
    assert dispatched["debate_id"] == 3411
    assert dispatched["proposition"]["team_name"] == "DS B"
    assert dispatched["opposition"]["team_name"] == "DS A"


def test_atomos_query_team_record(query_engine):
    """Verify get_team_record returns exact circuit and tournament records with averaged panel scores."""
    # 1. Circuit-wide record for DS A
    rec_a = query_engine.get_team_record("DS A")
    assert "error" not in rec_a
    assert rec_a["highest_team_score"]["score"] == 261.5
    assert "Visakha" in rec_a["highest_team_score"]["tournament"] or "VVIDC" in rec_a["highest_team_score"]["tournament"]
    assert rec_a["highest_quality_debate"]["combined_score"] == 514.5
    assert "ISDC" in rec_a["highest_quality_debate"]["tournament"]

    # 2. Chap's 2026 record for DS A (matching Calicotab Team Tab exactly)
    chaps_a = query_engine.get_team_record("DS A", tournament="Chaps")
    assert "error" not in chaps_a
    assert chaps_a["highest_team_score"]["score"] == 255.0
    assert chaps_a["highest_team_score"]["round"] == "Round 4"
    assert chaps_a["highest_quality_debate"]["combined_score"] == 507.0
    # Verify exact round-by-round scores on Calicotab
    scores_a = [r["team_score"] for r in chaps_a["detailed_rounds"] if r["round_number"] <= 5]
    assert scores_a == [246.5, 249.0, 251.5, 255.0, 254.0]

    # 3. Chap's 2026 record for DS B (matching Calicotab Team Tab exactly)
    chaps_b = query_engine.get_team_record("DS B", tournament="Chaps")
    assert "error" not in chaps_b
    assert chaps_b["highest_team_score"]["score"] == 252.0
    assert chaps_b["highest_quality_debate"]["combined_score"] == 506.0
    scores_b = [r["team_score"] for r in chaps_b["detailed_rounds"] if r["round_number"] <= 5]
    assert scores_b == [252.0, 248.0, 247.5, 251.5, 252.0]

    # 4. Via dispatch_tool
    dispatched = dispatch_tool("get_team_record", {"team_name": "DS A", "tournament": "Chaps"}, query_engine=query_engine)
    assert "error" not in dispatched
    assert dispatched["highest_team_score"]["score"] == 255.0


def test_atomos_query_new_engines(query_engine):
    """Verify dispatching and query execution for 4 newly integrated analytical engines."""
    # 1. Tournament Bracket
    bracket = query_engine.get_tournament_bracket("Chaps2026")
    assert "error" not in bracket
    assert "Chap" in bracket["tournament_name"]
    assert bracket["is_same_institution_closeout"] is True
    dispatched_bracket = dispatch_tool("get_tournament_bracket", {"tournament": "Chaps2026"}, query_engine=query_engine)
    assert "error" not in dispatched_bracket
    assert "Chap" in dispatched_bracket["tournament_name"]

    # 2. Judge Dossier
    judge = query_engine.get_judge_dossier("Minithi Hewage")
    assert "error" not in judge
    assert "Minithi" in judge["adjudicator_name"]
    dispatched_judge = dispatch_tool("get_judge_profile", {"identifier": "Minithi Hewage"}, query_engine=query_engine)
    assert "error" not in dispatched_judge
    assert "Minithi" in dispatched_judge["adjudicator_name"]

    # 3. Judge Leaderboard
    j_lb = query_engine.get_judge_leaderboard(min_debates=3, limit=5)
    assert len(j_lb) > 0
    dispatched_j_lb = dispatch_tool("get_judge_leaderboard", {"min_debates": 3, "limit": 5}, query_engine=query_engine)
    assert "error" not in dispatched_j_lb
    assert len(dispatched_j_lb["leaderboard"]) > 0

    # 4. Match Predictor
    pred = query_engine.predict_matchup("DS A", "RC A")
    assert "error" not in pred
    assert "simulation" in pred
    dispatched_pred = dispatch_tool("predict_matchup", {"team_a": "DS A", "team_b": "RC A"}, query_engine=query_engine)
    assert "error" not in dispatched_pred
    assert "simulation" in dispatched_pred

