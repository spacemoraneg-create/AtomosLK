# Tabbycat Data Investigation & Mapping

This document records the findings from **Phase 1: Tabbycat Investigation**, conducted on two live DC-endorsed Sri Lankan tournaments:
1. **VJIS '26** (`https://vijis26.calicotab.com/vijis26/`)
2. **SLSDC 2026** (`https://slsdc2026.calicotab.com/slsdc26/`)

---

## 1. Access & API Availability

- **Public Access**: Both tournament sites are completely public; no authentication, session cookies, or tokens are required to view results, tabs, participants, or scoresheets.
- **REST API (`/api/v1/`)**: Returns HTTP 404 (disabled or unexposed on Calicotab public endpoints).
- **Embedded Structured Data (`window.vueData`)**: **Every single data page** on Tabbycat 2.11.0-c embeds structured JSON directly into a script tag as `tablesData`. This provides structured, machine-readable data without needing HTML scraping.

---

## 2. Page & Data Map

| Page | URL Path | Data Available | Format |
|---|---|---|---|
| **Team Tab** | `/<slug>/tab/team/` | Rank, Team name, Round results, Wins, ATSS, AWM, DSR. Popovers include full school name and all registered debaters. | `window.vueData.tablesData` (JSON) |
| **Speaker Tab** | `/<slug>/tab/speaker/` | Rank, Debater name, Team name, Round-by-round substantive scores, Average score, Stdev, Number of rounds. | `window.vueData.tablesData` (JSON) |
| **Replies Tab** | `/<slug>/tab/replies/` | Rank, Debater name, Team name, Round-by-round reply scores, Average score, Stdev, Number of rounds. | `window.vueData.tablesData` (JSON) |
| **Round Results** | `/<slug>/results/round/<N>/` | Team name, Result (Win/Loss), Opponent, Side (Prop/Opp), Motion, Adjudicators, and Link to Debate Scoresheet. | `window.vueData.tablesData` (JSON) |
| **Debate Scoresheet** | `/<slug>/results/debate/<id>/scoresheets/` | **Atomic Scoresheet**: Substantive scores (1st, 2nd, 3rd) and Reply speech, with exact breakdowns: **Content**, **Style**, **Strategy**, and Team Total. | HTML DOM structure |
| **Participants** | `/<slug>/participants/list/` | Complete directory of debaters, teams, institutions, and adjudicators. | `window.vueData.tablesData` (JSON) |
| **Break Rounds** | `/<slug>/break/teams/open/` | Breaking teams list and seed rankings. | `window.vueData.tablesData` (JSON) |

---

## 3. Atomic Scoresheet Layout

At the deepest level (`/<slug>/results/debate/<id>/scoresheets/`), Tabbycat exposes the atomic performance data required by the Atomos Constitution:

```text
Ballot: Proposition Team vs Opposition Team
Motion: Full motion text
Adjudicator: Adjudicator Name (and panel if paneled)

Proposition:
  1st Speaker: Name, Total Score, Content, Style, Strategy
  2nd Speaker: Name, Total Score, Content, Style, Strategy
  3rd Speaker: Name, Total Score, Content, Style, Strategy
  Reply:       Name, Total Score, Content, Style, Strategy
  Team Total:  Sum of all 4 speeches

Opposition:
  1st Speaker: Name, Total Score, Content, Style, Strategy
  2nd Speaker: Name, Total Score, Content, Style, Strategy
  3rd Speaker: Name, Total Score, Content, Style, Strategy
  Reply:       Name, Total Score, Content, Style, Strategy
  Team Total:  Sum of all 4 speeches
```

---

## 4. Tournament Configuration Variations

Comparing VJIS '26 and SLSDC 2026 revealed the following configuration variations that Atomos must accommodate:
- **Preliminary Round Count**: VJIS '26 had 5 preliminary rounds; SLSDC 2026 had 7 preliminary rounds. Atomos must dynamically discover the number of preliminary rounds from the navigation menu rather than hardcoding.
- **URL Slug Structure**: `https://vijis26.calicotab.com` uses `/vijis26/`, while `https://slsdc2026.calicotab.com` uses `/slsdc26/`. The extractor should take the base URL and detect the slug automatically.
- **Knockout Formats**: VJIS '26 uses Double Partial Octos (top 8 advance, bottom 16 play); SLSDC 2026 uses Octofinals (top 16 play). Both are supported by our domain rules.
