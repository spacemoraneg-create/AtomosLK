# ATOMOS — PROJECT SPECIFICATION

## Vision

Atomos is intended to turn Sri Lankan debating tournament data into a structured historical knowledge and analytical system that can answer both ordinary and novel questions about debating.

The user should ultimately be able to ask questions in ordinary language while Atomos determines what data, definitions, mathematics, and reasoning are required to answer them.

## Fold 1 — Extractor

Input: a Tabbycat tournament URL or other supported source.

Goal: extract as much tournament information as technically available, including API data, HTML data, linked tournament information, and structured information embedded in pages.

Relevence of that information does not matter, as the Normalizer will filter irrelevency. In the absense of Information refer to "ATOMOS_CONSTITUTION.md" for rules of action.

The extractor should preserve source information and provenance.

## Fold 2 — Normalizer / Database

Transform extracted information into a consistent model organized around:

### Creator

- Person
- Debater
- Adjudicator
- Team
- Institution
- Relationships among them

### Creation

The smallest important performance records, especially individual speeches and scoresheets.

Higher-level outputs such as speaker tabs, team tabs, rankings, and deviations should be derivable from underlying records where possible.

Goal is to preserve the Atomic information that is the root of all other, Substantive Speaker scores & Reply Speaker scores. 

### Context

- Tournament
- Tournament date
- Round
- Draw / matchup
- Adjudicator assignment
- Motion, where available
- Other relevant contextual information

## Fold 3 — Analytical Engine

Maintain commonly used derived information so the LLM does not need to recompute everything from raw records for every question.

Examples include:

- Master Speaker Tab (The overall Avg of the Avgs of each individual who debated, Refer to docs\debating\DEBATING_RULEBOOK.md for rules of eligibilty)
- Speaker Tab (The speaker ranking for each tournament, tournament specific)
- Master Team Tab (The overall Avg of wins and Avgs from tournaments inputed, Refer to "docs\debating\DEBATING_RULEBOOK.md" for rules of ranking and eligibility) 
- Averages (Individually averages of {Wins, Losses, Ranking, Prelimanary rounds debated, Deviations of speaks, Win margins,} Some of these are independent to Teams/Debaters, some apply to both)
- Rankings 
- Trends
- Growth metrics
- Historical comparisons

The analytical layer should evolve as repeated user questions reveal useful common computations.

Complex or novel questions can fall back to normalized atomic data.

## Fold 4 — LLM Intelligence

The LLM must:

1. Understand human language and debating terminology.
2. Resolve ambiguity explicitly rather than making hidden assumptions.
3. Determine what data is needed.
4. Choose between analytical data and atomic data.
5. Perform mathematical calculations accurately.
6. Explain definitions and assumptions when they materially affect the answer.
7. Avoid inventing facts or rules.


## Fold 5 — Interactive UI / Atomos Environment

The UI is not merely a dashboard.

The long-term goal is an interactive environment through which a user can:

- Ask natural-language questions.
- Inspect data.
- Explore people, teams, institutions, tournaments, rounds, and scoresheets.
- View analytical results.
- Inspect calculations and provenance.
- Investigate data problems.
- Run or refine queries.
- Visualize trends and relationships.
- Eventually interact with and extend the system itself.

Long-term, the UI should function as an AI-native development and analysis environment, reducing the need for a conventional IDE for many Atomos-specific tasks.

## Non-Goals for the First Version

The first version does not need:

- A sophisticated LLM interface.
- A complete nationwide tournament archive.
- Every possible statistic.
- Autonomous modification of its own architecture.
- A polished production UI.

The first version should prove that reliable tournament data can be extracted, normalized, validated, and queried.
