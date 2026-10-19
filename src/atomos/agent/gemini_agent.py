"""
Atomos Gemini Cloud LLM Autonomous ReAct Agent.

Provides true human-like comprehension, dynamic tone adaptation, persistent multi-turn
memory, and an intelligent data hierarchy:
1. Analytical Engine: used for standard, abundant, high-level summaries and V2 metrics.
2. Atomic Normalized SQLite Fallback: immediately queried via SQL for complex, niche,
   relational, or subset questions.
"""

import copy
import json
import math
import os
import requests
from typing import Any, Dict, List, Optional

from atomos.config import get_gemini_api_key, get_gemini_model
from atomos.query import AtomosQuery
from atomos.tools import TOOL_SCHEMAS, dispatch_tool
from atomos.agent.prompts import (
    SYSTEM_INSTRUCTION,
    OFF_TOPIC_REFUSAL,
    is_off_topic_query,
    contains_off_topic_leak,
)


def fmt_val(v: Any, max_decimals: int = 3) -> str:
    """Universal Precision Rule: Do not round up, show up to 3 decimal places if exist."""
    if v is None:
        return "N/A"
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "N/A"
        if f % 1 == 0:
            return str(int(f))
        s = f"{f:.8f}"
        parts = s.split('.')
        dec = parts[1][:max_decimals].rstrip('0')
        return f"{parts[0]}.{dec}" if dec else parts[0]
    except (ValueError, TypeError):
        return str(v)


