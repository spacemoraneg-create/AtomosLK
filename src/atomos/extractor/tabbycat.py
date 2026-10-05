"""
Atomos Tabbycat Extractor (Fold 1)

Comprehensive extractor for Tabbycat debating tournament instances:
- Automatically discovers all public tournament routes (Tabs, Novice Tabs, Motions, Breaks, Participants, Rounds)
- Preserves raw HTML and structured JSON responses for provenance (Constitution §2, §9)
- Extracts atomic debate scoresheets for all adjudicators in paneled and single-judge rooms
- Preserves individual speech component marks: Content, Style, Strategy, and totals
"""

import concurrent.futures
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class SpeechRecord:
    position: str             # "1st", "2nd", "3rd", "Reply"
    speaker_name: str
    total_score: float
    content: Optional[float] = None
    style: Optional[float] = None
    strategy: Optional[float] = None


@dataclass
class TeamBallot:
    team_name: str
    side: str                 # "Proposition" or "Opposition"
    total_score: float
    speeches: List[SpeechRecord] = field(default_factory=list)


@dataclass
class AdjudicatorBallot:
    adjudicator_name: str     # Name from card title e.g. "Adam Dhilshan" or "Single / Unnamed"
    institution: str          # Institution from card title e.g. "GCD"
    proposition: Optional[TeamBallot] = None
    opposition: Optional[TeamBallot] = None


@dataclass
class DebateRecord:
    debate_id: str
    url: str
    motion: str
    round_info: str
    ballots: List[AdjudicatorBallot] = field(default_factory=list)


