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
    RECONSTRUCT_SPEAKER_TAB = "RECONSTRUCT_SPEAKER_TAB"
    RECONSTRUCT_TEAM_TAB = "RECONSTRUCT_TEAM_TAB"
    ELO_ANALYSIS = "ELO_ANALYSIS"
    SPEAKER_RANKINGS = "SPEAKER_RANKINGS"
    INSTITUTION_LEADERBOARD = "INSTITUTION_LEADERBOARD"
    INSTITUTION_DOSSIER = "INSTITUTION_DOSSIER"
    DEBATER_DOSSIER = "DEBATER_DOSSIER"
    MOTION_INTELLIGENCE = "MOTION_INTELLIGENCE"
    UNKNOWN = "UNKNOWN"


TOURNAMENT_KEYWORDS = [
    "henley", "henleys", "stanley", "stanleys", "stanley's", "nixon", "nixons", "nixon's",
    "chaps", "chap's", "chapman", "slsdc", "law fac", "law faculty", "vvidc", "visakha",
    "vijis", "vijitha", "metho", "shanthi", "ric", "isdc", "aisdc", "ais", "apiit",
]


def extract_tournament_from_query(q_lower: str) -> Optional[str]:
    """Extract tournament alias from query if mentioned."""
    for kw in TOURNAMENT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', q_lower):
            return kw
    return None


