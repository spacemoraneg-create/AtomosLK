"""
Atomos Debate Intelligence Agent Orchestrator

Executes multi-step reasoning, entity disambiguation, forensic data retrieval,
and analytical synthesis for natural language debate queries.
"""

from dataclasses import dataclass, field
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from atomos.agent.intent import AgentIntent, classify_intent
from atomos.database.connection import get_connection
from atomos.query import AtomosQuery
from atomos.tools import dispatch_tool


def fmt_val(v: Any, max_decimals: int = 3) -> str:
    """Universal Precision Rule: Do not round up, show up to 3 decimal places if exist."""
    if v is None:
        return "N/A"
    try:
        import math
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "N/A"
        if f % 1 == 0:
            return str(int(f))
        s = f"{f:.8f}"
        parts = s.split(".")
        dec = parts[1][:max_decimals].rstrip("0")
        return f"{parts[0]}.{dec}" if dec else parts[0]
    except (ValueError, TypeError):
        return str(v)


@dataclass
class AgentResult:
    query: str
    intent: str
    answer: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "answer": self.answer,
            "tool_calls": self.tool_calls,
            "data": self.data,
            "success": self.success,
            "error": self.error,
        }


class AtomosAgent:
    """
    AI debate analyst grounded in the Atomos database.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None, use_llm: Optional[bool] = None):
        self._conn = conn or get_connection()
        self._query_engine = AtomosQuery(self._conn)
        self._session_last_entity: Dict[str, str] = {}

        # Determine whether to use Cloud LLM (Gemini)
        from atomos.config import get_gemini_api_key
        has_key = bool(get_gemini_api_key())
        self._use_llm = has_key if use_llm is None else use_llm

        self._gemini_agent = None
        if self._use_llm and has_key:
            try:
                from atomos.agent.gemini_agent import GeminiAgent
                self._gemini_agent = GeminiAgent(query_engine=self._query_engine)
            except Exception:
                self._gemini_agent = None

    def reset_memory(self, session_id: Optional[str] = None):
        """Reset conversation memory in the underlying LLM agent."""
        if session_id:
            self._session_last_entity.pop(session_id, None)
        else:
            self._session_last_entity.clear()
        if self._gemini_agent:
            self._gemini_agent.reset_memory(session_id=session_id)

    @property
    def conversation_history(self) -> List[Dict[str, Any]]:
        """Return conversation history from LLM agent."""
        if self._gemini_agent:
            return self._gemini_agent.conversation_history
        return []

    def ask(self, query: str, session_id: str = "default") -> AgentResult:
        """Process a natural language question and return a structured AgentResult."""
        # 1. Prioritize Cloud LLM (Gemini) if active
        if self._use_llm and self._gemini_agent:
            try:
                g_res = self._gemini_agent.run(query, session_id=session_id)
                if g_res.get("success") and g_res.get("answer"):
                    for tc in g_res.get("tool_calls", []):
                        args = tc.get("args", {})
                        for k in ("identifier", "debater", "team_name"):
                            if args.get(k):
                                self._session_last_entity[session_id] = str(args[k])
                    return AgentResult(
                        query=query,
                        intent="GEMINI_LLM",
                        answer=g_res.get("answer", ""),
                        tool_calls=g_res.get("tool_calls", []),
                        data=g_res.get("data", {}),
                        success=True,
                    )
            except Exception:
                pass

        # 2. Local deterministic & reverse-engineering synthesis engine (grounded in atomos.db)
        from atomos.agent.prompts import is_off_topic_query, OFF_TOPIC_REFUSAL
        if is_off_topic_query(query):
            return AgentResult(
                query=query,
                intent="OFF_TOPIC_GUARD",
                answer=OFF_TOPIC_REFUSAL,
                tool_calls=[],
                success=True,
            )

        intent, params = classify_intent(query)
        tool_calls: List[Dict[str, Any]] = []

        # Resolve conversational pronouns ("his", "her", "their", "he", "she") from session context
        if not params.get("identifier") and session_id in self._session_last_entity:
            import re
            if re.search(r"\b(his|her|their|him|he|she)\b", query.lower()):
                params["identifier"] = self._session_last_entity[session_id]

        try:
            if intent == AgentIntent.GREETING:
                return self._handle_greeting(query, tool_calls)
            elif intent == AgentIntent.SYSTEM_IDENTITY:
                return self._handle_system_identity(query, tool_calls)
            elif intent == AgentIntent.HELP_CAPABILITIES:
                return self._handle_help(query, tool_calls)
            elif intent in (AgentIntent.GENERAL_CIRCUIT, AgentIntent.CIRCUIT_META):
                return self._handle_circuit_meta(query, tool_calls)
            elif intent == AgentIntent.RECONSTRUCT_SPEAKER_TAB:
                return self._handle_reconstructed_speaker_tab(query, params, tool_calls, session_id=session_id)
            elif intent == AgentIntent.RECONSTRUCT_TEAM_TAB:
                return self._handle_reconstructed_team_tab(query, params, tool_calls, session_id=session_id)
            elif intent == AgentIntent.ELO_ANALYSIS:
                return self._handle_elo_analysis(query, params, tool_calls, session_id=session_id)
            elif intent == AgentIntent.SUPERLATIVE_ROUND:
                return self._handle_superlative_round(query, params, tool_calls)
            elif intent == AgentIntent.SIDE_SPLIT:
                return self._handle_side_split(query, params, tool_calls)
            elif intent == AgentIntent.POSITION_ANALYSIS:
                return self._handle_position_analysis(query, params, tool_calls)
            elif intent == AgentIntent.OUTROUND_HISTORY:
                return self._handle_outrounds(query, params, tool_calls)
            elif intent == AgentIntent.ADJUDICATOR_LOOKUP:
                return self._handle_adjudicator_lookup(query, params, tool_calls)
            elif intent == AgentIntent.HEAD_TO_HEAD:
                return self._handle_head_to_head(query, params, tool_calls)
            elif intent == AgentIntent.MATH_DERIVATION:
                return self._handle_math_derivation(query, params, tool_calls)
            elif intent == AgentIntent.SPEAKER_RANKINGS:
                return self._handle_speaker_rankings(query, params, tool_calls)
            elif intent == AgentIntent.INSTITUTION_LEADERBOARD:
                return self._handle_institution_leaderboard(query, params, tool_calls)
            elif intent == AgentIntent.INSTITUTION_DOSSIER:
                return self._handle_institution_dossier(query, params, tool_calls)
            elif intent == AgentIntent.DEBATER_DOSSIER:
                res = self._handle_debater_dossier(query, params, tool_calls)
                if params.get("identifier"):
                    self._session_last_entity[session_id] = str(params["identifier"])
                return res
            elif intent == AgentIntent.MOTION_INTELLIGENCE:
                return self._handle_motion_intelligence(query, params, tool_calls)
            else:
                return self._handle_general_search(query, tool_calls, session_id=session_id)

        except Exception as exc:
            return AgentResult(
                query=query,
                intent=intent.value if isinstance(intent, AgentIntent) else str(intent),
                answer=f"**Error processing query:** {str(exc)}",
                tool_calls=tool_calls,
                success=False,
                error=str(exc)
            )

    # ------------------------------------------------------------------------
    # ENTITY RESOLUTION HELPERS
    # ------------------------------------------------------------------------

    def _resolve_debater(self, identifier: Any, tool_calls: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
        """Resolves an identifier or name into (person_id, canonical_name)."""
        if not identifier:
            return None, None
        
        # If pure integer
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            pid = int(identifier)
            cursor = self._conn.cursor()
            cursor.execute("SELECT canonical_name FROM persons WHERE id = ?", (pid,))
            row = cursor.fetchone()
            if row:
                return pid, row[0]
            return pid, f"Debater #{pid}"

        raw_str = str(identifier).strip()
        candidates = [raw_str]
        # Strip possessive 's or trailing s if missing apostrophe (e.g. "balishtas" -> "balishta")
        cleaned = raw_str.replace("’", "'")
        if cleaned.lower().endswith("'s"):
            candidates.append(cleaned[:-2].strip())
        elif cleaned.lower().endswith("s") and len(cleaned) > 4:
            candidates.append(cleaned[:-1].strip())

        for cand in candidates:
            tool_calls.append({"tool": "search_entities", "args": {"query": cand, "entity_types": ["debater"], "limit": 1}})
            matches = self._query_engine.search(cand, entity_types=["debater"], limit=1)
            if matches:
                pid = matches[0].get("person_id") or matches[0].get("id")
                name = matches[0].get("canonical_name") or matches[0].get("name")
                return pid, name

        return None, raw_str


    # ------------------------------------------------------------------------
    # CONVERSATIONAL & SYSTEM HANDLERS
    # ------------------------------------------------------------------------

    def _handle_greeting(self, query: str, tool_calls: List[Dict[str, Any]]) -> AgentResult:
        answer = (
            "### Hello! Welcome to Atomos Debate Intelligence\n\n"
            "I am Atomos. I combine the intelligence of Gemini 3.1 with the data of Atomos's proprietary database. I am designed to answer any and every debate statistics-based question—ask whatever you can think of, and I will answer with the most accurate information.\n\n"
            "Here are some examples of what you can ask me:\n"
            "- **Debater Performance**: *\"What was Balishta's best round?\"*, *\"What was his worst round?\"*, *\"How does Balishta perform on Gov vs Opp?\"*\n"
            "- **Head-to-Head**: *\"Balishta vs Navidhi\"*, *\"Compare Royal College and D. S. Senanayake College\"*\n"
            "- **Mathematical Proofs**: *\"Derive Balishta's speaker average step-by-step\"*\n"
            "- **Institutions**: *\"Top 10 schools by IPI\"*, *\"Tell me about Royal College\"*\n"
            "- **Circuit Trends**: *\"What are the most biased motions?\"*, *\"Who are the top 10 speakers?\"*\n\n"
            "What would you like to explore?"
        )
        return AgentResult(query=query, intent="GREETING", answer=answer, tool_calls=tool_calls)

    def _handle_system_identity(self, query: str, tool_calls: List[Dict[str, Any]]) -> AgentResult:
        cursor = self._conn.cursor()
        cursor.execute("SELECT count(*) FROM tournaments")
        n_t = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM persons")
        n_p = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM institutions")
        n_i = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM debates")
        n_d = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM speech_performances")
        n_s = cursor.fetchone()[0]

        answer = (
            f"### About Atomos\n\n"
            f"**Atomos** is a debate analytics and knowledge engine designed specifically for the Sri Lankan Schools Debating Circuit.\n\n"
            f"#### Live Database Scope:\n"
            f"- **Tournaments**: {n_t} national championships\n"
            f"- **Debaters**: {n_p} debaters and adjudicators\n"
            f"- **Institutions**: {n_i} schools and academies\n"
            f"- **Debates**: {n_d} contested debates\n"
            f"- **Speeches**: {n_s} individual scored speech performances\n\n"
            f"#### Core Principles:\n"
            f"1. **Zero-Hallucination**: Every stat, rank, score, motion, and win is strictly computed from atomic records.\n"
            f"2. **Unrounded Precision Regulation**: All numeric values preserve up to 5 decimal places max with zero premature rounding.\n"
            f"3. **Dual Regulation Support**: Prioritizes the New Standard Regulation (Cumulative Speech Average $\\sum S / N$) while providing the Legacy Regulation (Mean of Tournament Averages) in parallel."
        )
        return AgentResult(query=query, intent="SYSTEM_IDENTITY", answer=answer, tool_calls=tool_calls)

    def _handle_help(self, query: str, tool_calls: List[Dict[str, Any]]) -> AgentResult:
        answer = (
            "### Atomos Intelligence Capabilities & Query Guide\n\n"
            "You can query Atomos in plain English. Key analytical capabilities include:\n\n"
            "| Category | Example Query |\n"
            "| :--- | :--- |\n"
            "| **Extremes & Superlatives** | `balishta's best round`, `balishta's worst round`, `highest score in isdc` |\n"
            "| **Side Split (Gov vs Opp)** | `how does balishta perform on gov vs opp?`, `side bias for Royal College` |\n"
            "| **Position Analysis** | `what is balishta's performance by position?`, `balishta reply speeches` |\n"
            "| **Head-to-Head Clashes** | `balishta vs navidhi`, `compare Royal College and DS`, `RC A vs DS A` |\n"
            "| **Adjudicator Histories** | `who judged balishta when he scored his highest score?` |\n"
            "| **Outround Records** | `what motions did DS debate in outrounds?`, `outround results for Ananda` |\n"
            "| **Mathematical Derivations** | `derive balishta speaker average`, `show calculation for Vidath` |\n"
            "| **Leaderboards & Tabs** | `top 10 speakers`, `IPI leaderboard`, `top schools in Colombo` |\n"
            "| **Motion Intelligence** | `what are the hardest motions?`, `motions on economics` |\n"
            "| **Circuit Vitals** | `what tournaments are recorded?`, `database summary` |\n"
        )
        return AgentResult(query=query, intent="HELP_CAPABILITIES", answer=answer, tool_calls=tool_calls)

    def _handle_circuit_meta(self, query: str, tool_calls: List[Dict[str, Any]]) -> AgentResult:
        tool_calls.append({"tool": "get_circuit_summary", "args": {}})
        summary = self._query_engine.get_circuit_summary()

        cursor = self._conn.cursor()
        cursor.execute("SELECT id, name, year, scoring_scale, format FROM tournaments ORDER BY year DESC, id DESC")
        tournaments = cursor.fetchall()

        t_lines = "\n".join([f"- **{r[1]}** ({r[2]}) — Format: `{r[4]}`, Scale: `{r[3]}`" for r in tournaments])

        answer = (
            f"### National Circuit Macro Overview\n\n"
            f"- **Tournaments Tracked**: {summary.get('total_tournaments', 'N/A')}\n"
            f"- **Participating Debaters**: {summary.get('total_debaters', 'N/A')}\n"
            f"- **Active Institutions**: {summary.get('total_institutions', 'N/A')}\n"
            f"- **Contested Debates**: {summary.get('total_debates_debated', 'N/A')}\n"
            f"- **Scored Speeches**: {summary.get('total_valid_speeches', 'N/A')}\n"
            f"- **Circuit-Wide Side Balance**: Proposition Wins: {fmt_val(summary.get('overall_side_balance', {}).get('prop_win_pct'))}% vs Opposition Wins: {fmt_val(summary.get('overall_side_balance', {}).get('opp_win_pct'))}%\n\n"
            f"#### Tournaments in Database:\n{t_lines}"
        )
        return AgentResult(query=query, intent=AgentIntent.GENERAL_CIRCUIT.value, answer=answer, tool_calls=tool_calls, data=summary)

    # ------------------------------------------------------------------------
    # ANALYTICAL & PERFORMANCE HANDLERS
    # ------------------------------------------------------------------------

    def _handle_superlative_round(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", "")
        polarity = params.get("polarity", "best")
        order_dir = "DESC" if polarity == "best" else "ASC"
        order_word = "Best" if polarity == "best" else "Lowest-Scoring"

        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(
                query=query,
                intent="SUPERLATIVE_ROUND",
                answer=f"Could not locate debater '{identifier}' in the database to retrieve their {order_word.lower()} round.",
                tool_calls=tool_calls,
                success=False
            )

        sql = f"""
            SELECT 
                sp.total_score, sp.position, sp.side, sp.speech_type,
                r.name as round_name, r.round_type, r.motion,
                t.name as tournament_name, t.year,
                tm.name as speaker_team,
                opp_tm.name as opponent_team,
                b.winner_side, b.win_margin,
                b.adjudicator_raw_name
            FROM speech_performances sp
            JOIN rounds r ON sp.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN teams tm ON sp.team_id = tm.id
            JOIN debates d ON sp.debate_id = d.id
            LEFT JOIN teams opp_tm ON (CASE WHEN sp.side = 'Proposition' THEN d.opp_team_id ELSE d.prop_team_id END) = opp_tm.id
            LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
            WHERE sp.person_id = ? AND sp.speech_type = 'SUBSTANTIVE'
            ORDER BY sp.total_score {order_dir}
            LIMIT 5
        """
        tool_calls.append({"tool": "execute_sql", "args": {"query": f"Fetch substantive speeches for person_id={pid} order {order_dir} limit 5"}})
        cursor = self._conn.cursor()
        cursor.execute(sql, (pid,))
        rows = cursor.fetchall()

        if not rows:
            return AgentResult(
                query=query,
                intent="SUPERLATIVE_ROUND",
                answer=f"No substantive speech records found for **{name}**.",
                tool_calls=tool_calls,
                success=True
            )

        top = rows[0]
        score = fmt_val(top[0])
        pos = top[1]
        side = top[2]
        round_name = top[4]
        motion = top[6] or "Motion not recorded"
        tourn = top[7]
        speaker_team = top[9]
        opp_team = top[10] or "N/A"
        winner = top[11] or "N/A"
        margin = fmt_val(abs(top[12])) if top[12] is not None else "N/A"
        judge = top[13] or "Adjudicator not recorded"

        is_win = (winner == side)
        outcome_str = f"Won by {side} (Margin: {margin} pts)" if is_win else f"Won by Opponent ({winner})"

        # Table of top 3
        table_rows = []
        for i, r in enumerate(rows[:3], 1):
            table_rows.append(f"| #{i} | **{fmt_val(r[0])}** | {r[4]} | {r[7]} | {r[1]} on {r[2]} | {r[10] or 'N/A'} |")
        table_md = "\n".join(table_rows)

        # Debater profile for career stats
        prof = self._query_engine.get_debater(pid, compact=True)
        speech_avg = fmt_val(prof.get("speech_average") or prof.get("overall_substantive_avg"))
        leg_avg = fmt_val(prof.get("avg_of_avgs"))
        win_rate = fmt_val(prof.get("win_rate"))
        prelims = prof.get("prelim_rounds_debated") or len(rows)

        answer = (
            f"### {name}'s {order_word} Performance\n\n"
            f"{name}'s {order_word.lower()} individual substantive performance was in **{round_name}** at **{tourn}**:\n\n"
            f"- **Score**: **{score}** pts\n"
            f"- **Speaker Position & Side**: {pos} Speaker on **{side}**\n"
            f"- **Team**: {speaker_team} (debating against **{opp_team}**)\n"
            f"- **Debate Outcome**: {outcome_str}\n"
            f"- **Motion**: *\"{motion}\"*\n"
            f"- **Chair Adjudicator**: {judge}\n\n"
            f"#### Performance Rankings:\n"
            f"| Rank | Score | Round | Tournament | Position | Opponent |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n\n"
            f"*(Career Context: {prelims} qualifying prelim speeches | Cumulative Speech Avg: **{speech_avg} pts** | Legacy Mean: {leg_avg} pts | Win Rate: **{win_rate}%**)*"
        )
        return AgentResult(query=query, intent="SUPERLATIVE_ROUND", answer=answer, tool_calls=tool_calls, data={"rows": rows})

    def _handle_side_split(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", "")
        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(
                query=query,
                intent="SIDE_SPLIT",
                answer=f"Could not locate debater '{identifier}' in the database to analyze side performance.",
                tool_calls=tool_calls,
                success=False
            )

        sql = """
            SELECT 
                sp.side,
                COUNT(sp.id) as speech_count,
                SUM(sp.total_score) as total_points,
                AVG(sp.total_score) as avg_score,
                SUM(CASE WHEN (sp.side = 'Proposition' AND b.winner_side = 'Proposition') OR (sp.side = 'Opposition' AND b.winner_side = 'Opposition') THEN 1 ELSE 0 END) as wins,
                COUNT(DISTINCT sp.debate_id) as total_debates
            FROM speech_performances sp
            LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
            WHERE sp.person_id = ? AND sp.speech_type = 'SUBSTANTIVE'
            GROUP BY sp.side
        """
        tool_calls.append({"tool": "execute_sql", "args": {"query": f"Side split for person_id={pid}"}})
        cursor = self._conn.cursor()
        cursor.execute(sql, (pid,))
        rows = cursor.fetchall()

        stats_by_side = {r[0]: r for r in rows}
        prop = stats_by_side.get("Proposition", ("Proposition", 0, 0, 0, 0, 0))
        opp = stats_by_side.get("Opposition", ("Opposition", 0, 0, 0, 0, 0))

        prop_wr = (prop[4] / prop[5] * 100) if prop[5] > 0 else 0
        opp_wr = (opp[4] / opp[5] * 100) if opp[5] > 0 else 0

        score_diff = opp[3] - prop[3]
        wr_diff = opp_wr - prop_wr

        if score_diff > 0:
            lean_str = f"**{name}** achieves higher substantive scores on **Opposition** (+{fmt_val(score_diff)} pts higher average) with a **{fmt_val(wr_diff)}%** higher win rate."
        elif score_diff < 0:
            lean_str = f"**{name}** achieves higher substantive scores on **Proposition** (+{fmt_val(abs(score_diff))} pts higher average) with a **{fmt_val(abs(wr_diff))}%** higher win rate."
        else:
            lean_str = f"**{name}** maintains identical scoring averages across both Proposition and Opposition."

        answer = (
            f"### Side Performance Breakdown: {name}\n\n"
            f"{lean_str}\n\n"
            f"| Metric | Proposition (Gov) | Opposition (Opp) | Differential |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **Substantive Speeches** | {prop[1]} | {opp[1]} | {opp[1] - prop[1]} |\n"
            f"| **Average Score** | **{fmt_val(prop[3])}** pts | **{fmt_val(opp[3])}** pts | **{'+' if score_diff > 0 else ''}{fmt_val(score_diff)}** pts |\n"
            f"| **Debates Contested** | {prop[5]} | {opp[5]} | {opp[5] - prop[5]} |\n"
            f"| **Debates Won** | {prop[4]} | {opp[4]} | {opp[4] - prop[4]} |\n"
            f"| **Side Win Rate** | **{fmt_val(prop_wr)}%** | **{fmt_val(opp_wr)}%** | **{'+' if wr_diff > 0 else ''}{fmt_val(wr_diff)}%** |\n"
        )
        return AgentResult(query=query, intent="SIDE_SPLIT", answer=answer, tool_calls=tool_calls, data={"prop": prop, "opp": opp})

    def _handle_position_analysis(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", "")
        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(
                query=query,
                intent="POSITION_ANALYSIS",
                answer=f"Could not locate debater '{identifier}' in the database.",
                tool_calls=tool_calls,
                success=False
            )

        sql = """
            SELECT 
                sp.position, sp.speech_type,
                COUNT(sp.id) as speech_count,
                SUM(sp.total_score) as total_points,
                AVG(sp.total_score) as avg_score
            FROM speech_performances sp
            WHERE sp.person_id = ?
            GROUP BY sp.position, sp.speech_type
            ORDER BY sp.speech_type, sp.position
        """
        tool_calls.append({"tool": "execute_sql", "args": {"query": f"Position breakdown for person_id={pid}"}})
        cursor = self._conn.cursor()
        cursor.execute(sql, (pid,))
        rows = cursor.fetchall()

        table_rows = []
        for r in rows:
            pos_label = f"{r[0]} ({r[1].capitalize()})"
            table_rows.append(f"| **{pos_label}** | {r[2]} | **{fmt_val(r[4])}** pts | {fmt_val(r[3])} |")
        table_md = "\n".join(table_rows)

        answer = (
            f"### Speaker Position Breakdown: {name}\n\n"
            f"| Position | Speeches Delivered | Average Score | Total Points |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="POSITION_ANALYSIS", answer=answer, tool_calls=tool_calls, data={"rows": rows})

    def _handle_outrounds(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", "")
        cursor = self._conn.cursor()

        sql = """
            SELECT 
                t.name as tournament,
                r.name as round_name,
                pt.name as prop_team,
                ot.name as opp_team,
                r.motion,
                b.winner_side,
                b.win_margin
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            LEFT JOIN teams pt ON d.prop_team_id = pt.id
            LEFT JOIN teams ot ON d.opp_team_id = ot.id
            LEFT JOIN adjudicator_ballots b ON b.debate_id = d.id
            WHERE r.round_type = 'ELIMINATION'
              AND (pt.name LIKE ? OR ot.name LIKE ? OR t.name LIKE ?)
            ORDER BY t.year DESC, r.round_number ASC
            LIMIT 15
        """
        pattern = f"%{identifier}%" if identifier else "%"
        tool_calls.append({"tool": "execute_sql", "args": {"query": f"Outround history for '{identifier}'"}})
        cursor.execute(sql, (pattern, pattern, pattern))
        rows = cursor.fetchall()

        if not rows:
            return AgentResult(
                query=query,
                intent="OUTROUND_HISTORY",
                answer=f"No elimination outround debates located matching '{identifier}'.",
                tool_calls=tool_calls,
                success=True
            )

        lines = []
        for r in rows:
            prop = r[2] or "N/A"
            opp = r[3] or "N/A"
            motion = r[4] or "Motion not recorded"
            winner = r[5] or "N/A"
            margin = f" (Margin: {fmt_val(abs(r[6]))} pts)" if r[6] is not None else ""
            lines.append(f"- **{r[1]}** at *{r[0]}*: **{prop}** (Prop) vs **{opp}** (Opp) -> Winner: **{winner}**{margin}\n  - *Motion*: \"{motion}\"")
        debate_list = "\n".join(lines)

        answer = (
            f"### Elimination Outround History: {identifier or 'Circuit-Wide'}\n\n"
            f"Found **{len(rows)}** outround match records:\n\n"
            f"{debate_list}"
        )
        return AgentResult(query=query, intent="OUTROUND_HISTORY", answer=answer, tool_calls=tool_calls, data={"rows": rows})

    def _handle_adjudicator_lookup(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", "")
        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(
                query=query,
                intent="ADJUDICATOR_LOOKUP",
                answer=f"Could not locate debater '{identifier}' to look up adjudicator history.",
                tool_calls=tool_calls,
                success=False
            )

        if params.get("for_best", False):
            sql = """
                SELECT 
                    sp.total_score, r.name as round_name, t.name as tournament_name,
                    b.adjudicator_raw_name, b.adjudicator_institution, r.motion
                FROM speech_performances sp
                JOIN rounds r ON sp.round_id = r.id
                JOIN tournaments t ON r.tournament_id = t.id
                LEFT JOIN adjudicator_ballots b ON sp.ballot_id = b.id
                WHERE sp.person_id = ? AND sp.speech_type = 'SUBSTANTIVE'
                ORDER BY sp.total_score DESC
                LIMIT 1
            """
            cursor = self._conn.cursor()
            cursor.execute(sql, (pid,))
            row = cursor.fetchone()
            if row:
                score = fmt_val(row[0])
                r_name = row[1]
                t_name = row[2]
                judge = row[3] or "Adjudicator not recorded"
                inst = f" ({row[4]})" if row[4] else ""
                motion = row[5] or "N/A"
                answer = (
                    f"### Adjudicator for {name}'s Highest Score\n\n"
                    f"When **{name}** achieved their highest substantive score of **{score}** pts (in **{r_name}** of **{t_name}**), the chair adjudicator was:\n\n"
                    f"**{judge}**{inst}\n\n"
                    f"- **Motion**: *\"{motion}\"*\n"
                )
                return AgentResult(query=query, intent="ADJUDICATOR_LOOKUP", answer=answer, tool_calls=tool_calls)

        # General adjudicators who judged this debater via dedicated query engine
        tool_calls.append({"tool": "get_debater_adjudicator_record", "args": {"debater": name}})
        adj_record = self._query_engine.get_debater_adjudicator_record(name)
        if "error" in adj_record or not adj_record.get("judges_summary"):
            return AgentResult(
                query=query,
                intent="ADJUDICATOR_LOOKUP",
                answer=f"No adjudicator clash history found for {name}.",
                tool_calls=tool_calls,
                success=True
            )

        table_rows = []
        for s in adj_record["judges_summary"][:10]:
            avg_str = f"**{fmt_val(s['average_score_awarded'])}** pts" if s["average_score_awarded"] is not None else "--"
            table_rows.append(
                f"| **{s['adjudicator']}** | {s['debates_judged']} | {s['wins']} - {s['losses']} ({s['win_percentage']}%) | {avg_str} | {', '.join(s['tournaments'])} |"
            )
        table_md = "\n".join(table_rows)

        answer = (
            f"### Official Adjudicator Record for {name}\n\n"
            f"| Adjudicator | Debates Judged | Record (Win - Loss) | Avg Score | Tournaments |\n"
            f"| :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="ADJUDICATOR_LOOKUP", answer=answer, tool_calls=tool_calls, data=adj_record)

    # ------------------------------------------------------------------------
    # COMPARISON & CLASH HANDLERS
    # ------------------------------------------------------------------------

    def _handle_head_to_head(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        ea = params.get("entity_a", "")
        eb = params.get("entity_b", "")

        tool_calls.append({"tool": "get_head_to_head", "args": {"entity_a": ea, "entity_b": eb, "mode": "auto"}})
        data = self._query_engine.get_head_to_head(ea, eb, mode="auto")

        if "error" in data:
            return AgentResult(
                query=query,
                intent="HEAD_TO_HEAD",
                answer=f"**Head-to-Head Clash Error:** {data['error']}",
                tool_calls=tool_calls,
                success=False,
                error=data["error"]
            )

        name_a = data.get("entity_a", ea)
        name_b = data.get("entity_b", eb)
        summary = data.get("summary", {})
        comp_type = data.get("comparison_type", "debater")

        # Debater comparison breakdown
        if comp_type == "debater":
            da = data.get("debater_a") or {}
            db = data.get("debater_b") or {}
            name_a = da.get("canonical_name", ea)
            name_b = db.get("canonical_name", eb)
            inst_a = da.get("institution") or "Independent"
            inst_b = db.get("institution") or "Independent"
            a_direct_wins = data.get("a_direct_wins", 0)
            b_direct_wins = data.get("b_direct_wins", 0)
            direct_record = f"{name_a} {a_direct_wins} - {b_direct_wins} {name_b}"
            common_opponents = data.get("common_opponents", [])

            c_avg_a = fmt_val(da.get("speech_average") if da.get("speech_average") is not None else da.get("overall_substantive_avg"))
            c_avg_b = fmt_val(db.get("speech_average") if db.get("speech_average") is not None else db.get("overall_substantive_avg"))
            l_avg_a = fmt_val(da.get("avg_of_avgs"))
            l_avg_b = fmt_val(db.get("avg_of_avgs"))

            rank_a = f"#{da.get('master_tab_rank')}" if da.get("master_tab_rank") else "Unranked"
            rank_b = f"#{db.get('master_tab_rank')}" if db.get("master_tab_rank") else "Unranked"

            wr_a = fmt_val(da.get("win_rate"))
            wr_b = fmt_val(db.get("win_rate"))
            br_a = fmt_val(da.get("break_rate"))
            br_b = fmt_val(db.get("break_rate"))
            dev_a = fmt_val(da.get("avg_of_deviations"))
            dev_b = fmt_val(db.get("avg_of_deviations"))
            rep_a = fmt_val(da.get("reply_average"))
            rep_b = fmt_val(db.get("reply_average"))

            answer = (
                f"### Head-to-Head Clash: **{name_a}** vs. **{name_b}**\n\n"
                f"- **Schools**: {inst_a} vs. {inst_b}\n"
                f"- **Direct Match Record**: `{direct_record}`\n\n"
                f"#### Side-by-Side Standings\n"
                f"| Metric | {name_a} | {name_b} |\n"
                f"| :--- | :--- | :--- |\n"
                f"| **Master Tab Rank** | {rank_a} | {rank_b} |\n"
                f"| **Cumulative Speech Avg (New Standard)** | **{c_avg_a} pts** | **{c_avg_b} pts** |\n"
                f"| **Mean of Tournament Avgs (Legacy)** | {l_avg_a} pts | {l_avg_b} pts |\n"
                f"| **Win Rate** | **{wr_a}%** | **{wr_b}%** |\n"
                f"| **Break Rate** | **{br_a}%** | **{br_b}%** |\n"
                f"| **Consistency Deviation (σ)** | {dev_a} pts | {dev_b} pts |\n"
                f"| **Reply Tab Average** | {rep_a} | {rep_b} |\n\n"
                f"#### Mutual Rival Performance ({len(common_opponents)} Common Opponents)\n"
                f"Both parties have contested matches against {len(common_opponents)} mutual rivals across the circuit."
            )
        elif comp_type == "school":
            ia = data.get("inst_a") or {}
            ib = data.get("inst_b") or {}
            name_a = ia.get("name", ea)
            name_b = ib.get("name", eb)
            a_direct_wins = data.get("a_direct_wins", 0)
            b_direct_wins = data.get("b_direct_wins", 0)
            direct_record = f"{name_a} {a_direct_wins} - {b_direct_wins} {name_b}"
            common_rivals = data.get("common_rivals", [])
            total_debates = len(data.get("direct_debates", []))
            margin_a = fmt_val(data.get("a_direct_margin_avg"))

            answer = (
                f"### Institutional Head-to-Head: **{name_a}** vs. **{name_b}**\n\n"
                f"- **Direct Institutional Record**: `{direct_record}`\n"
                f"- **Total Contested Clashes**: {total_debates}\n"
                f"- **Average Margin**: {margin_a} pts\n\n"
                f"#### Mutual Common Rivals: {len(common_rivals)} mutual rivals."
            )
        else:
            name_a = data.get("team_a_name", ea)
            name_b = data.get("team_b_name", eb)
            inst_a = data.get("institution_a", "N/A")
            inst_b = data.get("institution_b", "N/A")
            a_direct_wins = data.get("a_direct_wins", 0)
            b_direct_wins = data.get("b_direct_wins", 0)
            direct_record = f"{name_a} {a_direct_wins} - {b_direct_wins} {name_b}"
            total_debates = len(data.get("direct_debates", []))
            margin_a = fmt_val(data.get("a_direct_margin_avg"))

            answer = (
                f"### Team Head-to-Head: **{name_a}** ({inst_a}) vs. **{name_b}** ({inst_b})\n\n"
                f"- **Direct Match Record**: `{direct_record}`\n"
                f"- **Total Contested Clashes**: {total_debates}\n"
                f"- **Average Margin**: {margin_a} pts"
            )

        return AgentResult(query=query, intent="HEAD_TO_HEAD", answer=answer, tool_calls=tool_calls, data=data)

    # ------------------------------------------------------------------------
    # STANDARD ANALYTICAL WRAPPERS
    # ------------------------------------------------------------------------

    def _handle_math_derivation(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        identifier = params.get("identifier", query)
        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(
                query=query,
                intent="MATH_DERIVATION",
                answer=f"Could not locate debater '{identifier}' in the database to derive speaker average.",
                tool_calls=tool_calls,
                success=False
            )

        tool_calls.append({"tool": "get_debater_profile", "args": {"identifier": pid, "compact": False}})
        data = self._query_engine.get_debater(pid, compact=False)
        if "error" in data:
            return AgentResult(query=query, intent="MATH_DERIVATION", answer=f"Error: {data['error']}", tool_calls=tool_calls, success=False)

        name = data.get("canonical_name", f"Debater #{pid}")
        d_text = data.get("derivation_text")

        if d_text:
            answer = f"```text\n{d_text}\n```"
        else:
            answer = (
                f"### Mathematical Derivation: {name}\n\n"
                f"- **Cumulative Speech Average (New Standard)**: **{fmt_val(data.get('speech_average'))} pts**\n"
                f"- **Mean of Tournament Averages (Legacy)**: {fmt_val(data.get('avg_of_avgs'))} pts\n"
            )

        return AgentResult(query=query, intent="MATH_DERIVATION", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_speaker_rankings(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        limit = params.get("limit", 15)
        tool_calls.append({"tool": "get_master_speaker_tab", "args": {"limit": limit}})
        
        master_tab = self._query_engine._master_engine.get_master_speaker_tab()
        top_speakers = master_tab[:limit]

        rows = []
        for i, s in enumerate(top_speakers, 1):
            s_name = s.get("speaker_name") or s.get("name", "Unknown")
            inst_name = s.get("institution_name") or s.get("institution", "Independent")
            cum_avg = fmt_val(s.get("cumulative_speech_avg") or s.get("speech_average"))
            leg_avg = fmt_val(s.get("avg_of_avgs"))
            rnds = s.get("total_rounds", 0)
            peak = fmt_val(s.get("peak_score"))
            rows.append(
                f"| #{i} | **{s_name}** | {inst_name} | "
                f"**{cum_avg} pts** | {leg_avg} pts | {rnds} | {peak} pts |"
            )
        table_md = "\n".join(rows)

        answer = (
            f"### National Speaker Tab — Top {limit} Debaters\n\n"
            f"| Rank | Speaker | Institution | Cumulative Avg (New) | Legacy Avg | Prelims | Peak Score |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="SPEAKER_RANKINGS", answer=answer, tool_calls=tool_calls, data={"speakers": top_speakers})

    def _handle_institution_leaderboard(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        top_n = params.get("top_n", 20)
        is_ipi = "ipi" in query.lower()
        sort_by = "ipi" if is_ipi else "delta"
        tool_calls.append({"tool": "get_institutional_leaderboard", "args": {"min_debates": 5, "sort_by": sort_by}})
        board = self._query_engine.get_institutional_leaderboard(min_debates=5, sort_by=sort_by)[:top_n]

        if is_ipi:
            rows = []
            for i, inst in enumerate(board, 1):
                ipi = fmt_val(inst.get("ipi"))
                wr = fmt_val(inst.get("win_rate"))
                atss = fmt_val(inst.get("atss"))
                brk_cnt = inst.get("breaks_count", 0)
                fld = inst.get("teams_fielded", 1)
                brk_pct = fmt_val((brk_cnt / fld * 100) if fld > 0 else 0)
                rows.append(
                    f"| #{i} | **{inst['name']}** ({inst.get('code', 'N/A')}) | **{ipi}** | "
                    f"{wr}% | {atss} | {brk_pct}% |"
                )
            table_md = "\n".join(rows)

            answer = (
                f"### National Institutional Power Index (IPI) Leaderboard\n\n"
                f"| Rank | Institution | IPI Rating | Win Rate | ATSS | Break Rate |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                f"{table_md}\n"
            )
        else:
            rows = []
            for i, inst in enumerate(board, 1):
                delta = fmt_val(inst.get("delta"))
                a_atss = fmt_val(inst.get("a_atss"))
                b_atss = fmt_val(inst.get("b_atss")) if inst.get("b_atss") is not None else "-"
                diff = f"{inst['net_diff']:+.2f}" if inst.get("net_diff") is not None else "-"
                brk = f"{inst.get('break_percentage', 0):.1f}%"
                ach = inst.get("highest_break", "-")
                rows.append(
                    f"| #{i} | **{inst['name']}** ({inst.get('code', 'N/A')}) | **{delta}** | "
                    f"{a_atss} | {b_atss} | {diff} | {brk} | {ach} |"
                )
            table_md = "\n".join(rows)

            answer = (
                f"### National Institutional Delta Leaderboard\n\n"
                f"| Rank | School | Delta | A Team ATSS | B Team ATSS | Net Diff | Break % | Highest Achievement |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
                f"{table_md}\n"
            )
        return AgentResult(query=query, intent="INSTITUTION_LEADERBOARD", answer=answer, tool_calls=tool_calls, data={"leaderboard": board})

    def _handle_institution_dossier(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        school = params.get("school", query)
        tool_calls.append({"tool": "search_entities", "args": {"query": school, "entity_types": ["institution"], "limit": 1}})
        matches = self._query_engine.search(school, entity_types=["institution"], limit=1)

        if not matches:
            return AgentResult(query=query, intent="INSTITUTION_DOSSIER", answer=f"Could not locate institution matching '{school}'.", tool_calls=tool_calls, success=False)

        inst_id = matches[0].get("institution_id") or matches[0].get("id")
        tool_calls.append({"tool": "get_institution_profile", "args": {"institution_id": inst_id}})
        inst_prof = self._query_engine._inst_engine.get_institution_profile(inst_id)

        spk_lines = "\n".join([
            f"- **{td.name}**: National Rank #{td.national_rank or 'N/A'} | Master Score: **{fmt_val(td.master_score)} pts** ({td.total_rounds} prelims)"
            for td in inst_prof.top_debaters[:5]
        ])

        answer = (
            f"### Institution Profile: **{inst_prof.name}** ({inst_prof.code or 'N/A'})\n\n"
            f"- **National IPI Score**: **{fmt_val(inst_prof.ipi_score)}** (National Rank: #{inst_prof.ipi_rank or 'N/A'}, Tier: `{inst_prof.tier}`)\n"
            f"- **Circuit Win Rate**: **{fmt_val(inst_prof.win_rate)}%** ({inst_prof.wins} / {inst_prof.total_debates} debates)\n"
            f"- **Outround Break Rate**: **{fmt_val(inst_prof.break_rate)}%** ({inst_prof.total_breaks} breaks across {inst_prof.tournaments_entered} tournaments)\n"
            f"- **Average Team Speaker Score (ATSS)**: **{fmt_val(inst_prof.atss)}** pts\n"
            f"- **Squad Volume**: {inst_prof.debater_count} unique debaters fielded across {inst_prof.tournaments_entered} tournaments\n\n"
            f"#### Top Substantive Speakers:\n{spk_lines or 'None recorded'}"
        )
        return AgentResult(query=query, intent="INSTITUTION_DOSSIER", answer=answer, tool_calls=tool_calls, data={"name": inst_prof.name})

    def _handle_debater_dossier(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]], session_id: str = "default") -> AgentResult:
        identifier = params.get("identifier", query)
        pid, name = self._resolve_debater(identifier, tool_calls)

        if not pid:
            return AgentResult(query=query, intent="DEBATER_DOSSIER", answer=f"Could not locate debater '{identifier}' in the database.", tool_calls=tool_calls, success=False)

        self._session_last_entity[session_id] = name
        tool_calls.append({"tool": "get_debater_profile", "args": {"identifier": pid, "compact": False}})
        data = self._query_engine.get_debater(pid, compact=False)

        if "error" in data:
            return AgentResult(query=query, intent="DEBATER_DOSSIER", answer=f"Error: {data['error']}", tool_calls=tool_calls, success=False)

        name = data.get("canonical_name", f"Debater #{pid}")
        inst = data.get("institution", "Independent")
        mt_rank = f"#{data['master_tab_rank']}" if data.get("master_tab_rank") else "Unranked"
        cs_rank = f"#{data['critical_stats_rank']}" if data.get("critical_stats_rank") else "Unranked"

        new_avg = fmt_val(data.get("speech_average") or data.get("overall_substantive_avg"))
        leg_avg = fmt_val(data.get("avg_of_avgs"))
        win_rate = fmt_val(data.get("win_rate"))
        brk_rate = fmt_val(data.get("break_rate"))
        consistency = fmt_val(data.get("avg_of_deviations"))
        reply_avg = fmt_val(data.get("reply_average"))
        reply_cnt = data.get("reply_speech_count", 0)
        avg_sp_rank = fmt_val(data.get("avg_speaker_tab_rank")) if data.get("avg_speaker_tab_rank") is not None else "N/A"
        avg_sp_rank_full = fmt_val(data.get("avg_speaker_tab_rank_full_prelims")) if data.get("avg_speaker_tab_rank_full_prelims") is not None else "N/A"

        tournaments = data.get("tournaments", [])
        tourn_rows = []
        for t in tournaments:
            r_avg = f"#{t['speaker_tab_rank_avg']} / {t['eligible_speakers']}" if t.get("speaker_tab_rank_avg") else "--"
            r_tot = f"#{t['speaker_tab_rank_total']} / {t['total_speakers']}" if t.get("speaker_tab_rank_total") else "--"
            tourn_rows.append(
                f"| **{t['tournament_name']}** | **{fmt_val(t.get('tournament_average'))} pts** | "
                f"{fmt_val(t.get('total_points'))} pts | {len(t.get('prelim_substantive_scores', []))}/{t.get('max_prelims', 5)} | "
                f"**{r_avg}** | {r_tot} |"
            )
        tourn_md = "\n".join(tourn_rows)

        answer = (
            f"### Debater Profile: **{name}** (Person ID: `#{pid}`)\n\n"
            f"- **Institution / School**: {inst}\n"
            f"- **Teams Fielded**: {', '.join(data.get('teams_debated', [])) or 'None'}\n"
            f"- **Master Tab Rank**: **{mt_rank}** (Critical Stats Rank: **{cs_rank}**)\n"
            f"- **Cumulative Speech Avg (New Standard)**: **{new_avg} pts**\n"
            f"- **Mean of Tournament Avgs (Legacy)**: **{leg_avg} pts**\n"
            f"- **Career Avg Speaker Tab Rank (WSDC Qualifying >=3 Prelims)**: **{avg_sp_rank}**\n"
            f"- **Career Avg Speaker Tab Rank (Tabbycat Full Prelims)**: **{avg_sp_rank_full}**\n"
            f"- **Win Rate**: **{win_rate}%** ({data.get('wins_debated', 0)} wins / {data.get('total_debates', 0)} debates)\n"
            f"- **Break Rate**: **{brk_rate}%** ({data.get('eligible_tournaments_count', 0)} eligible tournaments)\n"
            f"- **Consistency Deviation (σ)**: {consistency} pts\n"
            f"- **Reply Tab Average**: {reply_avg} ({reply_cnt} replies)\n\n"
            f"#### Tournament Campaigns & Reconstructed Speaker Tab Ranks ({len(tournaments)} Tracked):\n"
            f"| Tournament | Substantive Avg | Total Pts | Prelims | Speaker Tab Rank (by Avg) | Speaker Tab Rank (by Total) |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{tourn_md}\n"
        )
        return AgentResult(query=query, intent="DEBATER_DOSSIER", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_reconstructed_speaker_tab(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]], session_id: str = "default") -> AgentResult:
        identifier = params.get("identifier")
        tournament = params.get("tournament")
        mode = params.get("mode", "auto")

        # Resolve pronouns ("his", "her", "their") from session memory if needed
        if not identifier and mode == "debater":
            identifier = self._session_last_entity.get(session_id)

        # If identifier is not extracted by regex, attempt to resolve from the query text
        if not identifier and not tournament and mode != "circuit":
            pid, resolved_name = self._resolve_debater(query, tool_calls)
            if pid:
                identifier = resolved_name
                mode = "debater"

        if (mode == "tournament" or (tournament and not identifier)) and tournament:
            tool_calls.append({"tool": "reconstruct_speaker_tab", "args": {"tournament": tournament, "limit": 25}})
            data = self._query_engine.reconstruct_speaker_tab(tournament=tournament, limit=25)
            if "error" in data:
                return AgentResult(query=query, intent="RECONSTRUCT_SPEAKER_TAB", answer=f"Error: {data['error']}", tool_calls=tool_calls, success=False)

            t_name = data.get("tournament_name", tournament)
            rows = []
            for s in data.get("top_by_wsdc_average", [])[:25]:
                r_scores_dict = s.get("round_scores") or {}
                scores_csv = ", ".join(f"{k}: {fmt_val(v)}" for k, v in r_scores_dict.items())
                rows.append(
                    f"| **#{s['rank_by_avg_eligible']}** | #{s['rank_by_total_points']} | **{s['speaker_name']}** | {s['institution']} | "
                    f"{s.get('team_name') or '-'} | **{fmt_val(s['tournament_average'])} pts** | {fmt_val(s['total_points'])} pts | "
                    f"{s['prelims_spoken']}/{s['max_prelims']} | `{scores_csv}` |"
                )
            table_md = "\n".join(rows)
            answer = (
                f"### Reconstructed Tournament Speaker Tab: **{t_name}**\n\n"
                f"- **Eligible Speakers (>=3 Prelims)**: {data.get('eligible_speakers', 0)} (Total Speakers: {data.get('total_speakers', 0)})\n"
                f"- **Scheduled Preliminary Rounds**: {data.get('max_prelims', 5)}\n\n"
                f"| Rank (Avg) | Rank (Total) | Speaker | Institution | Team | Substantive Avg | Total Points | Prelims | Scores |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
                f"{table_md}\n"
            )
            return AgentResult(query=query, intent="RECONSTRUCT_SPEAKER_TAB", answer=answer, tool_calls=tool_calls, data=data)

        if identifier:
            pid, name = self._resolve_debater(str(identifier), tool_calls)
            if pid:
                self._session_last_entity[session_id] = name
                tool_calls.append({"tool": "reconstruct_speaker_tab", "args": {"identifier": pid, "tournament": tournament}})
                data = self._query_engine.reconstruct_speaker_tab(identifier=pid, tournament=tournament)
                if "error" not in data:
                    t_rows = []
                    for r in data.get("tournaments", []):
                        r_avg_val = r.get("rank_by_avg_eligible")
                        r_avg_str = f"**#{r_avg_val}** / {r['eligible_speakers']}" if r_avg_val is not None else "Ineligible (<3 Rds)"
                        r_tot_str = f"**#{r['rank_by_total_points']}** / {r['total_speakers']}"
                        full_badge = "Full Prelims" if r.get("spoke_all_prelims") else ("Qualifying (>=3)" if r.get("is_eligible") else "Sub-threshold (<3)")
                        scores_list = r.get("round_scores") or []
                        scores_csv = ", ".join(f"R{sc['round']}: {fmt_val(sc['score'])}" for sc in scores_list)
                        t_rows.append(
                            f"| **{r['tournament_name']}** | {r.get('team_name') or '-'} | {r['prelims_spoken']}/{r['max_prelims']} ({full_badge}) | "
                            f"**{fmt_val(r['tournament_average'])} pts** | {fmt_val(r['total_points'])} pts | {r_avg_str} | {r_tot_str} | `{scores_csv}` |"
                        )
                    t_md = "\n".join(t_rows)

                    avg_wsdc = fmt_val(data.get("avg_rank_by_avg_eligible"))
                    avg_full_tot = fmt_val(data.get("avg_rank_by_total_full_prelims"))
                    avg_full_avg = fmt_val(data.get("avg_rank_by_avg_full_prelims"))
                    avg_elig_tot = fmt_val(data.get("avg_rank_by_total_eligible"))
                    avg_all_tot = fmt_val(data.get("avg_rank_by_total_all"))

                    best_avg_obj = data.get("best_rank_by_avg") or {}
                    best_tot_obj = data.get("best_rank_by_total") or {}
                    best_avg_str = f"#{best_avg_obj['rank']} ({best_avg_obj['tournament_name']})" if best_avg_obj.get("rank") else "N/A"
                    best_tot_str = f"#{best_tot_obj['rank']} ({best_tot_obj['tournament_name']})" if best_tot_obj.get("rank") else "N/A"

                    answer = (
                        f"### Reconstructed Speaker Tab Rank Analysis: **{data.get('canonical_name', name)}** ({data.get('institution', 'Independent')})\n\n"
                        f"Speaker tabs are reverse-engineered directly from all raw preliminary substantive speeches (`speech_performances`) across every tournament in the database.\n\n"
                        f"#### Career Average Speaker Tab Rank Summary\n"
                        f"| Methodology | Career Avg Speaker Tab Rank | Best Rank | Exact Arithmetic Derivation |\n"
                        f"| :--- | :--- | :--- | :--- |\n"
                        f"| **1. WSDC Qualifying Speaker Tab (Ranked by Avg Score, >=3 Prelims)** | **{avg_wsdc}** | {best_avg_str} | `{data.get('derivation_avg_eligible') or 'N/A'}` |\n"
                        f"| **2. Tabbycat Full-Prelim Speaker Tab (Ranked by Total Points, 100% Prelims Spoken)** | **{avg_full_tot}** | {best_tot_str} | `{data.get('derivation_total_full_prelims') or 'N/A'}` |\n"
                        f"| **3. Full-Prelim Speaker Tab (Ranked by Average Score, 100% Prelims Spoken)** | **{avg_full_avg}** | {best_avg_str} | `{data.get('derivation_avg_full_prelims') or 'N/A'}` |\n"
                        f"| **4. All Qualifying Tournaments (>=3 Prelims, Ranked by Total Points)** | **{avg_elig_tot}** | {best_tot_str} | `{data.get('derivation_total_eligible') or 'N/A'}` |\n"
                        f"| **5. All Tournaments Attended (Including 1-Round Appearances, by Total Points)** | **{avg_all_tot}** | {best_tot_str} | `{data.get('derivation_total_all') or 'N/A'}` |\n\n"
                        f"#### Tournament-by-Tournament Reconstructed Speaker Tab Standings ({data.get('tournaments_attended', 0)} Tournaments)\n"
                        f"| Tournament | Team | Prelims Spoken | Substantive Avg | Total Points | Rank by Avg (Eligible Pool) | Rank by Total Pts (All Pool) | Raw Prelim Scores |\n"
                        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
                        f"{t_md}\n"
                    )
                    return AgentResult(query=query, intent="RECONSTRUCT_SPEAKER_TAB", answer=answer, tool_calls=tool_calls, data=data)

        # Circuit Leaderboard of Reconstructed Average Speaker Tab Rank
        tool_calls.append({"tool": "reconstruct_speaker_tab", "args": {"min_tournaments": 2, "limit": 20}})
        data = self._query_engine.reconstruct_speaker_tab(min_tournaments=2, limit=20)
        rows = []
        for i, r in enumerate(data.get("leaderboard", []), 1):
            rows.append(
                f"| #{i} | **{r['speaker_name']}** | {r['institution']} | **{fmt_val(r['avg_speaker_tab_rank_eligible'])}** | "
                f"{fmt_val(r['avg_speaker_tab_rank_full_prelims'])} | #{r.get('best_speaker_tab_rank_avg') or 'N/A'} | "
                f"{r['eligible_tournaments']} |"
            )
        table_md = "\n".join(rows)
        answer = (
            f"### Reconstructed Circuit Leaderboard — Lowest Career Average Speaker Tab Rank (Min. 2 Qualifying Tournaments)\n\n"
            f"| Pos | Debater | Institution | Career Avg Tab Rank (by Avg) | Full-Prelim Avg Tab Rank (by Total) | Peak Rank | Qualifying Tourns |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="RECONSTRUCT_SPEAKER_TAB", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_reconstructed_team_tab(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]], session_id: str = "default") -> AgentResult:
        tournament = params.get("tournament")
        team_name = params.get("team_name")
        identifier = params.get("identifier")

        if not team_name and identifier:
            pid, name = self._resolve_debater(str(identifier), tool_calls)
            if pid:
                self._session_last_entity[session_id] = name
                prof = self._query_engine.get_debater(pid, compact=True)
                teams = prof.get("teams_debated", [])
                if teams:
                    team_name = teams[0]

        tool_calls.append({"tool": "reconstruct_team_tab", "args": {"tournament": tournament, "team_name": team_name, "limit": 25}})
        data = self._query_engine.reconstruct_team_tab(tournament=tournament, team_name=team_name, limit=25)
        if "error" in data:
            return AgentResult(query=query, intent="RECONSTRUCT_TEAM_TAB", answer=f"Error: {data['error']}", tool_calls=tool_calls, success=False)

        if data.get("mode") == "tournament":
            t_name = data.get("tournament_name", tournament)
            rows = []
            for t in data.get("standings", [])[:25]:
                brk = "Yes" if t.get("broke") else "No"
                losses = max(0, (t.get("prelim_debates") or 0) - (t.get("prelim_wins") or 0))
                rows.append(
                    f"| **#{t['prelim_tab_rank']}** | **{t['team_name']}** | {t['institution']} | "
                    f"**{t['prelim_wins']}W - {losses}L** ({t.get('ballots_won', 0)} ballots) | **{fmt_val(t['total_team_score'])} pts** | "
                    f"{fmt_val(t['atss'])} pts | {brk} |"
                )
            table_md = "\n".join(rows)
            answer = (
                f"### Reconstructed Preliminary Team Tab: **{t_name}**\n\n"
                f"| Prelim Rank | Team | Institution | Prelim Record | Total Team Speaks | Avg Team Score (ATSS) | Broke |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
                f"{table_md}\n"
            )
            return AgentResult(query=query, intent="RECONSTRUCT_TEAM_TAB", answer=answer, tool_calls=tool_calls, data=data)

        rows = []
        for r in data.get("campaigns", [])[:25]:
            brk = "Yes" if r.get("broke") else "No"
            losses = max(0, (r.get("prelim_debates") or 0) - (r.get("prelim_wins") or 0))
            rows.append(
                f"| **{r['tournament_name']}** | **{r['team_name']}** | **#{r['prelim_tab_rank']}** / {r['total_teams']} | "
                f"**{r['prelim_wins']}W - {losses}L** | {fmt_val(r['total_team_score'])} pts | {fmt_val(r['atss'])} pts | {brk} |"
            )
        table_md = "\n".join(rows)
        answer = (
            f"### Reconstructed Team Tab Standings: **{data.get('team_name', team_name)}** ({data.get('institution', 'Independent')})\n\n"
            f"- **Average Preliminary Team Tab Rank (All Campaigns)**: **{fmt_val(data.get('avg_prelim_team_tab_rank_all'))}** across {data.get('tournaments_competed', 0)} tournaments\n"
            f"- **Average Break Seed Rank (BRA)**: **{fmt_val(data.get('avg_break_seed_rank_bra'))}** ({data.get('breaks_count', 0)} breaks)\n"
            f"- **Peak Prelim Tab Rank**: **#{data.get('best_prelim_tab_rank') or 'N/A'}**\n\n"
            f"| Tournament | Team | Prelim Tab Rank | Prelim Record | Total Team Speaks | ATSS | Broke |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="RECONSTRUCT_TEAM_TAB", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_elo_analysis(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]], session_id: str = "default") -> AgentResult:
        mode = params.get("mode", "leaderboard")
        identifier = params.get("identifier")

        if identifier:
            tool_calls.append({"tool": "get_elo_trajectory", "args": {"identifier": identifier}})
            data = self._query_engine.get_elo_trajectory(identifier=identifier)
            if "error" not in data:
                hist = data.get("history", [])
                rows = [
                    f"| #{i} | {h.get('tournament_name')} | {h.get('round_name')} | {h.get('opponent')} | {h.get('result')} | **{fmt_val(h.get('elo_after'))}** ({h.get('delta'):+.2f}) |"
                    for i, h in enumerate(hist[-15:], 1)
                ]
                table_md = "\n".join(rows)
                answer = (
                    f"### Elo Rating Trajectory: **{data.get('name', identifier)}**\n\n"
                    f"- **Current Elo**: **{fmt_val(data.get('current_elo'))}** (Peak Elo: **{fmt_val(data.get('peak_elo'))}**)\n\n"
                    f"| Step | Tournament | Round | Opponent | Outcome | Elo After (Delta) |\n"
                    f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                    f"{table_md}\n"
                )
                return AgentResult(query=query, intent="ELO_ANALYSIS", answer=answer, tool_calls=tool_calls, data=data)

        tool_calls.append({"tool": "get_elo_leaderboard", "args": {"mode": "debater", "limit": 20}})
        data = self._query_engine.get_elo_leaderboard(mode="debater", limit=20)
        rows = []
        for i, r in enumerate(data.get("leaderboard", []), 1):
            rows.append(
                f"| #{i} | **{r.get('name')}** | {r.get('institution', 'Independent')} | **{fmt_val(r.get('elo'))}** | "
                f"{fmt_val(r.get('peak_elo'))} | {r.get('debates', 0)} |"
            )
        table_md = "\n".join(rows)
        answer = (
            f"### National Debater Elo Leaderboard\n\n"
            f"| Rank | Debater | Institution | Current Elo | Peak Elo | Debates |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            f"{table_md}\n"
        )
        return AgentResult(query=query, intent="ELO_ANALYSIS", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_motion_intelligence(self, query: str, params: Dict[str, Any], tool_calls: List[Dict[str, Any]]) -> AgentResult:
        theme = params.get("theme")
        q = params.get("query")
        tool_calls.append({"tool": "get_motion_analytics", "args": {"theme": theme, "extreme_only": True}})
        data = self._query_engine.get_motion_analytics(theme=theme, query=q, extreme_only=True)

        overall = data.get("overall_side_balance", {})
        cats = data.get("categories", [])[:5]
        cat_lines = "\n".join([f"- **{c.get('theme')}**: {c.get('total_motions', 0)} motions | Prop: {fmt_val(c.get('prop_win_pct'))}% vs Opp: {fmt_val(c.get('opp_win_pct'))}%" for c in cats])

        answer = (
            f"### Debate Motion Intelligence & Side Bias\n\n"
            f"- **Circuit Side Balance**: Proposition Wins: {fmt_val(overall.get('prop_win_pct'))}% vs Opposition Wins: {fmt_val(overall.get('opp_win_pct'))}%\n"
            f"- **Total Scored Motions**: {overall.get('total_debates', 'N/A')}\n\n"
            f"#### Top Thematic Categories:\n{cat_lines or 'None recorded'}"
        )
        return AgentResult(query=query, intent="MOTION_INTELLIGENCE", answer=answer, tool_calls=tool_calls, data=data)

    def _handle_general_search(self, query: str, tool_calls: List[Dict[str, Any]], session_id: str = "default") -> AgentResult:
        # Before falling back to a plain entity list, check if the query mentions a debater and "rank" / "tab" / "average"
        q_low = query.lower()
        if any(w in q_low for w in ["rank", "tab", "average", "avg", "speaks", "speaker"]):
            pid, name = self._resolve_debater(query, tool_calls)
            if pid:
                if "tab" in q_low or "rank" in q_low:
                    return self._handle_reconstructed_speaker_tab(
                        query, {"mode": "debater", "identifier": name}, tool_calls, session_id=session_id
                    )
                return self._handle_debater_dossier(
                    query, {"identifier": name}, tool_calls, session_id=session_id
                )

        tool_calls.append({"tool": "search_entities", "args": {"query": query, "limit": 5}})
        results = self._query_engine.search(query, limit=5)

        if not results:
            return AgentResult(
                query=query,
                intent="GENERAL_SEARCH",
                answer=f"No direct matches found for *\"{query}\"*. You can ask for a debater profile, reconstructed speaker tab rank, school comparison, motion analysis, or circuit statistics.",
                tool_calls=tool_calls,
                success=True
            )

        # If the top result is a single debater, return their full dossier directly instead of just a bullet point
        if len(results) >= 1 and results[0].get("type") == "debater":
            top_name = results[0].get("canonical_name") or results[0].get("name")
            if top_name and top_name.lower().split()[0] in q_low:
                return self._handle_debater_dossier(query, {"identifier": top_name}, tool_calls, session_id=session_id)

        items = []
        for r in results:
            t = r.get("type", "entity").capitalize()
            name = r.get("name") or r.get("canonical_name") or r.get("motion_text", "Unknown")
            items.append(f"- **[{t}]** {name}")
        items_md = "\n".join(items)

        answer = f"Found the following records matching *\"{query}\"*:\n\n{items_md}"
        return AgentResult(query=query, intent="GENERAL_SEARCH", answer=answer, tool_calls=tool_calls, data={"results": results})

