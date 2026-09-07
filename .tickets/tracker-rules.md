# Tracker Rules

## Purpose
This tracker is the operational build control surface for humans and builder agents.

## First file to read
Read `docs/ticket-progress.md` first. Do not scan the full backlog to choose work
unless the queue is empty or the user explicitly asks for broader planning.

## How to choose work
Choose the first row in `LLM_NEXT_QUEUE` where `Status` is `next` and `Blocked By` is `None`.

## Required queue maintenance rule
Every ticket update must regenerate `docs/ticket-progress.md`, including `LLM_NEXT_QUEUE`.
Use `foreman tickets update <id>` — never manually edit generated sections.

## Blocked work
Do not implement blocked rows unless the blocker itself is the approved next work.

## Done policy
Never mark a ticket `done` without required validation evidence or a documented test exception.
Use `foreman tickets complete <id> --validation-result passed --evidence "..."`.

## New work policy
Newly discovered work belongs in the Discovered Future Work Inbox.
Use `foreman tickets discover --summary "..." --rationale "..."`.

## Generated document policy
Do not manually edit generated sections of `docs/ticket-progress.md`.
Use the `foreman tickets` commands instead.

## STEP_STATUS protocol
When Foreman is running this project, include the ticket ID in your done marker:
  STEP_STATUS: done | ticket="T001" summary="implemented the feature"
Use `foreman tickets discover` for newly discovered work during a build run.
