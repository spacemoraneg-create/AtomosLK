# ATOMOS DEBATING RULEBOOK

## Purpose

This file is the authoritative domain reference for debating rules used by Atomos.

**The coding agent must not invent missing rules.**

When a rule is not yet documented here, the agent should mark the requirement as unknown and ask the project owner to define it before implementing behavior that depends on it.

Atomos is specifically designed for **Sri Lankan Debaters' Council (DC) endorsed WSDC-format high school debating**.

## Rule Status

Every rule has one of these statuses:

- `[CONFIRMED]` — explicitly established and approved by the project owner.
- `[PROVISIONAL]` — currently believed to be correct but awaiting confirmation.
- `[UNKNOWN]` — not yet defined. Agent must not implement behaviour that depends on this.
- `[RETIRED]` — no longer applies, with historical applicability documented.

---

## 1. Debate Format

`[CONFIRMED]` The format is WSDC (World Schools Debating Championship) style, as used in all DC-endorsed high school tournaments in Sri Lanka.

`[CONFIRMED]` Every debate has exactly **8 speeches**: 6 substantive speeches (3 per side) and 2 reply speeches (1 per side).

`[CONFIRMED]` The speech order is fixed: **P1 → O1 → P2 → O2 → P3 → O3 → OR → PR**

- P = Proposition, O = Opposition
- Speeches 1–3 on each side are substantive speeches
- OR = Opposition Reply, PR = Proposition Reply
- The reply speeches are in reverse order (Opposition replies first)

`[CONFIRMED]` This format does not change between tournaments. All DC-endorsed tournaments use the same format.

---

## 2. Scoring

### 2.1 Score Ranges

`[CONFIRMED]` A **substantive speech** is scored in the range **60–80**.

`[CONFIRMED]` A **reply speech** is scored in the range **30–40**.

`[CONFIRMED]` The current scoring scale (60–80 for substantive, 30–40 for reply) came into effect on **1 January 2026**, replacing the previous 69–81 scale. Atomos currently handles only the new scale.

> Source: `docs/debating/Scoring Scale.txt` — "Amendment of Speaker Scoring Criteria for Endorsed Tournaments"

### 2.2 Score Components

`[CONFIRMED]` Each speech is scored across 3 components:

| Component | Weight | Substantive Range | Reply Range |
|-----------|--------|-------------------|-------------|
| **Content** (what is said) | 40% | 24–32 | 12–16 |
| **Style** (how it is said) | 40% | 24–32 | 12–16 |
| **Strategy** (why it is said) | 20% | 12–16 | 6–8 |

`[CONFIRMED]` The component scoring ranges for substantive speeches are defined at these standards:

| Standard | Content (/32) | Style (/32) | Strategy (/16) |
|----------|--------------|-------------|----------------|
| Perfect | 31.5–32 | 31.5–32 | 16 |
| Exceptional | 30.5–31 | 30.5–31 | 15.5 |
| Excellent | 29.5–30 | 29.5–30 | 15 |
| Good | 28.5–29 | 28.5–29 | 14.5 |
| Average | 28 | 28 | 14 |
| Below Average | 27–27.5 | 27–27.5 | 13.5 |
| Unsatisfactory | 26–26.5 | 26–26.5 | 13 |
| Poor | 25–25.5 | 25–25.5 | 12.5 |
| Very Poor | 24–24.5 | 24–24.5 | 12 |

> Source: `docs/debating/Scoring Scale.txt` — Guideline 3

`[CONFIRMED]` Reply speeches use the same 3 components with the same percentage weighting, scaled to the 30–40 range.

### 2.3 Scoresheet

`[CONFIRMED]` A single adjudicator's scoresheet for a round contains individual component scores (Content, Style, Strategy) for each of the 8 speeches.

### 2.4 Team Round Score

`[CONFIRMED]` A team's score for a round = **sum of all 4 of their speeches** (3 substantive + 1 reply).

- Minimum possible team round score: 60 + 60 + 60 + 30 = **210**
- Maximum possible team round score: 80 + 80 + 80 + 40 = **280**

`[CONFIRMED]` The team with the higher total wins the round.

### 2.5 Win Margin

`[CONFIRMED]` Win margin for a round = the team's score minus their opponent's score. This can be positive (if they won) or negative (if they lost).

