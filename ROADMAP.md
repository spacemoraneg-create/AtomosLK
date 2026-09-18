# ATOMOS ROADMAP

The project should be built in small verified stages.

## Phase 0 — Foundation

- Set up Git repository.
- Add project rules and specifications.
- Define debating terminology and rules.
- Establish a test structure.

## Phase 1 — Tabbycat Investigation

- Choose several real tournaments.
- Inspect available APIs and HTML.
- Identify exactly where relevant information appears.
- Record differences between tournament versions / configurations.

Do not build a large extractor before understanding the source.

## Phase 2 — Minimal Extractor

Build a small extractor that can reliably process one known tournament.

Validate the extracted data against the source.

## Phase 3 — Normalizer / Database

Create the first structured representation of people, teams, institutions, speeches, scores, rounds, tournaments, and context.

Preserve provenance.

## Phase 4 — Validation

Build automated tests for critical domain behavior, particularly identity, score handling, tournament structure, and eligibility.

## Phase 5 — Analytical Engine

Implement a small set of reliable common analytics first.

## Phase 6 — LLM Layer

Give the LLM controlled access to the structured data and analytical tools.

Do not let the LLM directly invent or mutate domain facts.

## Phase 7 — Interactive UI

Build the first useful interface for searching, inspecting, analysing, and visualizing Atomos data.

## Phase 8 — Atomos Environment

Gradually make the UI capable of orchestrating analysis, development, debugging, and system extension.

## Rule

At every phase, prefer a small working system over a large unfinished system.

Only when the User is satisfied with the State of a specific Phase you are allowed to start progresion of next
