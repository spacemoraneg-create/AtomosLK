"""
Tests for Atomos Natural Language Agent Layer (Fold 4)
"""

import pytest

from atomos.agent.intent import AgentIntent, classify_intent
from atomos.agent.orchestrator import AtomosAgent
from atomos.database.connection import get_connection


class TestAgentIntentClassification:
    def test_classify_debater_dossier(self):
        intent, params = classify_intent("Who is Balishta Wijesinghe?")
        assert intent == AgentIntent.DEBATER_DOSSIER
        assert "Balishta" in params.get("identifier", "")

    def test_classify_debater_id(self):
        intent, params = classify_intent("Scout debater #42")
        assert intent == AgentIntent.DEBATER_DOSSIER
        assert params.get("identifier") == "42"

    def test_classify_head_to_head(self):
        intent, params = classify_intent("Compare Royal College and D. S. Senanayake College")
        assert intent == AgentIntent.HEAD_TO_HEAD
        assert "Royal College" in params.get("entity_a", "")
        assert "D. S. Senanayake College" in params.get("entity_b", "")

    def test_classify_head_to_head_vs_syntax(self):
        intent, params = classify_intent("Balishta Wijesinghe vs Abeesha Wickramasinghe")
        assert intent == AgentIntent.HEAD_TO_HEAD
        assert "Balishta" in params.get("entity_a", "")
        assert "Abeesha" in params.get("entity_b", "")

    def test_classify_institution_leaderboard(self):
        intent, params = classify_intent("Show me the top 10 schools by IPI ranking")
        assert intent == AgentIntent.INSTITUTION_LEADERBOARD
        assert params.get("top_n") == 10

    def test_classify_speaker_rankings(self):
        intent, params = classify_intent("Who are the top 15 speakers on the Master Tab?")
        assert intent == AgentIntent.SPEAKER_RANKINGS
        assert params.get("limit") == 15

    def test_classify_motion_intelligence(self):
        intent, params = classify_intent("Which motions had the highest Opposition side bias?")
        assert intent == AgentIntent.MOTION_INTELLIGENCE
        assert params.get("extreme_only") is True

    def test_classify_math_derivation(self):
        intent, params = classify_intent("How was the speaker average calculated for debater 42?")
        assert intent == AgentIntent.MATH_DERIVATION
        assert params.get("identifier") == "42"

    def test_classify_circuit_summary(self):
        intent, params = classify_intent("Give me a circuit overview and total debaters")
        assert intent == AgentIntent.GENERAL_CIRCUIT


