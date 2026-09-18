"""
Atomos Tab Reconciler

Recovers missing debate ballots and speech marks by cross-referencing:
1. Team Draw Matchups (from round results tables)
2. Individual Speaker Tab per-round marks (from tab_speaker.json)
3. Individual Reply Tab per-round marks (from tab_replies.json)

For true walkovers (where the Speaker Tab records dashes '—'), it flags the debate
as `is_walkover = 1` and attributes the win to the victor without creating fake speeches.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# Cross-tournament team alias resolution (maps raw single-team entries to canonical circuit teams)
CANONICAL_TEAM_ALIASES = {
    ("ric2026", "RC"): "RC A",
    ("ric2026", "AIS"): "AIS A",
    ("ric2026", "STC"): "STC A",
    ("ric2026", "MC"): "Metho A",
    ("ric2026", "GCD"): "GCD A",
    ("ric2026", "HC"): "HC A",
    ("Chaps2026", "Moir"): "Moir A",
    ("Chaps2026", "AC"): "AC A",
    ("Chaps2026", "SBC"): "SBC A",
    ("Chaps2026", "CIS"): "CIS A",
    ("Chaps2026", "Metho"): "Metho A",
    ("Chaps2026", "LIS"): "LIS A",
    ("metho2026", "SBC"): "SBC A",
    ("metho2026", "BSC"): "BSC A",
    ("metho2026", "DBV"): "DBV A",
    ("metho2026", "GCD"): "GCD A",
    ("metho2026", "IC"): "IC A",
}


def clean_text(raw_text: str) -> str:
    s = (
        raw_text.replace("&#x27;", "'")
        .replace("&amp;", "&")
        .replace("’", "'")
        .replace("`", "'")
        .strip()
    )
    return re.sub(r"\s+", " ", s)


def clean_adj(raw_html: str) -> str:
    s = re.sub(r"<[^>]+>", "", raw_html)
    s = (
        s.replace("\u24b8", "")
        .replace("\u00a9", "")
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


class TabReconciler:
    """Reconciles unballoted or zero-scored debates using Speaker, Reply, and Team Tabs."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def reconcile_tournament(self, tournament_id: int, raw_dir: Path) -> dict:
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        raw_path = Path(raw_dir)

        cur.execute("SELECT slug FROM tournaments WHERE id = ?", (tournament_id,))
        slug_row = cur.fetchone()
        slug = slug_row["slug"] if slug_row else ""

        # Update database team names with canonical aliases for this tournament
        for (s_cand, old_name), new_name in CANONICAL_TEAM_ALIASES.items():
            if s_cand == slug:
                cur.execute("SELECT id FROM teams WHERE name = ? AND tournament_id = ?", (new_name, tournament_id))
                new_row = cur.fetchone()
                cur.execute("SELECT id FROM teams WHERE name = ? AND tournament_id = ?", (old_name, tournament_id))
                old_row = cur.fetchone()

                if old_row and new_row:
                    old_id = old_row["id"]
                    new_id = new_row["id"]
                    if old_id != new_id:
                        cur.execute("UPDATE debates SET prop_team_id = ? WHERE prop_team_id = ?", (new_id, old_id))
                        cur.execute("UPDATE debates SET opp_team_id = ? WHERE opp_team_id = ?", (new_id, old_id))
                        cur.execute("UPDATE speech_performances SET team_id = ? WHERE team_id = ?", (new_id, old_id))
                        cur.execute("DELETE FROM team_members WHERE team_id = ?", (old_id,))
                        cur.execute("DELETE FROM teams WHERE id = ?", (old_id,))
                elif old_row and not new_row:
                    cur.execute("UPDATE teams SET name = ? WHERE id = ?", (new_name, old_row["id"]))

        # 1. Index Speaker Tab per-round scores
        spk_files = [
            raw_path / "tab_speaker.json",
            raw_path / "speaker_tab.json",
            raw_path / "tab_speaker_novice.json",
        ]
        team_round_speakers: Dict[Tuple[str, int], List[Tuple[str, float]]] = {}

        for sf in spk_files:
            if not sf.exists():
                continue
            tables = json.loads(sf.read_text(encoding="utf-8"))
            if not tables or "data" not in tables[0]:
                continue
            head = [c.get("key") if isinstance(c, dict) else str(c) for c in tables[0].get("head", [])]
            if "name" not in head or "team" not in head:
                continue
            name_idx = head.index("name")
            team_idx = head.index("team")

            for row in tables[0]["data"]:
                team_cell = row[team_idx].get("text", "") if isinstance(row[team_idx], dict) else str(row[team_idx])
                name_cell = row[name_idx].get("text", "") if isinstance(row[name_idx], dict) else str(row[name_idx])
                raw_t_name = clean_text(team_cell)
                t_name = CANONICAL_TEAM_ALIASES.get((slug, raw_t_name), raw_t_name)
                s_name = clean_text(name_cell)

                for r_num in range(1, 15):
                    rc = f"R{r_num}"
                    if rc in head:
                        idx = head.index(rc)
                        cell = row[idx].get("text", "") if isinstance(row[idx], dict) else str(row[idx])
                        clean = re.sub(r"<[^>]+>", "", cell).strip()
                        if clean and clean not in ["—", "-"]:
                            try:
                                score = float(clean)
                                existing = team_round_speakers.setdefault((t_name, r_num), [])
                                if not any(spk == s_name for spk, _ in existing):
                                    existing.append((s_name, score))
                            except ValueError:
                                pass

        # 2. Index Replies Tab per-round scores
        rep_files = [
            raw_path / "tab_replies.json",
            raw_path / "tab_reply.json",
            raw_path / "tab_replies_novice.json",
        ]
        team_round_replies: Dict[Tuple[str, int], Tuple[str, float]] = {}

        for rf in rep_files:
            if not rf.exists():
                continue
            tables = json.loads(rf.read_text(encoding="utf-8"))
            if not tables or "data" not in tables[0]:
                continue
            head = [c.get("key") if isinstance(c, dict) else str(c) for c in tables[0].get("head", [])]
            if "name" not in head or "team" not in head:
                continue
            name_idx = head.index("name")
            team_idx = head.index("team")

            for row in tables[0]["data"]:
                team_cell = row[team_idx].get("text", "") if isinstance(row[team_idx], dict) else str(row[team_idx])
                name_cell = row[name_idx].get("text", "") if isinstance(row[name_idx], dict) else str(row[name_idx])
                raw_t_name = clean_text(team_cell)
                t_name = CANONICAL_TEAM_ALIASES.get((slug, raw_t_name), raw_t_name)
                s_name = clean_text(name_cell)

                for r_num in range(1, 15):
                    rc = f"R{r_num}"
                    if rc in head:
                        idx = head.index(rc)
                        cell = row[idx].get("text", "") if isinstance(row[idx], dict) else str(row[idx])
                        clean = re.sub(r"<[^>]+>", "", cell).strip()
                        if clean and clean not in ["—", "-"]:
                            try:
                                score = float(clean)
                                team_round_replies[(t_name, r_num)] = (s_name, score)
                            except ValueError:
                                pass

        # 3. Index Team Tab per-round scores and results
        team_files = [raw_path / "tab_team.json", raw_path / "tab_team_novice.json"]
        team_round_totals: Dict[Tuple[str, int], float] = {}
        team_round_results: Dict[Tuple[str, int], dict] = {}

        for tf in team_files:
            if not tf.exists():
                continue
            tables = json.loads(tf.read_text(encoding="utf-8"))
            if not tables or "data" not in tables[0]:
                continue
            head = [c.get("key") if isinstance(c, dict) else str(c) for c in tables[0].get("head", [])]
            if "team" not in head:
                continue
            team_idx = head.index("team")

            for row in tables[0]["data"]:
                team_cell = row[team_idx].get("text", "") if isinstance(row[team_idx], dict) else str(row[team_idx])
                raw_t_name = clean_text(team_cell)
                t_name = CANONICAL_TEAM_ALIASES.get((slug, raw_t_name), raw_t_name)

                for r_num in range(1, 15):
                    rc = f"R{r_num}"
                    if rc in head:
                        idx = head.index(rc)
                        cell = row[idx]
                        if isinstance(cell, dict):
                            st = cell.get("subtext", "")
                            clean_st = re.sub(r"<[^>]+>", "", st).strip()
                            try:
                                team_round_totals[(t_name, r_num)] = float(clean_st)
                            except ValueError:
                                pass
                            team_round_results[(t_name, r_num)] = {
                                "title": cell.get("title", ""),
                                "sort": cell.get("sort", 0),  # 2 for win, 1 for loss
                            }

        # 4. Discover Preliminary Rounds from Tabs
        prelim_rounds: Set[int] = set()
        for tab_cand in [raw_path / "tab_team.json", raw_path / "tab_speaker.json", raw_path / "team_tab.json"]:
            if tab_cand.exists():
                try:
                    tb = json.loads(tab_cand.read_text(encoding="utf-8"))
                    if tb and "head" in tb[0]:
                        for col in tb[0]["head"]:
                            k = col.get("key", "") if isinstance(col, dict) else str(col)
                            m_r = re.match(r"^R(\d+)$", k)
                            if m_r:
                                prelim_rounds.add(int(m_r.group(1)))
                except Exception:
                    pass
            if prelim_rounds:
                break

        # Sync database rounds: strictly PRELIMINARY for tab prelims, ELIMINATION for others
        if prelim_rounds:
            for r_n in range(1, 25):
                if r_n not in prelim_rounds:
                    cur.execute(
                        "UPDATE rounds SET round_type = 'ELIMINATION' WHERE tournament_id = ? AND round_number = ? AND round_type != 'ELIMINATION'",
                        (tournament_id, r_n),
                    )
                else:
                    cur.execute(
                        "UPDATE rounds SET round_type = 'PRELIMINARY' WHERE tournament_id = ? AND round_number = ? AND round_type != 'PRELIMINARY'",
                        (tournament_id, r_n),
                    )

        # 5. Index Matchup Results and Adjudicators from Round Results files
        round_results_lookup: Dict[Tuple[int, str, str], dict] = {}
        for r_file in raw_path.glob("round_*_results.json"):
            m = re.search(r"round_(\d+)_results\.json", r_file.name)
            if not m:
                continue
            r_num = int(m.group(1))
            try:
                tables = json.loads(r_file.read_text(encoding="utf-8"))
                if not tables or "data" not in tables[0]:
                    continue
                head = [c.get("key") if isinstance(c, dict) else str(c) for c in tables[0].get("head", [])]
                t_idx = head.index("team") if "team" in head else 0
                res_idx = head.index("result") if "result" in head else 1
                side_idx = head.index("side") if "side" in head else 2

                for row in tables[0]["data"]:
                    t_cell = row[t_idx] if t_idx < len(row) else {}
                    res_cell = row[res_idx] if res_idx < len(row) else {}
                    side_cell = row[side_idx] if side_idx < len(row) else {}

                    t_name = clean_text(t_cell.get("text", "") if isinstance(t_cell, dict) else str(t_cell))
                    res_text = clean_text(res_cell.get("text", "") if isinstance(res_cell, dict) else str(res_cell))
                    opp_name = re.sub(r"^\s*vs\s+", "", res_text).strip()
                    side = clean_text(side_cell.get("text", "") if isinstance(side_cell, dict) else str(side_cell))
                    sort_val = res_cell.get("sort", 0) if isinstance(res_cell, dict) else 0

                    adj_name = ""
                    for cell in row:
                        if isinstance(cell, dict) and (
                            "adjudicator" in cell.get("class", "")
                            or "Adjudicators" in str(cell.get("popover", ""))
                        ):
                            adj_name = clean_adj(cell.get("text", ""))
                            break

                    p_team = t_name if side.lower() == "proposition" else opp_name
                    o_team = opp_name if side.lower() == "proposition" else t_name

                    winner = None
                    if sort_val == 2:
                        winner = side
                    elif sort_val == 1:
                        winner = "Opposition" if side.lower() == "proposition" else "Proposition"

                    round_results_lookup[(r_num, p_team, o_team)] = {
                        "winner_side": winner,
                        "adjudicator": adj_name,
                    }
            except Exception:
                pass

        # Purge any dummy placeholder 0.0 ballots for this tournament
        cur.execute("""
            DELETE FROM adjudicator_ballots
            WHERE prop_total_score = 0.0 AND opp_total_score = 0.0
              AND debate_id IN (
                  SELECT d.id FROM debates d
                  JOIN rounds r ON d.round_id = r.id
                  WHERE r.tournament_id = ?
              )
        """, (tournament_id,))

        # 6. Query all debates needing reconciliation
        cur.execute("""
            SELECT d.id, d.debate_id, d.round_id, r.round_number, r.round_type, r.name as round_name,
                   d.prop_team_id, d.opp_team_id,
                   p.name as prop_name, o.name as opp_name,
                   COUNT(sp.id) as speech_count,
                   COALESCE(SUM(sp.total_score), 0.0) as speech_sum
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN teams p ON d.prop_team_id = p.id
            JOIN teams o ON d.opp_team_id = o.id
            LEFT JOIN speech_performances sp ON d.id = sp.debate_id
            WHERE r.tournament_id = ?
            GROUP BY d.id
        """, (tournament_id,))
        debates = cur.fetchall()

        reconciled_debates = 0
        walkover_debates = 0
        elimination_debates = 0
        bye_swing_debates = 0

        # Helper to get person ID
        def get_person(p_name: str) -> int:
            cur.execute("SELECT id FROM persons WHERE canonical_name = ?", (p_name,))
            r = cur.fetchone()
            if r:
                return r["id"]
            cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", (p_name,))
            return cur.lastrowid

        positions = ["1st", "2nd", "3rd"]

        for d in debates:
            d_id = d["id"]
            r_num = d["round_number"]
            r_type = d["round_type"]
            r_name = d["round_name"]
            p_name = d["prop_name"]
            o_name = d["opp_name"]
            p_tid = d["prop_team_id"]
            o_tid = d["opp_team_id"]
            r_id = d["round_id"]

            p_tab_tot = team_round_totals.get((p_name, r_num))
            o_tab_tot = team_round_totals.get((o_name, r_num))
            p_res = team_round_results.get((p_name, r_num), {})
            o_res = team_round_results.get((o_name, r_num), {})
            p_sort = p_res.get("sort", 0)
            o_sort = o_res.get("sort", 0)

            needs_backfill = (
                d["speech_count"] == 0
                or d["speech_sum"] == 0.0
                or (p_tab_tot is None and o_tab_tot is None and (p_sort in (1, 2) or o_sort in (1, 2)))
            )
            if not needs_backfill:
                continue

            # Bucket 1: Elimination / Out-Rounds
            is_knockout = (
                (r_type == "ELIMINATION")
                or (prelim_rounds and r_num not in prelim_rounds)
                or any(
                    kw in (r_name or "").lower()
                    for kw in ["octo", "quarter", "semi", "final", "elimination", "knockout"]
                )
            )
            if is_knockout:
                cur.execute("UPDATE debates SET is_walkover = 0 WHERE id = ?", (d_id,))
                elimination_debates += 1

                res_info = round_results_lookup.get((r_num, p_name, o_name), {})
                elim_winner = res_info.get("winner_side")
                adj_str = res_info.get("adjudicator", "")

                if elim_winner:
                    ballot_name = f"Official Panel Decision ({adj_str})" if adj_str else "Official Panel Decision"
                    cur.execute("DELETE FROM adjudicator_ballots WHERE debate_id = ?", (d_id,))
                    cur.execute("""
                        INSERT INTO adjudicator_ballots (
                            debate_id, adjudicator_raw_name, adjudicator_institution,
                            prop_total_score, opp_total_score, win_margin, winner_side
                        ) VALUES (?, ?, 'Tournament Adjudication Core', NULL, NULL, NULL, ?)
                    """, (d_id, ballot_name, elim_winner))
                continue

            # Bucket 2: BYE / Swing Matches
            is_swing_or_bye = (
                "swing" in p_name.lower() or "bye" in p_name.lower() or
                "swing" in o_name.lower() or "bye" in o_name.lower()
            )
            if is_swing_or_bye:
                cur.execute("UPDATE debates SET is_walkover = 0 WHERE id = ?", (d_id,))
                cur.execute("DELETE FROM speech_performances WHERE debate_id = ?", (d_id,))
                bye_swing_debates += 1
                continue

            # Bucket 3: Preliminary Walkovers (Chief Adjudicator Rule)
            # CA Rule: If Tabbycat does not show a team score in a round at all, only winning side and nothing, it's a walkover.
            p_spks = team_round_speakers.get((p_name, r_num), [])
            o_spks = team_round_speakers.get((o_name, r_num), [])
            p_rep = team_round_replies.get((p_name, r_num))
            o_rep = team_round_replies.get((o_name, r_num))

            p_tab_tot = team_round_totals.get((p_name, r_num))
            o_tab_tot = team_round_totals.get((o_name, r_num))
            p_res = team_round_results.get((p_name, r_num), {})
            o_res = team_round_results.get((o_name, r_num), {})
            p_sort = p_res.get("sort", 0)
            o_sort = o_res.get("sort", 0)

            is_wo = False
            if p_tab_tot is None and o_tab_tot is None:
                if p_sort in (1, 2) or o_sort in (1, 2):
                    is_wo = True
                elif not p_spks and not o_spks:
                    # Silent forfeit with 0 scores
                    is_wo = True

            if is_wo:
                cur.execute("UPDATE debates SET is_walkover = 1 WHERE id = ?", (d_id,))
                # Ensure no fake or forfeit speeches exist for walkovers
                cur.execute("DELETE FROM speech_performances WHERE debate_id = ?", (d_id,))

                # Determine winner side
                winner_side = None
                if p_sort == 2 or o_sort == 1:
                    winner_side = "Proposition"
                elif o_sort == 2 or p_sort == 1:
                    winner_side = "Opposition"
                else:
                    res_info = round_results_lookup.get((r_num, p_name, o_name), {})
                    winner_side = res_info.get("winner_side")

                cur.execute("DELETE FROM adjudicator_ballots WHERE debate_id = ?", (d_id,))
                if winner_side:
                    winner_id = p_tid if winner_side == "Proposition" else o_tid
                    cur.execute("UPDATE debates SET walkover_winner_id = ? WHERE id = ?", (winner_id, d_id))
                    cur.execute("""
                        INSERT INTO adjudicator_ballots (
                            debate_id, adjudicator_raw_name, adjudicator_institution,
                            prop_total_score, opp_total_score, win_margin, winner_side
                        ) VALUES (?, 'Official Walkover', 'Tabbycat Tab', NULL, NULL, NULL, ?)
                    """, (d_id, winner_side))

                walkover_debates += 1
                continue

            # Bucket 4: Contested Preliminary Rounds (must have team score on tab)
            cur.execute("UPDATE debates SET is_walkover = 0 WHERE id = ?", (d_id,))

            needs_backfill = (d["speech_count"] == 0 or d["speech_sum"] == 0.0)
            if not needs_backfill:
                continue

            # HARD BAN ON SYNTHESIZING SPEECH PERFORMANCES FROM SPEAKER TABS:
            # Under constitution rules, Atomos must NEVER guess or fabricate 1st, 2nd, 3rd speaking positions
            # based on speaker tab ordering or other datasets. Authentic speech performances must come exclusively
            # from genuine debate scoresheets. If a debate has no scoresheet, we only record the team ballot outcome.
            p_speeches = []
            o_speeches = []

            p_tot = p_tab_tot
            o_tot = o_tab_tot

            margin = None
            if p_tot is not None and o_tot is not None:
                margin = round(abs(p_tot - o_tot), 5)

            res_info = round_results_lookup.get((r_num, p_name, o_name), {})
            winner_side = res_info.get("winner_side")
            if not winner_side and p_tot is not None and o_tot is not None:
                winner_side = "Proposition" if p_tot > o_tot else ("Opposition" if o_tot > p_tot else "Tie")

            adj_str = res_info.get("adjudicator", "")
            chair_name = adj_str.split(",")[0].strip() if adj_str else None
            adj_pid = get_person(chair_name) if chair_name else None
            ballot_adj = f"Official Reconstructed ({chair_name})" if chair_name else "Official Tab Reconstructed"

            cur.execute("DELETE FROM speech_performances WHERE debate_id = ?", (d_id,))
            cur.execute("DELETE FROM adjudicator_ballots WHERE debate_id = ?", (d_id,))

            cur.execute("""
                INSERT INTO adjudicator_ballots (
                    debate_id, adjudicator_person_id, adjudicator_raw_name, adjudicator_institution,
                    prop_total_score, opp_total_score, win_margin, winner_side
                ) VALUES (?, ?, ?, 'Tabbycat Tab', ?, ?, ?, ?)
            """, (d_id, adj_pid, ballot_adj, p_tot, o_tot, margin, winner_side))

            if adj_pid:
                cur.execute(
                    "INSERT OR IGNORE INTO adjudicator_assignments (debate_id, person_id) VALUES (?, ?)",
                    (d_id, adj_pid),
                )

            reconciled_debates += 1

        # 7. Team Tab Golden Reconstruction & Deduplication for Preliminary Debates
        cur.execute("""
            SELECT d.id as debate_id, d.debate_id as deb_src_id, r.id as round_id, r.round_number,
                   pt.id as p_tid, ot.id as o_tid,
                   pt.name as prop_name, ot.name as opp_name
            FROM debates d
            JOIN rounds r ON d.round_id = r.id
            JOIN teams pt ON d.prop_team_id = pt.id
            JOIN teams ot ON d.opp_team_id = ot.id
            WHERE r.tournament_id = ? AND r.round_type = 'PRELIMINARY' AND d.is_walkover = 0
        """, (tournament_id,))
        prelim_debates = cur.fetchall()

        replies_backfilled = 0
        for pd in prelim_debates:
            did = pd["debate_id"]
            rid = pd["round_id"]
            rnum = pd["round_number"]
            pname = pd["prop_name"]
            oname = pd["opp_name"]
            p_tid = pd["p_tid"]
            o_tid = pd["o_tid"]

            p_tab_tot = team_round_totals.get((pname, rnum))
            o_tab_tot = team_round_totals.get((oname, rnum))
            p_res = team_round_results.get((pname, rnum), {})
            o_res = team_round_results.get((oname, rnum), {})

            if p_tab_tot is None and o_tab_tot is None:
                continue

            winner = None
            if p_res.get("sort") == 2:
                winner = "Proposition"
            elif o_res.get("sort") == 2:
                winner = "Opposition"
            elif p_tab_tot is not None and o_tab_tot is not None:
                winner = "Proposition" if p_tab_tot > o_tab_tot else ("Opposition" if o_tab_tot > p_tab_tot else "Tie")

            margin = round(abs(p_tab_tot - o_tab_tot), 5) if (p_tab_tot is not None and o_tab_tot is not None) else None

            # Ensure ballot exists for this debate
            cur.execute("SELECT id FROM adjudicator_ballots WHERE debate_id = ?", (did,))
            b_rows = cur.fetchall()

            if b_rows:
                ballot_ids = [b["id"] for b in b_rows]
            else:
                cur.execute("""
                    INSERT INTO adjudicator_ballots (
                        debate_id, adjudicator_raw_name, adjudicator_institution,
                        prop_total_score, opp_total_score, win_margin, winner_side
                    ) VALUES (?, 'Official Tab Reconstructed', 'Tabbycat Tab', ?, ?, ?, ?)
                """, (did, p_tab_tot, o_tab_tot, margin, winner))
                ballot_ids = [cur.lastrowid]

            for bid in ballot_ids:
                # Check speeches for this ballot
                cur.execute("""
                    SELECT 
                        (SELECT COUNT(*) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Proposition') as p_spk_cnt,
                        (SELECT COUNT(*) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Opposition') as o_spk_cnt,
                        (SELECT COUNT(*) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Proposition' AND sp.speech_type = 'REPLY') as p_rep_cnt,
                        (SELECT COUNT(*) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Opposition' AND sp.speech_type = 'REPLY') as o_rep_cnt,
                        (SELECT SUM(sp.total_score) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Proposition') as p_spk_sum,
                        (SELECT SUM(sp.total_score) FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Opposition') as o_spk_sum,
                        (SELECT sp.person_id FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Proposition' LIMIT 1) as p_first_pid,
                        (SELECT sp.person_id FROM speech_performances sp WHERE sp.ballot_id = ? AND sp.side = 'Opposition' LIMIT 1) as o_first_pid
                """, (bid, bid, bid, bid, bid, bid, bid, bid))
                spk_info = cur.fetchone()

            # If completely missing speeches:
            # HARD BAN ON SYNTHESIZING SPEECH PERFORMANCES FROM SPEAKER TABS:
            # Under constitution rules, Atomos must NEVER guess or fabricate 1st, 2nd, 3rd speaking positions
            # based on speaker tab ordering or other datasets. Authentic speech performances must come exclusively
            # from genuine debate scoresheets.
            if spk_info["p_spk_cnt"] == 0 and spk_info["o_spk_cnt"] == 0:
                pass

            else:
                # Substantives exist, check if reply is missing
                if p_tab_tot and spk_info["p_rep_cnt"] == 0 and spk_info["p_spk_sum"] and spk_info["p_first_pid"]:
                    derived_rep = round(p_tab_tot - spk_info["p_spk_sum"], 5)
                    if 30.0 <= derived_rep <= 40.0:
                        rep_spk = team_round_replies.get((pname, rnum))
                        pid = get_person(rep_spk[0]) if rep_spk else spk_info["p_first_pid"]
                        cur.execute("""
                            INSERT INTO speech_performances (
                                ballot_id, debate_id, round_id, team_id, person_id,
                                side, position, speech_type, total_score, is_valid_rubric, is_iron_man
                            ) VALUES (?, ?, ?, ?, ?, 'Proposition', 'Reply', 'REPLY', ?, 1, 0)
                        """, (bid, did, rid, p_tid, pid, derived_rep))
                        replies_backfilled += 1

                if o_tab_tot and spk_info["o_rep_cnt"] == 0 and spk_info["o_spk_sum"] and spk_info["o_first_pid"]:
                    derived_rep = round(o_tab_tot - spk_info["o_spk_sum"], 5)
                    if 30.0 <= derived_rep <= 40.0:
                        rep_spk = team_round_replies.get((oname, rnum))
                        pid = get_person(rep_spk[0]) if rep_spk else spk_info["o_first_pid"]
                        cur.execute("""
                            INSERT INTO speech_performances (
                                ballot_id, debate_id, round_id, team_id, person_id,
                                side, position, speech_type, total_score, is_valid_rubric, is_iron_man
                            ) VALUES (?, ?, ?, ?, ?, 'Opposition', 'Reply', 'REPLY', ?, 1, 0)
                        """, (bid, did, rid, o_tid, pid, derived_rep))
                        replies_backfilled += 1

        self.conn.commit()
        return {
            "reconciled_debates": reconciled_debates,
            "walkover_debates": walkover_debates,
            "elimination_debates": elimination_debates,
            "bye_swing_debates": bye_swing_debates,
            "replies_backfilled": replies_backfilled,
        }
