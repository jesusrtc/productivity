---
title: "Building AI Fluency Together Workshop"
date: 2026-04-02
type: meeting
scope: org
projects: []
tags: [claude-code, skills]
people: [daniel-olmedilla]
---

# Building AI Fluency Together Workshop

## TL;DR

The meeting focuses on the Trust organization's successful adoption of AI tools, highlighting significant productivity metrics, team milestones, and community contributions. The core objective of the discussion is to outline the strategic direction, ethical responsibilities, and architectural guidelines for creating, sharing, and managing AI skills through the newly established Trust AI Context Repository.

## Key Metrics

- 10x increase in PRs merged since early January with Claude adoption
- 60x increase in code changed (25K → ~1.54M lines)
- 83% of Trust engineers are active AI agent tool users

## Community Highlights

- Saurav: smart testing plugin for GitHub workflow guardrails
- Louis: 30% latency reduction using Claude + Memoscope
- Nathaniel: on-call investigation assistant plugin

## AI Skills Guidelines

- Skills are a craft — share explicitly to uplevel the team, not just individual productivity
- High-quality outputs are critical; inaccurate skills are harmful due to inherent trust in their results
- Builders must be accountable: keep skills up-to-date, accurate, and non-regressing
- Apply the "headline rule" before launching: would you be comfortable with your name publicly associated with the tool's actions?
- Company-wide access to agents handling deep investigations or private data = significant privacy risk
- Meta example referenced: AI agents going rogue, exposing private data to unauthorized employees

## AI Context Repository Architecture

### Where to put skills
- **Single-product context** → stays in that product's repo
- **Cross-product or complex logic** → Trust AI Context Repo
- **Broad company-wide value** → main LinkedIn Context Repository

### Trust AI Context Repo design
- Organized by **problem area**, not org structure
- Uses ACLs for ownership and approval permissions
- Supports workflows, schemas, agents (flexible formats)
- "Bootstrap and Sync" script creates symlinks connecting local skill folders to selected areas

### Principles
- Do NOT duplicate: don't copy context that exists elsewhere
- Do NOT create new repos: maintain centralized knowledge base
- Skills must offer obvious benefits and be continuously improved, or removed if unused
- Design modular, discoverable skills focused on specific problems

## Future Plans

- DPX acknowledges the single repo may become a bottleneck — plan to subdivide later
- Context plugin will expand to run on any specific folder by mid next week
- No strict mandatory guardrails yet — intentional, as industry standards for AI context management don't exist yet