class TabbycatExtractor:
    """Production-grade extractor for Tabbycat instances."""

    def __init__(self, user_agent: str = "Atomos/1.0 (+https://github.com/debating-atomos)", **kwargs):
        self.user_agent = user_agent

    def fetch(self, url: str, max_retries: int = 3, timeout: int = 30) -> str:
        """Fetch page content via HTTP GET with retry and backoff."""
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0 * (attempt + 1))
        return ""

    @staticmethod
    def extract_tables_data(html: str) -> List[Dict[str, Any]]:
        """
        Extract the `tablesData` array embedded inside `window.vueData`.
        Uses balanced bracket matching to cleanly extract the JSON array.
        """
        marker = "tablesData:"
        idx = html.find(marker)
        if idx == -1:
            return []
        start = idx + len(marker)
        open_bracket = html.find("[", start)
        if open_bracket == -1:
            return []

        count = 0
        in_string = False
        escape = False
        end_bracket = -1

        for i in range(open_bracket, len(html)):
            char = html[i]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "[":
                    count += 1
                elif char == "]":
                    count -= 1
                    if count == 0:
                        end_bracket = i + 1
                        break

        if end_bracket == -1:
            return []

        tables_json = html[open_bracket:end_bracket]
        try:
            return json.loads(tables_json)
        except Exception:
            return []

    def discover_tournament(self, base_url: str) -> Dict[str, Any]:
        """
        Inspect a tournament homepage to discover:
        - Slug and tournament title
        - Tabbycat version
        - All public routes (Tabs, Novice Tabs, Participants, Motions, Breaks, Rounds)
        """
        parsed = urllib.parse.urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        home_url = base_url if base_url.endswith("/") else base_url + "/"
        html = self.fetch(home_url)

        # Detect slug
        slug_match = re.search(r'<a[^>]*class=["\'][^"\']*navbar-brand[^"\']*["\'][^>]*href=["\']/([^/\s"\']+)["\']', html)
        if not slug_match:
            slug_match = re.search(r'<a[^>]*href=["\']/([^/\s"\']+)["\'][^>]*class=["\'][^"\']*navbar-brand[^"\']*["\']', html)
        if not slug_match:
            slug_match = re.search(r'class="navbar-brand"\s+href="/([^/]+)/"', html)

        if slug_match:
            slug = slug_match.group(1)
        else:
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                slug = path_parts[0]
            else:
                host_subdomain = parsed.netloc.split(".")[0]
                slug = host_subdomain if host_subdomain not in ("www", "tabbycat", "calicotab") else "tournament"

        # Tournament title
        title_match = re.search(r'<title>\s*(.*?)\s*</title>', html, re.DOTALL)
        raw_title = title_match.group(1) if title_match else slug
        clean_title = re.sub(r'\s+', ' ', raw_title).replace('&amp;', '&').replace('&#x27;', "'")

        # Tabbycat version
        ver_match = re.search(r'runs on Tabbycat\s+([^\s<]+)', html)
        version = ver_match.group(1) if ver_match else "unknown"

        # Discover all internal routes linked from navigation
        hrefs = set(re.findall(r'href=[\'"]([^\'"]+)[\'"]', html))
        
        discovered_routes: Dict[str, List[Dict[str, str]]] = {
            "tabs": [],
            "participants": [],
            "motions": [],
            "breaks": [],
            "rounds": [],
        }

        # Match rounds specifically from HTML elements or hrefs
        seen_round_nums: Set[int] = set()
        round_matches = re.findall(
            r'<a[^>]*href=["\'](?:/' + re.escape(slug) + r')?/results/round/(\d+)/?["\'][^>]*>(.*?)</a>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        for r_num_str, r_name in round_matches:
            r_num = int(r_num_str)
            if r_num not in seen_round_nums:
                seen_round_nums.add(r_num)
                clean_name = re.sub(r'<[^>]+>', '', r_name).strip()
                discovered_routes["rounds"].append({
                    "number": r_num,
                    "name": clean_name or f"Round {r_num}",
                    "path": f"/{slug}/results/round/{r_num}/",
                })

        # Also discover rounds from all hrefs if not captured above
        for h in sorted(hrefs):
            m_r = re.search(r'/results/round/(\d+)/?', h)
            if m_r:
                r_num = int(m_r.group(1))
                if r_num not in seen_round_nums:
                    seen_round_nums.add(r_num)
                    discovered_routes["rounds"].append({
                        "number": r_num,
                        "name": f"Round {r_num}",
                        "path": f"/{slug}/results/round/{r_num}/" if slug else h,
                    })

        discovered_routes["rounds"].sort(key=lambda x: x["number"])

        # Discover all other tournament-specific paths
        slug_prefix = f"/{slug}/"
        for h in sorted(hrefs):
            if h.startswith(slug_prefix):
                path_rel = h[len(slug_prefix):].rstrip("/")
            elif h.startswith("/") and not any(h.startswith(f"/{other}/") for other in ["static", "media", "admin"]):
                path_rel = h.lstrip("/").rstrip("/")
            else:
                continue

            if path_rel.startswith("tab/"):
                clean_name = path_rel.replace("tab/", "").replace("/", " ").title() + " Tab"
                if not any(r["path"] == h for r in discovered_routes["tabs"]):
                    discovered_routes["tabs"].append({"name": clean_name, "path": h})
            elif path_rel.startswith("participants/"):
                clean_name = path_rel.replace("participants/", "").replace("/", " ").title()
                if not any(r["path"] == h for r in discovered_routes["participants"]):
                    discovered_routes["participants"].append({"name": clean_name, "path": h})
            elif path_rel.startswith("motions"):
                clean_name = path_rel.replace("motions/", "").replace("/", " ").title() or "Motions"
                if not any(r["path"] == h for r in discovered_routes["motions"]):
                    discovered_routes["motions"].append({"name": clean_name, "path": h})
            elif path_rel.startswith("break/"):
                clean_name = path_rel.replace("break/", "").replace("/", " ").title()
                if not any(r["path"] == h for r in discovered_routes["breaks"]):
                    discovered_routes["breaks"].append({"name": clean_name, "path": h})

        return {
            "origin": origin,
            "slug": slug,
            "title": clean_title,
            "version": version,
            "base_url": home_url,
            "routes": discovered_routes,
        }

    def parse_scoresheet_html(self, html: str, debate_id: str, url: str) -> DebateRecord:
        """
        Parse a debate scoresheet HTML page to extract atomic speech marks
        across all adjudicator ballots (single or paneled).
        """
        # Motion
        motion = ""
        m_match = re.search(r'<h4[^>]*>\s*Motion\s*</h4>\s*(.*?)\s*</div>', html, re.DOTALL)
        if not m_match:
            m_match = re.search(r'Motion\s*</h4>\s*(.*?)\s*</div>', html, re.DOTALL)
        if m_match:
            motion = re.sub(r'<[^>]+>', ' ', m_match.group(1)).strip()

        # Round & venue info
        round_info = ""
        r_match = re.search(r'<small class="text-muted[^"]*">\s*(.*?)\s*</small>', html, re.DOTALL)
        if r_match:
            round_info = re.sub(r'<[^>]+>', ' ', r_match.group(1)).strip()

        # Split page by card blocks: <div class="card...">
        card_blocks = re.split(r'<div class="card(?:\s+[^"]*)?">', html)
        ballots: List[AdjudicatorBallot] = []

        for b in card_blocks:
            # Check if this card contains scoresheets (speeches)
            if "1st" not in b or "Reply" not in b:
                continue

            # Card title e.g. "From Adam Dhilshan (GCD)" or "Scoresheet"
            t_match = re.search(r'<h4[^>]*class="card-title"[^>]*>(.*?)</h4>', b, re.DOTALL)
            card_title = re.sub(r'<[^>]+>', '', t_match.group(1)).strip() if t_match else "Scoresheet"

            adj_name = card_title
            institution = ""
            m_adj = re.search(r'From\s+(.*?)\s*(?:\((.*?)\))?$', card_title)
            if m_adj:
                adj_name = m_adj.group(1).strip()
                institution = m_adj.group(2).strip() if m_adj.group(2) else ""

            # Extract team columns in this card: <div class="col-6 list-group mb-3">
            col_pattern = r'<div class="col-6 list-group mb-3">(.*?)</div>\s*(?=<div class="col-6 list-group mb-3"|</div>\s*</div>)'
            cols = re.findall(col_pattern, b, re.DOTALL)

            teams_ballots: List[TeamBallot] = []
            for c_html in cols:
                team_name = ""
                side = ""
                team_total = 0.0
                speeches: List[SpeechRecord] = []

                # Team total line: <li class="list-group-item active"><strong>Total for STC A (Proposition)</strong>...
                tot_match = re.search(r'Total for (.*?) \((Proposition|Opposition)\).*?<span[^>]*badge[^>]*>\s*([\d\.]+)\s*</span>', c_html, re.DOTALL)
                if tot_match:
                    team_name = tot_match.group(1).strip()
                    side = tot_match.group(2).strip()
                    try:
                        team_total = float(tot_match.group(3).strip())
                    except ValueError:
                        team_total = 0.0

                # Extract speeches
                items = re.findall(r'<li class="list-group-item">(.*?)(?=<li class="list-group-item|$)', c_html, re.DOTALL)
                for it in items:
                    pos_m = re.search(r'<strong>(1st|2nd|3rd|Reply)</strong>', it)
                    if not pos_m:
                        continue
                    pos = pos_m.group(1)

                    tot_m = re.search(r'<span class="badge[^"]*badge-secondary[^"]*float-right">\s*([\d\.]+)\s*</span>', it)
                    speech_total = float(tot_m.group(1)) if tot_m else 0.0

                    name_part = re.search(r'</strong>\s*(.*?)\s*<span class="badge', it, re.DOTALL)
                    speaker_name = re.sub(r'<[^>]+>', '', name_part.group(1)).strip() if name_part else ""

                    content_val = None
                    style_val = None
                    strategy_val = None

                    for comp_m in re.finditer(r'<li>\s*<strong>(Content|Style|Strategy)</strong>.*?<span class="badge[^>]*>\s*([\d\.]+)\s*</span>', it, re.DOTALL):
                        c_name = comp_m.group(1)
                        val = float(comp_m.group(2))
                        if c_name == "Content":
                            content_val = val
                        elif c_name == "Style":
                            style_val = val
                        elif c_name == "Strategy":
                            strategy_val = val

                    speeches.append(
                        SpeechRecord(
                            position=pos,
                            speaker_name=speaker_name,
                            total_score=speech_total,
                            content=content_val,
                            style=style_val,
                            strategy=strategy_val,
                        )
                    )

                if team_name or speeches:
                    teams_ballots.append(
                        TeamBallot(
                            team_name=team_name,
                            side=side,
                            total_score=team_total,
                            speeches=speeches,
                        )
                    )

            prop_ballot = next((tb for tb in teams_ballots if tb.side == "Proposition"), None)
            opp_ballot = next((tb for tb in teams_ballots if tb.side == "Opposition"), None)
            if not prop_ballot and len(teams_ballots) >= 1:
                prop_ballot = teams_ballots[0]
            if not opp_ballot and len(teams_ballots) >= 2:
                opp_ballot = teams_ballots[1]

            ballots.append(
                AdjudicatorBallot(
                    adjudicator_name=adj_name,
                    institution=institution,
                    proposition=prop_ballot,
                    opposition=opp_ballot,
                )
            )

        return DebateRecord(
            debate_id=debate_id,
            url=url,
            motion=motion,
            round_info=round_info,
            ballots=ballots,
        )

    def extract_tournament(
        self,
        base_url: str,
        output_dir: Path,
        max_ballots_per_round: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive extraction of all tournament data:
        - Automatically navigates all discovered tabs, novice tabs, participants, and breaks.
        - Extracts all round results and atomic debate scoresheets.
        - Preserves raw HTML and JSON files on disk with a provenance manifest.
        """
        disc = self.discover_tournament(base_url)
        origin = disc["origin"]
        slug = disc["slug"]

        raw_dir = output_dir / slug
        raw_dir.mkdir(parents=True, exist_ok=True)
        scoresheets_dir = raw_dir / "scoresheets"
        scoresheets_dir.mkdir(parents=True, exist_ok=True)

        extracted_data: Dict[str, Any] = {
            "metadata": disc,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "tabs": {},
            "participants": {},
            "motions": {},
            "breaks": {},
            "rounds": {},
            "debates": [],
        }

        # 1. Extract all discovered Tabs (Open, Novice, Replies, etc.)
        for tab_route in disc["routes"]["tabs"]:
            tab_path = tab_route["path"]
            clean_slug_key = tab_path.replace(f"/{slug}/", "").strip("/").replace("/", "_")
            tab_url = f"{origin}{tab_path}"
            try:
                html = self.fetch(tab_url)
                (raw_dir / f"{clean_slug_key}.html").write_text(html, encoding="utf-8")
                tables = self.extract_tables_data(html)
                (raw_dir / f"{clean_slug_key}.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
                extracted_data["tabs"][clean_slug_key] = {
                    "name": tab_route["name"],
                    "url": tab_url,
                    "tables": tables,
                }
            except Exception as e:
                extracted_data["tabs"][f"{clean_slug_key}_error"] = str(e)

        # 2. Extract Participants & Institutions
        for part_route in disc["routes"]["participants"]:
            part_path = part_route["path"]
            clean_slug_key = part_path.replace(f"/{slug}/", "").strip("/").replace("/", "_")
            part_url = f"{origin}{part_path}"
            try:
                html = self.fetch(part_url)
                (raw_dir / f"{clean_slug_key}.html").write_text(html, encoding="utf-8")
                tables = self.extract_tables_data(html)
                (raw_dir / f"{clean_slug_key}.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
                extracted_data["participants"][clean_slug_key] = {
                    "name": part_route["name"],
                    "url": part_url,
                    "tables": tables,
                }
            except Exception as e:
                extracted_data["participants"][f"{clean_slug_key}_error"] = str(e)

        # 3. Extract Break Lists & Brackets
        for break_route in disc["routes"]["breaks"]:
            break_path = break_route["path"]
            clean_slug_key = break_path.replace(f"/{slug}/", "").strip("/").replace("/", "_")
            break_url = f"{origin}{break_path}"
            try:
                html = self.fetch(break_url)
                (raw_dir / f"{clean_slug_key}.html").write_text(html, encoding="utf-8")
                tables = self.extract_tables_data(html)
                if tables:
                    (raw_dir / f"{clean_slug_key}.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
                extracted_data["breaks"][clean_slug_key] = {
                    "name": break_route["name"],
                    "url": break_url,
                    "has_tables": bool(tables),
                }
            except Exception as e:
                extracted_data["breaks"][f"{clean_slug_key}_error"] = str(e)

        # 4. Extract Motions & Statistics
        for mot_route in disc["routes"]["motions"]:
            mot_path = mot_route["path"]
            clean_slug_key = mot_path.replace(f"/{slug}/", "").strip("/").replace("/", "_")
            mot_url = f"{origin}{mot_path}"
            try:
                html = self.fetch(mot_url)
                (raw_dir / f"{clean_slug_key}.html").write_text(html, encoding="utf-8")
                tables = self.extract_tables_data(html)
                if tables:
                    (raw_dir / f"{clean_slug_key}.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
                extracted_data["motions"][clean_slug_key] = {
                    "name": mot_route["name"],
                    "url": mot_url,
                    "has_tables": bool(tables),
                }
            except Exception as e:
                extracted_data["motions"][f"{clean_slug_key}_error"] = str(e)

        # 5. Extract Preliminary and Knockout Rounds & All Debate Scoresheets
        for r_info in disc["routes"]["rounds"]:
            r_num = r_info["number"]
            r_url = f"{origin}{r_info['path']}"
            try:
                r_html = self.fetch(r_url)
                (raw_dir / f"round_{r_num}_results.html").write_text(r_html, encoding="utf-8")
                r_tables = self.extract_tables_data(r_html)
                (raw_dir / f"round_{r_num}_results.json").write_text(json.dumps(r_tables, indent=2), encoding="utf-8")
                extracted_data["rounds"][r_num] = {
                    "info": r_info,
                    "tables": r_tables,
                }
            except Exception as re_err:
                extracted_data["rounds"][f"{r_num}_error"] = str(re_err)
                continue

            # Extract debate scoresheets from ballot links
            if r_tables:
                col_keys = [c.get("key") for c in r_tables[0].get("head", [])]
                ballot_idx = col_keys.index("ballot") if "ballot" in col_keys else -1
                if ballot_idx != -1:
                    seen_ballots: Set[str] = set()
                    for row in r_tables[0].get("data", []):
                        cell = row[ballot_idx]
                        if isinstance(cell, dict) and cell.get("link"):
                            link = cell["link"]
                            if link not in seen_ballots:
                                seen_ballots.add(link)

                    ballots_to_fetch = sorted(seen_ballots)
                    if max_ballots_per_round is not None:
                        ballots_to_fetch = ballots_to_fetch[:max_ballots_per_round]

                    def _fetch_single_ballot(item: Tuple[int, str]) -> Optional[Dict[str, Any]]:
                        idx, b_link = item
                        debate_id_m = re.search(r'/results/debate/(\d+)/scoresheets/?', b_link)
                        debate_id = debate_id_m.group(1) if debate_id_m else f"r{r_num}_{idx}"
                        b_url = f"{origin}{b_link}"

                        html_file = scoresheets_dir / f"debate_{debate_id}.html"
                        json_file = scoresheets_dir / f"debate_{debate_id}.json"

                        try:
                            if html_file.exists():
                                b_html = html_file.read_text(encoding="utf-8")
                            else:
                                b_html = self.fetch(b_url)
                                html_file.write_text(b_html, encoding="utf-8")

                            parsed_record = self.parse_scoresheet_html(b_html, debate_id, b_url)
                            rec_dict = asdict(parsed_record)
                            json_file.write_text(json.dumps(rec_dict, indent=2), encoding="utf-8")
                            return rec_dict
                        except Exception as d_err:
                            print(f"[EXTRACT WARNING] Failed debate {debate_id} in round {r_num}: {d_err}")
                            return None

                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                        fetched_ballots = list(executor.map(_fetch_single_ballot, enumerate(ballots_to_fetch)))

                    for rec in fetched_ballots:
                        if rec is not None:
                            extracted_data["debates"].append(rec)

        # 6. Generate Complete Provenance Manifest
        manifest = {
            "tournament_slug": slug,
            "title": disc["title"],
            "version": disc["version"],
            "source_url": base_url,
            "extracted_at": extracted_data["extracted_at"],
            "tabs_extracted": list(extracted_data["tabs"].keys()),
            "participants_extracted": list(extracted_data["participants"].keys()),
            "motions_extracted": list(extracted_data["motions"].keys()),
            "breaks_extracted": list(extracted_data["breaks"].keys()),
            "rounds_extracted": [r["number"] for r in disc["routes"]["rounds"]],
            "rounds_info": disc["routes"]["rounds"],
            "total_debates_extracted": len(extracted_data["debates"]),
        }
        (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        extracted_data["metadata"] = manifest

        return extracted_data
