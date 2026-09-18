"""
Atomos Motion and Side Balance Analytics

Analyzes:
1. Side Bias (Proposition vs Opposition win rates overall, per tournament, and prelims vs outrounds)
2. Thematic Motion Classification (Geopolitics, Economics, Tech/AI, Social/Feminism, etc.)
3. Motion Difficulty & Scoring Distribution (highest vs lowest scoring motions)
4. Extreme & Balanced Motions (highest Prop lean, Opp lean, and 50/50 balance)
"""

import html
import re
import sqlite3
from typing import Dict, List, Optional


class MotionAnalytics:
    """Analyzes motion balance, side bias, thematic patterns, and scoring difficulty."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def classify_motion_theme(motion_text: Optional[str]) -> str:
        """
        Classifies motion text into standard debating topic categories using keyword
        and regex pattern matching calibrated against the Sri Lankan debating circuit.
        """
        if not motion_text:
            return "General & Policy"

        m = html.unescape(motion_text).lower()

        # 1. Tech, AI & Science
        if any(k in m for k in [
            "ai bubble", "frontier ai", "anti-ai", "artificial intelligence",
            "two-lives technology", "techno-pessimist", "data centers"
        ]) or re.search(r'\b(ai|tech)\b', m):
            return "Tech, AI & Science"

        # 2. Environment & Animals
        if any(k in m for k in ["pets", "domestication", "livestock", "nature over religious"]):
            return "Environment & Animals"

        # 3. Social, Gender & Identity
        if any(k in m for k in [
            "feminist", "female", "benevolent sexism", "gender gap", "trans movement",
            "detransition", "lgbtqia", "queerbaiting", "marriage", "diversity"
        ]):
            return "Social, Gender & Identity"

        # 4. Law, Crime & Justice
        if any(k in m for k in [
            "jury nullification", "bounty hunters", "incarceration", "san pedro",
            "sentences", "overcrowding", "law enforcement", "legal services were never privatized", "prisoners"
        ]):
            return "Law, Crime & Justice"

        # 5. Geopolitics & International Relations
        if any(k in m for k in [
            "un security council", "gulf states", "chinese communist party", "refugee",
            "venezuela and iran", "military", "foreign policy", "authoritarian state",
            "eelam", "tamils", "democratic over the next decade"
        ]):
            return "Geopolitics & International Relations"

        # 6. Economics & Development
        if any(k in m for k in [
            "nationalize", "subsidiz", "asian tigers", "land titles",
            "plantation", "fire", "privatized", "market reform", "middle class"
        ]):
            return "Economics & Development"

        # 7. Philosophy, Ethics & Religion
        if any(k in m for k in [
            "seven deadly sins", "moral relativism", "moral absolutism", "morals",
            "abrahamic", "karmic", "catholic pope", "subconscious manipulation",
            "colombian love", "young love", "nonchalance", "focus mode", "religios",
            "religious", "morally right"
        ]):
            return "Philosophy, Ethics & Religion"

        # 8. Culture, Media & Sports
        if any(k in m for k in [
            "cricket", "sports", "olympic", "enhanced games", "fifa", "world cup",
            "music artist", "virality", "disney", "ghibli", "movie", "television",
            "film", "spider man", "politainment", "painting", "race-blind casting",
            "inclusive casting", "cobb", "limbo", "chosen one", "re:write",
            "chandrika would ask vijaya"
        ]):
            return "Culture, Media & Sports"

        # 9. Education & Debating Circuit
        if any(k in m for k in [
            "higher education", "university", "sri lankan circuit", "strong debater",
            "degree qualifications"
        ]):
            return "Education & Circuit"

        return "General & Policy"

    def get_overall_side_balance(self) -> dict:
        """
        Computes national cumulative side balance across all tournaments and adjudicator ballots.
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT b.winner_side, COUNT(*) as cnt
            FROM debates d
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0 AND b.winner_side IS NOT NULL
            GROUP BY b.winner_side
        """)
        rows = cur.fetchall()
        counts = {r["winner_side"]: r["cnt"] for r in rows}
        prop = counts.get("Proposition", 0)
        opp = counts.get("Opposition", 0)
        tie = counts.get("Tie", 0)
        total = prop + opp + tie

        prop_rate = round(prop / total * 100.0, 5) if total > 0 else 0.0
        opp_rate = round(opp / total * 100.0, 5) if total > 0 else 0.0

        if prop_rate > opp_rate:
            dominant = "Proposition"
        elif opp_rate > prop_rate:
            dominant = "Opposition"
        else:
            dominant = "Balanced"

        diff = abs(prop_rate - 50.0)
        if diff <= 2.0:
            rating = "BALANCED"
        elif prop_rate > opp_rate:
            rating = "HEAVILY_PROP_BIASED" if diff >= 8.0 else "SLIGHT_PROP_BIAS"
        else:
            rating = "HEAVILY_OPP_BIASED" if diff >= 8.0 else "SLIGHT_OPP_BIAS"

        return {
            "total_decisions": total,
            "prop_wins": prop,
            "opp_wins": opp,
            "ties": tie,
            "prop_win_rate": prop_rate,
            "opp_win_rate": opp_rate,
            "dominant_side": dominant,
            "bias_margin": round(diff, 5),
            "bias_classification": rating,
        }

    def get_tournament_side_balance(self) -> List[dict]:
        """
        Computes Proposition vs Opposition win rates broken down by tournament.
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT t.id, t.name, t.slug, b.winner_side, COUNT(*) as cnt
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0 AND b.winner_side IS NOT NULL
            GROUP BY t.id, b.winner_side
            ORDER BY t.name
        """)
        rows = cur.fetchall()

        tourneys: Dict[int, dict] = {}
        for r in rows:
            tid = r["id"]
            if tid not in tourneys:
                tourneys[tid] = {
                    "tournament_id": tid,
                    "tournament_name": r["name"],
                    "tournament_slug": r["slug"],
                    "prop_wins": 0,
                    "opp_wins": 0,
                    "ties": 0,
                }
            side = r["winner_side"]
            if side == "Proposition":
                tourneys[tid]["prop_wins"] += r["cnt"]
            elif side == "Opposition":
                tourneys[tid]["opp_wins"] += r["cnt"]
            else:
                tourneys[tid]["ties"] += r["cnt"]

        result = []
        for tid, st in tourneys.items():
            total = st["prop_wins"] + st["opp_wins"] + st["ties"]
            if total == 0:
                continue
            prop_rate = round(st["prop_wins"] / total * 100.0, 5)
            opp_rate = round(st["opp_wins"] / total * 100.0, 5)

            if prop_rate > opp_rate:
                dominant = "Proposition"
            elif opp_rate > prop_rate:
                dominant = "Opposition"
            else:
                dominant = "Balanced"

            diff = abs(prop_rate - 50.0)
            if diff <= 2.5:
                rating = "BALANCED"
            elif prop_rate > opp_rate:
                rating = "HEAVILY_PROP_BIASED" if diff >= 8.0 else "SLIGHT_PROP_BIAS"
            else:
                rating = "HEAVILY_OPP_BIASED" if diff >= 8.0 else "SLIGHT_OPP_BIAS"

            result.append({
                "tournament_id": tid,
                "tournament_name": st["tournament_name"],
                "tournament_slug": st["tournament_slug"],
                "total_decisions": total,
                "prop_wins": st["prop_wins"],
                "opp_wins": st["opp_wins"],
                "ties": st["ties"],
                "prop_win_rate": prop_rate,
                "opp_win_rate": opp_rate,
                "dominant_side": dominant,
                "bias_classification": rating,
            })

        result.sort(key=lambda x: x["total_decisions"], reverse=True)
        return result

    def get_round_type_side_balance(self) -> Dict[str, dict]:
        """
        Compares side balance across Preliminary rounds vs Elimination (outrounds).
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.round_type, b.winner_side, COUNT(*) as cnt
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0 AND b.winner_side IS NOT NULL
            GROUP BY r.round_type, b.winner_side
        """)
        rows = cur.fetchall()

        breakdown: Dict[str, dict] = {
            "PRELIMINARY": {"prop_wins": 0, "opp_wins": 0, "ties": 0},
            "ELIMINATION": {"prop_wins": 0, "opp_wins": 0, "ties": 0},
        }

        for r in rows:
            rtype = r["round_type"] or "PRELIMINARY"
            if rtype not in breakdown:
                breakdown[rtype] = {"prop_wins": 0, "opp_wins": 0, "ties": 0}
            side = r["winner_side"]
            if side == "Proposition":
                breakdown[rtype]["prop_wins"] += r["cnt"]
            elif side == "Opposition":
                breakdown[rtype]["opp_wins"] += r["cnt"]
            else:
                breakdown[rtype]["ties"] += r["cnt"]

        summary = {}
        for rtype, st in breakdown.items():
            total = st["prop_wins"] + st["opp_wins"] + st["ties"]
            if total == 0:
                continue
            prop_rate = round(st["prop_wins"] / total * 100.0, 5)
            opp_rate = round(st["opp_wins"] / total * 100.0, 5)
            dominant = "Proposition" if prop_rate > opp_rate else ("Opposition" if opp_rate > prop_rate else "Balanced")
            diff = abs(prop_rate - 50.0)
            if diff <= 2.5:
                rating = "BALANCED"
            elif prop_rate > opp_rate:
                rating = "HEAVILY_PROP_BIASED" if diff >= 8.0 else "SLIGHT_PROP_BIAS"
            else:
                rating = "HEAVILY_OPP_BIASED" if diff >= 8.0 else "SLIGHT_OPP_BIAS"

            summary[rtype] = {
                "round_type": rtype,
                "total_decisions": total,
                "prop_wins": st["prop_wins"],
                "opp_wins": st["opp_wins"],
                "ties": st["ties"],
                "prop_win_rate": prop_rate,
                "opp_win_rate": opp_rate,
                "dominant_side": dominant,
                "bias_classification": rating,
            }
        return summary

    def get_motion_balance_report(self, min_debates: int = 2) -> List[dict]:
        """
        Computes side bias, win distribution, average team score, and margins for all debated motions.
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.id as round_id, r.name as round_name, r.round_number, r.round_type, r.motion,
                   t.id as tournament_id, t.name as tournament_name, t.slug as tournament_slug,
                   b.winner_side, b.win_margin, b.prop_total_score, b.opp_total_score, d.id as debate_id
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN tournaments t ON r.tournament_id = t.id
            JOIN adjudicator_ballots b ON d.id = b.debate_id
            WHERE d.is_walkover = 0
              AND r.motion IS NOT NULL
              AND b.winner_side IS NOT NULL
        """)
        rows = cur.fetchall()

        motion_stats: Dict[int, dict] = {}

        for row in rows:
            r_id = row["round_id"]
            if r_id not in motion_stats:
                clean_motion = html.unescape(row["motion"]).strip()
                motion_stats[r_id] = {
                    "round_id": r_id,
                    "round_name": row["round_name"],
                    "round_type": row["round_type"] or "PRELIMINARY",
                    "tournament_name": row["tournament_name"],
                    "tournament_slug": row["tournament_slug"],
                    "motion": clean_motion,
                    "theme": self.classify_motion_theme(clean_motion),
                    "debates_seen": set(),
                    "decisions_count": 0,
                    "prop_wins": 0,
                    "opp_wins": 0,
                    "ties": 0,
                    "margins": [],
                    "all_scores": [],
                }

            st = motion_stats[r_id]
            st["debates_seen"].add(row["debate_id"])
            st["decisions_count"] += 1
            winner = row["winner_side"]
            if winner == "Proposition":
                st["prop_wins"] += 1
            elif winner == "Opposition":
                st["opp_wins"] += 1
            else:
                st["ties"] += 1

            if row["win_margin"] is not None:
                st["margins"].append(abs(row["win_margin"]))
            if row["prop_total_score"]:
                st["all_scores"].append(row["prop_total_score"])
            if row["opp_total_score"]:
                st["all_scores"].append(row["opp_total_score"])

        report = []
        for r_id, st in motion_stats.items():
            num_debates = len(st["debates_seen"])
            if num_debates < min_debates:
                continue

            decisions = st["decisions_count"]
            prop_rate = round(st["prop_wins"] / decisions * 100.0, 5) if decisions > 0 else 0.0
            opp_rate = round(st["opp_wins"] / decisions * 100.0, 5) if decisions > 0 else 0.0
            avg_margin = round(sum(st["margins"]) / len(st["margins"]), 5) if st["margins"] else 0.0
            avg_score = round(sum(st["all_scores"]) / len(st["all_scores"]), 5) if st["all_scores"] else 0.0

            if prop_rate >= 62.0:
                bias = "HEAVILY_PROP_BIASED"
            elif prop_rate >= 55.0:
                bias = "SLIGHT_PROP_BIAS"
            elif opp_rate >= 62.0:
                bias = "HEAVILY_OPP_BIASED"
            elif opp_rate >= 55.0:
                bias = "SLIGHT_OPP_BIAS"
            else:
                bias = "BALANCED"

            report.append({
                "round_id": r_id,
                "tournament_slug": st["tournament_slug"],
                "tournament_name": st["tournament_name"],
                "round_name": st["round_name"],
                "round_type": st["round_type"],
                "motion": st["motion"],
                "theme": st["theme"],
                "debates_count": num_debates,
                "decisions_count": decisions,
                "prop_wins": st["prop_wins"],
                "opp_wins": st["opp_wins"],
                "ties": st["ties"],
                "prop_win_rate": prop_rate,
                "opp_win_rate": opp_rate,
                "bias_classification": bias,
                "avg_win_margin": avg_margin,
                "avg_team_score": avg_score,
            })

        report.sort(key=lambda x: (x["debates_count"], abs(x["prop_win_rate"] - 50.0)), reverse=True)
        return report

    def get_thematic_motion_analysis(self) -> List[dict]:
        """
        Aggregates motion performance, side lean, and scoring metrics by thematic category.
        """
        motions = self.get_motion_balance_report(min_debates=1)
        themes: Dict[str, dict] = {}

        for m in motions:
            t = m["theme"]
            if t not in themes:
                themes[t] = {
                    "theme": t,
                    "motions_count": 0,
                    "debates_count": 0,
                    "decisions_count": 0,
                    "prop_wins": 0,
                    "opp_wins": 0,
                    "ties": 0,
                    "all_scores": [],
                    "margins": [],
                }
            th = themes[t]
            th["motions_count"] += 1
            th["debates_count"] += m["debates_count"]
            th["decisions_count"] += m["decisions_count"]
            th["prop_wins"] += m["prop_wins"]
            th["opp_wins"] += m["opp_wins"]
            th["ties"] += m["ties"]
            if m["avg_team_score"] > 0:
                th["all_scores"].append(m["avg_team_score"])
            if m["avg_win_margin"] > 0:
                th["margins"].append(m["avg_win_margin"])

        summary = []
        for t, th in themes.items():
            dec = th["decisions_count"]
            if dec == 0:
                continue
            prop_rate = round(th["prop_wins"] / dec * 100.0, 5)
            opp_rate = round(th["opp_wins"] / dec * 100.0, 5)
            avg_score = round(sum(th["all_scores"]) / len(th["all_scores"]), 5) if th["all_scores"] else 0.0
            avg_margin = round(sum(th["margins"]) / len(th["margins"]), 5) if th["margins"] else 0.0

            dominant = "Proposition" if prop_rate > opp_rate else ("Opposition" if opp_rate > prop_rate else "Balanced")
            diff = abs(prop_rate - 50.0)
            if diff <= 2.5:
                rating = "BALANCED"
            elif prop_rate > opp_rate:
                rating = "HEAVILY_PROP_BIASED" if diff >= 8.0 else "SLIGHT_PROP_BIAS"
            else:
                rating = "HEAVILY_OPP_BIASED" if diff >= 8.0 else "SLIGHT_OPP_BIAS"

            summary.append({
                "theme": t,
                "motions_count": th["motions_count"],
                "debates_count": th["debates_count"],
                "decisions_count": dec,
                "prop_wins": th["prop_wins"],
                "opp_wins": th["opp_wins"],
                "ties": th["ties"],
                "prop_win_rate": prop_rate,
                "opp_win_rate": opp_rate,
                "dominant_side": dominant,
                "avg_team_score": avg_score,
                "avg_win_margin": avg_margin,
                "bias_classification": rating,
            })

        summary.sort(key=lambda x: x["decisions_count"], reverse=True)
        return summary

    def get_motion_difficulty_ranking(self, min_debates: int = 3, reverse: bool = False) -> List[dict]:
        """
        Ranks motions by average team score.
        reverse=False (default): Lowest scores first (toughest / most defensive motions).
        reverse=True: Highest scores first (highest scoring motions).
        """
        motions = self.get_motion_balance_report(min_debates=min_debates)
        valid = [m for m in motions if m["avg_team_score"] > 0]
        valid.sort(key=lambda x: x["avg_team_score"], reverse=reverse)
        return valid

    def get_extreme_motions(self, min_debates: int = 4) -> dict:
        """
        Identifies motions with highest Proposition bias, highest Opposition bias,
        and the most evenly balanced motions (closest to 50/50 split).
        """
        motions = self.get_motion_balance_report(min_debates=min_debates)

        prop_biased = sorted(
            [m for m in motions if m["prop_win_rate"] >= 55.0],
            key=lambda x: x["prop_win_rate"],
            reverse=True,
        )

        opp_biased = sorted(
            [m for m in motions if m["opp_win_rate"] >= 55.0],
            key=lambda x: x["opp_win_rate"],
            reverse=True,
        )

        balanced = sorted(
            motions,
            key=lambda x: abs(x["prop_win_rate"] - 50.0),
        )

        return {
            "most_prop_biased": prop_biased,
            "most_opp_biased": opp_biased,
            "most_balanced": balanced[:10],
        }
