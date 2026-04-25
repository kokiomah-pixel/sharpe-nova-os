# Status: REQUIRED — Institutional Infrastructure Enforcement

This document is binding repository policy.

This document defines mandatory access control standards for Sharpe Nova OS.

# Sharpe Nova OS — GitHub Access Policy & Implementation Plan

## Institutional Infrastructure Upgrade

## Version: v1.1

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

## Enforcement

### Non-Compliance Definition

The following are considered violations of Nova infrastructure standards:

- use of personal access tokens for system automation
- undocumented or untracked credentials
- credentials with excessive or undefined scope
- automation dependent on operator-specific access
- bypassing GitHub App-based system access

### Consequence

Any system or workflow found in violation:

- is considered non-compliant with Nova infrastructure
- must be corrected before continued use
- may be halted if integrity risk is present

### Principle

Nova enforces discipline on capital.

Nova must also enforce discipline on its own infrastructure.

No exceptions.

## Implementation Summary

### Decision

Upgrade GitHub access to institutional infrastructure quality.

### Constraint

Operator-dependent credentials are not acceptable as system infrastructure.

### Outcome

Nova gains auditable, role-based, least-privilege repository access.

### Adjustment

Migrate automation and treasury agent access to GitHub App-based credentials.

### Status

**Required**
