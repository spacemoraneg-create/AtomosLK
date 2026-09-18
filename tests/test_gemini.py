"""
Live Integration Tests for Gemini Cloud LLM Agent.
"""

import pytest
from atomos.config import get_gemini_api_key
from atomos.agent.gemini_agent import GeminiAgent
from atomos.agent.orchestrator import AtomosAgent

@pytest.mark.skipif(not get_gemini_api_key(), reason="GEMINI_API_KEY not configured")
class TestGeminiLiveAgent:
    @pytest.fixture
    def gemini_agent(self):
        agent = GeminiAgent()
        yield agent
        agent.close()

    def test_gemini_general_reasoning_no_tools(self, gemini_agent):
        res = gemini_agent.run("What is 1+1? Answer in 5 words.")
        assert res["success"] is True
        assert "2" in res["answer"] or "two" in res["answer"].lower()
        assert len(res["tool_calls"]) == 0

    def test_gemini_autonomous_tool_call(self, gemini_agent):
        res = gemini_agent.run("Who is Balishta Wijesinghe?")
        assert res["success"] is True
        assert len(res["tool_calls"]) > 0
        assert "D. S. Senanayake" in res["answer"] or "DS" in res["answer"]

    def test_atomos_agent_auto_gemini(self):
        agent = AtomosAgent(use_llm=True)
        res = agent.ask("what is 1+1")
        assert res.success is True
        assert res.intent == "GEMINI_LLM"
        assert "2" in res.answer