`[CONFIRMED]` A team's **average win margin** = the average of their margins across all preliminary rounds. This can be negative overall.

---

## 3. Adjudication

`[CONFIRMED]` In preliminary rounds, a room will have **1–3 adjudicators**.

`[CONFIRMED]` In a **paneled room** (multiple adjudicators), multiple scoresheets may be submitted.

`[CONFIRMED]` If the panel has a **unanimous decision**, the final score is the average of all scoresheets.

`[CONFIRMED]` If the panel has a **split decision** (e.g., 1–2), only the scoresheets of the **majority** are averaged. The dissenting scoresheet is discarded from the final score calculation.

`[PROVISIONAL]` Individual adjudicator scoresheets are publicly visible on some Tabbycat tournament pages but not all. Atomos should extract individual ballots when available and fall back to the final averaged score when they are not.

---

## 4. Teams

### 4.1 Team Composition

`[CONFIRMED]` A team must be **registered with at least 3 members**. A team can have **at most 4 members**.

`[CONFIRMED]` A team cannot register with fewer than 3 members.

`[CONFIRMED]` Who speaks in which round can change from round to round. Members may rotate, sit out, or speak in every round — this is flexible within the team.

`[CONFIRMED]` Team members cannot change within a tournament. The roster is fixed for the duration of one tournament but can change freely between tournaments.

### 4.2 Iron Man

`[CONFIRMED]` **Iron Man** is when a team debates a round with only **2 active speakers** (the 3rd or 4th member is unavailable for that round).

`[CONFIRMED]` In an Iron Man round, one of the two speakers gives **two substantive speeches** (typically 1st and 3rd positions).

`[CONFIRMED]` A team of 3+ members registered can Iron Man occasionally, but cannot register with only 2.

### 4.3 Team Identity

`[CONFIRMED]` Team names follow the pattern: **school abbreviation + team identifier** (e.g., "RC A", "BC Gold").

`[CONFIRMED]` The school abbreviation is consistent (a team from Royal College always starts with "RC").

`[CONFIRMED]` The team identifier (A, B, Gold, Purple, X, etc.) can change between tournaments. "RC A" at one tournament and "RC X" at another might be the same team.

`[CONFIRMED]` When Atomos encounters two teams with the same school abbreviation but different identifiers, it should present this to the user for manual resolution rather than automatically merging or splitting them.

---

## 5. People and Identity

### 5.1 Person

`[CONFIRMED]` An **individual** (person) is a singular human. Their identity is permanent.

`[CONFIRMED]` A person can be a **debater** (speaks in a team) or an **adjudicator** (judges debates).

`[CONFIRMED]` A person's role can change from tournament to tournament (debater at one, adjudicator at another), but **cannot change within a single tournament**.

`[CONFIRMED]` The same person's debater history and adjudicator history should both be linked to one person entity.

### 5.2 Cross-Tournament Identity

`[CONFIRMED]` People are identified **by name only** in Tabbycat. There is no persistent cross-tournament ID.

`[CONFIRMED]` Names can be spelled differently across tournaments (e.g., "Balishta Wijesinghe" vs "B. Wijesinghe").

`[CONFIRMED]` Identity resolution across tournaments must not automatically merge people based on name similarity. Ambiguous cases must be flagged for manual resolution.

### 5.3 Team Membership

`[CONFIRMED]` A person does not need to speak in a round to be considered part of the team. If they are registered on the team, they share in the team's results.

`[CONFIRMED]` Debaters can move between teams within the same school, and can move to different schools between tournaments.

---

## 6. Institutions

`[CONFIRMED]` An **institution** is the school that hosts teams.

`[CONFIRMED]` Teams represent their host school — a team is an extension of the school.

`[CONFIRMED]` Individuals are not permanently tied to a school. They can represent different schools at different tournaments.

---

## 7. Eligibility

Eligibility determines whether a debater or team qualifies to be represented in certain rankings and tabs.

### 7.1 Individual Speaker Tab Eligibility

`[CONFIRMED]` A debater must have spoken in **at least 3 preliminary rounds** in a tournament to be eligible for the **Speaker Tab** of that tournament.

### 7.2 Individual Reply Tab Eligibility

`[CONFIRMED]` There is **no minimum round requirement** for the Reply Tab. Anyone who gave at least one reply speech is listed.

### 7.3 Iron Man — Individual Eligibility Effect