class TestAtomosAgentExecution:
    @pytest.fixture
    def agent(self):
        conn = get_connection()
        yield AtomosAgent(conn, use_llm=False)
        conn.close()

    def test_ask_debater_dossier(self, agent):
        res = agent.ask("Who is Balishta Wijesinghe?")
        assert res.success is True
        assert res.intent == AgentIntent.DEBATER_DOSSIER.value
        assert "Balishta Wijesinghe" in res.answer
        assert "D. S. Senanayake College" in res.answer
        assert "71.23" in res.answer  # New regulation speech avg across 10 attended tournaments
        assert "67.5%" in res.answer  # Win rate
        assert "22.625" in res.answer  # Career Avg Speaker Tab Rank

    def test_ask_debater_by_id(self, agent):
        res = agent.ask("Scout debater #42")
        assert res.success is True
        assert "#42" in res.answer
        assert "Balishta Wijesinghe" in res.answer

    def test_ask_head_to_head_schools(self, agent):
        res = agent.ask("Compare Royal College and D. S. Senanayake College")
        assert res.success is True
        assert res.intent == AgentIntent.HEAD_TO_HEAD.value
        assert "Royal College" in res.answer
        assert "D. S. Senanayake College" in res.answer
        assert "Direct Institutional Record" in res.answer

    def test_ask_institution_leaderboard(self, agent):
        res = agent.ask("Show top 5 schools on the IPI leaderboard")
        assert res.success is True
        assert res.intent == AgentIntent.INSTITUTION_LEADERBOARD.value
        assert "Royal College" in res.answer
        assert "D. S. Senanayake College" in res.answer

    def test_ask_motion_intelligence(self, agent):
        res = agent.ask("What is the circuit side bias on motions?")
        assert res.success is True
        assert res.intent == AgentIntent.MOTION_INTELLIGENCE.value
        assert "Proposition Wins" in res.answer
        assert "Opposition Wins" in res.answer

    def test_ask_math_derivation(self, agent):
        res = agent.ask("How was the speaker average calculated for debater 42?")
        assert res.success is True
        assert res.intent == AgentIntent.MATH_DERIVATION.value
        assert "WSDC & Atomos Master Tab Standardization Rules" in res.answer
        assert "Sum of Qualifying Speeches" in res.answer
        assert "71.23026 pts" in res.answer

    def test_ask_circuit_summary(self, agent):
        res = agent.ask("How many debaters and tournaments are in the circuit?")
        assert res.success is True
        assert res.intent == AgentIntent.GENERAL_CIRCUIT.value
        assert "Tournaments Tracked" in res.answer
        assert "Contested Debates" in res.answer

    def test_ask_greeting(self, agent):
        res = agent.ask("hello")
        assert res.success is True
        assert res.intent == AgentIntent.GREETING.value
        assert "Welcome to Atomos Debate Intelligence" in res.answer

    def test_ask_system_identity(self, agent):
        res = agent.ask("who are you")
        assert res.success is True
        assert res.intent == AgentIntent.SYSTEM_IDENTITY.value
        assert "national championships" in res.answer
        assert "Zero-Hallucination" in res.answer

    def test_ask_best_round(self, agent):
        res = agent.ask("balishta's best round")
        assert res.success is True
        assert res.intent == AgentIntent.SUPERLATIVE_ROUND.value
        assert "Balishta Wijesinghe" in res.answer
        assert "74" in res.answer
        assert "ISDC 26" in res.answer
        assert "Opposition" in res.answer

    def test_ask_worst_round(self, agent):
        res = agent.ask("balishta's worst round")
        assert res.success is True
        assert res.intent == AgentIntent.SUPERLATIVE_ROUND.value
        assert "Balishta Wijesinghe" in res.answer
        assert "Lowest-Scoring" in res.answer

    def test_ask_side_split(self, agent):
        res = agent.ask("how does balishta perform on gov vs opp?")
        assert res.success is True
        assert res.intent == AgentIntent.SIDE_SPLIT.value
        assert "Proposition" in res.answer
        assert "Opposition" in res.answer
        assert "71.04" in res.answer
        assert "71.5" in res.answer

    def test_ask_adjudicator_lookup(self, agent):
        res = agent.ask("who judged balishta when he scored his highest score?")
        assert res.success is True
        assert res.intent == AgentIntent.ADJUDICATOR_LOOKUP.value
        assert "Adam Dhilshan" in res.answer
        assert "74" in res.answer

    def test_ask_institution_dossier(self, agent):
        res = agent.ask("tell me about Royal College")
        assert res.success is True
        assert res.intent == AgentIntent.INSTITUTION_DOSSIER.value
        assert "Royal College" in res.answer
        assert "National Rank: #1" in res.answer
        assert "National IPI Score" in res.answer

    def test_ask_top_speakers(self, agent):
        res = agent.ask("top 5 speakers")
        assert res.success is True
        assert res.intent == AgentIntent.SPEAKER_RANKINGS.value
        assert "National Speaker Tab — Top 5 Debaters" in res.answer
        assert "Kulith Wickramasinghe" in res.answer

    def test_safe_execute_sql_tool(self):
        from atomos.tools import dispatch_tool
        # 1. Valid select
        ok_res = dispatch_tool("execute_sql", {"query": "SELECT count(*) as c FROM persons"})
        assert "rows" in ok_res
        assert ok_res["rows"][0]["c"] >= 770

        # 2. Blocked mutation
        bad_res = dispatch_tool("execute_sql", {"query": "DELETE FROM persons WHERE id = 1"})
        assert "error" in bad_res
        assert "strictly forbidden" in bad_res["error"]

    def test_reconstruct_speaker_tab_debater(self, agent):
        res = agent.ask("what is balishta's avg rank in Speaker tab")
        assert res.success is True
        assert res.intent == AgentIntent.RECONSTRUCT_SPEAKER_TAB.value
        assert "Balishta Wijesinghe" in res.answer
        assert "22.625" in res.answer
        assert "17.4" in res.answer
        assert "RIC ISDC 2026" in res.answer
        assert "(20 + 47 + 21 + 25 + 9 + 18 + 29 + 12) / 8 = 181 / 8 = 22.625" in res.answer

        # Also test without apostrophe ("balishtas")
        res_no_apos = agent.ask("what is balishtas avg rank in Speaker tab")
        assert res_no_apos.success is True
        assert res_no_apos.intent == AgentIntent.RECONSTRUCT_SPEAKER_TAB.value
        assert "Balishta Wijesinghe" in res_no_apos.answer
        assert "22.625" in res_no_apos.answer

    def test_reconstruct_speaker_tab_tournament_and_team_tab(self, agent):
        res_t = agent.ask("speaker tab for Henley 2026")
        assert res_t.success is True
        assert res_t.intent == AgentIntent.RECONSTRUCT_SPEAKER_TAB.value
        assert "Henley 2026" in res_t.answer
        assert "Savithru Liyanapathirana" in res_t.answer

        res_team = agent.ask("prelim team tab for RIC ISDC 2026")
        assert res_team.success is True
        assert res_team.intent == AgentIntent.RECONSTRUCT_TEAM_TAB.value
        assert "RIC ISDC 2026" in res_team.answer
        assert "DS A" in res_team.answer

