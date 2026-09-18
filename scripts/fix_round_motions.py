"""
Fix and clean all round motions in atomos.db:
1. Replaces adjudicator chairs erroneously written to vvidc2026 rounds with real motions from motions.html.
2. Unescapes all HTML entities (&quot;, &#x27;, &amp;, etc.) across all rounds.
3. Normalizes whitespace and removes trailing/leading junk.
"""

import sqlite3
import html
import re
from pathlib import Path

DB_PATH = Path("data/atomos.db")
RAW_DIR = Path("data/raw")

def clean_motion_text(text: str) -> str:
    if not text:
        return ""
    t = html.unescape(text)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("’", "'").replace("`", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t

def fix_motions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Update vvidc2026 from raw/vvidc2026/motions.html
    vvidc_html = RAW_DIR / "vvidc2026" / "motions.html"
    if vvidc_html.exists():
        content = vvidc_html.read_text(encoding="utf-8")
        pattern = r'<h4[^>]*card-title[^>]*>(.*?)</h4>(.*?)(?=<h4|$)'
        for match in re.finditer(pattern, content, re.DOTALL):
            r_title = clean_motion_text(match.group(1))
            body = match.group(2)
            lead_m = re.search(r'<div[^>]*lead[^>]*>(.*?)</div>', body, re.DOTALL)
            if lead_m:
                m_lead = clean_motion_text(lead_m.group(1))
                if m_lead:
                    cur.execute("""
                        UPDATE rounds 
                        SET motion = ?
                        WHERE tournament_id = (SELECT id FROM tournaments WHERE slug = 'vvidc2026')
                          AND (LOWER(name) = LOWER(?) OR LOWER(REPLACE(name, ' ', '')) = LOWER(REPLACE(?, ' ', '')))
                    """, (m_lead, r_title, r_title))
                    print(f"Updated vvidc2026 [{r_title}] -> {m_lead[:60]}...")

    # 1b. Update slsdc26 from raw/slsdc26/motions.html
    slsdc_map = {
        1: "In developing nations, This House would nationalize all public services (e.g. healthcare, education, transport)",
        2: "This House, as an Olympic Athlete, would choose to participate in the Enhanced Games",
        3: "This House predicts a significant decline in higher education by 2050. This can include, but is not limited to, a sharp drop in university enrolment, closure of universities, much less emphasis placed on degree qualifications, etc.",
        4: "Assuming the government offers both, This House, as Sri Lanka's plantation communities, would accept land titles outside the estates rather than within them.",
        5: "This House, as a highly educated professional in an authoritarian state, would not work in any organization that is controlled or heavily influenced by the government.",
        6: "This House prefers Abrahamic religions over karmic religions.",
        7: "This House prefers a world where people did not keep pets.",
        8: "This House believes that American frontier AI firms should cease all cooperation with the US military.",
        9: "This House believes that local communities should have a veto over the construction of large scale infrastructure projects (e.g. data centers, pipelines, etc.)in their areas.",
        10: "This House predicts that the political gender gap will widen rather than shrink over the next 50 years.",
        11: "This House believes that lighter sentences and earlier release times should be implemented to combat the issue of overcrowding",
    }
    for r_num, m_text in slsdc_map.items():
        cur.execute("""
            UPDATE rounds
            SET motion = ?
            WHERE tournament_id = (SELECT id FROM tournaments WHERE slug = 'slsdc26')
              AND round_number = ?
        """, (clean_motion_text(m_text), r_num))
        print(f"Updated slsdc26 R{r_num} -> {m_text[:60]}...")

    # 1c. Update vijis26 from raw/vijis26/motions.html
    vijis_map = {
        1: "This house supports narratives that diversity is instrumentally valuable rather than morally right",
        2: "This House supports Jury Nullification",
        3: "This house, as a developing nation, would attempt to emulate the economic and cultural strategies of the Four Asian Tigers, as opposed to a Western-style development strategy that emphasizes establishing strong democratic institutions, gradual market reform, civil liberties and human rights protections as preconditions for economic progress.",
        4: "In the Sri Lankan circuit, This House would rather be a strong debater in an average team over an average debater in a strong team.",
        5: "This house, as a developing nation, would attempt to emulate the economic and cultural strategies of the Four Asian Tigers, as opposed to a Western-style development strategy that emphasizes establishing strong democratic institutions, gradual market reform, civil liberties and human rights protections as preconditions for economic progress.",
        6: "This House opposes the narrative that young love will fail",
        7: "This House would destroy the painting",
        8: "This House believes that it is in the interests of the Catholic Pope to have a foreign policy stance",
        9: "This House regrets the rise of the far-left",
        10: "This House, as Cobb, would choose to stay in limbo",
    }
    for r_num, m_text in vijis_map.items():
        cur.execute("""
            UPDATE rounds
            SET motion = ?
            WHERE tournament_id = (SELECT id FROM tournaments WHERE slug = 'vijis26')
              AND round_number = ?
        """, (clean_motion_text(m_text), r_num))
        print(f"Updated vijis26 R{r_num} -> {m_text[:60]}...")

    # 2. General cleanup of all motions in all rounds
    cur.execute("SELECT id, name, motion FROM rounds WHERE motion IS NOT NULL")
    rounds = cur.fetchall()
    cleaned_count = 0
    for r in rounds:
        orig = r["motion"]
        cleaned = clean_motion_text(orig)
        if cleaned != orig:
            cur.execute("UPDATE rounds SET motion = ? WHERE id = ?", (cleaned, r["id"]))
            cleaned_count += 1
            print(f"Cleaned entity/whitespace in round {r['id']} ({r['name']})")

    conn.commit()
    print(f"\nSuccessfully cleaned {cleaned_count} round motions.")

    # 3. Print report of all motions
    print("\n--- Current Rounds Motion Inventory ---")
    cur.execute("""
        SELECT t.slug, r.id, r.round_number, r.name, r.motion
        FROM rounds r
        JOIN tournaments t ON r.tournament_id = t.id
        ORDER BY t.slug, r.round_number
    """)
    rows = cur.fetchall()
    for row in rows:
        m_str = f"'{row['motion'][:65]}...'" if row['motion'] else "None"
        print(f"[{row['slug']}] R{row['round_number']:02d} ({row['name']}): {m_str}")

    conn.close()

if __name__ == "__main__":
    fix_motions()
