# ATOMOS CONSTITUTION

## 1. Purpose

Atomos is an analytical system for Sri Lankan debating.

Its long-term architecture has five folds:

1. Extractor
2. Normalizer / Database
3. Analytical Engine
4. LLM Intelligence
5. Interactive UI / Atomos Environment

## 2. Core Principle

Atomos must preserve information instead of throwing information away.

Raw source data should remain traceable to normalized records, and normalized records should remain traceable to derived analytics.

## 3. Domain Truth Comes Before Convenience

A convenient implementation must never override a debating rule.

If the software and the rulebook disagree, the software is wrong until the conflict is investigated.

If a rule is unknown, ambiguous, missing, or disputed, the system must not silently invent an answer, Rather it must communicate with the User immediately before any action is taken.

## 4. Eligibility Is a First-Class Domain Concept

Eligibility must never be guessed from names, rankings, institutional affiliation, or other weak signals unless an explicit rule authorizes that inference.

Where eligibility cannot be established, the system should be capable of representing `UNKNOWN` rather than forcing a true/false answer.

Eligibility decisions must be traceable to the rule and evidence used.

## 5. Atomic Performance Data

The fundamental unit of debating performance is an individual speech in a round.

Scoresheets and other source evidence should be preserved so that higher-level statistics can be recomputed.

## 6. Context Is Mandatory

A score without context is incomplete.

Where available, Atomos should preserve tournament, date, round, matchup, adjudication, motion, and other relevant context.

## 7. Identity Must Be Explicit

People, teams, and institutions are different entities.

Identity resolution must not casually merge two people because their names look similar.

Uncertainty about identity must be representable.

## 8. Derived Data Must Be Reproducible

Analytics are derived from underlying data.

A stored statistic should have a known definition and a reproducible calculation whenever practical.

## 9. Raw Data Is Evidence

Raw extracted data must not be silently overwritten by normalized or corrected data.

Corrections should preserve the original source and record what was changed and why.

## 10. Agent Behaviour

Before making a significant change, the coding agent should inspect the existing system, read the relevant rulebook sections, identify assumptions, implement the smallest reasonable change, and run relevant tests.

The agent must not perform broad refactors merely because it prefers a different architecture.

The agent should not Assume without reason, the agent is allowed independent decision making with the authorizarion of the user, absense of conflict with existing rules to that point and progressing the mission.

## 11. Testing

Important domain rules must have automated tests.

A passing test suite is not proof that a domain rule is correct, but a broken domain test is a reason to stop and investigate rather than silently weakening the test.

## 12. Human Authority

The project owner defines what debating means for Atomos.

The coding agent defines implementation details only within those domain constraints.

## 13. Change Management

Changes to domain rules must be deliberate and documented.

When a rule changes, check its effect on code, tests, historical data, and analytics.

## 14. Abense of Data

In the absense of data even withen Tabycat Websites, it is the responcibility of the Agent to notify the User and request a solution, whatever the solution maybe, the agent must verify it is possible to continue down that path

## 15. Relationship Between User and Agent

The User is the Human, that has the vast undesanding of Debating and Debating rules and regulations, and the one who has the core philosophy of the project

The agent is the Worker, that has vast undestanding of Coding and computational work in general, he will undestand the philosophy of the user, he will learn from the user's Debating knowledge and he will help achieve the goals of the User.

## 16. Development

The agent must wait for Direct and Confident cofirmation from the User that the develop of a specific Fold is comeplete and that progresion of the next can start

If the User of the Agent identifies a issue with a earlier Fold while in development of another Fold, the Development of the current work must hault immediately untill the User is confident that the issue you or the User flagged has been resolved
