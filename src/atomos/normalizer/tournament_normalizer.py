"""
Atomos Tournament Normalizer (Fold 2)

Normalizes raw tournament archives into structured SQLite database tables:
- Separates Host Institution (School) from Team Identifier (e.g. 'Trinity College Kandy' vs 'Munchi')
- Standardizes canonical Sri Lankan debating schools
- Normalizes Persons, Teams, and Rosters (Creator)
- Normalizes Tournaments, Rounds, Debates, and Motions (Context)
- Normalizes Adjudicator Ballots and Speech Performances (Creation)
- Enforces strict Identity Resolution rules (Uncertain names -> PENDING_REVIEW)
- Preserves raw provenance links for all imported records
"""

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from atomos.domain.scoring import (
    is_valid_substantive_components,
    is_valid_reply_components,
)
from atomos.normalizer.reconciler import TabReconciler
from atomos.normalizer.manual_patch import ManualBallotPatcher


# Canonical registry for Sri Lankan debating institutions
CANONICAL_SCHOOLS = {
    "RC": "Royal College",
    "STC": "S. Thomas' College",
    "AC": "Ananda College",
    "TCK": "Trinity College Kandy",
    "LC": "Ladies' College",
    "BC": "Bishop's College",
    "VV": "Visakha Vidyalaya",
    "DS": "D. S. Senanayake College",
    "HFC": "Holy Family Convent",
    "SBC": "St. Bridget's Convent",
    "HCK": "Hillwood College Kandy",
    "SACK": "St. Anthony's College Kandy",
    "Moir": "Elizabeth Moir School",
    "EMS": "Elizabeth Moir School",
    "GCD": "Gateway College Dehiwala",
    "GCC": "Gateway College Colombo",
    "GCK": "Gateway College Kandy",
    "GCN": "Gateway College Negombo",
    "CIS": "Colombo International School",
    "AIS": "Asian International School",
    "SPC": "St. Peter's College",
    "SJC": "St. Joseph's College",
    "WC": "Wesley College",
    "TC": "Thurstan College",
    "NC": "Nalanda College",
    "MC": "Methodist College",
    "DRCK": "Dharmaraja College Kandy",
    "DBV": "Devi Balika Vidyalaya",
    "RISK": "Royal International School Kurunegala",
    "SJM": "Sujatha Vidyalaya Matara",
    "SCG": "Southlands College Galle",
    "SJCJ": "St. John's College Jaffna",
    "JLC": "Jaffna Ladies' College",
    "JHLC": "Jaffna Hindu Ladies' College",
    "Anula": "Anula Vidyalaya",
    "Hejaaz": "Hejaaz International School",
    "Daybridge": "Daybridge International School",
    "Maliyadeva": "Kurunegala Maliyadeva Balika Vidyalaya",
    "Logos": "Logos College",
    "Isipathana": "Isipathana College",
    "Hindu": "Hindu College",
    "Swarnamali": "Swarnamali Girls' College Kandy",
    "Sussex": "Sussex College Kurunegala",
    "MLC": "Muslim Ladies' College",
}

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
        html.unescape(raw_text)
        .replace("’", "'")
        .replace("`", "'")
        .strip()
    )
    return re.sub(r"\s+", " ", s)


def extract_school_and_team_identifier(short_name: str, popover_title: str) -> Tuple[str, str, str]:
    """
    Given a short team name like 'TCK Munchi' or 'STC A' and popover title like
    'Trinity College Kandy Munchi' or 'S. Thomas' College A', cleanly separates:
    (school_code, school_full_name, team_identifier)
    """
    clean_short = clean_text(short_name)
    clean_title = clean_text(popover_title) if popover_title else clean_short

    parts = clean_short.split()
    if len(parts) >= 2:
        code = parts[0]
        identifier = " ".join(parts[1:])
        if clean_title.endswith(identifier):
            school_name = clean_title[:-len(identifier)].strip()
        else:
            school_name = clean_title
        return code, school_name, identifier
    else:
        return clean_short, clean_title, ""


