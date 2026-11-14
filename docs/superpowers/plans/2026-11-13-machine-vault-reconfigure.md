# Machine Vault Reconfiguration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reconfigure legacy machine access as darckware with per-machine ForgeVault credentials.

**Architecture:** Keep connectivity separate from login standardization. Reuse the preparation route and panel for servers and workstations. Stage credentials and activate only after the new key authenticates as darckware.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic, React/TypeScript/TanStack Query, Vitest/pytest.

**Spec:** docs/superpowers/specs/2026-11-13-machine-vault-reconfigure.md

## Global Constraints

No SSH from agents, no production database in tests, no merge/push/deploy, no shared passwords/keys, no credential values in logs. Executors edit only the task worktree. A different reviewer inspects the diff; the supervisor homologates.

## Review Focus

- Ready legacy machine still offers reconfiguration.
- An existing darckware account cannot disable itself.
- A failed or concurrent preparation preserves the active credentials.
- Copy mode remains pending across screen reloads.
- A stored bootstrap password can only belong to the same machine.

## Tasks

- [ ] Extend backend preparation/schema/model for safe staged credentials, exact identity verification, existing account bootstrap, same-machine stored password and explicit copy validation. Add migration only if persistent staging needs new columns. Run isolated preparation/unique-key tests.
- [ ] Update MachinesCard/useMachinesViewModel to expose one configuration path and show legacy/pending state. Update usePreparationViewModel, useHostInventory and PrepareDialog for reconfiguration, self-lock protection, password source and pending validation. Localize pt-BR/en/es. Test through the existing component owners.
- [ ] Document the per-machine migration runbook, preserving existing access until validation. Update DESIGN.md behavior context. Run focused frontend tests/build and premium audit; supervisor verifies at 390px/1440px.
- [ ] Independent review, executor fixes, repeat until no BLOCKER/HIGH; supervisor reports verified results and any operational migration left pending. No merge/deploy without Marcelo's approval of the resulting content.
