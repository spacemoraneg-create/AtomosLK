#!/usr/bin/env python3
"""
Atomos LLM Test, Agent Query & Interactive Chat Console (Ask Atomos)

Features:
1. Natural Language Agent Query: `python scripts/ask_atomos.py "Who is the top speaker from DS?"`
2. Interactive Chat REPL: `python scripts/ask_atomos.py --chat`
3. Headless REST API Server: `python scripts/ask_atomos.py --serve --port 5000`
4. Direct Tool Execution: `search`, `debater`, `h2h`, `schools`, `leaderboard`, `motions`, `circuit`
5. Schema Inspection: `python scripts/ask_atomos.py --tools`

Usage:
    python scripts/ask_atomos.py "Compare Royal College and Ananda College"
    python scripts/ask_atomos.py --chat
    python scripts/ask_atomos.py --serve
    python scripts/ask_atomos.py debater "Balishta"
    python scripts/ask_atomos.py h2h "Royal" "Ananda"
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from atomos.agent.orchestrator import AtomosAgent
from atomos.database.connection import get_connection
from atomos.server import run_server
from atomos.tools import TOOL_SCHEMAS, dispatch_tool


def run_interactive_chat(agent: AtomosAgent):
    """Interactive terminal conversation loop with Atomos."""
    model_name = agent._gemini_agent.model if agent._gemini_agent else "N/A"
    engine_name = f"Google Gemini Cloud LLM ({model_name})" if agent._gemini_agent else "Local Offline Engine"
    print("==================================================================================")
    print("                    ATOMOS AI DEBATE INTELLIGENCE CONSOLE")
    print(f"       Engine: {engine_name} | Grounded in atomos.db")
    print("       Commands: 'exit' to quit | '/reset' or '/clear' to wipe session memory")
    print("==================================================================================")

    while True:
        try:
            query = input("Atomos> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Atomos Console.")
            break

        if not query:
            continue
        if query.lower() in ["exit", "quit", "q"]:
            print("Exiting Atomos Console. Goodbye!")
            break
        if query.lower() in ["/reset", "/clear", "clear", "reset"]:
            agent.reset_memory()
            print("\n🧹 Session conversation memory has been cleared.\n")
            continue
        if query.lower() in ["/history", "/turns"]:
            history_len = len(agent.conversation_history)
            print(f"\n📊 Active session history: {history_len} messages in context.\n")
            continue

        think_msg = "[Thinking... querying Gemini Cloud LLM & atomos.db...]" if agent._gemini_agent else "[Querying local database...]"
        print(f"\n{think_msg}\n")
        res = agent.ask(query)
        print(res.answer)
        print("\n" + "-" * 82 + "\n")


def main():
    known_commands = {"search", "debater", "h2h", "schools", "leaderboard", "circuit", "motions"}

    # Direct one-shot prompt execution (e.g. `python scripts/ask_atomos.py "Who is Balishta?"`)
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in known_commands:
        nl_query = " ".join(sys.argv[1:])
        conn = get_connection()
        agent = AtomosAgent(conn)
        res = agent.ask(nl_query)
        print("\n" + res.answer + "\n")
        conn.close()
        return

    parser = argparse.ArgumentParser(
        description="Atomos Natural Language Query Agent & Testing Console",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-q", "--query", help="Optional natural language query in quotes")
    parser.add_argument("--chat", action="store_true", help="Launch interactive conversational REPL")
    parser.add_argument("--serve", action="store_true", help="Start the headless local REST API server")
    parser.add_argument("--port", type=int, default=5000, help="Port for REST API server (default: 5000)")
    parser.add_argument("--tools", action="store_true", help="Print standard JSON schema tool declarations for LLMs")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON for agent query")

    subparsers = parser.add_subparsers(dest="command", help="Direct tool command to execute")

    # 1. Search
    p_search = subparsers.add_parser("search", help="Search entities (debaters, schools, teams, tournaments, motions)")
    p_search.add_argument("search_query", type=str, help="Search query")
    p_search.add_argument("--type", type=str, help="Filter entity type")
    p_search.add_argument("--limit", type=int, default=5, help="Result limit")

    # 2. Debater
    p_debater = subparsers.add_parser("debater", help="Get debater profile")
    p_debater.add_argument("name", type=str, help="Debater name or Person ID")
    p_debater.add_argument("--full", action="store_true", help="Include full round breakdown (not compact)")

    # 3. Head-to-Head
    p_h2h = subparsers.add_parser("h2h", help="Direct head-to-head clash")
    p_h2h.add_argument("entity_a", type=str, help="First entity name or ID")
    p_h2h.add_argument("entity_b", type=str, help="Second entity name or ID")
    p_h2h.add_argument("--mode", type=str, default="auto", choices=["auto", "debater", "team", "school"], help="Comparison mode")

    # 4. Compare Schools
    p_schools = subparsers.add_parser("schools", help="Compare two institutions side-by-side")
    p_schools.add_argument("school_a", type=str, help="First school name or code")
    p_schools.add_argument("school_b", type=str, help="Second school name or code")

    # 5. Leaderboard
    p_lb = subparsers.add_parser("leaderboard", help="Institutional Power Index leaderboard")
    p_lb.add_argument("--min-debates", type=int, default=5, help="Minimum debates threshold")

    # 6. Circuit
    subparsers.add_parser("circuit", help="Circuit summary vitals")

    # 7. Motions
    p_motions = subparsers.add_parser("motions", help="Motion analytics and side bias")
    p_motions.add_argument("--theme", type=str, help="Filter by theme")
    p_motions.add_argument("--filter-query", type=str, help="Filter by keyword")
    p_motions.add_argument("--extreme", action="store_true", help="Include most biased & balanced motions")

    args = parser.parse_args()

    # 1. Output tools schema
    if args.tools:
        print(json.dumps(TOOL_SCHEMAS, indent=2))
        return

    # 2. Start REST API Server
    if args.serve:
        run_server(port=args.port)
        return

    conn = get_connection()
    agent = AtomosAgent(conn)

    # 3. Interactive Chat REPL
    if args.chat:
        run_interactive_chat(agent)
        conn.close()
        return

    # 4. Direct Subcommands
    if args.command == "search":
        entity_types = [args.type] if args.type else None
        res = dispatch_tool("search_entities", {"query": args.search_query, "entity_types": entity_types, "limit": args.limit})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "debater":
        res = dispatch_tool("get_debater_profile", {"identifier": args.name, "compact": not args.full})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "h2h":
        res = dispatch_tool("get_head_to_head", {"entity_a": args.entity_a, "entity_b": args.entity_b, "mode": args.mode})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "schools":
        res = dispatch_tool("compare_institutions", {"school_a": args.school_a, "school_b": args.school_b})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "leaderboard":
        res = dispatch_tool("get_institutional_leaderboard", {"min_debates": args.min_debates})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "circuit":
        res = dispatch_tool("get_circuit_summary", {})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    elif args.command == "motions":
        res = dispatch_tool("get_motion_analytics", {"theme": args.theme, "query": args.filter_query, "extreme_only": args.extreme})
        print(json.dumps(res, indent=2))
        conn.close()
        return

    # 5. Natural Language Query
    if args.query:
        res = agent.ask(args.query)
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print("\n" + res.answer + "\n")
        conn.close()
        return

    # No arguments given: default to interactive chat
    run_interactive_chat(agent)
    conn.close()


if __name__ == "__main__":
    main()
