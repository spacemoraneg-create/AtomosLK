"""
Atomos Headless REST / JSON API Server

Exposes high-performance, typed JSON endpoints for downstream frontends,
mobile apps, and AI clients using Flask.
"""

import functools
import hashlib
import os
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, jsonify, request, send_from_directory, send_file

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atomos.agent.orchestrator import AtomosAgent
from atomos.database.connection import get_connection
from atomos.query import AtomosQuery
from atomos.tools import dispatch_tool
from atomos.pipeline.ingestion import IngestionPipeline
from atomos.normalizer.validator import IntegrityValidator
from atomos.analytics.v2_metrics import V2MetricsEngine
from atomos.analytics.tournaments import CHRONOLOGICAL_TOURNAMENT_ORDER, CLEAN_TOURNAMENT_NAMES, OFFICIAL_TOURNAMENT_DATES
from atomos.analytics.identity_resolver import IdentityResolver

ADMIN_PASSWORD = "Sexyback"
ADMIN_AUTH_TOKEN = hashlib.sha256(f"{ADMIN_PASSWORD}_atomos_secure_salt_2026".encode("utf-8")).hexdigest()


def create_app(db_conn=None) -> Flask:
    """Application factory for Atomos REST API."""
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    data_export_dir = Path(__file__).resolve().parent.parent.parent / "data" / "web_export"

    app = Flask(__name__)
    conn = db_conn or get_connection(check_same_thread=False)
    query_engine = AtomosQuery(conn)
    agent = AtomosAgent(conn)
    v2_engine = V2MetricsEngine(conn)
    identity_resolver = IdentityResolver(conn)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-Token, X-GitHub-Token"
        return response

    def get_request_github_token() -> Optional[str]:
        req_json = request.get_json(force=True, silent=True) if request.is_json else {}
        token = (
            request.headers.get("X-GitHub-Token")
            or (req_json.get("github_token") if isinstance(req_json, dict) else None)
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
        )
        return str(token).strip() if token else None

    def trigger_async_export_and_sync(commit_message: str, custom_token: Optional[str] = None):
        token_to_use = custom_token or get_request_github_token()

        def _worker():
            try:
                root_dir = Path(__file__).resolve().parent.parent.parent
                if str(root_dir) not in sys.path:
                    sys.path.insert(0, str(root_dir))
                from scripts.export_web_data import export_web_data
                export_web_data(data_export_dir)

                from atomos.sync import GitHubSyncService
                sync_svc = GitHubSyncService(token=token_to_use)
                if sync_svc.is_configured():
                    db_f = Path(__file__).resolve().parent.parent.parent / "data" / "atomos.db"
                    sync_svc.sync_database_and_export(
                        db_path=db_f,
                        export_dir=data_export_dir,
                        commit_message=commit_message,
                    )
            except Exception as exp_err:
                print(f"[WARN] Async static export and sync encountered an issue: {exp_err}")

        threading.Thread(target=_worker, daemon=True).start()

    # Static Web Dashboard Frontend Routes
    @app.route("/")
    def index():
        return send_from_directory(str(web_dir), "index.html")

    @app.route("/leaderboards")
    def page_leaderboards():
        return send_from_directory(str(web_dir), "leaderboards.html")

    @app.route("/bio")
    def page_bio():
        return send_from_directory(str(web_dir), "bio.html")

    @app.route("/h2h")
    def page_h2h():
        return send_from_directory(str(web_dir), "h2h.html")

    @app.route("/chat")
    def page_chat():
        return send_from_directory(str(web_dir), "chat.html")

    @app.route("/admin")
    def page_admin():
        return send_from_directory(str(web_dir), "admin.html")

    @app.route("/team-bio")
    @app.route("/team_bio")
    def page_team_bio():
        return send_from_directory(str(web_dir), "team_bio.html")

    @app.route("/institution-bio")
    @app.route("/institution_bio")
    def page_institution_bio():
        return send_from_directory(str(web_dir), "institution_bio.html")

    @app.route("/adjudicator-bio")
    @app.route("/adjudicator_bio")
    def page_adjudicator_bio():
        return send_from_directory(str(web_dir), "adjudicator_bio.html")

    @app.route("/pool")
    def page_pool():
        return send_from_directory(str(web_dir), "pool.html")

    @app.route("/data/web_export/<path:filename>")
    def serve_export_data(filename):
        return send_from_directory(str(data_export_dir), filename)

    @app.route("/<path:filename>")
    def static_files(filename):
        target = web_dir / filename
        if target.is_file():
            return send_from_directory(str(web_dir), filename)
        target_html = web_dir / f"{filename}.html"
        if target_html.is_file():
            return send_from_directory(str(web_dir), f"{filename}.html")
        return send_from_directory(str(web_dir), "index.html")

    @app.after_request
    def add_cache_control_headers(response):
        if request.path.startswith("/api/") or request.path.startswith("/data/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # 1. Health & Vitals
    @app.route("/api/health", methods=["GET"])
    def health():
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM persons")
        p_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM debates")
        d_cnt = cur.fetchone()["c"]
        return jsonify({
            "status": "online",
            "engine": "Atomos Debate Intelligence Engine",
            "version": "2.0.0",
            "database": {
                "active": True,
                "persons_indexed": p_cnt,
                "contested_debates": d_cnt,
            }
        })

    # 2. Natural Language Agent Q&A
    @app.route("/api/ask", methods=["POST"])
    def ask():
        payload = request.get_json(force=True, silent=True) or {}
        session_id = str(payload.get("session_id") or request.headers.get("X-Session-ID") or "default").strip()

        if payload.get("reset"):
            agent.reset_memory(session_id=session_id)
            return jsonify({"status": "reset", "session_id": session_id, "success": True})

        query = payload.get("query") or request.args.get("q")
        if not query:
            return jsonify({"error": "Missing required field 'query' in JSON body or 'q' query parameter."}), 400

        try:
            result = agent.ask(query, session_id=session_id)
            return jsonify(result.to_dict())
        except Exception as exc:
            try:
                # Deterministic fallback grounded directly in SQLite
                fb_agent = AtomosAgent(conn, use_llm=False)
                res = fb_agent.ask(query)
                return jsonify(res.to_dict())
            except Exception as inner_exc:
                return jsonify({
                    "query": query,
                    "intent": "ERROR",
                    "answer": f"Unable to process query: {str(exc)}",
                    "tool_calls": [],
                    "success": False,
                    "error": str(exc),
                }), 200

    @app.route("/api/chat/reset", methods=["POST"])
    def reset_chat():
        payload = request.get_json(force=True, silent=True) or {}
        session_id = str(payload.get("session_id") or request.headers.get("X-Session-ID") or "default").strip()
        agent.reset_memory(session_id=session_id)
        return jsonify({"status": "reset", "session_id": session_id, "success": True})

    # 3. Unified Entity Search
    @app.route("/api/search", methods=["GET"])
    def search():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "Query parameter 'q' is required."}), 400
        entity_type = request.args.get("type")
        types = [entity_type] if entity_type else None
        limit = int(request.args.get("limit", 10))

        results = query_engine.search(q, entity_types=types, limit=limit)
        return jsonify({"query": q, "results": results})

    # 4. Debater Dossier
    @app.route("/api/debaters/<identifier>", methods=["GET"])
    def get_debater(identifier: str):
        compact = request.args.get("compact", "true").lower() in ["true", "1", "yes"]
        profile = query_engine.get_debater(identifier, compact=compact)
        if "error" in profile:
            return jsonify(profile), 404
        return jsonify(profile)

    # 5. Debater Mathematical Derivation
    @app.route("/api/debaters/<identifier>/derivation", methods=["GET"])
    def get_debater_derivation(identifier: str):
        profile = query_engine.get_debater(identifier, compact=False)
        if "error" in profile:
            return jsonify(profile), 404
        return jsonify({
            "person_id": profile.get("person_id"),
            "canonical_name": profile.get("canonical_name"),
            "derivation_text": profile.get("derivation_text"),
        })

    # 6. Head-to-Head Comparison
    @app.route("/api/h2h", methods=["GET"])
    def get_head_to_head():
        ea = request.args.get("a")
        eb = request.args.get("b")
        mode = request.args.get("mode", "auto")
        if not ea or not eb:
            return jsonify({"error": "Both 'a' and 'b' query parameters are required."}), 400

        result = query_engine.get_head_to_head(ea, eb, mode=mode)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    # 7. Institutional Leaderboard
    @app.route("/api/institutions", methods=["GET"])
    def get_institutions():
        sort_by = request.args.get("sort_by", "delta")
        top_n = int(request.args.get("top", 25))
        if sort_by == "ipi":
            min_debates = int(request.args.get("min_debates", 2))
            leaderboard = query_engine.get_institutional_leaderboard(min_debates=min_debates, sort_by="ipi")
        else:
            leaderboard = query_engine.get_institutional_delta_leaderboard()
        return jsonify({"leaderboard": leaderboard[:top_n], "total_ranked": len(leaderboard)})

    # 8. Institution Dossier
    @app.route("/api/institutions/<identifier>", methods=["GET"])
    def get_institution(identifier: str):
        prof = query_engine._inst_engine.get_institution_profile(identifier)
        if not prof:
            return jsonify({"error": f"Institution '{identifier}' not found."}), 404
        return jsonify(prof.__dict__)

    # 9. Institutional Head-to-Head
    @app.route("/api/institutions/compare", methods=["GET"])
    def compare_institutions():
        sa = request.args.get("a")
        sb = request.args.get("b")
        if not sa or not sb:
            return jsonify({"error": "Both 'a' and 'b' parameters are required."}), 400
        result = query_engine.compare_institutions(sa, sb)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    # 10. Motion Summary & Dynamics
    @app.route("/api/motions/summary", methods=["GET"])
    def get_motions_summary():
        theme = request.args.get("theme")
        q = request.args.get("q")
        analytics = query_engine.get_motion_analytics(theme=theme, query=q, extreme_only=True)
        return jsonify(analytics)

    # 11. Circuit High-Level Summary
    @app.route("/api/circuit", methods=["GET"])
    def get_circuit():
        summary = query_engine.get_circuit_summary()
        return jsonify(summary)

    # 12. Full Debater Profile (with Trajectory)
    @app.route("/api/debaters/<identifier>/profile", methods=["GET"])
    def get_debater_profile_full(identifier: str):
        profile = query_engine.get_debater(identifier, compact=False)
        if "error" in profile:
            return jsonify(profile), 404
        return jsonify(profile)

    # 13. Multi-Metric Speaker Leaderboard
    @app.route("/api/leaderboard/speakers", methods=["GET"])
    def get_speakers_leaderboard():
        metric = request.args.get("metric", "master_tab")
        limit = int(request.args.get("limit", 20))
        qual = request.args.get("qualified_tournaments_only", "false").lower() in ["true", "1", "yes"]
        nat_filter = request.args.get("nat_status")
        res = query_engine.get_speaker_leaderboard(metric=metric, limit=limit, qualified_tournaments_only=qual)
        if nat_filter and "leaderboard" in res:
            res["leaderboard"] = [
                r for r in res["leaderboard"]
                if r.get("national_level") and nat_filter.lower() in r["national_level"].lower()
            ]
            res["total_returned"] = len(res["leaderboard"])
        return jsonify(res)

    # 13b. Multi-Metric Team Leaderboard
    @app.route("/api/leaderboard/teams", methods=["GET"])
    def get_teams_leaderboard():
        mode = request.args.get("mode", "master").lower()
        min_tournaments = int(request.args.get("min_tournaments", 3))
        limit = request.args.get("limit")
        teams = query_engine._critical_engine.get_critical_team_stats(min_tournaments=min_tournaments)
        if limit:
            teams = teams[:int(limit)]
        return jsonify({
            "mode": mode,
            "min_tournaments": min_tournaments,
            "leaderboard": teams,
            "total_returned": len(teams),
        })

    # 13c. Activity Leaderboard
    @app.route("/api/leaderboard/activity", methods=["GET"])
    def get_activity_leaderboard():
        limit = request.args.get("limit")
        lb = query_engine.get_activity_leaderboard()
        if limit:
            lb = lb[:int(limit)]
        return jsonify({
            "leaderboard": lb,
            "total_returned": len(lb),
        })

    # 13d. Tournament Quality Rankings (APTTSS)
    @app.route("/api/leaderboard/tournaments", methods=["GET"])
    def get_tournament_rankings():
        limit = request.args.get("limit")
        rankings = query_engine.get_tournament_rankings()
        if limit:
            rankings = rankings[:int(limit)]
        return jsonify({
            "leaderboard": rankings,
            "total_returned": len(rankings),
        })

    # 14. Tournament Knockout Bracket
    @app.route("/api/tournaments/<slug>/bracket", methods=["GET"])
    def get_bracket(slug: str):
        result = query_engine.get_tournament_bracket(slug)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    # 15. Adjudicator Intelligence
    @app.route("/api/judges/<identifier>", methods=["GET"])
    def get_judge(identifier: str):
        dossier = query_engine.get_judge_dossier(identifier)
        if "error" in dossier:
            return jsonify(dossier), 404
        return jsonify(dossier)

    @app.route("/api/judges", methods=["GET"])
    def get_judges():
        min_deb = int(request.args.get("min_debates", 3))
        sort_by = request.args.get("sort", "debates")
        limit = int(request.args.get("limit", 25))
        lb = query_engine.get_judge_leaderboard(min_debates=min_deb, sort_by=sort_by)
        return jsonify({"leaderboard": lb[:limit], "total_ranked": len(lb)})

    # 16. Match Clash Predictor
    @app.route("/api/predict", methods=["GET"])
    def predict_clash():
        team_a = request.args.get("team_a") or request.args.get("a")
        team_b = request.args.get("team_b") or request.args.get("b")
        if not team_a or not team_b:
            return jsonify({"error": "Both 'team_a' and 'team_b' query parameters are required."}), 400
        result = query_engine.predict_matchup(team_a, team_b)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    # 17. National Team Pool Registry
    @app.route("/api/national-pool", methods=["GET"])
    def get_nat_pool():
        status = request.args.get("status")
        pool = query_engine.get_national_pool(status=status)
        return jsonify({"total_contingent": len(pool), "debaters": pool})

    # 18. Detailed Debate Scoresheet
    @app.route("/api/debates/<int:debate_id>", methods=["GET"])
    def get_debate(debate_id: int):
        ballot = query_engine.get_debate_ballot(debate_id=debate_id)
        if "error" in ballot:
            return jsonify(ballot), 404
        return jsonify(ballot)

    # =========================================================================
    # ATOMOS V2 REST API ENDPOINTS
    # =========================================================================

    @app.route("/api/v2/leaderboard/speakers", methods=["GET"])
    def v2_speakers_lb():
        tier = request.args.get("tier", "tab").lower()
        sort_by = request.args.get("sort", "speaker_score").lower()
        limit = request.args.get("limit")
        data = v2_engine.get_multipurpose_speakers(tier=tier, sort_by=sort_by)
        if limit and limit.isdigit():
            data = data[:int(limit)]
        return jsonify({
            "tier": tier,
            "sort_by": sort_by,
            "leaderboard": data,
            "total_returned": len(data),
        })

    @app.route("/api/v2/leaderboard/teams", methods=["GET"])
    def v2_teams_lb():
        tier = request.args.get("tier", "tab").lower()
        sort_by = request.args.get("sort", "atss").lower()
        limit = request.args.get("limit")
        data = v2_engine.get_multipurpose_teams(tier=tier, sort_by=sort_by)
        if limit and limit.isdigit():
            data = data[:int(limit)]
        return jsonify({
            "tier": tier,
            "sort_by": sort_by,
            "leaderboard": data,
            "total_returned": len(data),
        })

    @app.route("/api/v2/leaderboard/institutions", methods=["GET"])
    def v2_institutions_lb():
        tier = request.args.get("tier", "tab").lower()
        sort_by = request.args.get("sort", "delta").lower()
        limit = request.args.get("limit")
        data = v2_engine.get_multipurpose_institutions(tier=tier, sort_by=sort_by)
        if limit and limit.isdigit():
            data = data[:int(limit)]
        return jsonify({
            "tier": tier,
            "sort_by": sort_by,
            "leaderboard": data,
            "total_returned": len(data),
        })

    @app.route("/api/v2/leaderboard/tournaments", methods=["GET"])
    def v2_tournaments_lb():
        sort_by = request.args.get("sort", "atss").lower()
        data = v2_engine.get_tournament_hard_rankings(sort_by=sort_by)
        limit = request.args.get("limit")
        if limit and limit.isdigit():
            data = data[:int(limit)]
        return jsonify({
            "sort_by": sort_by,
            "leaderboard": data,
            "total_returned": len(data),
        })

    @app.route("/api/v2/leaderboard/adjudicators", methods=["GET"])
    def v2_adjudicators_lb():
        sort_by = request.args.get("sort", "debates").lower()
        data = v2_engine.get_adjudicator_leaderboard()
        if sort_by == "aass":
            data.sort(key=lambda x: -x["aass"])
        elif sort_by == "aatss":
            data.sort(key=lambda x: -x["aatss"])
        elif sort_by == "tournaments":
            data.sort(key=lambda x: -x["tournaments_adjudicated"])
        else:
            data.sort(key=lambda x: -x["prelims_adjudicated"])
        for idx, j in enumerate(data, start=1):
            j["rank"] = idx
        limit = request.args.get("limit")
        if limit and limit.isdigit():
            data = data[:int(limit)]
        return jsonify({
            "sort_by": sort_by,
            "leaderboard": data,
            "total_returned": len(data),
        })

    @app.route("/api/v2/pool", methods=["GET"])
    def v2_national_pool():
        return jsonify(v2_engine.get_national_pool_tiers())

    @app.route("/api/v2/debaters/<path:identifier>/bio", methods=["GET"])
    def v2_debater_bio(identifier: str):
        profile = v2_engine.get_debater_v2_profile(identifier)
        if not profile:
            return jsonify({"error": f"Debater '{identifier}' not found"}), 404
        return jsonify(profile)

    @app.route("/api/v2/teams/<path:team_name>/bio", methods=["GET"])
    def v2_team_bio(team_name: str):
        bio = v2_engine.get_team_bio(team_name)
        if not bio:
            return jsonify({"error": f"Team '{team_name}' not found"}), 404
        return jsonify(bio)

    @app.route("/api/v2/institutions/<path:inst_name>/bio", methods=["GET"])
    def v2_institution_bio(inst_name: str):
        bio = v2_engine.get_institution_bio(inst_name)
        if not bio:
            return jsonify({"error": f"Institution '{inst_name}' not found"}), 404
        return jsonify(bio)

    @app.route("/api/v2/adjudicators/<path:judge_name>/bio", methods=["GET"])
    def v2_adjudicator_bio(judge_name: str):
        bio = v2_engine.get_adjudicator_bio(judge_name)
        if not bio:
            return jsonify({"error": f"Adjudicator '{judge_name}' not found"}), 404
        return jsonify(bio)

    # =========================================================================
    # ADMINISTRATIVE API ENDPOINTS (PROTECTED BY PASSWORD "Olivedelight")
    # =========================================================================

    def require_admin(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("X-Admin-Token") or request.args.get("token")
            if not token or token != ADMIN_AUTH_TOKEN:
                return jsonify({"error": "Administrative authentication required. Access denied.", "authenticated": False}), 401
            return f(*args, **kwargs)
        return decorated

    # 19. Admin Authentication
    @app.route("/api/admin/login", methods=["POST"])
    def admin_login():
        payload = request.get_json(force=True, silent=True) or {}
        password = payload.get("password", "").strip()
        if password == ADMIN_PASSWORD:
            return jsonify({
                "success": True,
                "token": ADMIN_AUTH_TOKEN,
                "message": "Administrative access granted.",
                "authenticated": True,
            })
        return jsonify({
            "success": False,
            "error": "Invalid administrative password. Access denied.",
            "authenticated": False,
        }), 401

    @app.route("/api/admin/verify", methods=["GET"])
    def admin_verify():
        token = request.headers.get("X-Admin-Token") or request.args.get("token")
        if token and token == ADMIN_AUTH_TOKEN:
            return jsonify({"authenticated": True, "status": "authorized"})
        return jsonify({"authenticated": False, "error": "Unauthorized"}), 401

    # 20. Admin System & Database Status
    @app.route("/api/admin/status", methods=["GET"])
    @require_admin
    def admin_status():
        db_file = Path("data/atomos.db").resolve()
        file_size_mb = round(db_file.stat().st_size / (1024 * 1024), 2) if db_file.exists() else 0
        mtime = db_file.stat().st_mtime if db_file.exists() else 0
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if mtime else "N/A"

        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        integrity_row = cur.fetchone()
        integrity_status = integrity_row[0] if integrity_row else "unknown"

        cur.execute("SELECT COUNT(*) as c FROM tournaments")
        t_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM debates")
        d_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM debates WHERE is_walkover = 0")
        contested_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM debates WHERE is_walkover = 1")
        walkover_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM rounds")
        r_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM adjudicator_ballots")
        b_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM speech_performances")
        sp_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM adjudicator_ballots WHERE adjudicator_raw_name = 'Official Tab Reconciled'")
        fallback_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM persons")
        p_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM teams")
        tm_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM institutions")
        inst_cnt = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) as c FROM persons WHERE national_level IS NOT NULL")
        nat_cnt = cur.fetchone()["c"]

        # Full tournaments list with live aggregates
        cur.execute("""
            SELECT t.id, t.slug, t.name, t.year, t.format, t.source_url, t.hosting_dates, t.created_at,
                   (SELECT COUNT(*) FROM debates d JOIN rounds r ON d.round_id = r.id WHERE r.tournament_id = t.id) as debate_count,
                   (SELECT COUNT(*) FROM rounds r WHERE r.tournament_id = t.id) as round_count,
                   (SELECT COUNT(*) FROM teams tm WHERE tm.tournament_id = t.id) as team_count,
                   (SELECT COUNT(*) FROM speech_performances sp JOIN rounds r ON sp.round_id = r.id WHERE r.tournament_id = t.id) as speech_count
            FROM tournaments t
            ORDER BY t.id ASC
        """)
        raw_tournaments = [dict(row) for row in cur.fetchall()]
        for t in raw_tournaments:
            t["official_name"] = CLEAN_TOURNAMENT_NAMES.get(t["id"], t["name"])
            t["hosting_dates"] = t.get("hosting_dates") or OFFICIAL_TOURNAMENT_DATES.get(t["id"], "2026")
            t["chrono_order"] = CHRONOLOGICAL_TOURNAMENT_ORDER.get(t["id"], 999)

        tournaments = sorted(raw_tournaments, key=lambda x: x["chrono_order"])

        return jsonify({
            "authenticated": True,
            "database": {
                "file_path": str(db_file),
                "file_size_mb": file_size_mb,
                "last_modified": last_modified,
                "integrity_check": integrity_status,
                "tournaments_count": t_cnt,
                "debates_count": d_cnt,
                "contested_debates": contested_cnt,
                "walkover_debates": walkover_cnt,
                "rounds_count": r_cnt,
                "ballots_count": b_cnt,
                "speeches_count": sp_cnt,
                "fallback_ballots": fallback_cnt,
                "persons_count": p_cnt,
                "teams_count": tm_cnt,
                "institutions_count": inst_cnt,
                "national_pool_count": nat_cnt,
            },
            "tournaments": tournaments,
        })

    # 21. Tournament Ingestion Pipeline Trigger & Status
    ingestion_job_lock = threading.Lock()
    ingestion_job_state = {
        "status": "idle",
        "target": "",
        "slug": "",
        "step": "",
        "message": "No ingestion active.",
        "data": None,
        "error": None,
        "started_at": None,
        "finished_at": None,
    }

    @app.route("/api/admin/tournaments/import", methods=["POST"])
    @require_admin
    def admin_import_tournament():
        payload = request.get_json(force=True, silent=True) or {}
        target = payload.get("target", "").strip()
        skip_extract = bool(payload.get("skip_extract", False))
        hosting_dates = (payload.get("hosting_dates") or "").strip() or None
        req_token = get_request_github_token()

        if not target:
            return jsonify({"error": "Target URL or local slug is required."}), 400

        with ingestion_job_lock:
            if ingestion_job_state["status"] == "running":
                return jsonify({
                    "success": False,
                    "error": f"An ingestion pipeline is already running for '{ingestion_job_state.get('target')}'.",
                    "status": "running",
                }), 409

            ingestion_job_state["status"] = "running"
            ingestion_job_state["target"] = target
            ingestion_job_state["slug"] = target.rstrip("/").split("/")[-1]
            ingestion_job_state["step"] = "STARTING"
            ingestion_job_state["message"] = f"Initializing ingestion pipeline for '{target}'..."
            ingestion_job_state["data"] = None
            ingestion_job_state["error"] = None
            ingestion_job_state["started_at"] = time.time()
            ingestion_job_state["finished_at"] = None

        def _worker():
            try:
                def _on_progress(step_key: str, msg: str):
                    with ingestion_job_lock:
                        ingestion_job_state["step"] = step_key
                        ingestion_job_state["message"] = msg

                pipeline = IngestionPipeline(db_path=Path("data/atomos.db"))
                res = pipeline.ingest_tournament(
                    target=target,
                    skip_extract=skip_extract,
                    verbose=True,
                    hosting_dates=hosting_dates,
                    progress_callback=_on_progress,
                )

                t_label = res.get("slug", target)
                with ingestion_job_lock:
                    ingestion_job_state["step"] = "SYNCING"
                    ingestion_job_state["message"] = f"Exporting static web data and syncing to GitHub for '{t_label}'..."

                trigger_async_export_and_sync(
                    commit_message=f"chore(data): auto-sync after importing tournament {t_label}",
                    custom_token=req_token,
                )

                with ingestion_job_lock:
                    ingestion_job_state["status"] = "success"
                    ingestion_job_state["step"] = "COMPLETED"
                    ingestion_job_state["data"] = res
                    ingestion_job_state["message"] = f"Tournament '{t_label}' successfully imported."
                    ingestion_job_state["finished_at"] = time.time()
            except Exception as e:
                with ingestion_job_lock:
                    ingestion_job_state["status"] = "error"
                    ingestion_job_state["step"] = "FAILED"
                    ingestion_job_state["error"] = str(e)
                    ingestion_job_state["message"] = f"Ingestion failed: {str(e)}"
                    ingestion_job_state["finished_at"] = time.time()

        threading.Thread(target=_worker, daemon=True).start()

        return jsonify({
            "success": True,
            "status": "running",
            "message": f"Ingestion pipeline launched in background for '{target}'.",
            "target": target,
        })

    @app.route("/api/admin/tournaments/import/status", methods=["GET"])
    @require_admin
    def admin_import_status():
        with ingestion_job_lock:
            return jsonify(dict(ingestion_job_state))

    # 22. Tournament Purge / Deletion (Cascading)
    @app.route("/api/admin/tournaments/<identifier>", methods=["DELETE"])
    @require_admin
    def admin_delete_tournament(identifier: str):
        cur = conn.cursor()
        if identifier.isdigit():
            cur.execute("SELECT id, slug, name FROM tournaments WHERE id = ?", (int(identifier),))
        else:
            cur.execute("SELECT id, slug, name FROM tournaments WHERE slug = ?", (identifier,))
        t = cur.fetchone()
        if not t:
            return jsonify({"error": f"Tournament '{identifier}' not found in database."}), 404

        t_id = t["id"]
        t_name = t["name"]
        t_slug = t["slug"]

        try:
            cur.execute("PRAGMA foreign_keys = ON;")
            cur.execute("DELETE FROM provenance_records WHERE tournament_id = ?", (t_id,))
            cur.execute("""
                DELETE FROM speech_performances WHERE debate_id IN (
                    SELECT d.id FROM debates d JOIN rounds r ON d.round_id = r.id WHERE r.tournament_id = ?
                )
            """, (t_id,))
            cur.execute("""
                DELETE FROM adjudicator_ballots WHERE debate_id IN (
                    SELECT d.id FROM debates d JOIN rounds r ON d.round_id = r.id WHERE r.tournament_id = ?
                )
            """, (t_id,))
            cur.execute("""
                DELETE FROM adjudicator_assignments WHERE debate_id IN (
                    SELECT d.id FROM debates d JOIN rounds r ON d.round_id = r.id WHERE r.tournament_id = ?
                )
            """, (t_id,))
            cur.execute("""
                DELETE FROM debates WHERE round_id IN (
                    SELECT id FROM rounds WHERE tournament_id = ?
                )
            """, (t_id,))
            cur.execute("DELETE FROM rounds WHERE tournament_id = ?", (t_id,))
            cur.execute("""
                DELETE FROM team_members WHERE team_id IN (
                    SELECT id FROM teams WHERE tournament_id = ?
                )
            """, (t_id,))
            cur.execute("""
                DELETE FROM team_resolutions WHERE team_id IN (
                    SELECT id FROM teams WHERE tournament_id = ?
                )
            """, (t_id,))
            cur.execute("DELETE FROM teams WHERE tournament_id = ?", (t_id,))
            cur.execute("DELETE FROM tournament_roles WHERE tournament_id = ?", (t_id,))
            cur.execute("DELETE FROM person_aliases WHERE source_tournament_id = ?", (t_id,))
            cur.execute("DELETE FROM tournaments WHERE id = ?", (t_id,))
            conn.commit()

            # Refresh static web exports and auto-sync to GitHub
            trigger_async_export_and_sync(
                commit_message=f"chore(data): auto-sync after deleting tournament {t_slug}"
            )

            return jsonify({
                "success": True,
                "message": f"Tournament '{t_name}' ({t_slug}) and all associated records deleted.",
                "deleted_id": t_id,
                "deleted_slug": t_slug,
            })
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Failed to delete tournament: {str(e)}"}), 500

    # 22b. Update Tournament Hosting Dates
    @app.route("/api/admin/tournaments/<identifier>/dates", methods=["POST"])
    @require_admin
    def admin_update_tournament_dates(identifier: str):
        payload = request.get_json(force=True, silent=True) or {}
        dates_raw = payload.get("hosting_dates", "")
        hosting_dates = str(dates_raw).strip() if dates_raw is not None else ""

        cur = conn.cursor()
        if identifier.isdigit():
            cur.execute("SELECT id, slug, name, hosting_dates FROM tournaments WHERE id = ?", (int(identifier),))
        else:
            cur.execute("SELECT id, slug, name, hosting_dates FROM tournaments WHERE slug = ?", (identifier,))
        t = cur.fetchone()
        if not t:
            return jsonify({"error": f"Tournament '{identifier}' not found in database."}), 404

        t_id = t["id"]
        t_slug = t["slug"]
        t_name = t["name"]

        try:
            cur.execute("UPDATE tournaments SET hosting_dates = ? WHERE id = ?", (hosting_dates or None, t_id))
            conn.commit()

            trigger_async_export_and_sync(
                commit_message=f"chore(data): update hosting dates for tournament {t_slug}"
            )

            return jsonify({
                "success": True,
                "message": f"Hosting dates for '{t_name}' updated successfully.",
                "tournament_id": t_id,
                "tournament_slug": t_slug,
                "hosting_dates": hosting_dates or None,
            })
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Failed to update tournament dates: {str(e)}"}), 500

    # 23. Diagnostic Testing Runner
    @app.route("/api/admin/run_tests", methods=["POST"])
    @require_admin
    def admin_run_tests():
        payload = request.get_json(force=True, silent=True) or {}
        suite = payload.get("suite", "integrity").lower()
        start_time = time.time()

        if suite == "integrity":
            try:
                validator = IntegrityValidator(conn)
                report = validator.validate()
                duration = round(time.time() - start_time, 2)
                return jsonify({
                    "success": report.is_valid,
                    "suite": "integrity",
                    "report": report.summary(),
                    "stats": report.stats,
                    "critical_errors": report.critical_errors,
                    "anomalies": report.domain_anomalies,
                    "duration_seconds": duration,
                })
            except Exception as e:
                return jsonify({"error": f"Integrity check failed: {str(e)}"}), 500

        elif suite in ("unit", "accuracy", "all"):
            if suite == "accuracy":
                cmd = [
                    sys.executable, "-m", "pytest",
                    "tests/test_normalizer.py",
                    "tests/test_critical_stats.py",
                    "tests/test_data_accuracy.py",
                    "tests/test_v2_metrics.py",
                    "tests/test_adjudicator_accuracy.py",
                    "-v"
                ]
                suite_timeout = 90
            elif suite == "all":
                cmd = [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short"]
                suite_timeout = 180
            else:
                cmd = [sys.executable, "-m", "pytest", "tests/test_normalizer.py", "tests/test_critical_stats.py", "-v"]
                suite_timeout = 90

            root_dir = str(Path(__file__).resolve().parent.parent.parent)
            env = os.environ.copy()
            env["PYTHONPATH"] = "src"

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=root_dir,
                    capture_output=True,
                    text=True,
                    timeout=suite_timeout,
                    env=env,
                )
                duration = round(time.time() - start_time, 2)
                output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                return jsonify({
                    "success": proc.returncode == 0,
                    "suite": suite,
                    "exit_code": proc.returncode,
                    "output": output.strip(),
                    "duration_seconds": duration,
                })
            except subprocess.TimeoutExpired:
                return jsonify({"error": f"Test suite timed out after {suite_timeout} seconds."}), 504
            except Exception as e:
                return jsonify({"error": f"Test runner execution error: {str(e)}"}), 500

        return jsonify({"error": f"Unknown test suite '{suite}'. Options: 'integrity', 'accuracy', 'unit', 'all'"}), 400

    # 24. Identity Resolver & Merger Endpoints
    @app.route("/api/admin/merges/suggestions", methods=["GET"])
    @require_admin
    def admin_merge_suggestions():
        try:
            persons = identity_resolver.get_person_suggestions()
            teams = identity_resolver.get_team_suggestions()
            return jsonify({
                "success": True,
                "persons": persons,
                "teams": teams,
                "counts": {
                    "persons": len(persons),
                    "teams": len(teams),
                }
            })
        except Exception as e:
            return jsonify({"error": f"Failed to compute merge suggestions: {str(e)}"}), 500

    @app.route("/api/admin/merges/execute", methods=["POST"])
    @require_admin
    def admin_merge_execute():
        payload = request.get_json(force=True, silent=True) or {}
        entity_type = payload.get("type", "").strip().lower()
        primary_id = payload.get("primary_id")
        duplicate_id = payload.get("duplicate_id")

        if not entity_type or primary_id is None or duplicate_id is None:
            return jsonify({"error": "Missing required fields: type ('person'|'team'), primary_id, duplicate_id"}), 400

        try:
            primary_id = int(primary_id)
            duplicate_id = int(duplicate_id)
            if entity_type == "person":
                res = identity_resolver.execute_person_merge(primary_id, duplicate_id)
            elif entity_type == "team":
                res = identity_resolver.execute_team_merge(primary_id, duplicate_id)
            else:
                return jsonify({"error": f"Invalid entity type '{entity_type}'. Must be 'person' or 'team'."}), 400

            # Re-export static cache and auto-sync to GitHub asynchronously
            trigger_async_export_and_sync(
                commit_message=f"chore(data): auto-sync after merge {entity_type} #{duplicate_id} -> #{primary_id}"
            )

            return jsonify(res)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Merge failed: {str(e)}"}), 500

    @app.route("/api/admin/merges/dismiss", methods=["POST"])
    @require_admin
    def admin_merge_dismiss():
        payload = request.get_json(force=True, silent=True) or {}
        entity_type = payload.get("type", "").strip().lower()
        id_a = payload.get("id_a")
        id_b = payload.get("id_b")

        if not entity_type or id_a is None or id_b is None:
            return jsonify({"error": "Missing required fields: type ('person'|'team'), id_a, id_b"}), 400

        try:
            id_a = int(id_a)
            id_b = int(id_b)
            identity_resolver.dismiss_suggestion(entity_type, id_a, id_b)
            return jsonify({"success": True, "message": f"Suggestion dismissed."})
        except Exception as e:
            return jsonify({"error": f"Failed to dismiss suggestion: {str(e)}"}), 500

    @app.route("/api/admin/database/download", methods=["GET"])
    @require_admin
    def admin_database_download():
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "atomos.db"
        if not db_path.exists():
            return jsonify({"error": "Database file data/atomos.db not found"}), 404
        return send_file(
            db_path,
            as_attachment=True,
            download_name="atomos.db",
            mimetype="application/x-sqlite3",
        )

    @app.route("/api/admin/export/download", methods=["GET"])
    @require_admin
    def admin_export_download():
        import io, zipfile
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(data_export_dir):
                for file in files:
                    abs_file = Path(root) / file
                    rel_path = abs_file.relative_to(data_export_dir)
                    zf.write(abs_file, str(rel_path))
        memory_file.seek(0)
        return send_file(
            memory_file,
            as_attachment=True,
            download_name="atomos_web_export.zip",
            mimetype="application/zip",
        )

    @app.route("/api/admin/github/status", methods=["GET"])
    @require_admin
    def admin_github_status():
        from atomos.sync import GitHubSyncService
        token = get_request_github_token()
        sync_svc = GitHubSyncService(token=token)
        return jsonify({
            "configured": sync_svc.is_configured(),
            "repo": sync_svc.repo,
            "branch": sync_svc.branch,
        })

    @app.route("/api/admin/github/sync", methods=["POST"])
    @require_admin
    def admin_github_sync():
        from atomos.sync import GitHubSyncService
        payload = request.get_json(force=True, silent=True) or {}
        token = get_request_github_token()
        message = payload.get("message") or "chore(data): manual sync of database and web export from admin console"
        
        sync_svc = GitHubSyncService(token=token)
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "atomos.db"
        res = sync_svc.sync_database_and_export(db_path=db_path, export_dir=data_export_dir, commit_message=message)
        status_code = 200 if res.get("success") else 400
        return jsonify(res), status_code

    @app.route("/api/admin/institutions/list", methods=["GET"])
    @require_admin
    def admin_institutions_list():
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT i.id, i.name, i.code, COUNT(t.id) as team_count
                FROM institutions i
                LEFT JOIN teams t ON t.institution_id = i.id
                GROUP BY i.id
                ORDER BY i.name ASC
            """)
            institutions = [dict(r) for r in cur.fetchall()]
            return jsonify({"success": True, "institutions": institutions, "count": len(institutions)})
        except Exception as e:
            return jsonify({"error": f"Failed to list institutions: {str(e)}"}), 500

    @app.route("/api/admin/institutions/<identifier>/teams", methods=["GET"])
    @require_admin
    def admin_institution_teams(identifier: str):
        try:
            cur = conn.cursor()
            identifier_clean = identifier.strip()
            if identifier_clean.isdigit():
                cur.execute("SELECT id, name, code FROM institutions WHERE id = ?", (int(identifier_clean),))
            else:
                cur.execute(
                    "SELECT id, name, code FROM institutions WHERE LOWER(name) = LOWER(?) OR LOWER(code) = LOWER(?)",
                    (identifier_clean, identifier_clean)
                )
            inst = cur.fetchone()
            if not inst:
                cur.execute(
                    "SELECT id, name, code FROM institutions WHERE LOWER(name) LIKE LOWER(?) ORDER BY LENGTH(name) ASC LIMIT 1",
                    (f"%{identifier_clean}%",)
                )
                inst = cur.fetchone()

            if not inst:
                return jsonify({"error": f"Institution '{identifier}' not found."}), 404

            inst_id = inst["id"]

            # Ensure confirmed_team_merges tracking table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS confirmed_team_merges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    institution_id INTEGER NOT NULL,
                    target_canonical_name TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(institution_id, variant_name)
                )
            """)

            cur.execute("""
                SELECT t.id, t.name, t.canonical_name, t.tier, t.tournament_id,
                       tour.name as tournament_name, tour.slug as tournament_slug, tour.year,
                       (SELECT COUNT(*) FROM speech_performances sp WHERE sp.team_id = t.id) as speech_count,
                       (SELECT COUNT(DISTINCT d.id) FROM debates d WHERE d.prop_team_id = t.id OR d.opp_team_id = t.id) as debate_count,
                       (SELECT GROUP_CONCAT(DISTINCT p.canonical_name) 
                        FROM team_members tm 
                        JOIN persons p ON tm.person_id = p.id 
                        WHERE tm.team_id = t.id) as members
                FROM teams t
                JOIN tournaments tour ON t.tournament_id = tour.id
                WHERE t.institution_id = ?
                ORDER BY tour.id ASC, t.name ASC
            """, (inst_id,))
            raw_teams = cur.fetchall()

            # Group teams by distinct team name (t.name)
            grouped = defaultdict(lambda: {
                "name": "",
                "canonical_name": "",
                "tier": "",
                "instance_count": 0,
                "team_ids": [],
                "tournaments": [],
                "all_members": set(),
                "total_debates": 0,
                "total_speeches": 0,
                "merged_variants": set(),
            })

            teams_list = []
            for r in raw_teams:
                d = dict(r)
                d["official_tournament_name"] = CLEAN_TOURNAMENT_NAMES.get(d["tournament_id"], d["tournament_name"])
                teams_list.append(d)

                name = r["name"]
                g = grouped[name]
                g["name"] = name
                row_canon = (r["canonical_name"] or "").strip()
                if row_canon and row_canon != name:
                    g["canonical_name"] = row_canon
                elif not g["canonical_name"]:
                    g["canonical_name"] = row_canon or name
                if r["tier"]:
                    g["tier"] = r["tier"]
                elif not g["tier"]:
                    g["tier"] = "A" if name.endswith(" A") else ("B" if name.endswith(" B") else None)
                g["instance_count"] += 1
                g["team_ids"].append(r["id"])

                g["tournaments"].append({
                    "id": r["tournament_id"],
                    "name": d["official_tournament_name"],
                    "slug": r["tournament_slug"],
                    "team_id": r["id"]
                })

                if r["members"]:
                    for m in r["members"].split(","):
                        m_clean = m.strip()
                        if m_clean:
                            g["all_members"].add(m_clean)

                g["total_debates"] += r["debate_count"] or 0
                g["total_speeches"] += r["speech_count"] or 0

            # Determine merged variants for canonical targets
            for name, g in grouped.items():
                canon = g["canonical_name"]
                if canon and canon != name and canon in grouped:
                    grouped[canon]["merged_variants"].add(name)

            # Query confirmed merges audit log
            cur.execute("""
                SELECT target_canonical_name, variant_name, decided_at
                FROM confirmed_team_merges
                WHERE institution_id = ?
                ORDER BY decided_at DESC
            """, (inst_id,))
            confirmed_merges = [dict(row) for row in cur.fetchall()]

            # Ensure confirmed merges reflected in grouping even if variant was absorbed
            for cm in confirmed_merges:
                tgt = cm["target_canonical_name"]
                var = cm["variant_name"]
                if tgt in grouped:
                    grouped[tgt]["merged_variants"].add(var)
                if var in grouped:
                    grouped[var]["canonical_name"] = tgt

            team_names = []
            for name, g in sorted(grouped.items(), key=lambda x: (-x[1]["instance_count"], x[0])):
                is_merged = (g["canonical_name"] != name)
                team_names.append({
                    "name": g["name"],
                    "canonical_name": g["canonical_name"],
                    "tier": g["tier"],
                    "instance_count": g["instance_count"],
                    "team_ids": g["team_ids"],
                    "tournaments": g["tournaments"],
                    "members": ", ".join(sorted(g["all_members"])),
                    "total_debates": g["total_debates"],
                    "total_speeches": g["total_speeches"],
                    "is_merged": is_merged,
                    "merged_into": g["canonical_name"] if is_merged else None,
                    "merged_variants": sorted(list(g["merged_variants"])),
                })

            return jsonify({
                "success": True,
                "institution": dict(inst),
                "team_names": team_names,
                "teams": teams_list,
                "confirmed_merges": confirmed_merges,
                "count": len(team_names),
                "total_instances": len(teams_list),
            })
        except Exception as e:
            return jsonify({"error": f"Failed to fetch institution teams: {str(e)}"}), 500

    @app.route("/api/admin/institutions/merge_team_names", methods=["POST"])
    @require_admin
    def admin_merge_team_names():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            inst_id = int(payload.get("institution_id", 0))
            target_name = (payload.get("target_canonical_name") or "").strip()
            variant_name = (payload.get("variant_name") or "").strip()
            tier = (payload.get("tier") or "").strip().upper() or None

            if not inst_id or not target_name or not variant_name:
                return jsonify({"error": "institution_id, target_canonical_name, and variant_name are required."}), 400

            if target_name == variant_name:
                return jsonify({"error": "Target canonical name and variant name cannot be identical."}), 400

            cur = conn.cursor()
            cur.execute("SELECT id, name FROM institutions WHERE id = ?", (inst_id,))
            inst = cur.fetchone()
            if not inst:
                return jsonify({"error": f"Institution ID {inst_id} not found."}), 404

            # Determine tier if missing
            if not tier:
                cur.execute("SELECT tier FROM teams WHERE institution_id = ? AND (name = ? OR canonical_name = ?) AND tier IS NOT NULL LIMIT 1",
                            (inst_id, target_name, target_name))
                tier_row = cur.fetchone()
                tier = tier_row[0] if tier_row else ("A" if target_name.endswith(" A") else ("B" if target_name.endswith(" B") else "A"))

            # Find all variant teams (including any teams whose canonical_name currently points to variant_name)
            cur.execute("""
                SELECT t.id, t.tournament_id, tour.name as tour_name
                FROM teams t
                JOIN tournaments tour ON t.tournament_id = tour.id
                WHERE t.institution_id = ? AND (t.name = ? OR t.canonical_name = ? OR LOWER(t.name) = LOWER(?) OR LOWER(t.canonical_name) = LOWER(?))
                  AND t.name != ?
            """, (inst_id, variant_name, variant_name, variant_name, variant_name, target_name))
            variant_teams = cur.fetchall()
            if not variant_teams:
                return jsonify({"error": f"No team entries found with name '{variant_name}'."}), 404

            affected_tournaments = []
            same_tournament_merged = 0

            for vt in variant_teams:
                v_id = vt["id"]
                tour_id = vt["tournament_id"]
                t_name = CLEAN_TOURNAMENT_NAMES.get(tour_id, vt["tour_name"])
                affected_tournaments.append(t_name)

                # Check if target team exists in same tournament
                cur.execute("""
                    SELECT id FROM teams
                    WHERE institution_id = ? AND tournament_id = ? AND (name = ? OR canonical_name = ?) AND id != ?
                    LIMIT 1
                """, (inst_id, tour_id, target_name, target_name, v_id))
                target_in_same = cur.fetchone()

                if target_in_same:
                    t_id = target_in_same["id"]
                    cur.execute("UPDATE speech_performances SET team_id = ? WHERE team_id = ?", (t_id, v_id))
                    cur.execute("UPDATE OR IGNORE team_members SET team_id = ? WHERE team_id = ?", (t_id, v_id))
                    cur.execute("DELETE FROM team_members WHERE team_id = ?", (v_id,))
                    cur.execute("UPDATE debates SET prop_team_id = ? WHERE prop_team_id = ?", (t_id, v_id))
                    cur.execute("UPDATE debates SET opp_team_id = ? WHERE opp_team_id = ?", (t_id, v_id))
                    cur.execute("UPDATE debates SET walkover_winner_id = ? WHERE walkover_winner_id = ?", (t_id, v_id))
                    cur.execute("DELETE FROM team_resolutions WHERE team_id = ?", (v_id,))
                    cur.execute("DELETE FROM teams WHERE id = ?", (v_id,))
                    same_tournament_merged += 1
                else:
                    cur.execute("UPDATE teams SET canonical_name = ?, tier = ? WHERE id = ?",
                                (target_name, tier, v_id))
                    cur.execute("""
                        INSERT INTO team_resolutions (team_id, canonical_name, tier, institution_id, status, confidence, reason, reviewed_by_user, decided_at)
                        VALUES (?, ?, ?, ?, 'CONFIRMED', 1.0, 'Manual admin team name merge', 1, CURRENT_TIMESTAMP)
                        ON CONFLICT(team_id) DO UPDATE SET
                            canonical_name = excluded.canonical_name,
                            tier = excluded.tier,
                            institution_id = excluded.institution_id,
                            status = 'CONFIRMED',
                            confidence = 1.0,
                            reason = 'Manual admin team name merge',
                            reviewed_by_user = 1,
                            decided_at = CURRENT_TIMESTAMP
                    """, (v_id, target_name, tier, inst_id))

            # Record in confirmed_team_merges
            cur.execute("""
                CREATE TABLE IF NOT EXISTS confirmed_team_merges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    institution_id INTEGER NOT NULL,
                    target_canonical_name TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(institution_id, variant_name)
                )
            """)
            cur.execute("""
                INSERT OR REPLACE INTO confirmed_team_merges (institution_id, target_canonical_name, variant_name, decided_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (inst_id, target_name, variant_name))
            # Update any transitive merges that previously pointed to variant_name
            cur.execute("""
                UPDATE confirmed_team_merges
                SET target_canonical_name = ?, decided_at = CURRENT_TIMESTAMP
                WHERE institution_id = ? AND target_canonical_name = ? AND variant_name != ?
            """, (target_name, inst_id, variant_name, target_name))

            conn.commit()

            # Refresh static web data and sync to GitHub in background thread
            trigger_async_export_and_sync(
                commit_message=f"chore(data): auto-sync after institution team merge '{variant_name}' -> '{target_name}'"
            )

            decided_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            return jsonify({
                "success": True,
                "message": f"Confirmed: All instances of team name '{variant_name}' are now unified under canonical team '{target_name}'.",
                "target_canonical_name": target_name,
                "variant_name": variant_name,
                "institution_name": inst["name"],
                "affected_tournaments": list(dict.fromkeys(affected_tournaments)),
                "instances_updated": len(variant_teams),
                "same_tournament_merged": same_tournament_merged,
                "decided_at": decided_time,
            })
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Failed to merge team names: {str(e)}"}), 500

    @app.route("/api/admin/institutions/unmerge_team_name", methods=["POST"])
    @require_admin
    def admin_unmerge_team_name():
        try:
            payload = request.get_json(force=True, silent=True) or {}
            inst_id = int(payload.get("institution_id", 0))
            variant_name = (payload.get("variant_name") or "").strip()

            if not inst_id or not variant_name:
                return jsonify({"error": "institution_id and variant_name are required."}), 400

            cur = conn.cursor()
            cur.execute("SELECT id, name FROM institutions WHERE id = ?", (inst_id,))
            inst = cur.fetchone()
            if not inst:
                return jsonify({"error": f"Institution ID {inst_id} not found."}), 404

            # Restore canonical_name = name
            cur.execute("""
                UPDATE teams SET canonical_name = name
                WHERE institution_id = ? AND name = ?
            """, (inst_id, variant_name))

            cur.execute("""
                UPDATE team_resolutions SET canonical_name = ?
                WHERE team_id IN (SELECT id FROM teams WHERE institution_id = ? AND name = ?)
            """, (variant_name, inst_id, variant_name))

            cur.execute("""
                DELETE FROM confirmed_team_merges
                WHERE institution_id = ? AND variant_name = ?
            """, (inst_id, variant_name))

            conn.commit()

            # Refresh static web data and sync to GitHub in background thread
            trigger_async_export_and_sync(
                commit_message=f"chore(data): auto-sync after unmerging institution team '{variant_name}'"
            )

            return jsonify({
                "success": True,
                "message": f"Confirmed: Team name '{variant_name}' has been unmerged and restored as an independent team identity.",
                "variant_name": variant_name,
                "institution_name": inst["name"],
            })
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Failed to unmerge team name: {str(e)}"}), 500

    @app.route("/api/admin/entities/search", methods=["GET"])
    @require_admin
    def admin_entities_search():
        try:
            entity_type = request.args.get("type", "person").strip().lower()
            q = request.args.get("q", "").strip()
            limit = min(50, max(1, int(request.args.get("limit", 15))))

            if not q:
                return jsonify({"success": True, "results": []})

            cur = conn.cursor()
            results = []

            if entity_type == "person":
                is_num = q.isdigit()
                cur.execute("""
                    SELECT p.id, p.canonical_name, p.national_level,
                           COUNT(sp.id) as speech_count,
                           (SELECT i.name FROM speech_performances sp2
                            JOIN teams t ON sp2.team_id = t.id
                            JOIN institutions i ON t.institution_id = i.id
                            WHERE sp2.person_id = p.id
                            ORDER BY sp2.id DESC LIMIT 1) as institution
                    FROM persons p
                    LEFT JOIN speech_performances sp ON p.id = sp.person_id
                    WHERE LOWER(p.canonical_name) LIKE LOWER(?) OR p.id = ?
                    GROUP BY p.id
                    ORDER BY (CASE WHEN p.id = ? THEN 1 WHEN LOWER(p.canonical_name) = LOWER(?) THEN 2 ELSE 3 END), speech_count DESC
                    LIMIT ?
                """, (f"%{q}%", int(q) if is_num else -1, int(q) if is_num else -1, q, limit))
                for r in cur.fetchall():
                    results.append(dict(r))

            elif entity_type == "team":
                is_num = q.isdigit()
                cur.execute("""
                    SELECT t.id, t.name, t.canonical_name, t.tournament_id,
                       tour.name as tournament_name, i.name as institution_name,
                       (SELECT COUNT(*) FROM speech_performances sp WHERE sp.team_id = t.id) as speech_count,
                       (SELECT GROUP_CONCAT(DISTINCT p.canonical_name) 
                        FROM team_members tm 
                        JOIN persons p ON tm.person_id = p.id 
                        WHERE tm.team_id = t.id) as members
                    FROM teams t
                    JOIN tournaments tour ON t.tournament_id = tour.id
                    LEFT JOIN institutions i ON t.institution_id = i.id
                    WHERE LOWER(t.name) LIKE LOWER(?) OR LOWER(i.name) LIKE LOWER(?) OR t.id = ?
                    ORDER BY (CASE WHEN t.id = ? THEN 1 ELSE 2 END), t.id DESC
                    LIMIT ?
                """, (f"%{q}%", f"%{q}%", int(q) if is_num else -1, int(q) if is_num else -1, limit))
                for r in cur.fetchall():
                    d = dict(r)
                    d["official_tournament_name"] = CLEAN_TOURNAMENT_NAMES.get(d["tournament_id"], d["tournament_name"])
                    results.append(d)

            return jsonify({"success": True, "type": entity_type, "results": results})
        except Exception as e:
            return jsonify({"error": f"Search error: {str(e)}"}), 500

    return app



def run_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Run the Atomos REST API server."""
    app = create_app()
    print(f"==================================================================")
    print(f"           ATOMOS HEADLESS REST API SERVER ONLINE")
    print(f"           Listening at: http://{host}:{port}")
    print(f"           Documentation & Endpoints:")
    print(f"             - GET  /api/health")
    print(f"             - POST /api/ask")
    print(f"             - GET  /api/search?q=...")
    print(f"             - GET  /api/debaters/<id>")
    print(f"             - GET  /api/h2h?a=...&b=...")
    print(f"             - GET  /api/institutions")
    print(f"             - GET  /api/motions/summary")
    print(f"==================================================================")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Atomos Local REST API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port number (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, debug=args.debug)
