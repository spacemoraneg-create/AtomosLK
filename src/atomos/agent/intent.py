"""
Atomos Natural Language Intent Classifier & Entity Extractor

Analyzes human language questions and maps them to concrete analytical intents
and parameter sets for the Atomos debate intelligence layer.
"""

from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple


class AgentIntent(str, Enum):
    GREETING = "GREETING"
    SYSTEM_IDENTITY = "SYSTEM_IDENTITY"
    HELP_CAPABILITIES = "HELP_CAPABILITIES"
    GENERAL_CIRCUIT = "GENERAL_CIRCUIT"
    CIRCUIT_META = "GENERAL_CIRCUIT"
    SUPERLATIVE_ROUND = "SUPERLATIVE_ROUND"
    SIDE_SPLIT = "SIDE_SPLIT"
    POSITION_ANALYSIS = "POSITION_ANALYSIS"
    OUTROUND_HISTORY = "OUTROUND_HISTORY"
    ADJUDICATOR_LOOKUP = "ADJUDICATOR_LOOKUP"
    MATCH_OPPONENT_LOOKUP = "MATCH_OPPONENT_LOOKUP"
    HEAD_TO_HEAD = "HEAD_TO_HEAD"
    MATH_DERIVATION = "MATH_DERIVATION"
    SPEAKER_RANKINGS = "SPEAKER_RANKINGS"
    INSTITUTION_LEADERBOARD = "INSTITUTION_LEADERBOARD"
    INSTITUTION_DOSSIER = "INSTITUTION_DOSSIER"
    DEBATER_DOSSIER = "DEBATER_DOSSIER"
    MOTION_INTELLIGENCE = "MOTION_INTELLIGENCE"
    UNKNOWN = "UNKNOWN"