def _strip_thought_signatures(contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strip model-specific thought parts and thoughtSignature fields from contents
    when switching fallback models mid-loop to prevent HTTP 400 INVALID_ARGUMENT errors.
    """
    cleaned: List[Dict[str, Any]] = []
    for turn in contents:
        new_parts = []
        for p in turn.get("parts", []):
            if p.get("thought") and "functionCall" not in p and "functionResponse" not in p:
                continue
            p_copy = {k: v for k, v in p.items() if k not in ("thoughtSignature", "thought")}
            if p_copy:
                new_parts.append(p_copy)
        if new_parts:
            cleaned.append({"role": turn.get("role", "user"), "parts": new_parts})
    return cleaned


class GeminiAgent:
    """Autonomous ReAct agent with persistent conversational memory and intelligent atomic SQL fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        query_engine: Optional[AtomosQuery] = None,
        max_history_turns: int = 20,
    ):
        self.api_key = api_key or get_gemini_api_key()
        self.model = model or get_gemini_model()
        self._owned_query = False
        if query_engine is None:
            self.query_engine = AtomosQuery()
            self._owned_query = True
        else:
            self.query_engine = query_engine

        self.function_declarations = [s["function"] for s in TOOL_SCHEMAS]
        self.max_history_turns = max_history_turns
        # Compacted conversational memory: session_id -> list of clean {role, parts} turns
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        self._ensure_session_table()

    def _ensure_session_table(self):
        try:
            if self.query_engine and getattr(self.query_engine, "conn", None):
                cur = self.query_engine.conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_session_memory (
                        session_id TEXT PRIMARY KEY,
                        history_json TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                self.query_engine.conn.commit()
        except Exception:
            pass

    def _load_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        if session_id in self.sessions:
            return self.sessions[session_id]
        try:
            if self.query_engine and getattr(self.query_engine, "conn", None):
                cur = self.query_engine.conn.cursor()
                cur.execute("SELECT history_json FROM chat_session_memory WHERE session_id = ?", (session_id,))
                row = cur.fetchone()
                if row and row[0]:
                    loaded = json.loads(row[0])
                    if isinstance(loaded, list):
                        self.sessions[session_id] = loaded
                        return loaded
        except Exception:
            pass
        return []

    def _save_session_history(self, session_id: str, history: List[Dict[str, Any]]):
        self.sessions[session_id] = history
        self.conversation_history = history
        try:
            if self.query_engine and getattr(self.query_engine, "conn", None):
                cur = self.query_engine.conn.cursor()
                cur.execute("""
                    INSERT INTO chat_session_memory (session_id, history_json, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id) DO UPDATE SET
                        history_json = excluded.history_json,
                        updated_at = CURRENT_TIMESTAMP
                """, (session_id, json.dumps(history)))
                self.query_engine.conn.commit()
        except Exception:
            pass

    def close(self):
        if self._owned_query and self.query_engine:
            self.query_engine.close()

    def reset_memory(self, session_id: Optional[str] = None):
        """Clear conversational memory for a specific session or all sessions."""
        if session_id:
            self.sessions.pop(session_id, None)
            if session_id == "default":
                self.conversation_history = []
            try:
                if self.query_engine and getattr(self.query_engine, "conn", None):
                    cur = self.query_engine.conn.cursor()
                    cur.execute("DELETE FROM chat_session_memory WHERE session_id = ?", (session_id,))
                    self.query_engine.conn.commit()
            except Exception:
                pass
        else:
            self.sessions.clear()
            self.conversation_history = []
            try:
                if self.query_engine and getattr(self.query_engine, "conn", None):
                    cur = self.query_engine.conn.cursor()
                    cur.execute("DELETE FROM chat_session_memory")
                    self.query_engine.conn.commit()
            except Exception:
                pass

    def run(self, query: str, session_id: str = "default", max_turns: int = 15) -> Dict[str, Any]:
        """
        Execute an autonomous multi-turn reasoning and tool-calling loop,
        maintaining clean compacted conversational history across calls for the given session.
        """
        # 1. Pre-flight topic boundary guard
        if is_off_topic_query(query):
            return {
                "query": query,
                "intent": "OFF_TOPIC_GUARD",
                "answer": OFF_TOPIC_REFUSAL,
                "tool_calls": [],
                "success": True,
                "model_used": "circuit_boundary_guard",
            }

        if not self.api_key:
            return {
                "query": query,
                "intent": "GEMINI_LLM",
                "answer": "Gemini API key not found. Please configure GEMINI_API_KEY in .env.",
                "tool_calls": [],
                "success": False,
                "error": "Missing GEMINI_API_KEY",
            }

        headers = {"Content-Type": "application/json"}

        # Fast and resilient model hierarchy: prioritize fastest available model with highest quota headroom
        candidate_models = [
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
            "gemini-3.6-flash",
        ]
        if self.model and self.model in candidate_models:
            candidate_models.remove(self.model)
            candidate_models.insert(0, self.model)
        elif self.model and self.model not in ("gemini-2.5-flash", "gemini-2.0-flash"):
            candidate_models.insert(0, self.model)

        # Build contents from pristine compacted conversation history + new user query
        session_history = self._load_session_history(session_id)
        contents: List[Dict[str, Any]] = []
        for turn in session_history:
            text_parts = [{"text": str(p.get("text", ""))} for p in turn.get("parts", []) if "text" in p and str(p.get("text", "")).strip()]
            if text_parts:
                contents.append({
                    "role": turn.get("role", "user"),
                    "parts": text_parts
                })

        contents.append({"role": "user", "parts": [{"text": query}]})

        # Trim oldest turns if history exceeds max capacity (keep even number of turns)
        if len(contents) > self.max_history_turns * 2:
            excess = len(contents) - (self.max_history_turns * 2)
            contents = contents[excess:]

        turn_tool_calls: List[Dict[str, Any]] = []
        active_model = candidate_models[0]
        final_answer = ""
        success = False

        for step in range(max_turns):
            is_final_step = (step >= max_turns - 1)
            if is_final_step:
                contents.append({
                    "role": "user",
                    "parts": [{"text": "Synthesize and present your final answer now using all facts collected so far."}]
                })

            resp = None
            last_err = ""

            models_to_try = [active_model] + [m for m in candidate_models if m != active_model]
            for m_idx, m in enumerate(models_to_try):
                # If switching models mid-turn, strip model-specific thoughtSignatures to prevent HTTP 400
                req_contents = contents if m_idx == 0 else _strip_thought_signatures(contents)
                payload: Dict[str, Any] = {
                    "contents": req_contents,
                    "systemInstruction": {
                        "parts": [{"text": SYSTEM_INSTRUCTION}]
                    },
                    "generationConfig": {
                        "temperature": 0.1,
                    }
                }
                if not is_final_step:
                    payload["tools"] = [{"functionDeclarations": self.function_declarations}]

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
                try:
                    r = requests.post(url, headers=headers, json=payload, timeout=18)
                    if r.status_code == 200:
                        resp = r
                        if m_idx > 0:
                            contents = req_contents
                        active_model = m
                        break
                    elif r.status_code == 400 and step > 0:
                        # Retry once on the same model after stripping thought signatures
                        clean_c = _strip_thought_signatures(contents)
                        payload["contents"] = clean_c
                        r2 = requests.post(url, headers=headers, json=payload, timeout=18)
                        if r2.status_code == 200:
                            resp = r2
                            contents = clean_c
                            active_model = m
                            break
                        last_err = f"Model {m} status {r2.status_code}: {r2.text[:140]}"
                        continue
                    elif r.status_code in (400, 404, 429, 500, 502, 503, 504):
                        last_err = f"Model {m} status {r.status_code}: {r.text[:140]}"
                        continue
                    else:
                        resp = r
                        break
                except Exception as exc:
                    last_err = str(exc)
                    continue

            if resp is None or resp.status_code != 200:
                err_text = resp.text if resp else last_err
                return {
                    "query": query,
                    "intent": "GEMINI_LLM",
                    "answer": f"Gemini API error ({active_model}): {err_text}",
                    "tool_calls": turn_tool_calls,
                    "success": False,
                    "error": err_text,
                }

            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if not candidates:
                return {
                    "query": query,
                    "intent": "GEMINI_LLM",
                    "answer": "No response candidate received from Gemini.",
                    "tool_calls": turn_tool_calls,
                    "success": False,
                }

            candidate_content = candidates[0].get("content", {})
            parts = candidate_content.get("parts", [])

            fc_parts = [p for p in parts if "functionCall" in p]

            if not fc_parts:
                # Separate final answer text from internal Gemini 3.x thinking parts
                non_thought_text = "".join([p.get("text", "") for p in parts if "text" in p and not p.get("thought")]).strip()
                candidate_text = non_thought_text or "".join([p.get("text", "") for p in parts if "text" in p]).strip()

                # Anti-Hallucination Interceptor:
                # Enforce tool grounding only for specific factual/statistical inquiries, NOT pure conceptual derivations.
                q_lower = query.lower()
                is_conceptual = any(k in q_lower for k in [
                    "how does elo work", "explain elo", "formula", "definition", "concept", "derive", "what is elo", "how is elo"
                ])

                if len(turn_tool_calls) == 0 and step == 0 and not is_conceptual:
                    circuit_inquiry_terms = [
                        "leaderboard", "ranking", "standings", "top speaker", "who is",
                        "average of", "record of", "score of", "winner", "closeout", "clash",
                        "how many speeches", "how many rounds", "how many debates"
                    ]
                    is_factual_inquiry = any(t in q_lower for t in circuit_inquiry_terms)

                    has_statistical_claims = (
                        "|" in candidate_text
                        or "rank" in candidate_text.lower()
                        or "substantive avg" in candidate_text.lower()
                        or any(c.isdigit() for c in candidate_text)
                    )

                    if is_factual_inquiry and has_statistical_claims:
                        contents.append(candidate_content)
                        contents.append({
                            "role": "user",
                            "parts": [{"text": "MANDATORY ANTI-HALLUCINATION GROUNDING ENFORCEMENT: You provided circuit statistics, rankings, or debater numbers without calling database tools. In Atomos, you must NEVER estimate or guess stats. Call the appropriate tool(s) now (e.g. get_debater_v2_profile, get_debater_elo_history, get_speaker_leaderboard, or execute_sql) to fetch ground-truth facts from atomos.db before answering."}]
                        })
                        continue

                final_answer = candidate_text
                success = True
                contents.append(candidate_content)
                break

            # Append assistant functionCall turn
            contents.append(candidate_content)

            # Execute tool calls
            tool_resp_parts = []
            for p in fc_parts:
                fc = p["functionCall"]
                call_id = fc.get("id")
                name = fc.get("name")
                args = fc.get("args", {})

                turn_tool_calls.append({"tool": name, "args": args})
                tool_output = dispatch_tool(name, args, query_engine=self.query_engine)

                tool_resp_parts.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"output": tool_output},
                        **({"id": call_id} if call_id else {})
                    }
                })

            contents.append({
                "role": "user",
                "parts": tool_resp_parts
            })

        # Post-flight topic leak safety check
        if contains_off_topic_leak(final_answer):
            final_answer = OFF_TOPIC_REFUSAL

        if success:
            entity_notes = []
            for tc in turn_tool_calls:
                args = tc.get("args", {})
                for k in ["identifier", "debater", "team_name", "school_a", "school_b", "tournament"]:
                    if k in args and args[k]:
                        entity_notes.append(str(args[k]))

            context_tag = f"<!-- Context Entities: {', '.join(set(entity_notes))} -->\n" if entity_notes else ""

            clean_turn = [
                {"role": "user", "parts": [{"text": query}]},
                {"role": "model", "parts": [{"text": f"{context_tag}{final_answer}"}]}
            ]

            compacted_history = list(self._load_session_history(session_id))
            compacted_history.extend(clean_turn)
            if len(compacted_history) > self.max_history_turns * 2:
                compacted_history = compacted_history[-(self.max_history_turns * 2):]

            self._save_session_history(session_id, compacted_history)

        return {
            "query": query,
            "intent": "GEMINI_LLM",
            "answer": final_answer,
            "tool_calls": turn_tool_calls,
            "success": success,
            "model_used": active_model,
        }