`[CONFIRMED]` When a debater Iron Mans (gives 2 substantive speeches in a round), **only the higher of the two substantive scores** represents them in the Speaker Tab.

`[CONFIRMED]` The reply score during an Iron Man round is treated normally — it counts toward the Reply Tab average as usual.

### 7.4 Team Tab Eligibility

`[CONFIRMED]` A team must have debated in **at least 3 preliminary rounds** to qualify for the Team Tab and knockout rounds.

### 7.5 Iron Man — Team Eligibility Effect

`[CONFIRMED]` If a team Iron Mans in **more than 2 rounds**, they remain eligible for the Team Tab but are **disqualified from knockout rounds**, regardless of their preliminary performance.

---

## 8. Tournament Tabs and Rankings

### 8.1 Speaker Tab (per tournament)

`[CONFIRMED]` The Speaker Tab ranks individual debaters within a tournament.

`[CONFIRMED]` Only **substantive speech scores** count toward the Speaker Tab. Reply scores do not.

`[CONFIRMED]` A debater's Speaker Tab score = **average of their substantive scores** across all preliminary rounds they spoke in.

`[CONFIRMED]` Eligibility: must have spoken in at least 3 preliminary rounds (see §7.1).

### 8.2 Reply Tab (per tournament)

`[CONFIRMED]` The Reply Tab is a **separate tab** from the Speaker Tab.

`[CONFIRMED]` The Reply Tab ranks individual debaters by their **average reply speech score** across all preliminary rounds where they gave a reply.

`[CONFIRMED]` No minimum round requirement for eligibility (see §7.2).

### 8.3 Team Tab (per tournament)

`[CONFIRMED]` Teams are ranked using the following criteria, in order of priority:

