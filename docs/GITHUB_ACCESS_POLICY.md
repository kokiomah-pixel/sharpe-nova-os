# Sharpe Nova OS — GitHub Access Policy & Implementation Plan

## Institutional Infrastructure Upgrade

Version: `v1.0`

## Purpose

This document upgrades Sharpe Nova OS GitHub access from operator-dependent credentials to institutional infrastructure quality.

The goal is to ensure that repository access is:

- role-based
- auditable
- revocable
- least-privilege
- not dependent on one individual credential

## Core Principle

**No system-critical GitHub access should depend on a personal classic token.**

Personal credentials may exist only for:

- human development access
- emergency break-glass recovery
- temporary bridge usage during migration

System automation must use:

- GitHub App
- scoped permissions
- short-lived installation tokens

## Target State

### Human Access

Used by:

- Architect
- developers
- authorized operators

Allowed methods:

- SSH keys
- fine-grained personal access tokens only if needed

Not allowed as system infrastructure:

- classic PAT as primary automation credential

### System Access

Used by:

- treasury agent
- automation
- CI/CD
- repo-integrated services
- machine-to-repo workflows

Required method:

- GitHub App

### Governance State

GitHub access must support:

- attribution
- rotation
- revocation
- audit trail
- least-privilege scoping
- separation between operator access and system access

## Policy Rules

### Rule 1 — Personal classic PATs are not institutional infrastructure

Classic PATs may be used only as temporary bridge credentials or break-glass admin access.

### Rule 2 — All machine access must migrate to a GitHub App

Any repo operation performed by agents, scripts, or automation must use GitHub App credentials.

### Rule 3 — Least privilege is mandatory

Every credential must be scoped only to the repositories and actions required.

### Rule 4 — Human and system access must remain separate

No automation may depend on a personal workstation credential.

### Rule 5 — Break-glass access must be explicitly labeled

Any retained personal credential must be marked as:

- temporary
- emergency-only
- non-primary

### Rule 6 — Access inventory is required

All current credential usage must be mapped before migration is considered complete.

## Immediate Implementation Plan

### Phase 1 — Stabilize Current State

Objectives:

- preserve continuity
- reduce hidden credential dependence
- identify all token exposure points

Actions:

- label regenerated PAT as `BREAK_GLASS_TEMP_ONLY`
- record where it is currently used:
  - local git
  - VS Code Git integration
  - terminal credential helper
  - scripts
  - GitHub Actions secrets
  - deployment hooks
  - automation tools
- remove any duplicate or unknown copies
- verify which workflows actually require write access

Deliverable:

- a complete access inventory

### Phase 2 — Create Nova GitHub App

App name recommendation:

- `nova-infra`
- `nova-treasury-agent`

App purpose:

This GitHub App will act as Nova’s institutional system identity for repository automation.

Minimum use cases:

- treasury agent repo read/write
- branch creation
- PR creation
- issue/comment automation if needed
- workflow interaction if required

### Phase 3 — Scope Permissions

Repository scope:

Only install the GitHub App on repositories it actually needs.

Recommended permissions:

Adjust as needed, but begin minimally.

Repository permissions:

- Contents: Read and Write
- Pull Requests: Read and Write
- Metadata: Read
- Issues: Read and Write only if needed
- Actions: Read or Write only if required
- Commit statuses: Read and Write only if required

Organization permissions:

- none unless clearly needed

Rule:

Do not grant permissions because they "might be useful later."

### Phase 4 — Install and Test

Test scenarios:

- repo read
- repo clone/fetch
- branch creation
- commit/push
- PR creation
- workflow trigger compatibility
- failure logging
- revocation behavior

Acceptance standard:

The treasury agent and related automations must function without the personal PAT.

### Phase 5 — Cutover

Actions:

- migrate automation to GitHub App credentials
- update secrets/configuration
- remove personal token from automation paths
- retain personal token only as emergency admin fallback

Deliverable:

- system workflows no longer depend on personal credentials

### Phase 6 — Lockdown

Actions:

- phase out classic PAT usage where possible
- enforce fine-grained PAT only for humans if PAT use remains necessary
- treat personal credentials as operator access only
- document approval rules for future credential creation

Desired end state:

Nova source-control access becomes institutional, not personal.

## VS Code Implementation Notes

### Local Developer Setup

Recommended for human developers:

- use SSH for git operations in VS Code
- avoid storing classic PATs as long-lived editor credentials
- keep system automation outside personal editor auth state

Practical rule:

VS Code should be used for:

- human authoring
- review
- local development

VS Code should not become the hidden runtime credential source for Nova automation.

## Credential Classification

### Class A — Human Developer Access

Owner: named individual

Allowed methods:

- SSH
- fine-grained PAT

Use case:

- interactive development

### Class B — System Automation Access

Owner: Nova system role

Allowed method:

- GitHub App

Use case:

- agent and workflow operations

### Class C — Break-Glass Access

Owner: authorized admin only

Allowed method:

- tightly controlled personal credential

Use case:

- emergency continuity only

## Required Access Inventory Template

### Credential Inventory Table

| Credential Name | Type | Owner | Scope | Used By | Repo Access | Write Access | Rotation Status | Notes |
|---|---|---|---|---|---|---|---|---|
| MacBook git push | Classic PAT | Architect | Broad repo | Local git | TBD | Yes | Temporary | Break-glass only after migration |

## GitHub App Implementation Checklist

### Creation

- [ ] Create GitHub App
- [ ] Name app
- [ ] Add description
- [ ] Set homepage URL
- [ ] Disable unnecessary webhooks unless required
- [ ] Configure permissions minimally

### Installation

- [ ] Install app only on required repos
- [ ] Verify repo scope
- [ ] Store credentials securely
- [ ] Document app owner and admin authority

### Testing

- [ ] Read access test
- [ ] Write access test
- [ ] Branch creation test
- [ ] PR creation test
- [ ] Automation test
- [ ] Revocation test
- [ ] Failure-path test

### Cutover

- [ ] Remove personal PAT from automation
- [ ] Update config and secrets
- [ ] Confirm treasury agent path works
- [ ] Reclassify personal PAT as break-glass only

### Lockdown

- [ ] Review remaining personal token usage
- [ ] Remove non-essential legacy credentials
- [ ] Document final approved access paths

## Governance Roles

### Doctrine Owner

Ensures GitHub access model matches Nova’s institutional standards.

### API Boundary Steward

Ensures source-control credentials do not collapse system boundaries.

### Logging & Registry Owner

Maintains access inventory, migration records, and credential state.

### Treasury Agent Operator

Uses only approved system paths.

### Halt Authority

Can suspend deployment or automation if credential integrity weakens.

## Failure Conditions

The migration is incomplete if any of the following remain true:

- treasury agent depends on a personal credential
- a classic PAT is still the main automation credential
- repo write access cannot be traced to a role
- permissions are broader than necessary
- no break-glass distinction exists
- credential usage inventory is incomplete

## Success Conditions

The upgrade is successful when:

- system automation uses a GitHub App
- human access and system access are separated
- all credentials are inventoried
- all permissions are least-privilege
- personal PAT is no longer part of normal operations
- access can be rotated or revoked without operational confusion

## Implementation Summary

### Decision

Upgrade GitHub access to institutional infrastructure quality.

### Constraint

Operator-dependent classic PATs are not acceptable as long-term system credentials.

### Outcome

Nova gains auditable, role-based, least-privilege repository access.

### Adjustment

Migrate treasury agent and automation access to a GitHub App, while retaining personal access only for human development or emergency recovery.

### Status

**Required**
