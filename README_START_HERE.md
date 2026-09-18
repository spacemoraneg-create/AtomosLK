# Atomos — Start Here

You do not need to understand all of these files yet.

## Where these files go

Copy the contents of this package into the **root folder of your Atomos Git project**.

The most important files are:

- `ATOMOS_CONSTITUTION.md` — permanent principles for the project.
- `PROJECT_SPEC.md` — what Atomos is supposed to become.
- `docs/debating/DEBATING_RULEBOOK.md` — debating rules. **You will edit this.**
- `.agents/rules/atomos.md` — instructions Antigravity should follow while coding.
- `ROADMAP.md` — the order in which we should build Atomos.
- `DECISIONS.md` — important decisions we make during development.

## What you need to do now

Read these three files first:

1. `PROJECT_SPEC.md`
2. `ATOMOS_CONSTITUTION.md`
3. `docs/debating/DEBATING_RULEBOOK.md`

The first two are mostly my translation of your idea into engineering language.
The third is deliberately incomplete. **Do not let the agent invent debating rules. You will gradually fill this in.**

## Antigravity

Open the entire Atomos folder as your Antigravity workspace.

Antigravity workspace Rules belong in `.agents/rules`. The included `atomos.md` is the persistent project rule for the agent.

After these files are in place, the first useful Antigravity prompt is:

> Read `ATOMOS_CONSTITUTION.md`, `PROJECT_SPEC.md`, `ROADMAP.md`, `DECISIONS.md`, and `docs/debating/DEBATING_RULEBOOK.md`. Do not write application code yet. Inspect the workspace and tell me what you understand about Atomos, what information is still missing, and what the smallest safe first implementation should be. Do not invent any debating rule.