1. **Number of wins** (more wins = higher rank)
2. **ATSS — Average Total Speaker Score** (the average of the team's round scores across all preliminary rounds, where team round score = sum of all 4 speeches)
3. **Average win margin** (the average point difference across all preliminary rounds)

`[CONFIRMED]` Eligibility: must have debated in at least 3 preliminary rounds (see §7.4).

---

## 9. Master Tabs (cross-tournament)

### 9.1 Master Speaker Tab

`[CONFIRMED]` The Master Speaker Tab ranks individual debaters across all tournaments.

`[CONFIRMED]` **New Standard Regulation (Priority)**: A debater's Master Speaker Tab score = **cumulative speech average** across all qualifying tournaments ($\frac{\sum \text{qualifying substantive speeches}}{N}$). Each qualifying speech is weighted equally.

`[RETIRED / LEGACY]` **Legacy Regulation**: A debater's score was calculated as the **arithmetic mean of tournament averages** (average of averages). This regulation remains computed and accessible in parallel for backwards compatibility under `avg_of_avgs`.

`[CONFIRMED]` Only tournaments where the debater was **eligible for Speaker Tab** (§7.1, $\ge 3$ prelim rounds) count towards either master calculation.

### 9.2 Master Reply Tab

`[CONFIRMED]` The Master Reply Tab ranks individual debaters across all tournaments by reply performance.

`[CONFIRMED]` A debater's Master Reply Tab score = **average of their tournament Reply Tab averages** (average of averages). Each tournament is weighted equally.

### 9.3 Master Team Tab

`[CONFIRMED]` The Master Team Tab ranks teams across tournaments.

`[CONFIRMED]` A team must have been **eligible for Team Tab in at least 3 tournaments** to appear on the Master Team Tab.

`[UNKNOWN]` The exact ranking formula for the Master Team Tab (average of ATSS? average of wins? combination?) is not yet defined. The project owner should specify this.

---

## 10. Novice and Open Classification

### 10.1 Individual Classification

`[CONFIRMED]` A debater is classified as **Open** if they have been eligible for Speaker Tab in **7 or more DC-endorsed tournaments where their team was classified as Open**.

`[CONFIRMED]` A debater is classified as **Novice** if they have been eligible for Speaker Tab in **6 or fewer** such tournaments.

`[CONFIRMED]` A brand-new debater with zero tournaments is Novice (0 ≤ 6).

`[CONFIRMED]` **Only DC-endorsed Open tournaments count** toward the 7-tournament threshold:
- ✅ Pure Open tournament, on an Open team, eligible for Speaker Tab → counts
- ✅ Novice&Open tournament, on an Open team, eligible for Speaker Tab → counts
- ❌ Novice&Open tournament, on a Novice team, eligible for Speaker Tab → does NOT count
- ❌ Pure Novice tournament → does NOT count

`[CONFIRMED]` The count is based on the **team's classification**, not the individual's. If you are individually under the threshold but are on an Open team (because a teammate is Open), that tournament counts.

### 10.2 Team Classification

`[CONFIRMED]` A team is **Novice** only if **all members are Novice**.

`[CONFIRMED]` If **at least one member** has been eligible for Speaker Tab in 7 or more qualifying tournaments (making them Open), the entire team is classified as **Open**.

### 10.3 Tournament Types

`[CONFIRMED]` **Open tournaments**: Standard tournaments. Any team can participate.

`[CONFIRMED]` **Novice tournaments**: Only Novice debaters may participate. No Open debater can be involved in the debating process in any way.

`[CONFIRMED]` **Novice&Open tournaments**: Have a shared preliminary round structure, but after preliminaries:
- Novice teams are placed in a **separate Novice Team Tab** and **Novice Speaker Tab**
- Open teams are placed in a **separate Open Team Tab** and **Open Speaker Tab**
- Two separate knockout brackets exist: Novice knockouts and Open knockouts

---

## 11. Tournament Structure

### 11.1 Preliminary Rounds

`[CONFIRMED]` A tournament has **4–7 preliminary rounds**, depending on the organizer's decision.

`[CONFIRMED]` Preliminary rounds determine team rankings, speaker tabs, and who qualifies for knockouts.

### 11.2 Knockout Rounds

`[CONFIRMED]` Knockout rounds are **elimination rounds** that follow preliminary rounds.

`[CONFIRMED]` Knockout rounds **do not have speaker scores** and do not affect Team Tab or Speaker Tab.

`[CONFIRMED]` The possible knockout formats are:

| Format | Teams Breaking | Type |
|--------|---------------|------|
| Double Octos | 32 | Standard |
| Double Partial Octos (DPO) | 24 | Partial |
| Octos | 16 | Standard |
| Partial Octos | 12 | Partial |
| Quarters | 8 | Standard |
| Semis | 4 | Standard |

### 11.3 Standard Knockout Pairing

`[CONFIRMED]` In standard formats, knockout rounds use **power pairing**: highest-ranked vs lowest-ranked.

Example (Octos): 1st vs 16th, 2nd vs 15th, 3rd vs 14th, ... 8th vs 9th.

### 11.4 Partial Knockout Format

`[CONFIRMED]` In partial formats, the bracket is split:

- **Top ⅓** of breaking teams advance directly to the next knockout stage.
- **Bottom ⅔** debate a preliminary knockout round. Half of them (the winners) advance to join the top ⅓.

Specifically:
- **DPO (24 teams):** Top 8 advance → bottom 16 play → 8 winners join → Octos with 16 teams
- **Partial Octos (12 teams):** Top 4 advance → bottom 8 play → 4 winners join → Quarters with 8 teams

### 11.5 Knockout Path Inheritance

`[CONFIRMED]` When a lower-ranked team defeats a higher-ranked team in knockouts, they inherit that higher-ranked team's knockout path.

Example: If 16th-seed beats 1st-seed, 16th takes the 1st-seed's path and faces whoever is in the 8th-seed's path.

---

## 12. Draws and Pairing (Preliminary Rounds)

> Source: `docs/debating/Tab rules.txt` — Official DC Tabulation Procedures, mandatory from October 2020.

### 12.1 Round 1

`[CONFIRMED]` Preliminary Round 1 is **randomly drawn**.

`[CONFIRMED]` Teams from the **same institution** will not be drawn against each other in Round 1.

### 12.2 Subsequent Rounds

`[CONFIRMED]` All rounds after Round 1 are **power-paired** using the tabulation software.

`[CONFIRMED]` After each round, a league table is calculated, ranking teams by:
1. Number of wins
2. Total speaker score
3. Net margin of victory

`[CONFIRMED]` Teams are divided into **brackets** (groups of teams with the same number of wins).

`[CONFIRMED]` Each team is drawn against another team **from the same bracket**.

`[CONFIRMED]` **No two teams may debate each other more than once** during preliminary rounds.

### 12.3 Within-Bracket Ranking (for pairing purposes)

`[CONFIRMED]` Within a bracket, teams are ranked by:
1. Average judges' scores (ATSS)
2. Net margin of victory

Note: number of wins does not matter within a bracket (all teams in the bracket have the same wins).

`[CONFIRMED]` Pairing within a bracket: **highest-ranked vs lowest-ranked** (fold pairing).

### 12.4 Pull-Ups

`[CONFIRMED]` When a bracket has an odd number of teams, a team from the **bracket immediately below** is "pulled up".

`[CONFIRMED]` The pulled-up team is taken from the **middle** of the lower bracket.

`[CONFIRMED]` A team should be pulled up **no more than once** during preliminary rounds (with extreme exceptions).

`[CONFIRMED]` Each bracket should contain **no more than one pull-up team** (with extreme exceptions).

> For the full pull-up rules including extreme edge cases, see `docs/debating/Tab rules.txt` sections 2.6–2.10.

### 12.5 Side Allocation

`[CONFIRMED]` The tabulation software should ensure **balanced side allocation** across preliminary rounds as far as possible.

`[CONFIRMED]` Where necessary, a team may have **4 debates on one side and 1 on the other** to meet other draw constraints.

---

## 13. Walkovers and Swing Teams

> Source: `docs/debating/Tab rules.txt` — sections 3.1–3.5.

### 13.1 Swing Teams

`[CONFIRMED]` If the tournament has an odd number of competing teams, the host arranges a **swing team** for preliminary rounds.

`[CONFIRMED]` The swing team consists of 3 students meeting the DC age and education criteria, but they do not need to come from the same institution.

`[CONFIRMED]` The swing team is judged normally, but is **not eligible** for break rounds or any team/individual awards.

### 13.2 Walkovers

`[CONFIRMED]` If a team cannot participate in a round:

**For the team receiving the walkover (the team that showed up):**
- Awarded a win with a **6-point margin**
- Receives a team score equal to their own **average score across rounds they did participate in**, rounded down to the nearest 0.5

**For the team giving the walkover (the team that didn't show up):**
- Awarded a loss with a **6-point deficit**
- Receives a team score adjusted to reflect a 6-point loss based on the opposition's average score

### 13.3 First-Round Walkovers

`[CONFIRMED]` If a walkover occurs in Round 1 (and no swing team can be fielded), scores are calculated using the modern 60–80 scale averages (note: old 2020 tab documentation referenced 75 based on the legacy 69–81 scale, but on the 60–80 scale, 70 is the standard average score):

**Team receiving the walkover (Winner):**
- Average speaker score of **70.0** for substantive speeches
- Reply speech score of **35.0**
- Total team round score: **245.0** ($70 + 70 + 70 + 35$)
- Margin: **+6.0**

**Team giving the walkover (Loser / Forfeiting Team):**
- Total team round score: **239.0** (reflecting a 6-point deficit: $245.0 - 6.0$)
- Margin: **-6.0**


---

## 14. Time and Season Definitions

`[CONFIRMED]` Tournaments are organized into **years** and **seasons** (terms).

| Season | Months |
|--------|--------|
| 1st Term | January, February, March, April |
| Mid Term | May, June, July, August |
| End Term | September, October, November, December |

---

## 15. Data Source

`[CONFIRMED]` The sole data source for Atomos is **Tabbycat** (online tabulation software).

`[CONFIRMED]` All DC-endorsed tournament pages are **publicly accessible** without login.

`[CONFIRMED]` Tabbycat has a public API in addition to HTML pages.

---

## Appendix: Unresolved Questions

The following questions have been identified but not yet resolved. The agent must not implement behaviour that depends on these.

| ID | Question | Impact |
|----|----------|--------|
| UQ-1 | What is the exact ranking formula for the Master Team Tab? (Average of ATSS? Average of wins? Combination?) | Master Team Tab implementation |
| UQ-2 | Should the old scoring scale (69–81, pre-January 2026) be supported in future? A mapping exists in `Scoring Scale.txt`. | Historical data support |
| UQ-3 | In a Novice&Open tournament, are there separate Reply Tabs for Novice and Open? | Novice&Open tournament tab structure |
| UQ-4 | What are the exact scoring rules and component breakdowns for the **Reply speech** component table (equivalent to the substantive table in §2.2)? | Reply score validation |
