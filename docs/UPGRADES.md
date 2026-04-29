# Upgrade Records

This directory is the product and engineering upgrade log for SpeechFolio.

Every non-trivial upgrade should have a short design record before implementation starts. The goal is to keep product intent, data-model choices, rollout order, and verification notes in one place, so later changes do not have to reconstruct context from chat history or commits.

## Required For

- Schema changes or new persisted data fields
- Pipeline behavior changes that affect generated article quality
- LLM prompt, taxonomy, classifier, or model-routing changes
- New background jobs, migrations, or batch backfills
- User-facing workflow changes that affect analytics, digest, import, export, or settings

## Template

```md
# YYYY-MM-DD Upgrade Name

## Status

Proposed | In Progress | Shipped | Superseded

## Context

What problem are we solving, and why now?

## Decision

What are we changing?

## Data Model

Any schema, settings, or migration changes.

## Execution Plan

Ordered steps, including scripts and rollout sequence.

## Verification

Tests, backfills, production checks, and rollback notes.

## Open Questions

Things that need product or engineering decisions later.
```

## Records

- [2026-04-29 Mobile Adaptation](./upgrades/2026-04-29-mobile-adaptation.md)
- [2026-04-28 Tag / Topic Taxonomy Upgrade](./upgrades/2026-04-28-tag-topic-taxonomy.md)
- [2026-04-28 Tags / Entities Cleanup](./upgrades/2026-04-28-tags-entities-cleanup.md)