def clean_entity_name(raw: str) -> str:
    """Clean common conversational prefixes, debate metric qualifiers, and punctuation from entity names."""
    s = raw.strip()
    # Strip leading conversational phrasing
    s = re.sub(
        r"^(?:who is|who are|scout|profile|stats for|tell me about|show me|search for|lookup|find|what was|what is|what's|how does|about|details on|information on|record of|record for|derive|derivation of|recreate|reconstruct|reverse engineer)\s+",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    # Strip trailing possessives
    s = re.sub(r"\'s\b", "", s, flags=re.IGNORECASE).strip()
    # Strip trailing metric words
    s = re.sub(
        r"\s+\b(?:average rank|avg rank|speaker tab rank|speaker tab|master tab|team tab|speaker average|speaker avg|speech average|average|avg|stats|profile|dossier|score|rank|ranking|elo|rating)\b.*$",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
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
    if any(k in q_lower for k in ["who judged", "has judged", "who has judged", "judged by", "judged", "who judges", "judges", "chair judge", "adjudicator", "adjudicators", "judge who"]):
        m = re.search(r"(?:judged|judges|for|of)\s+([A-Za-z\s\.\']+?)(?:\'s|\s+the|when|\?|$)", q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else ""
        return AgentIntent.ADJUDICATOR_LOOKUP, {
            "identifier": ident,
            "for_best": any(k in q_lower for k in ["best", "highest", "peak", "top"]),
            "for_worst": any(k in q_lower for k in ["worst", "lowest", "bottom"]),
        }

    # 7. Reconstructed Tournament Speaker Tab & Average Speaker Tab Rank
    # Catch queries like "what is balishta's avg rank in Speaker tab", "recreate speaker tab for Henley",
    # "balishta speaker tab rank", "who has the best avg rank in speaker tab"
    is_speaker_tab_query = any(k in q_lower for k in [
        "avg rank", "average rank", "rank in speaker tab", "rank on speaker tab",
        "ranks in speaker tab", "speaker tab rank", "speaker tab ranks",
        "recreate speaker tab", "reconstruct speaker tab", "reverse engineer speaker tab",
        "speaker tab for", "speaker tab at", "speaker tab in", "speaker tab of",
    ]) or (
        "speaker tab" in q_lower and not re.search(r'^\s*(?:show\s+|what\s+is\s+)?(?:the\s+)?(?:national\s+|master\s+)?speaker\s+tab\s*\??\s*$', q_lower)
    )
    if is_speaker_tab_query:
        tourn = extract_tournament_from_query(q_lower)
        ident = None
        # Check possessive e.g. "balishta's avg rank"
        m_poss = re.search(r"(?:what\s+is|what's|show|tell\s+me|find|get|calculate|derive)?\s*([A-Za-z\.\s]+?)'s\s+", q, re.IGNORECASE)
        if m_poss:
            cand = clean_entity_name(m_poss.group(1))
            if cand and cand.lower() not in ("what", "who", "atomos", "circuit", "tournament"):
                ident = cand
        if not ident:
            m_for = re.search(r"(?:for|of)\s+([A-Za-z\s\.\']+?)(?:\s+in|\s+at|\s+across|\s+on|\?|$)", q, re.IGNORECASE)
            if m_for:
                cand = clean_entity_name(m_for.group(1))
                cand_no_year = re.sub(r"\b(?:202\d|'?\d{2}|championship|memorial|debating|isdc|slsdc|vvidc|aisdc)\b", "", cand, flags=re.IGNORECASE).strip()
                if cand_no_year and cand_no_year.lower() not in TOURNAMENT_KEYWORDS and cand_no_year.lower() not in ("speaker tab", "the speaker tab", "tournaments", "each tournament"):
                    ident = cand
        if not ident:
            # Strip common speaker tab words and see if a person name remains
            stripped = re.sub(
                r"\b(?:what|is|was|whats|what's|the|avg|average|rank|ranking|ranks|in|on|at|for|of|across|all|each|every|tournament|tournaments|speaker|speakers|tab|tabs|recreate|reconstruct|show|me|tell|his|her|their|who|has|best|highest|lowest|top|championship|memorial|debating|202\d|'?\d{2})\b",
                " ",
                q_lower,
                flags=re.IGNORECASE,
            )
            for kw in TOURNAMENT_KEYWORDS:
                stripped = re.sub(r"\b" + re.escape(kw) + r"\b", " ", stripped, flags=re.IGNORECASE)
            stripped = clean_entity_name(stripped)
            if stripped and len(stripped) >= 3 and not stripped.isdigit():
                ident = stripped

        return AgentIntent.RECONSTRUCT_SPEAKER_TAB, {
            "identifier": ident,
            "tournament": tourn,
            "raw_query": q,
        }

    # 7B. Reconstructed Preliminary Team Tab / Break Seed Queries
    if any(k in q_lower for k in [
        "team tab", "prelim tab", "preliminary tab", "recreate team tab", "reconstruct team tab",
        "break seed", "break rank average", "bra of", "bra for"
    ]) or re.search(r"\b(?:what\s+is|what's)\s+.*?\bbra\b", q_lower):
        tourn = extract_tournament_from_query(q_lower)
        m_team = re.search(r"\b([A-Za-z]{2,10}\s+[A-C])\b", q)
        team_name = m_team.group(1) if m_team else None
        ident = None
        if not team_name:
            m_poss = re.search(r"([A-Za-z\s\.]+?)'s\b", q)
            if m_poss:
                ident = clean_entity_name(m_poss.group(1))
        return AgentIntent.RECONSTRUCT_TEAM_TAB, {
            "team_name": team_name,
            "identifier": ident,
            "tournament": tourn,
            "raw_query": q,
        }

    # 7C. Elo Rating & Progression Queries
    if re.search(r"\belo\b", q_lower):
        ident = None
        m_poss = re.search(r"([A-Za-z\s\.]+?)'s\s+(?:elo|peak elo|rating)", q, re.IGNORECASE)
        if m_poss:
            ident = clean_entity_name(m_poss.group(1))
        if not ident:
            m_for = re.search(r"(?:elo|rating)\s+(?:for|of|history\s+for|history\s+of)\s+([A-Za-z0-9\s\.\']+?)(?:\?|$)", q, re.IGNORECASE)
            if m_for:
                ident = clean_entity_name(m_for.group(1))
        if not ident:
            stripped = re.sub(
                r"\b(?:what|is|was|whats|what's|the|current|peak|highest|lowest|elo|rating|ratings|history|progression|timeline|for|of|in|at|show|me|tell|debater|team)\b",
                " ",
                q_lower,
                flags=re.IGNORECASE,
            )
            stripped = clean_entity_name(stripped)
            if stripped and len(stripped) >= 2:
                ident = stripped
        return AgentIntent.ELO_ANALYSIS, {
            "identifier": ident,
            "raw_query": q,
        }

    # 8. Mathematical Derivations
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

    # 9. Superlatives & Extremes (Best Round, Worst Round, Highest Score)
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

    # 10. Side Performance Split (Gov vs Opp / Prop vs Opp)
    if any(k in q_lower for k in ["gov vs opp", "prop vs opp", "proposition vs opposition", "on proposition", "on opposition", "as proposition", "as opposition", "on gov", "on opp", "as gov", "as opp", "side split"]):
        m = re.search(r'(?:for|of|does)\s+([A-Za-z\s\.\']+?)(?:\s+perform|\s+do|\s+on|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else clean_entity_name(re.sub(r'\b(gov|opp|prop|opposition|proposition|side|vs|split|perform|performance|how|does|on|as)\b', '', q, flags=re.IGNORECASE))
        return AgentIntent.SIDE_SPLIT, {"identifier": ident}

    # 11. Outround / Elimination Round History
    if any(k in q_lower for k in ["outround", "outrounds", "break record", "elimination round", "elimination rounds", "knockouts", "finals", "semifinals", "quarterfinals", "octofinals"]):
        m = re.search(r'(?:for|of|did)\s+([A-Za-z0-9\s\.\']+?)(?:\s+debate|\s+reach|\s+win|\s+break|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else ""
        return AgentIntent.OUTROUND_HISTORY, {"identifier": ident, "query": q}

    # 12. Position Breakdown (1st vs 2nd vs 3rd vs Reply)
    if any(k in q_lower for k in ["1st speaker", "2nd speaker", "3rd speaker", "reply speaker", "reply speeches", "positions debated", "as reply", "as 1st", "as 2nd", "as 3rd", "position breakdown", "by position"]):
        m = re.search(r'(?:for|of|does)\s+([A-Za-z\s\.\']+?)(?:\s+debate|\s+speak|\?|$)', q, re.IGNORECASE)
        ident = clean_entity_name(m.group(1)) if m else clean_entity_name(q)
        return AgentIntent.POSITION_ANALYSIS, {"identifier": ident}

    # 13. Head-to-Head Clash / Comparison
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

    # 14. Institutional Leaderboard / Rankings
    if any(k in q_lower for k in [
        "ipi", "school leaderboard", "school ranking", "school rankings",
        "institutional leaderboard", "institution ranking"
    ]) or re.search(r'\b(?:top|best)\s*(?:\d+\s*)?(?:schools?|institutions?|colleges?)', q_lower):
        limit_match = re.search(r'(?:top|best)\s+(\d+)', q_lower)
        limit = int(limit_match.group(1)) if limit_match else 25
        return AgentIntent.INSTITUTION_LEADERBOARD, {"top_n": limit}

    # 15. Speaker Rankings / Master Tab (ONLY when generic circuit-wide top speakers, NOT debater-specific)
    if any(k in q_lower for k in [
        "speaker tab", "master tab", "speaker ranking", "highest average",
        "highest speaker score"
    ]) or re.search(r'\b(?:top|best|highest)\s*(?:\d+\s*)?(?:speakers?|debaters?)', q_lower):
        limit_match = re.search(r'(?:top|best|highest)\s+(\d+)', q_lower)
        limit = int(limit_match.group(1)) if limit_match else 15
        return AgentIntent.SPEAKER_RANKINGS, {"limit": limit}

    # Guard: Comparative or complex questions about institutions/championships
    if any(k in q_lower for k in [
        "which institution", "which school", "which college", "won the most",
        "most championships", "championships this year", "most titles", "who won"
    ]):
        return AgentIntent.UNKNOWN, {"query": q}

    # 16. Institution Dossier (Look for school names/keywords)
    if any(k in q_lower for k in ["school", "college", "convent", "academy", "institution", "squad depth"]):
        name_match = re.search(r'(?:about|for|school|college|convent|institution)\s+([A-Za-z\s\.\']+?)(?:\?|$)', q, re.IGNORECASE)
        inst_query = clean_entity_name(name_match.group(1)) if name_match else clean_entity_name(q)
        if not any(w in inst_query.lower() for w in ["which", "what", "how", "has won", "most", "championship", "fun facts"]):
            return AgentIntent.INSTITUTION_DOSSIER, {"school": inst_query}

    # 17. Single Person / Debater Dossier
    id_match = re.search(r'\b(?:debater|person|id)\s*#?(\d+)\b', q, re.IGNORECASE) or re.search(r'#(\d+)\b', q)
    if id_match and not any(k in q_lower for k in ["top", "limit", "min", "round"]):
        return AgentIntent.DEBATER_DOSSIER, {"identifier": id_match.group(1)}

    if any(q_lower.startswith(p) for p in ["who is", "tell me about", "profile of", "stats for", "debater", "scout", "what is", "what's"]):
        clean_target = clean_entity_name(q)
        if clean_target and not any(w in clean_target.lower() for w in ["which", "what", "fun facts"]):
            return AgentIntent.DEBATER_DOSSIER, {"identifier": clean_target}

    # If it's a short 1-4 word query of alphabetic words not matching any known commands, treat as entity lookup
    non_name_indicators = {"which", "what", "where", "when", "why", "how", "tell", "fun", "facts", "tournament", "round", "speech", "speeches"}
    clean_target = clean_entity_name(q)
    if (
        clean_target
        and re.match(r'^[A-Za-z\s\.\'\-]+$', clean_target)
        and len(clean_target.split()) <= 4
        and not any(t in greeting_words for t in tokens)
        and not any(t in non_name_indicators for t in tokens)
    ):
        return AgentIntent.DEBATER_DOSSIER, {"identifier": clean_target}

    return AgentIntent.UNKNOWN, {"query": q}

