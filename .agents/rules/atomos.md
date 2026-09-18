# Atomos Workspace Rule

You are working on Atomos, a debating data and analytical system.

Always treat the following files as project authority:

- @../../ATOMOS_CONSTITUTION.md
- @../../PROJECT_SPEC.md
- @../../ROADMAP.md
- @../../DECISIONS.md
- @../../docs/debating/DEBATING_RULEBOOK.md

## Required behavior

1. Read the relevant authority files before implementing domain behavior.
2. Never invent a debating rule.
3. Never silently resolve eligibility ambiguity.
4. Prefer `UNKNOWN` over unsupported certainty.
5. Preserve raw source data and provenance.
6. Keep people, teams, institutions, tournaments, rounds, speeches, scores, and context as distinct concepts unless the specification explicitly connects them.
7. For significant changes, explain the proposed approach before making broad modifications.
8. Make the smallest reasonable change.
9. Run relevant tests after changes.
10. Do not weaken or delete a domain test merely to make an implementation pass.
11. When code and a domain rule conflict, stop and report the conflict.
12. Do not perform large refactors during a small feature task without explicit justification.
13. When an assumption materially affects correctness, expose the assumption to the user.
14. Keep implementation details separate from domain definitions.

## Communication

The project owner is an experienced debater but a beginner programmer. Explain important programming concepts in plain language when they affect project decisions. Do not assume programming knowledge.

Refer to his superior Debating knowledge is needed
