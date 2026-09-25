"""
Atomos LLM Tool Definitions & Function Dispatcher

Exports:
1. `TOOL_SCHEMAS`: Standard JSON Schema function calling definitions (compatible with
   Gemini, OpenAI, Anthropic, LangChain, and LiteLLM).
2. `dispatch_tool`: Single entry-point dispatcher executing any tool call against AtomosQuery.
"""

import json
from typing import Any, Dict, List, Optional
from atomos.query import AtomosQuery

# ============================================================================
# STANDARD JSON FUNCTION SCHEMAS
# ============================================================================

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "Search across Sri Lankan WSDC debate entities: debaters (by name or alias), institutions (by school name or acronym e.g. 'RC', 'WC', 'AC', 'SJC'), teams, tournaments (e.g. 'SLSDC', 'ISDC'), and motions. Use this first to resolve names or IDs before calling detailed profiling tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search term, e.g. 'Royal', 'Balishta', 'Vidath', 'ISDC', 'AI', 'Economics'."
                    },
                    "entity_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["debater", "institution", "team", "tournament", "motion"]},
                        "description": "Optional list of entity types to restrict search to. If omitted, searches all types."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (default: 5)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_debater_profile",
            "description": "Retrieve the comprehensive career profile, official Master Tab rank, national Critical Stats rank, overall substantive average, tournament performances, and break records for a specific debater.",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "The debater's canonical name (e.g. 'Balishta Wijesinghe') or numeric Person ID (e.g. '42')."
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true (recommended for LLM efficiency), omits verbose individual round speech arrays and mathematical derivation text."
                    }
                },
                "required": ["identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_head_to_head",
            "description": "Compute direct head-to-head clash statistics between two debaters, two teams, or two schools. Includes direct match history, win/loss splits, speaker margins, and records against mutual common opponents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_a": {
                        "type": "string",
                        "description": "Name or ID of first entity (e.g. 'Royal College', 'DS A', 'Vidath Marasinghe')."
                    },
                    "entity_b": {
                        "type": "string",
                        "description": "Name or ID of second entity (e.g. 'Ananda College', 'RC A', 'Kaveesha De Silva')."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "debater", "team", "school"],
                        "description": "Comparison mode. Default is 'auto' (detects whether schools, debaters, or teams are being compared)."
                    }
                },
                "required": ["entity_a", "entity_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_institutions",
            "description": "Side-by-side institutional comparison between two debating schools: Institutional Power Index (IPI), squad depth, tournament campaign summaries, direct school-versus-school matches, and common rival records.",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_a": {
                        "type": "string",
                        "description": "Name or code of school A (e.g. 'Royal College' or 'RC')."
                    },
                    "school_b": {
                        "type": "string",
                        "description": "Name or code of school B (e.g. 'Wesley College' or 'WC')."
                    }
                },
                "required": ["school_a", "school_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_institutional_leaderboard",
            "description": "Retrieve the national Institutional Power Index (IPI) leaderboard across Sri Lankan debating schools, including Dominance, Volume, Conversion, and Stability component breakdowns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_debates": {
                        "type": "integer",
                        "description": "Minimum debates required to be included on the national leaderboard (default: 5)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_speaker_leaderboard",
            "description": "Retrieve official national debater leaderboards and rankings across multiple metrics: 'prelims' (most preliminary rounds debated, max 36 in circuit), 'debates' (most total debates participated in), 'master_tab' (highest overall substantive average on Master Tab), 'critical_stats' (top ranked on national Critical Stats), or 'replies' (highest reply speech average). Every returned debater includes their name, school, national level ('Trials', 'Nat Pool, Trialed', 'Nat Pool, Direct', or null), and performance metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "enum": ["prelims", "debates", "master_tab", "critical_stats", "replies"],
                        "description": "Ranking dimension: 'prelims' (most preliminary rounds participated in), 'debates' (total debates participated in), 'master_tab' (highest substantive speaker avg), 'critical_stats' (national high-rigor critical tab), 'replies' (highest reply speech avg)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of debaters to return (default: 10, max: 50)."
                    },
                    "qualified_tournaments_only": {
                        "type": "boolean",
                        "description": "If true, for prelims volume rankings, only counts preliminary rounds from tournaments where the debater met the Speaker Tab threshold (>= 3 prelim rounds in that tournament), strictly excluding tournaments where they were ineligible for the speaker tab (e.g. only spoke in 1 or 2 rounds). Default is false."
                    }
                },
                "required": ["metric"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_circuit_summary",
            "description": "Retrieve high-level national circuit vitals: total debaters, schools, tournaments, debates debated, valid speeches scored, and overall national side balance.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_motion_analytics",
            "description": "Retrieve debate motion intelligence: Proposition vs Opposition side bias, preliminary vs knockout side balance, tournament-by-tournament bias, thematic topic win rates (Geopolitics, Economics, Tech/AI, Social, etc.), and extreme/balanced motions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "description": "Optional theme filter (e.g. 'Economics & Development', 'Tech, AI & Science', 'Geopolitics & International Relations')."
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional keyword search for specific motions (e.g. 'AI', 'Pets', 'Jury')."
                    },
                    "extreme_only": {
                        "type": "boolean",
                        "description": "If true, includes the top Proposition-biased, Opposition-biased, and most evenly balanced motions."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tournament_finals",
            "description": "Retrieve Grand Finals and championship clash results across Sri Lankan debate tournaments or for a specific tournament. Includes participating teams, schools/institutions, winners, winning margins, and flags 'is_same_institution_final' for same-school closeouts (e.g. all-Royal or all-DS finals). Supports tournament names or circuit aliases like 'Law Fac', 'SLSDC', 'Chaps', 'Visakha', 'Vijis'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament": {
                        "type": "string",
                        "description": "Optional tournament name, slug, or popular alias (e.g. 'Law Fac', 'SLSDC', 'Chaps', 'VVIDC', 'Vijis', 'AIS'). If omitted, returns Grand Finals across all tournaments in the circuit."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_debate_ballot",
            "description": "Retrieve the official debate scoresheet, ballot, and full speaker lineup for a specific round or matchup. Returns proposition vs opposition teams, speaker positions (1st, 2nd, 3rd, Reply), speech scores, panel ballots, adjudicators, winning side, and margin. Use this whenever the user asks for a debate's ballot, scoresheet, speaker lineup for a round, or who debated for a team in a round.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament": {
                        "type": "string",
                        "description": "Tournament name or popular alias (e.g. 'Chaps', 'SLSDC', 'VVIDC', 'APIIT', 'Vijis', 'AIS', 'Metho')."
                    },
                    "round_number": {
                        "type": "integer",
                        "description": "Round number (e.g. 1, 2, 5, 11)."
                    },
                    "round_name": {
                        "type": "string",
                        "description": "Round name (e.g. 'Round 5', 'Grand Final', 'Quarterfinals')."
                    },
                    "team": {
                        "type": "string",
                        "description": "Team name involved in the debate (e.g. 'DS B', 'DS A', 'RC A')."
                    },
                    "debater": {
                        "type": "string",
                        "description": "Debater name who participated in the debate (e.g. 'Balishta', 'Vidath')."
                    },
                    "debate_id": {
                        "type": "integer",
                        "description": "Direct debate ID if known (e.g. 3411)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_record",
            "description": "Retrieve comprehensive team tournament records, highest team score in a round, highest quality debate (highest combined score), average team score (ATSS), wins/losses, and round-by-round breakdown across the circuit or for a specific tournament. Scores are officially debate-averaged across adjudicators. Use this whenever the user asks about a team's highest score, highest quality debate, or performance at a tournament (e.g. 'DS A', 'DS B', 'RC A').",
            "parameters": {
                "type": "object",
                "properties": {
                    "team_name": {
                        "type": "string",
                        "description": "Team name (e.g. 'DS A', 'DS B', 'RC A', 'Ananda A')."
                    },
                    "tournament": {
                        "type": "string",
                        "description": "Optional tournament name or alias (e.g. 'Chaps', 'SLSDC', 'VVIDC', 'ISDC'). If omitted, returns circuit-wide records and summaries across all tournaments."
                    }
                },
                "required": ["team_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tier_matchup_stats",
            "description": "Calculate win rates, total matchups, win ratios, and score margins between competitive tiers (e.g. Tier A vs Tier B, Tier A vs Tier C) across the circuit or for a specific tournament. Use this whenever the user asks about the win ratio of B teams vs A teams or how lower/higher tiered school teams perform against each other.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tier_a": {
                        "type": "string",
                        "description": "Primary tier (default 'A').",
                        "default": "A"
                    },
                    "tier_b": {
                        "type": "string",
                        "description": "Comparison tier (default 'B').",
                        "default": "B"
                    },
                    "tournament": {
                        "type": "string",
                        "description": "Optional tournament name or alias. If omitted, calculates circuit-wide statistics."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_national_pool",
            "description": "Retrieve debaters with National Team designations ('Trials', 'Nat Pool, Trialed', 'Nat Pool, Direct'), including their school, Master Tab ranking, and substantive average. Use this whenever the user asks about the National Pool, National Trials, or which debaters reached national levels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Optional filter: 'Trials', 'Nat Pool, Trialed', or 'Nat Pool, Direct'. If omitted, returns all debaters in national pool and trials."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Execute a read-only SQL SELECT query against the Atomos SQLite database (atomos.db) to retrieve precise atomic data (speeches, ballots, debates, rounds, tournaments, teams, institutions, persons). Only SELECT queries are permitted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A valid SQLite SELECT query, e.g. 'SELECT p.canonical_name, sp.total_score, r.name FROM speech_performances sp JOIN persons p ON sp.person_id = p.id JOIN rounds r ON sp.round_id = r.id WHERE p.canonical_name LIKE \"%Balishta%\" ORDER BY sp.total_score DESC LIMIT 5'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tournament_bracket",
            "description": "Retrieve the complete elimination knockout bracket tree for a tournament (e.g. 'Chaps', 'SLSDC', 'Visakha', 'Metho', 'RIC', 'Vijis', 'AISDC'), including all stages (Octos, Quarters, Semis, Grand Final), match lineups, scores, margins, adjudicators, and the tournament champion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tournament": {
                        "type": "string",
                        "description": "Tournament name, slug, or popular alias (e.g. 'Chaps', 'SLSDC', 'Law Fac', 'Visakha', 'Metho', 'Vijis', 'AIS', 'RIC')."
                    }
                },
                "required": ["tournament"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_judge_profile",
            "description": "Retrieve an adjudicator profile for a debate judge by name or person ID, including their side bias (Prop vs Opp win %), scoring strictness index relative to circuit benchmark (71.2 pts), average win margin, outround records, and recent debates officiated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "Adjudicator name or person ID (e.g. 'Minithi Hewage', 'Rudhesh Ram', 'Niranya Rathnayake')."
                    }
                },
                "required": ["identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_judge_leaderboard",
            "description": "Retrieve the national adjudicator leaderboard across judges with at least min_debates officiated. Can be sorted by 'debates' (most experienced), 'margin' (highest margins awarded), 'avg_score' (most generous scorers), or 'outrounds' (most elimination stages judged).",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_debates": {
                        "type": "integer",
                        "description": "Minimum debates officiated to appear on the leaderboard (default: 3)."
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["debates", "margin", "avg_score", "outrounds"],
                        "description": "Sorting dimension (default: 'debates')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "predict_matchup",
            "description": "Simulate a competitive debate clash between two teams (e.g. 'DS A' vs 'RC A', or 'LC Red' vs 'VV A') predicting win probability, projected score margin, tactical keys, and national debater roster density.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team_a": {
                        "type": "string",
                        "description": "First team name (e.g. 'DS A', 'RC B', 'AIS Green')."
                    },
                    "team_b": {
                        "type": "string",
                        "description": "Second team name (e.g. 'RC A', 'DS B', 'VV A')."
                    }
                },
                "required": ["team_a", "team_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_debater_adjudicator_record",
            "description": "Retrieve complete official record of all debates where an adjudicator judged a specific debater. Provides exact debate counts (deduplicated by debate ID), individual speech scores, debate sides (Proposition vs Opposition), winning side, and true match outcomes (Won or Lost). Use this whenever asked which judges have judged a debater, how a debater performed under an adjudicator, or whether a judge gave a debater a win or loss.",
            "parameters": {
                "type": "object",
                "properties": {
                    "debater": {
                        "type": "string",
                        "description": "Debater canonical name (e.g. 'Balishta Wijesinghe', 'Vidath Marasinghe')."
                    },
                    "adjudicator": {
                        "type": "string",
                        "description": "Optional adjudicator name filter (e.g. 'Adam Dhilshan', 'Senuka Seneviratne'). If omitted, returns all adjudicators who judged this debater, ranked by most frequent."
                    }
                },
                "required": ["debater"]
            }
        }
    },
]


# ============================================================================
# TOOL DISPATCHER
# ============================================================================

def safe_execute_sql(query_engine: AtomosQuery, sql: str, max_rows: int = 100) -> Dict[str, Any]:
    """Execute a read-only SQL query with safety validation."""
    clean = sql.strip().rstrip(';')
    # Disallow dangerous SQL operations
    forbidden = ["insert", "update", "delete", "drop", "alter", "create", "pragma", "attach", "detach", "replace"]
    tokens = clean.lower().split()
    for tok in tokens:
        clean_tok = tok.strip("(),;\"'`")
        if clean_tok in forbidden:
            return {"error": f"Security violation: SQL token '{clean_tok}' is strictly forbidden. Only read-only SELECT queries are allowed."}
    
    if not (clean.lower().startswith("select") or clean.lower().startswith("with") or clean.lower().startswith("explain")):
        return {"error": "Only SELECT or CTE queries are permitted."}

    try:
        cursor = query_engine.conn.cursor()
        cursor.execute(clean)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(max_rows)
        # Convert rows to dicts
        dict_rows = [dict(zip(columns, r)) for r in rows]
        return {
            "columns": columns,
            "rows": dict_rows,
            "row_count": len(dict_rows),
            "truncated": len(dict_rows) == max_rows
        }
    except Exception as exc:
        return {"error": f"SQL execution error: {str(exc)}"}


def dispatch_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    query_engine: Optional[AtomosQuery] = None,
) -> Dict[str, Any]:
    """
    Execute a tool call by name with arguments and return a structured dictionary.
    
    Args:
        name: Name of tool (e.g. 'search_entities', 'get_debater_profile', 'execute_sql')
        arguments: Dictionary of arguments passed by the LLM
        query_engine: Optional existing AtomosQuery instance
    """
    args = arguments or {}
    owned_query = False
    if query_engine is None:
        query_engine = AtomosQuery()
        owned_query = True

    try:
        if name == "execute_sql":
            q = args.get("query", "")
            return safe_execute_sql(query_engine, q)

        elif name == "search_entities":
            query = args.get("query", "")
            entity_types = args.get("entity_types")
            limit = args.get("limit", 5)
            return {"results": query_engine.search(query, entity_types=entity_types, limit=limit)}

        elif name == "get_debater_profile":
            identifier = args.get("identifier", "")
            compact = args.get("compact", True)
            return query_engine.get_debater(identifier, compact=compact)

        elif name == "get_head_to_head":
            ea = args.get("entity_a", "")
            eb = args.get("entity_b", "")
            mode = args.get("mode", "auto")
            return query_engine.get_head_to_head(ea, eb, mode=mode)

        elif name == "compare_institutions":
            sa = args.get("school_a", "")
            sb = args.get("school_b", "")
            return query_engine.compare_institutions(sa, sb)

        elif name == "get_institutional_leaderboard":
            min_debates = args.get("min_debates", 5)
            return {"leaderboard": query_engine.get_institutional_leaderboard(min_debates=min_debates)}

        elif name == "get_speaker_leaderboard":
            metric = args.get("metric", "master_tab")
            limit = args.get("limit", 10)
            qual = args.get("qualified_tournaments_only", False)
            return query_engine.get_speaker_leaderboard(metric=metric, limit=limit, qualified_tournaments_only=qual)

        elif name == "get_circuit_summary":
            return query_engine.get_circuit_summary()

        elif name == "get_tournament_finals":
            tourn = args.get("tournament")
            return query_engine.get_tournament_finals(tournament=tourn)

        elif name == "get_motion_analytics":
            theme = args.get("theme")
            q = args.get("query")
            extreme_only = args.get("extreme_only", False)
            return query_engine.get_motion_analytics(theme=theme, query=q, extreme_only=extreme_only)

        elif name == "get_debate_ballot":
            tourn = args.get("tournament")
            r_num = args.get("round_number")
            r_name = args.get("round_name")
            team = args.get("team")
            debater = args.get("debater")
            deb_id = args.get("debate_id")
            return query_engine.get_debate_ballot(
                tournament=tourn,
                round_number=r_num,
                round_name=r_name,
                team=team,
                debater=debater,
                debate_id=deb_id,
            )

        elif name == "get_team_record":
            team_name = args.get("team_name", "")
            tourn = args.get("tournament")
            return query_engine.get_team_record(team_name=team_name, tournament=tourn)

        elif name == "get_tier_matchup_stats":
            tier_a = args.get("tier_a", "A")
            tier_b = args.get("tier_b", "B")
            tourn = args.get("tournament")
            return query_engine.get_tier_matchup_stats(tier_a=tier_a, tier_b=tier_b, tournament=tourn)

        elif name == "get_national_pool":
            status = args.get("status")
            return query_engine.get_national_pool(status=status)

        elif name == "get_tournament_bracket":
            tourn = args.get("tournament", "")
            return query_engine.get_tournament_bracket(tourn)

        elif name == "get_judge_profile":
            ident = args.get("identifier") or args.get("judge_name") or args.get("name") or ""
            return query_engine.get_judge_dossier(ident)

        elif name == "get_judge_leaderboard":
            min_deb = args.get("min_debates", 3)
            sort_by = args.get("sort_by", "debates")
            limit = args.get("limit")
            return {"leaderboard": query_engine.get_judge_leaderboard(min_debates=min_deb, sort_by=sort_by, limit=limit)}

        elif name == "predict_matchup":
            ta = args.get("team_a", "")
            tb = args.get("team_b", "")
            return query_engine.predict_matchup(ta, tb)

        elif name == "get_debater_adjudicator_record":
            deb = args.get("debater") or args.get("debater_name") or args.get("identifier") or ""
            adj = args.get("adjudicator") or args.get("adjudicator_name") or args.get("judge")
            return query_engine.get_debater_adjudicator_record(debater=deb, adjudicator=adj)

        else:
            return {"error": f"Unknown tool name '{name}'."}

    except Exception as exc:
        return {"error": f"Tool execution failed for '{name}': {str(exc)}"}

    finally:
        if owned_query:
            query_engine.close()