def resolve_canonical_institution(code: str, full_name: str) -> Tuple[str, str]:
    """
    Standardize school code and name against known Sri Lankan institutions.
    """
    clean_code = code.strip()
    clean_name = clean_text(full_name)

    # Filter swing teams and byes
    if clean_code.upper() in ["SWING", "BYE"] or clean_name.upper() in ["SWING", "BYE"]:
        return "SWING", "Swing Team"

    if clean_code in CANONICAL_SCHOOLS:
        return clean_code, CANONICAL_SCHOOLS[clean_code]

    no_dot = clean_code.replace(".", "")
    if no_dot in CANONICAL_SCHOOLS:
        return no_dot, CANONICAL_SCHOOLS[no_dot]

    # Check common full name matches (prioritize longer institution names first to avoid substring collisions)
    for canon_code, canon_name in sorted(CANONICAL_SCHOOLS.items(), key=lambda x: len(x[1]), reverse=True):
        if canon_name.lower() in clean_name.lower() or clean_name.lower() in canon_name.lower():
            return canon_code, canon_name

    return clean_code, clean_name


class TournamentNormalizer:
    """Normalizes raw Tabbycat tournament archives into SQLite."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def get_or_create_person(
        self, raw_name: str, tournament_id: int, institution_code: Optional[str] = None
    ) -> int:
        """Resolve or create a Person record with strict review logging."""
        clean_name = clean_text(raw_name)
        if not clean_name:
            raise ValueError("Cannot create person with empty name")

        cur = self.conn.cursor()
        cur.execute("SELECT id FROM persons WHERE LOWER(canonical_name) = LOWER(?)", (clean_name,))
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute("SELECT person_id FROM person_aliases WHERE LOWER(raw_name) = LOWER(?)", (clean_name,))
        row = cur.fetchone()
        if row:
            return row["person_id"]

        # Check punctuation/whitespace normalized match (e.g. 'S.M.Yuthmi' vs 'S. M. Yuthmi')
        alnum_target = re.sub(r"[^\w]", "", clean_name.lower())
        if len(alnum_target) >= 5:
            cur.execute("SELECT id, canonical_name FROM persons")
            for p_row in cur.fetchall():
                if re.sub(r"[^\w]", "", (p_row["canonical_name"] or "").lower()) == alnum_target:
                    cur.execute(
                        "INSERT OR IGNORE INTO person_aliases (person_id, raw_name, source_tournament_id) VALUES (?, ?, ?)",
                        (p_row["id"], clean_name, tournament_id),
                    )
                    return p_row["id"]

        # Create new Person
        cur.execute("INSERT INTO persons (canonical_name) VALUES (?)", (clean_name,))
        new_person_id = cur.lastrowid

        cur.execute(
            "INSERT OR IGNORE INTO person_aliases (person_id, raw_name, source_tournament_id) VALUES (?, ?, ?)",
            (new_person_id, clean_name, tournament_id),
        )

        # Flag similar names for user review
        cur.execute("SELECT id, canonical_name FROM persons WHERE id != ?", (new_person_id,))
        existing_persons = cur.fetchall()

        tokens_new = set(clean_name.lower().split())
        for ep in existing_persons:
            ep_id = ep["id"]
            ep_name = ep["canonical_name"]
            tokens_ep = set(ep_name.lower().split())

            common = tokens_new.intersection(tokens_ep)
            significant_common = [t for t in common if len(t) > 3]

            if significant_common:
                reason = f"Shares significant name tokens: {significant_common}"
                cur.execute(
                    """
                    INSERT INTO identity_resolutions 
                    (raw_name_a, raw_name_b, person_a_id, person_b_id, status, confidence_score, reason)
                    VALUES (?, ?, ?, ?, 'PENDING_REVIEW', 0.5, ?)
                    """,
                    (clean_name, ep_name, new_person_id, ep_id, reason),
                )

        return new_person_id

    def get_or_create_institution(self, code: str, name: str) -> Optional[int]:
        """
        Get or create a canonical institution record.
        Returns None for swing teams or byes.
        """
        c_code, c_name = resolve_canonical_institution(code, name)
        if c_code == "SWING":
            return None

        cur = self.conn.cursor()
        cur.execute("SELECT id FROM institutions WHERE code = ? OR name = ?", (c_code, c_name))
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute("INSERT INTO institutions (name, code) VALUES (?, ?)", (c_name, c_code))
        return cur.lastrowid

    def normalize_tournament(self, raw_tournament_dir: Path) -> int:
        """
        Normalize a raw tournament directory into the database.
        Returns the new or existing tournament_id.
        """
        raw_dir = Path(raw_tournament_dir)
        manifest_file = raw_dir / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest not found in {raw_dir}")

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        slug = manifest["tournament_slug"]
        title = manifest["title"]
        source_url = manifest["source_url"]
        version = manifest.get("version", "2.11.0-c")

        year = None
        m_yr = re.search(r'20\d\d', title) or re.search(r"'?(\d\d)", slug)
        if m_yr:
            raw_yr = m_yr.group(0).replace("'", "")
            year = int("20" + raw_yr if len(raw_yr) == 2 else raw_yr)

        cur = self.conn.cursor()

        # 1. Insert or update tournament
        cur.execute(
            """
            INSERT INTO tournaments (slug, name, source_url, version, year, scoring_scale, extracted_at)
            VALUES (?, ?, ?, ?, ?, '60-80', ?)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                source_url=excluded.source_url,
                version=excluded.version,
                year=excluded.year,
                extracted_at=excluded.extracted_at
            """,
            (slug, title, source_url, version, year, manifest.get("extracted_at")),
        )
        cur.execute("SELECT id FROM tournaments WHERE slug = ?", (slug,))
        tournament_id = cur.fetchone()["id"]

        def find_file(*candidates):
            for c in candidates:
                p = raw_dir / c
                if p.exists():
                    return p
            return None

        # 2. Ingest Institutions (from official directory if present)
        inst_file = find_file("participants_institutions.json", "institutions.json")
        if inst_file:
            tables = json.loads(inst_file.read_text(encoding="utf-8"))
            if tables and "data" in tables[0]:
                for row in tables[0]["data"]:
                    code_cell = row[0].get("text", "") if isinstance(row[0], dict) else str(row[0])
                    name_cell = row[1].get("text", "") if isinstance(row[1], dict) else str(row[1])
                    if name_cell:
                        self.get_or_create_institution(code_cell, name_cell)

        # 3. Ingest Teams, Rosters, and Institutional Affiliation
        team_file = find_file("tab_team.json", "team_tab.json")
        team_id_map: Dict[str, int] = {}

        novice_team_names: Set[str] = set()
        novice_file = find_file("tab_team_novice.json", "team_tab_novice.json")
        if novice_file:
            n_tables = json.loads(novice_file.read_text(encoding="utf-8"))
            if n_tables and "data" in n_tables[0]:
                for row in n_tables[0]["data"]:
                    t_cell = row[1] if len(row) > 1 else None
                    if isinstance(t_cell, dict):
                        novice_team_names.add(t_cell.get("text", "").strip())

        if team_file:
            tables = json.loads(team_file.read_text(encoding="utf-8"))
            if tables and "data" in tables[0]:
                for row in tables[0]["data"]:
                    t_cell = None
                    for cell in row:
                        if isinstance(cell, dict) and "team-name" in cell.get("class", ""):
                            t_cell = cell
                            break
                    if not t_cell and len(row) > 1 and isinstance(row[1], dict):
                        t_cell = row[1]

                    if not t_cell:
                        continue

                    raw_team_name = t_cell.get("text", "").strip()
                    team_name = CANONICAL_TEAM_ALIASES.get((slug, raw_team_name), raw_team_name)
                    pop = t_cell.get("popover", {})
                    pop_title = pop.get("title", "")
                    content_list = pop.get("content", [])

                    roster_text = ""
                    source_team_link = ""
                    for c_item in content_list:
                        if "Record" in c_item.get("text", "") and c_item.get("link"):
                            source_team_link = c_item["link"]
                        elif not roster_text and c_item.get("text"):
                            roster_text = c_item["text"]

                    # Extract true school and separate from team identifier
                    s_code, s_name, ident = extract_school_and_team_identifier(team_name, pop_title)
                    inst_id = self.get_or_create_institution(s_code, s_name)

                    category = "NOVICE" if (team_name in novice_team_names or raw_team_name in novice_team_names) else "OPEN"

                    cur.execute(
                        """
                        INSERT INTO teams (tournament_id, name, institution_id, category, source_team_id, raw_roster_text)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(tournament_id, name) DO UPDATE SET
                            institution_id=excluded.institution_id,
                            category=excluded.category,
                            source_team_id=excluded.source_team_id,
                            raw_roster_text=excluded.raw_roster_text
                        """,
                        (tournament_id, team_name, inst_id, category, source_team_link, roster_text),
                    )
                    cur.execute("SELECT id FROM teams WHERE tournament_id = ? AND name = ?", (tournament_id, team_name))
                    tid = cur.fetchone()["id"]
                    team_id_map[team_name] = tid
                    team_id_map[raw_team_name] = tid

                    # Ingest team roster members
                    if roster_text:
                        members = [m.strip() for m in roster_text.split(",") if m.strip()]
                        for order, m_name in enumerate(members, 1):
                            p_id = self.get_or_create_person(m_name, tournament_id)
                            cur.execute(
                                """
                                INSERT OR IGNORE INTO tournament_roles (tournament_id, person_id, role, institution_id)
                                VALUES (?, ?, 'DEBATER', ?)
                                """,
                                (tournament_id, p_id, inst_id),
                            )
                            cur.execute(
                                """
                                INSERT OR IGNORE INTO team_members (team_id, person_id, member_order)
                                VALUES (?, ?, ?)
                                """,
                                (tid, p_id, order),
                            )

        # 4. Ingest Adjudicators from Participants List
        part_file = find_file("participants_list.json", "participants.json")
        if part_file:
            tables = json.loads(part_file.read_text(encoding="utf-8"))
            if tables and len(tables) > 0 and "data" in tables[0]:
                for row in tables[0]["data"]:
                    name_cell = row[0]
                    if isinstance(name_cell, dict):
                        adj_name = name_cell.get("text", "").strip()
                        if adj_name:
                            p_id = self.get_or_create_person(adj_name, tournament_id)
                            cur.execute(
                                """
                                INSERT OR IGNORE INTO tournament_roles (tournament_id, person_id, role)
                                VALUES (?, ?, 'ADJUDICATOR')
                                """,
                                (tournament_id, p_id),
                            )

        # 5. Ingest Rounds & Debates from Round Results Tables
        round_id_map: Dict[int, int] = {}

        # Build round name lookup from rounds_info if available
        rounds_meta: Dict[int, str] = {}
        for r_entry in manifest.get("rounds_info", []):
            if isinstance(r_entry, dict) and "number" in r_entry:
                rounds_meta[r_entry["number"]] = r_entry.get("name", f"Round {r_entry['number']}")

        # Determine preliminary rounds from tab_team.json or tab_speaker.json
        prelim_rounds: Set[int] = set()
        for tab_cand in ["tab_team.json", "tab_speaker.json", "team_tab.json", "speaker_tab.json"]:
            t_path = raw_dir / tab_cand
            if t_path.exists():
                try:
                    t_tables = json.loads(t_path.read_text(encoding="utf-8"))
                    if t_tables and "head" in t_tables[0]:
                        for col in t_tables[0]["head"]:
                            k = col.get("key", "") if isinstance(col, dict) else str(col)
                            m_r = re.match(r"^R(\d+)$", k)
                            if m_r:
                                prelim_rounds.add(int(m_r.group(1)))
                except Exception:
                    pass
            if prelim_rounds:
                break

        for r_num in manifest.get("rounds_extracted", []):
            r_file = raw_dir / f"round_{r_num}_results.json"
            if not r_file.exists():
                continue

            r_name = rounds_meta.get(r_num, f"Round {r_num}")
            name_lower = r_name.lower()
            is_knockout_name = any(kw in name_lower for kw in ["octo", "quarter", "semi", "final", "elimination", "knockout"])

            if prelim_rounds:
                r_type = "PRELIMINARY" if (r_num in prelim_rounds and not is_knockout_name) else "ELIMINATION"
            else:
                r_type = "ELIMINATION" if is_knockout_name or r_num > 7 else "PRELIMINARY"

            cur.execute(
                """
                INSERT INTO rounds (tournament_id, round_number, name, round_type)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tournament_id, round_number) DO UPDATE SET
                    name=excluded.name,
                    round_type=excluded.round_type
                """,
                (tournament_id, r_num, r_name, r_type),
            )
            cur.execute("SELECT id FROM rounds WHERE tournament_id = ? AND round_number = ?", (tournament_id, r_num))
            round_id = cur.fetchone()["id"]
            round_id_map[r_num] = round_id

            # Parse all debates directly from round results table
            tables = json.loads(r_file.read_text(encoding="utf-8"))
            if tables and "data" in tables[0]:
                col_keys = [c.get("key") for c in tables[0].get("head", [])]
                team_idx = col_keys.index("team") if "team" in col_keys else 0
                result_idx = col_keys.index("result") if "result" in col_keys else 1
                side_idx = col_keys.index("side") if "side" in col_keys else 2

                for row in tables[0]["data"]:
                    if len(row) < 3:
                        continue

                    debate_id = None
                    source_url = None
                    for cell in row:
                        if isinstance(cell, dict) and cell.get("link"):
                            m_deb = re.search(r'/debate/(\d+)/', cell["link"])
                            if m_deb:
                                debate_id = m_deb.group(1)
                                source_url = cell["link"]
                                break
                    if not debate_id:
                        continue

                    c0_cell = row[team_idx] if team_idx < len(row) else {}
                    c1_cell = row[result_idx] if result_idx < len(row) else {}
                    side_cell = row[side_idx] if side_idx < len(row) else {}

                    c0_text = clean_text(c0_cell.get("text", "") if isinstance(c0_cell, dict) else str(c0_cell))
                    c1_text = clean_text(c1_cell.get("text", "") if isinstance(c1_cell, dict) else str(c1_cell))
                    opp_name = re.sub(r"^\s*vs\s+", "", c1_text).strip()
                    side = clean_text(side_cell.get("text", "") if isinstance(side_cell, dict) else str(side_cell))

                    prop_team = c0_text if side.lower() == "proposition" else opp_name
                    opp_team = opp_name if side.lower() == "proposition" else c0_text

                    prop_tid = team_id_map.get(prop_team)
                    opp_tid = team_id_map.get(opp_team)

                    # Extract motion from cell 5 if present and valid
                    if len(row) > 5 and isinstance(row[5], dict):
                        m_text = clean_text(row[5].get("text", ""))
                        if m_text and not ("<span" in m_text or "<div" in m_text or "Ⓒ" in m_text or "adj-symbol" in m_text):
                            cur.execute("UPDATE rounds SET motion = ? WHERE id = ? AND motion IS NULL", (m_text, round_id))

                    cur.execute(
                        """
                        INSERT INTO debates (round_id, debate_id, venue, prop_team_id, opp_team_id, source_url)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(round_id, debate_id) DO UPDATE SET
                            prop_team_id=COALESCE(excluded.prop_team_id, debates.prop_team_id),
                            opp_team_id=COALESCE(excluded.opp_team_id, debates.opp_team_id),
                            source_url=COALESCE(excluded.source_url, debates.source_url)
                        """,
                        (round_id, debate_id, r_name, prop_tid, opp_tid, source_url),
                    )

        # Standardize Elimination Round Names using Backward Induction
        cur.execute("""
            SELECT r.id, r.round_number, r.name, COUNT(d.id) as deb_cnt
            FROM rounds r
            LEFT JOIN debates d ON d.round_id = r.id AND d.is_walkover = 0
            WHERE r.tournament_id = ? AND r.round_type = 'ELIMINATION'
            GROUP BY r.id
            ORDER BY r.round_number ASC
        """, (tournament_id,))
        elims = cur.fetchall()
        n_elims = len(elims)
        for e_idx, e_row in enumerate(elims):
            from_end = n_elims - 1 - e_idx
            cnt = e_row["deb_cnt"]
            old_name = e_row["name"] or ""
            old_lower = old_name.lower()

            if "novice" in old_lower:
                continue

            if from_end == 0:
                std_name = "Grand Final"
            elif from_end == 1:
                std_name = "Semifinals"
            elif from_end == 2:
                std_name = "Quarterfinals"
            elif from_end == 3:
                std_name = "Partial Octofinals" if cnt <= 4 else "Octofinals"
            elif from_end == 4:
                std_name = "Partial Double Octofinals" if cnt <= 8 else "Double Octofinals"
            else:
                std_name = old_name

            if std_name != old_name:
                cur.execute("UPDATE rounds SET name = ? WHERE id = ?", (std_name, e_row["id"]))


        # 5b. Extract Motions from motions.html if available
        motions_html_file = raw_dir / "motions.html"
        if motions_html_file.exists():
            m_html_content = motions_html_file.read_text(encoding="utf-8")
            card_pattern = r'<h4[^>]*card-title[^>]*>(.*?)</h4>(.*?)(?=<h4|$)'
            for m_match in re.finditer(card_pattern, m_html_content, re.DOTALL):
                r_title = clean_text(re.sub(r'<[^>]+>', ' ', m_match.group(1)))
                body_block = m_match.group(2)
                lead_m = re.search(r'<div[^>]*lead[^>]*>(.*?)</div>', body_block, re.DOTALL)
                if lead_m:
                    m_lead = clean_text(re.sub(r'<[^>]+>', ' ', lead_m.group(1)))
                    if m_lead:
                        cur.execute(
                            """
                            UPDATE rounds 
                            SET motion = ? 
                            WHERE tournament_id = ? 
                              AND (LOWER(name) = LOWER(?) OR LOWER(REPLACE(name, ' ', '')) = LOWER(REPLACE(?, ' ', '')))
                            """,
                            (m_lead, tournament_id, r_title, r_title),
                        )

        # 6. Ingest Atomic Debate Scoresheets
        scoresheets_dir = raw_dir / "scoresheets"
        if scoresheets_dir.exists():
            for s_file in scoresheets_dir.glob("debate_*.json"):
                data = json.loads(s_file.read_text(encoding="utf-8"))
                debate_id = str(data.get("debate_id", ""))
                motion = data.get("motion", "")
                round_info = data.get("round_info") or data.get("round", "")
                ballots = data.get("ballots", [])

                # Backward compatibility for single-ballot legacy format
                if not ballots and ("proposition" in data or "opposition" in data):
                    ballots = [{
                        "adjudicator_name": data.get("adjudicator_name", "Scoresheet"),
                        "institution": data.get("institution", ""),
                        "proposition": data.get("proposition", {}),
                        "opposition": data.get("opposition", {}),
                    }]

                cur.execute(
                    "SELECT d.id, d.round_id, d.prop_team_id, d.opp_team_id FROM debates d WHERE d.debate_id = ?",
                    (debate_id,),
                )
                existing_deb = cur.fetchone()

                if existing_deb:
                    db_debate_id = existing_deb["id"]
                    rid = existing_deb["round_id"]
                    prop_tid = existing_deb["prop_team_id"]
                    opp_tid = existing_deb["opp_team_id"]
                else:
                    m_rnum = re.search(r'Round\s+(\d+)', round_info)
                    round_num = int(m_rnum.group(1)) if m_rnum else 1
                    rid = round_id_map.get(round_num)
                    if not rid:
                        continue
                    prop_tid = None
                    opp_tid = None
                    db_debate_id = None

                if motion and rid:
                    cur.execute("UPDATE rounds SET motion = ? WHERE id = ? AND motion IS NULL", (motion, rid))

                # If prop_tid or opp_tid still missing, resolve from ballots
                if ballots and (not prop_tid or not opp_tid):
                    first_b = ballots[0]
                    p_b = first_b.get("proposition") or {}
                    o_b = first_b.get("opposition") or {}
                    p_name = clean_text(p_b.get("team_name") or p_b.get("team") or "")
                    o_name = clean_text(o_b.get("team_name") or o_b.get("team") or "")
                    if not prop_tid and p_name:
                        prop_tid = team_id_map.get(p_name)
                    if not opp_tid and o_name:
                        opp_tid = team_id_map.get(o_name)

                if db_debate_id is None:
                    cur.execute(
                        """
                        INSERT INTO debates (round_id, debate_id, venue, prop_team_id, opp_team_id, source_url)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(round_id, debate_id) DO UPDATE SET
                            venue=COALESCE(excluded.venue, debates.venue),
                            prop_team_id=COALESCE(excluded.prop_team_id, debates.prop_team_id),
                            opp_team_id=COALESCE(excluded.opp_team_id, debates.opp_team_id),
                            source_url=COALESCE(excluded.source_url, debates.source_url)
                        """,
                        (rid, debate_id, round_info, prop_tid, opp_tid, data.get("url")),
                    )
                    cur.execute("SELECT id FROM debates WHERE round_id = ? AND debate_id = ?", (rid, debate_id))
                    db_debate_id = cur.fetchone()["id"]
                else:
                    if round_info or prop_tid or opp_tid:
                        cur.execute(
                            """
                            UPDATE debates SET
                                venue = COALESCE(?, venue),
                                prop_team_id = COALESCE(?, prop_team_id),
                                opp_team_id = COALESCE(?, opp_team_id)
                            WHERE id = ?
                            """,
                            (round_info if round_info else None, prop_tid, opp_tid, db_debate_id),
                        )

                for b in ballots:
                    adj_name = b.get("adjudicator_name", "Scoresheet")
                    adj_inst = b.get("institution", "")

                    adj_pid = None
                    if adj_name and adj_name != "Scoresheet":
                        adj_pid = self.get_or_create_person(adj_name, tournament_id)
                        cur.execute(
                            "INSERT OR IGNORE INTO adjudicator_assignments (debate_id, person_id) VALUES (?, ?)",
                            (db_debate_id, adj_pid),
                        )

                    prop_data = b.get("proposition") or {}
                    opp_data = b.get("opposition") or {}
                    prop_total = prop_data.get("total_score") if prop_data.get("total_score") is not None else prop_data.get("total")
                    opp_total = opp_data.get("total_score") if opp_data.get("total_score") is not None else opp_data.get("total")

                    # Skip empty dummy scoresheet placeholders (0.0 totals)
                    if prop_total == 0.0 and opp_total == 0.0:
                        continue

                    margin = None
                    winner_side = None
                    if prop_total is not None and opp_total is not None:
                        margin = prop_total - opp_total
                        if margin > 0:
                            winner_side = "Proposition"
                        elif margin < 0:
                            winner_side = "Opposition"
                        else:
                            winner_side = "Tie"

                    # Check if ballot already recorded
                    cur.execute(
                        """
                        SELECT id FROM adjudicator_ballots 
                        WHERE debate_id = ? AND (adjudicator_person_id = ? OR adjudicator_raw_name = ?)
                        """,
                        (db_debate_id, adj_pid, adj_name),
                    )
                    b_row = cur.fetchone()
                    if b_row:
                        ballot_id = b_row["id"]
                    else:
                        cur.execute(
                            """
                            INSERT INTO adjudicator_ballots (
                                debate_id, adjudicator_person_id, adjudicator_raw_name, adjudicator_institution,
                                prop_total_score, opp_total_score, win_margin, winner_side
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (db_debate_id, adj_pid, adj_name, adj_inst, prop_total, opp_total, margin, winner_side),
                        )
                        ballot_id = cur.lastrowid

                        self._ingest_speeches(
                            ballot_id=ballot_id,
                            debate_id=db_debate_id,
                            round_id=rid,
                            team_id=prop_tid,
                            tournament_id=tournament_id,
                            side="Proposition",
                            speeches_data=prop_data.get("speeches", []),
                        )

                        self._ingest_speeches(
                            ballot_id=ballot_id,
                            debate_id=db_debate_id,
                            round_id=rid,
                            team_id=opp_tid,
                            tournament_id=tournament_id,
                            side="Opposition",
                            speeches_data=opp_data.get("speeches", []),
                        )

        # 7. Apply Manual Ballot Overrides (if any exist in data/overrides)
        patcher = ManualBallotPatcher(self.conn)
        patcher.apply_overrides()

        # 8. Reconcile Unballoted/Zero-Scored Debates from Speaker & Replies Tabs
        reconciler = TabReconciler(self.conn)
        reconciler.reconcile_tournament(tournament_id, raw_dir)

        self.conn.commit()
        return tournament_id


    def _ingest_speeches(
        self,
        ballot_id: int,
        debate_id: int,
        round_id: int,
        team_id: Optional[int],
        tournament_id: int,
        side: str,
        speeches_data: List[Dict[str, Any]],
    ) -> None:
        """Helper to ingest speech performances and detect Iron Man speeches."""
        cur = self.conn.cursor()

        substantive_speakers: Dict[str, int] = {}
        for s in speeches_data:
            spk_name = (s.get("speaker_name") or s.get("speaker") or "").strip()
            pos = s.get("position", "")
            if pos in ["1st", "2nd", "3rd"] and spk_name:
                substantive_speakers[spk_name] = substantive_speakers.get(spk_name, 0) + 1

        for s in speeches_data:
            spk_name = (s.get("speaker_name") or s.get("speaker") or "").strip()
            if not spk_name:
                continue

            spk_pid = self.get_or_create_person(spk_name, tournament_id)
            pos = s.get("position", "1st")
            speech_type = "REPLY" if pos == "Reply" else "SUBSTANTIVE"
            tot_score = (
                s.get("total_score") if s.get("total_score") is not None else s.get("total")
            ) or 0.0
            content = s.get("content")
            style = s.get("style")
            strategy = s.get("strategy")

            is_iron_man = 1 if (speech_type == "SUBSTANTIVE" and substantive_speakers.get(spk_name, 0) >= 2) else 0

            is_valid_rubric = 1
            if content is not None and style is not None and strategy is not None:
                if speech_type == "SUBSTANTIVE":
                    is_valid_rubric = 1 if is_valid_substantive_components(content, style, strategy) else 0
                else:
                    is_valid_rubric = 1 if is_valid_reply_components(content, style, strategy) else 0

            cur.execute(
                """
                INSERT INTO speech_performances (
                    ballot_id, debate_id, round_id, team_id, person_id,
                    side, position, speech_type, total_score, content, style, strategy,
                    is_valid_rubric, is_iron_man
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ballot_id, debate_id, round_id, team_id, spk_pid,
                    side, pos, speech_type, tot_score, content, style, strategy,
                    is_valid_rubric, is_iron_man,
                ),
            )