def clean_entity_name(raw: str) -> str:
    """Clean common conversational prefixes, debate metric qualifiers, and punctuation from entity names."""
    s = raw.strip()
    # Strip leading conversational phrasing
    s = re.sub(
        r"^(?:who is|who are|scout|profile|stats for|tell me about|show me|search for|lookup|find|what was|what is|what's|how does|about|details on|information on|record of|record for|derive|derivation of)\s+",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    # Strip trailing possessives
    s = re.sub(r"\'s\b", "", s, flags=re.IGNORECASE).strip()
    # Strip trailing metric words
    s = re.sub(r"\s+\b(?:speaker average|speaker avg|speech average|average|stats|profile|dossier|score|rank)\b.*$", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"[\?\.\!]+$", "", s).strip()
    return s


def classify_intent(query: str) -> Tuple[AgentIntent, Dict[str, Any]]:
    """
    Classifies a natural language query into an AgentIntent with extracted entities/parameters.
    """
    q = query.strip()
    q_lower = q.lower()
    tokens = [t.strip(".,?!\"'") for t in q_lower.split()]

    # 1. Conversational Greetings
    greeting_words = {"hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "yo", "sup", "howdy"}
    if q_lower in greeting_words or (len(tokens) <= 2 and any(t in greeting_words for t in tokens)):
        return AgentIntent.GREETING, {}

    # 2. System Identity & Role
    if any(p in q_lower for p in [
        "who are you", "what is atomos", "what are you", "tell me about yourself",
        "what is your purpose", "your role", "what do you do"
    ]):
        return AgentIntent.SYSTEM_IDENTITY, {}

    # 3. Help & Capabilities
    if any(p in q_lower for p in [
        "help", "what can you do", "capabilities", "commands", "what questions can i ask",
        "examples", "what can you answer", "how to use"
    ]):
        return AgentIntent.HELP_CAPABILITIES, {}

    # 4. Circuit Meta / High-level database summary
    if any(p in q_lower for p in [
        "what tournaments", "tournaments recorded", "tournaments in database",
        "circuit overview", "circuit summary", "total debaters", "circuit stats",
        "national summary", "how many debaters", "how many debates", "how many tournaments",
        "how many speeches", "database stats", "database summary", "in the circuit", "circuit?"
    ]):
        return AgentIntent.GENERAL_CIRCUIT, {}

    # 5. Motion Intelligence & Side Bias (Check before debater side split)
    if "motion" in q_lower or "motions" in q_lower or any(k in q_lower for k in [
        "thematic", "toughest motion", "hardest motion", "easiest motion",
        "balanced motion", "extreme motion"
    ]):
        theme = None
        for t_kw in ["economics", "geopolitics", "tech", "ai", "culture", "social", "law", "philosophy", "education"]:
            if t_kw in q_lower:
                theme = t_kw
                break
        return AgentIntent.MOTION_INTELLIGENCE, {
            "query": q,
            "theme": theme,
            "extreme_only": any(k in q_lower for k in ["toughest", "hardest", "extreme", "most biased", "balanced", "highest", "lowest", "heaviest", "side bias"])
        }

    # 6. Adjudicator / Judge Lookups
    if any(k in q_lower for k in ["who judged", "judged by", "chair judge", "adjudicator", "adjudicators", "judge who"]):
        m = re.search(r"(?:judged|for|of)\s+([A-Za-z\s\.\']+?)(?:\'s|when|\?|$)", q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else ""
        return AgentIntent.ADJUDICATOR_LOOKUP, {
            "identifier": ident,
            "for_best": any(k in q_lower for k in ["best", "highest", "peak", "top"]),
            "for_worst": any(k in q_lower for k in ["worst", "lowest", "bottom"]),
        }

    # 7. Mathematical Derivations
    if any(k in q_lower for k in [
        "how was", "derivation", "derive", "calculated", "formula",
        "walkthrough", "step by step", "calculation for", "math for"
    ]) and any(k in q_lower for k in ["average", "avg", "score", "speaker", "debater", "tab", "regulation", "ipi"]):
        id_match = re.search(r'#?(\d+)', q)
        identifier = id_match.group(1) if id_match else None
        if not identifier:
            name_match = re.search(r'(?:for|of|debater|derive)\s+([A-Za-z\s\.\']+?)(?:\'s|\?|$)', q, re.IGNORECASE)
            if name_match:
                identifier = clean_entity_name(name_match.group(1))
        return AgentIntent.MATH_DERIVATION, {"identifier": identifier or clean_entity_name(q)}

    # 8. Superlatives & Extremes (Best Round, Worst Round, Highest Score)
    superlative_keywords = ["best round", "worst round", "highest score", "lowest score", "peak speech", "peak round", "top speech", "best speech", "worst speech", "lowest speech", "highest speech", "highest individual"]
    if any(k in q_lower for k in superlative_keywords) or (
        ("round" in q_lower or "score" in q_lower or "speech" in q_lower) and
        any(s in q_lower for s in ["best", "worst", "highest", "lowest", "top", "peak"])
    ):
        polarity = "worst" if any(w in q_lower for w in ["worst", "lowest", "bottom", "poorest"]) else "best"
        m1 = re.search(r'([A-Za-z\s\.\']+?)(?:\'s|\s+)\b(?:best|worst|highest|lowest|peak|top)\b', q, re.IGNORECASE)
        m2 = re.search(r'\b(?:best|worst|highest|lowest|peak|top)\b(?:\s+\w+)*\s+(?:of|for|by)\s+([A-Za-z\s\.\']+?)(?:\?|$)', q, re.IGNORECASE)
        
        target = ""
        if m1:
            target = clean_entity_name(m1.group(1))
        elif m2:
            target = clean_entity_name(m2.group(1))
        else:
            leftover = q
            for phrase in ["what was", "what is", "tell me", "show me", "best round", "worst round", "highest score", "lowest score", "peak round", "top speech", "of", "for", "in", "?"]:
                leftover = re.sub(r'\b' + re.escape(phrase) + r'\b', ' ', leftover, flags=re.IGNORECASE)
            target = clean_entity_name(leftover)

        return AgentIntent.SUPERLATIVE_ROUND, {
            "identifier": target,
            "polarity": polarity,
            "raw_query": q
        }

    # 9. Side Performance Split (Gov vs Opp / Prop vs Opp)
    if any(k in q_lower for k in ["gov vs opp", "prop vs opp", "proposition vs opposition", "on proposition", "on opposition", "as proposition", "as opposition", "on gov", "on opp", "as gov", "as opp", "side split"]):
        m = re.search(r'(?:for|of|does)\s+([A-Za-z\s\.\']+?)(?:\s+perform|\s+do|\s+on|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else clean_entity_name(re.sub(r'\b(gov|opp|prop|opposition|proposition|side|vs|split|perform|performance|how|does|on|as)\b', '', q, flags=re.IGNORECASE))
        return AgentIntent.SIDE_SPLIT, {"identifier": ident}

    # 9. Outround / Elimination Round History
    if any(k in q_lower for k in ["outround", "outrounds", "break record", "elimination round", "elimination rounds", "knockouts", "finals", "semifinals", "quarterfinals", "octofinals"]):
        m = re.search(r'(?:for|of|did)\s+([A-Za-z0-9\s\.\']+?)(?:\s+debate|\s+reach|\s+win|\s+break|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else ""
        return AgentIntent.OUTROUND_HISTORY, {"identifier": ident, "query": q}

    # 10. Position Breakdown (1st vs 2nd vs 3rd vs Reply)
    if any(k in q_lower for k in ["1st speaker", "2nd speaker", "3rd speaker", "reply speaker", "reply speeches", "positions debated", "as reply", "as 1st", "as 2nd", "as 3rd"]):
        m = re.search(r'(?:for|of|does)\s+([A-Za-z\s\.\']+?)(?:\s+debate|\s+speak|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else clean_entity_name(q)
        return AgentIntent.POSITION_ANALYSIS, {"identifier": ident}

    # 11. Head-to-Head Clash / Comparison
    h2h_match = re.search(
        r'(?:compare|h2h|head to head|clash between|versus|vs\.?)\s+([^,\n\?]+?)\s+(?:and|with|to|vs\.?|against)\s+([^,\n\?]+)',
        q,
        re.IGNORECASE
    )
    if not h2h_match:
        h2h_match = re.search(r'([A-Za-z0-9\s\.\']+?)\s+(?:vs\.?|versus)\s+([A-Za-z0-9\s\.\']+)', q, re.IGNORECASE)

    if h2h_match:
        entity_a = clean_entity_name(h2h_match.group(1))
        entity_b = clean_entity_name(h2h_match.group(2))
        return AgentIntent.HEAD_TO_HEAD, {"entity_a": entity_a, "entity_b": entity_b}

    # 12. Institutional Leaderboard / Rankings
    if any(k in q_lower for k in [
        "ipi", "school leaderboard", "school ranking", "school rankings",
        "institutional leaderboard", "institution ranking"
    ]) or re.search(r'\b(?:top|best)\s*(?:\d+\s*)?(?:schools?|institutions?|colleges?)', q_lower):
        limit_match = re.search(r'(?:top|best)\s+(\d+)', q_lower)
        limit = int(limit_match.group(1)) if limit_match else 25
        return AgentIntent.INSTITUTION_LEADERBOARD, {"top_n": limit}

    # 13. Speaker Rankings / Master Tab
    if any(k in q_lower for k in [
        "speaker tab", "master tab", "speaker ranking", "highest average",
        "highest speaker score"
    ]) or re.search(r'\b(?:top|best|highest)\s*(?:\d+\s*)?(?:speakers?|debaters?)', q_lower):
        limit_match = re.search(r'(?:top|best|highest)\s+(\d+)', q_lower)
        limit = int(limit_match.group(1)) if limit_match else 15
        return AgentIntent.SPEAKER_RANKINGS, {"limit": limit}


    # 15. Institution Dossier (Look for school names/keywords)
    if any(k in q_lower for k in ["school", "college", "convent", "academy", "institution", "squad depth"]):
        name_match = re.search(r'(?:about|for|school|college|convent|institution)\s+([A-Za-z\s\.\']+?)(?:\?|$)', q, re.IGNORECASE)
        inst_query = clean_entity_name(name_match.group(1)) if name_match else clean_entity_name(q)
        return AgentIntent.INSTITUTION_DOSSIER, {"school": inst_query}

    # 16. Single Person / Debater Dossier
    # Explicit Person/Debater ID (e.g. "#42", "debater 42", "person 42", "id 42")
    id_match = re.search(r'\b(?:debater|person|id)\s*#?(\d+)\b', q, re.IGNORECASE) or re.search(r'#(\d+)\b', q)
    if id_match and not any(k in q_lower for k in ["top", "limit", "min", "round"]):
        return AgentIntent.DEBATER_DOSSIER, {"identifier": id_match.group(1)}

    if any(q_lower.startswith(p) for p in ["who is", "tell me about", "profile of", "stats for", "debater", "scout"]):
        clean_target = clean_entity_name(q)
        if clean_target:
            return AgentIntent.DEBATER_DOSSIER, {"identifier": clean_target}

    # If it's a short 1-4 word query of alphabetic words not matching any known commands, treat as entity lookup
    clean_target = clean_entity_name(q)
    if (
        clean_target
        and re.match(r'^[A-Za-z\s\.\'\-]+$', clean_target)
        and len(clean_target.split()) <= 4
        and not any(t in greeting_words for t in tokens)
    ):
        return AgentIntent.DEBATER_DOSSIER, {"identifier": clean_target}

    return AgentIntent.UNKNOWN, {"query": q}
