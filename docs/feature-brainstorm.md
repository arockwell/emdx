# EMDX Feature Brainstorm

This document captures feature ideas for evolving EMDX into a more intelligent, connected knowledge base. The ideas are organized by theme with both obvious implementations and more creative angles explored.

---

## Table of Contents

1. [Knowledge Connectivity](#knowledge-connectivity)
   - [Document Links & Backlinks](#1-document-links--backlinks)
   - [Knowledge Graph View](#2-knowledge-graph-view)
2. [AI-Powered Intelligence](#ai-powered-intelligence)
   - [Semantic Search](#6-semantic-search-with-embeddings) (Implemented)
   - [Auto-Summary Generation](#7-auto-summary-generation)
   - [Question-Answering / RAG](#8-question-answering-over-knowledge-base) (Implemented)
   - [Concept/Entity Extraction](#9-conceptentity-extraction)
   - [Natural Language Search](#14-natural-language-search)
3. [Content Ingestion](#content-ingestion)
   - [Web Clipper / URL Import](#10-web-clipper--url-import)
   - [Full Backup & Sync](#12-full-backup--sync)
4. [Advanced Search & Organization](#advanced-search--organization)
   - [Saved Searches / Smart Folders](#13-saved-searches--smart-folders)
   - [Boolean/Regex Search](#15-booleanregex-search-mode)
5. [Analytics & Visualization](#analytics--visualization)
   - [Activity Heatmap](#16-activity-heatmap)
   - [Tag Analytics Dashboard](#17-tag-analytics-dashboard)
   - [Project Timeline](#18-project-timeline)
6. [History & Provenance](#history--provenance)
   - [Document Revision History](#19-document-revision-history)
   - [Change Feed](#20-change-feed)
7. [Actionability](#actionability)
   - [Checklists / Extractable Tasks](#23-checklists--extractable-tasks)
8. [Powerful Combinations](#powerful-combinations)
9. [Implementation Status](#implementation-status)

---

## Knowledge Connectivity

### 1. Document Links & Backlinks

**Basic concept**: Wiki-style `[[links]]` between documents with automatic backlink tracking.

#### Standard Features

```bash
# Inline wiki-style links in document content
emdx save "See [[auth-design]] for details on [[id:456]]"

# View backlinks
emdx backlinks 123
# Documents referencing #123:
#   [456] API Design - "implements the pattern from [[id:123]]"
#   [789] Security Review - "see [[auth-design]] for context"
```

#### Advanced Ideas

**Auto-suggested links**: When you save a doc, AI scans for potential connections:
```
Suggested links for "Auth Implementation":
  [456] OAuth Flow (0.89 similarity, no link exists)
  [789] Security Checklist (mentioned but not linked)
Accept? [y/n/select]
```

**Link types with semantics**:
```
[[#42|implements]]     - This implements that design
[[#42|supersedes]]     - This replaces that doc
[[#42|contradicts]]    - Intentional disagreement
[[#42|questions]]      - Raises questions about
[[#42|extends]]        - Builds upon
```

**Link strength/weight**: Track navigation patterns. Strong paths = important relationships.

**Transitive discovery**: "Documents 2 hops away" - find related ideas you forgot about.

**Broken link detection**: Identify references to deleted documents.

#### Wild Idea: Bidirectional Links with Context

When you link to a doc, capture *why* in a snippet. When viewing backlinks, see not just "5 docs link here" but the context of each link:

```bash
emdx backlinks 42
# Backlinks to "Auth Design":
#
# [56] Implementation Plan
#   "...following the OAuth2 flow described in [[#42]]..."
#
# [78] Security Audit
#   "...contradicts recommendation in [[#42]] regarding token storage..."
```

---

### 2. Knowledge Graph View

**Basic concept**: Visualize document relationships as a network graph.

#### Standard Features

```bash
# ASCII graph in terminal
emdx graph 123 --depth 2
#        ┌──[456] API Design
# [123]──┼──[789] Security Review
#        └──[101] Implementation Notes
#                 └──[102] Bug Fix

# Export for visualization tools
emdx graph --export dot > knowledge.dot
emdx graph --export json > knowledge.json
```

#### Advanced Ideas

**Cluster detection**: Automatically identify topic clusters:
```
Cluster: "Authentication" (23 docs)
  Core: [123] Auth Design, [456] OAuth Flow
  Peripheral: [789] User Model

Cluster: "Performance" (15 docs)
  Core: [200] Caching Strategy
  Bridge to Auth: [210] Token Caching
```

**Bridge documents**: Identify docs that connect otherwise separate clusters - these are "glue" documents.

**Graph health metrics**:
- Connectivity: % of docs with at least one link
- Clustering coefficient: How interconnected are ideas?
- Orphan ratio: Isolated documents

**Evolution over time**: How has your knowledge graph grown/changed?

#### Wild Idea: Knowledge GPS

Navigate your knowledge base spatially:
```bash
emdx navigate --from "Auth" --to "Performance"
# Shortest path: Auth → API Gateway → Rate Limiting → Performance
#
# Alternative routes:
#   Auth → Caching → Performance (through token caching)
#   Auth → Security → Performance (through audit findings)
```

---

## AI-Powered Intelligence

### 6. Semantic Search with Embeddings

> **Status: Implemented** in `emdx ai search`

Uses local sentence-transformers model for semantic similarity search without API costs.

```bash
emdx ai index                              # Build embedding index
emdx ai search "authentication flow"       # Semantic search
emdx ai similar 42                         # Find similar docs
```

---

### 7. Auto-Summary Generation

**Basic concept**: Generate summaries of documents on demand.

#### Standard Features

```bash
emdx summarize 123
emdx summarize 123 --type bullets
emdx summarize 123 --type detailed
```

#### Advanced Ideas

**Summary types for different purposes**:
- `tldr`: One line for list views
- `context`: What you need to know before reading this
- `decisions`: Just the decisions made in this doc
- `actions`: Just the action items
- `changes`: What changed since last version (diff summary)

**Cross-document summaries**:
```bash
emdx summarize --project api
# "The API project covers authentication (OAuth2 + PKCE),
#  rate limiting (token bucket), and caching (Redis)..."

emdx summarize --tag gameplan --since "2024-01-01"
# "Q1 gameplans focused on performance and security..."
```

**Comparative summaries**:
```bash
emdx diff-summary 42 56
# "Doc #42 proposes JWT tokens while #56 recommends sessions.
#  Key difference: #56 adds refresh token rotation..."
```

#### Wild Idea: Summary Chains

Each doc has a one-line summary. A project's summary is synthesized from its doc summaries. Your whole KB has a "state of knowledge" summary:

```bash
emdx summary --meta
# Your knowledge base contains 847 documents across 12 projects.
# Primary focus areas: Backend architecture (34%), DevOps (28%), Frontend (18%)
# Recent activity concentrated on: Authentication, Performance
# Key open questions: 3 unresolved decisions pending
```

---

### 8. Question-Answering Over Knowledge Base

> **Status: Implemented** in `emdx ai ask`

RAG-based Q&A that retrieves relevant documents and generates answers using Claude.

```bash
emdx ai ask "What's our caching strategy?"
emdx ai ask "How did we solve the auth bug?" --project api
```

---

### 9. Concept/Entity Extraction

**Basic concept**: Extract structured information from unstructured documents.

#### Standard Features

```bash
emdx entities 123
# People: @john, @sarah
# Technologies: PostgreSQL, Redis, OAuth2
# Projects: auth-service, api-gateway

emdx find --tech "PostgreSQL"
emdx find --mentions "@john"
```

#### Advanced Ideas

**Decision extraction**: Find and index decisions:
```bash
emdx decisions --project api
# 2024-01: "Use PostgreSQL for persistence" [#42]
# 2024-02: "JWT with 24h expiry" [#56]
# 2024-03: "Switched to Redis sessions" [#78] ⚠️ contradicts #56?
```

**Question extraction**: Find unresolved questions:
```bash
emdx questions --open
# "Should we add rate limiting?" [#42] - RESOLVED in #56
# "How to handle token refresh?" [#42] - STILL OPEN
# "What's the backup strategy?" [#89] - OPEN
```

**Assumption tracking**:
```bash
emdx assumptions --project api
# "Users will have stable internet" [#42]
# "Redis is always available" [#56]
# "Max 1000 concurrent users" [#78]
```

**Technology radar**: What technologies appear in your docs?
```
ADOPT:    PostgreSQL, Redis, OAuth2
TRIAL:    GraphQL, Kubernetes
ASSESS:   gRPC, Kafka
HOLD:     MongoDB (negative mentions)
```

**Jira/GitHub ticket extraction**: (Discussed separately - regex-based, reliable)
```bash
emdx find --ticket AUTH-123
emdx tickets --index
```

#### Wild Idea: Institutional Knowledge Index

Track what you know about what:
```bash
emdx expertise "authentication"
# You wrote extensively about this in Q1 2024:
#   Core docs: #42, #56, #78 (OAuth2, PKCE, sessions)
#   Key insights: Token rotation, PKCE for mobile
#   Last updated: 3 months ago - might be stale
#
# Related expertise: Security (strong), API Design (moderate)
```

---

### 14. Natural Language Search

**Basic concept**: Use AI to parse natural language into structured queries.

#### Standard Features

```bash
emdx find "that thing about caching from last month"
# Interpreted as: content~"caching" created:>2024-02-01
# Found: [456] Redis Caching Strategy
```

#### Advanced Ideas

**Conversational refinement**:
```
> that thing about caching
Found 12 results. Narrow by:
  - Redis caching specifically? (8 docs)
  - API response caching? (3 docs)
  - Browser caching? (1 doc)

> redis
Showing 8 results for Redis caching...
```

**Context-aware search**:
```bash
emdx find "the doc I was looking at yesterday"
# Uses access history

emdx find "what I wrote after the outage"
# Correlates with known events
```

**Query explanation**:
```bash
emdx find "recent auth stuff" --explain
# Interpreted as:
#   content MATCH 'auth*'
#   OR tags IN ('auth', 'authentication', 'oauth')
#   AND created > 7 days ago
#   ORDER BY relevance
```

#### Wild Idea: Search by Example

```bash
emdx find --like "I want docs similar to #42 but about caching instead of auth"
# Uses semantic understanding to transpose concepts
```

---

## Content Ingestion

### 10. Web Clipper / URL Import

**Basic concept**: Save web content to your knowledge base.

#### Standard Features

```bash
emdx clip https://blog.example.com/article
# Saved: [847] "Understanding Distributed Systems"
# Source: https://blog.example.com/article

emdx clip URL --title "Custom Title" --tags "reference"
emdx clip URL --reader-mode  # Strip navigation/ads
```

#### Advanced Ideas

**Smart metadata extraction**:
```
Source: https://blog.example.com/article
Author: Jane Doe
Published: 2024-01-15
Clipped: 2024-03-20
Reading time: 8 min
Technologies mentioned: Kubernetes, Docker
```

**Diff tracking**: Page updated since you clipped it - show what changed.

**Batch clipping**:
```bash
emdx clip --from-file urls.txt
# Clips all URLs, creates a group
```

**Clip + annotate**:
```bash
emdx clip URL --annotate
# Opens editor to add your notes alongside clipped content
```

#### Wild Idea: Research Mode

```bash
emdx research "kubernetes networking" urls.txt
# 1. Clips all provided URLs
# 2. Extracts key points from each
# 3. Synthesizes: "Key approaches to K8s networking..."
# 4. Links to your existing docs on related topics
# 5. Identifies gaps: "You have nothing on CNI plugins"
```

---

### 12. Full Backup & Sync

**Basic concept**: Export, backup, and sync your knowledge base.

#### Standard Features

```bash
emdx backup
# Created: emdx-backup-2024-03-15.tar.gz

emdx restore emdx-backup-2024-03-15.tar.gz
```

#### Advanced Ideas

**Git-based backup**: Your KB as a version-controlled repo:
```bash
emdx backup --git ~/kb-backup
# Exports as markdown files with YAML frontmatter
# Commits to git repo
# Push to GitHub for offsite backup
```

**Export formats**:
```bash
emdx export --format markdown ~/kb-export/
emdx export --format obsidian ~/obsidian-vault/
emdx export --format html ~/kb-site/  # Static site
```

**Multi-device sync**:
```bash
emdx sync pull laptop:~/.emdx
emdx sync push server:~/.emdx
```

**Conflict resolution**: Same doc edited on two machines - show diff, let you merge.

#### Wild Idea: Knowledge Base Branches

Like git branches for experimenting with ideas:
```bash
emdx branch create "exploring-graphql"
# All new docs go to this branch

emdx branch merge "exploring-graphql"
# Decided to adopt - merge into main

emdx branch delete "exploring-graphql"
# Decided against - discard without trace
```

---

## Advanced Search & Organization

### 13. Saved Searches / Smart Folders

**Basic concept**: Save queries as reusable virtual folders.

#### Standard Features

```bash
emdx smartfolder create "active-work" \
  --query "tags:active OR tags:in-progress"

emdx smartfolder create "stale-gameplans" \
  --query "tags:gameplan AND NOT tags:done" \
  --older-than 30d

emdx list --folder "active-work"
```

#### Advanced Ideas

**Live counts**:
```
📁 Active Work (12)
📁 Blocked (3) ⚠️
📁 Stale Gameplans (5)
📁 Untagged (23)
```

**Alerts**:
```bash
emdx smartfolder "blocked" --alert-if-gt 5
# Warns when folder exceeds threshold
```

**Negative folders**: "Everything NOT in any smart folder" = stuff falling through cracks.

**Temporal folders**: "Modified this week", "Not accessed in 90 days"

#### Wild Idea: Smart Folder Templates

Pre-built folder sets for common workflows:
```bash
emdx smartfolder use "gtd"
# Creates: Inbox, Next Actions, Waiting For, Someday/Maybe

emdx smartfolder use "gameplan-tracker"
# Creates: Planning, Active, Blocked, Completed, Failed

emdx smartfolder use "zettelkasten"
# Creates: Fleeting, Literature, Permanent, Index
```

---

### 15. Boolean/Regex Search Mode

**Basic concept**: Power-user search capabilities.

#### Features

```bash
# Boolean operators
emdx find --bool "(auth OR authentication) AND security AND NOT deprecated"

# Regex in content
emdx find --regex "TODO:?\s*(fix|update)"

# Regex in titles
emdx find --regex-title "^(RFC|ADR)-\d+"

# Combine modes
emdx find --bool "project:api" --regex "raise\s+\w+Error"
```

**Full query language** (like GitHub search or Jira JQL):
```bash
emdx query "project:api AND created:>2024-01 AND (tags:bug OR tags:issue) ORDER BY updated DESC LIMIT 10"

emdx query --save-as "api-bugs"  # Save for reuse
```

**Faceted search**:
```bash
emdx find "authentication" --facets
# Results: 23 documents
#
# By Project:        By Tag:           By Year:
#   api (12)           security (15)     2024 (18)
#   auth-service (8)   design (10)       2023 (5)
#   docs (3)           active (4)
```

---

## Analytics & Visualization

### 16. Activity Heatmap

**Basic concept**: GitHub-style contribution graph for your knowledge base.

#### Standard Features

```bash
emdx heatmap
#     Jan    Feb    Mar    Apr
# Mon ░░▓▓░░ ░░░▓▓░ ▓▓░░░░ ░░▓▓▓▓
# Tue ▓▓░░▓▓ ░░▓▓░░ ░░▓▓▓▓ ▓▓░░░░
# Wed ░░▓▓▓▓ ▓▓░░▓▓ ░░░░▓▓ ░░▓▓░░
# ...
```

#### Advanced Ideas

**Multiple heatmap types**:
```bash
emdx heatmap --type created   # When you capture
emdx heatmap --type accessed  # When you retrieve
emdx heatmap --type modified  # When you refine
```

**Insights extraction**:
```
Most productive day: Wednesdays
Longest streak: 23 days (Jan-Feb)
Current streak: 5 days
Most active project: api (45%)
```

**Decay visualization**: Show which docs are "fading" (not accessed recently).

#### Wild Idea: Knowledge Velocity

Track not just activity but *outcomes*:
```bash
emdx velocity
# This week: 12 docs created, 5 marked successful
# Hit rate: 42% (improving from 35% last month)
# Most valuable topic: Performance (67% success rate)
# Suggestion: Your research docs have high success - do more research
```

---

### 17. Tag Analytics Dashboard

**Basic concept**: Understand your tagging patterns and effectiveness.

#### Standard Features

```bash
emdx analyze --tags
# 🎯 gameplan    45 docs  ████████████
# 🚀 active      23 docs  ██████
# ✅ done        67 docs  █████████████████
```

#### Advanced Ideas

**Co-occurrence analysis**:
```
Tag pairs that appear together:
  gameplan + active: 89%
  bug + urgent: 34%
  research + success: 78% ← research pays off!
```

**Lifecycle analysis**:
```
gameplan → active: avg 2 days
active → done: avg 8 days
active → blocked: 15% of cases
blocked recovery time: avg 12 days
```

**Health warnings**:
```
⚠️ "urgent" has 23 items - overused?
⚠️ "old-api" has 0 items - delete?
⚠️ "wip"/"in-progress" 80% overlap - merge?
```

**Success predictors**:
```
Tags correlated with success:
  +analysis: 73% success (vs 45% baseline)
  +small-scope: 82% success

Tags correlated with failure:
  +large-scope: 45% failure rate
  +blocked >10 days: 70% failure
```

#### Wild Idea: Tag Autopsy

When a gameplan fails, analyze what went wrong:
```bash
emdx autopsy 42
# Gameplan #42 "Migrate to GraphQL" failed
#
# Risk factors identified:
#   - 'large-scope' tag (2x failure rate)
#   - Missing 'analysis' tag (correlated with success)
#   - Blocked for 14 days (pattern: >10d blocked → 70% fail)
#
# Similar failed gameplans: #23, #31, #38
# Common thread: All were infrastructure changes without POC
#
# Suggestion: Add 'analysis' phase, break into smaller scopes
```

---

### 18. Project Timeline

**Basic concept**: Visualize a project's document history.

#### Standard Features

```bash
emdx timeline --project api
#
# api Project Timeline
# ════════════════════════════════════════
# 2024-01 ┤ [123] Initial Design 🎯
#         │ [124] Database Schema
# 2024-02 ┤ [130] Implementation 🚀
#         │ [131] Rate Limiting
# 2024-03 ┤ [140] v1.0 Release ✅
```

#### Advanced Ideas

**Phase detection**:
```
RESEARCH    ████░░░░░░░░░░░░  Jan
DESIGN      ░░░░████████░░░░  Feb-Mar
BUILD       ░░░░░░░░░░░░████  Apr-May
LAUNCH      ░░░░░░░░░░░░░░██  Jun
```

**Milestone markers**: Auto-identify significant moments (decisions, completions, blockers).

**Parallel tracks**: Multiple workstreams shown as parallel lanes.

**Export**: Mermaid, PlantUML, or image formats.

#### Wild Idea: Project Replay

Step through a project's history interactively:
```bash
emdx replay --project api
# [1/47] 2024-01-05: "API Design Ideas"
#        Initial exploration of REST vs GraphQL
#
# [2/47] 2024-01-08: "Decision: REST over GraphQL" ⭐ KEY
#        Chose REST for simplicity and team familiarity
#
# [n]ext [p]rev [d]ecisions-only [m]ilestones [q]uit
```

---

## History & Provenance

### 19. Document Revision History

**Basic concept**: Track changes to documents over time.

#### Standard Features

```bash
emdx history 123
# v5  2024-03-15  +45 -12 lines  "Added PKCE flow"
# v4  2024-02-20  +12 -3 lines   "Token lifetime"
# v3  2024-02-01  +89 -0 lines   "OAuth section"
# v2  2024-01-15  +23 -5 lines   "Requirements"
# v1  2024-01-10  +120 -0 lines  "Initial"

emdx diff 123 --v1 3 --v2 5
emdx view 123 --version 3
emdx restore 123 --version 3
```

#### Advanced Ideas

**Semantic diff**: Not just text changes, but conceptual changes:
```
v3 → v4 summary:
  + Added PKCE flow requirement
  - Removed basic auth (deprecated)
  ~ Changed token expiry 1h → 24h
```

**Blame/annotate**: See when each section was added:
```bash
emdx annotate 123
# [v1] ## Overview
# [v1] This document describes...
# [v3] ## OAuth2 Flow
# [v3] We use authorization code with PKCE...
# [v5] ### PKCE Details
# [v5] The code verifier is generated...
```

**Cross-document diff**:
```bash
emdx diff 42 56
# Compare any two documents, not just versions
```

#### Wild Idea: Evolution View

See how a *concept* evolved across multiple documents:
```bash
emdx evolution "authentication"
#
# 2024-01: Simple JWT [#42]
#          "Basic JWT with HS256, 1h expiry"
#
# 2024-02: Added refresh [#56]
#          "Introduced refresh tokens for better UX"
#
# 2024-03: Full OAuth2 [#78]
#          "Migrated to OAuth2 + PKCE for security"
#
# 2024-04: Added SSO [#89]
#          "Enterprise SSO integration"
#
# Trajectory: Started simple, added complexity as requirements grew
```

---

### 20. Change Feed

**Basic concept**: Track recent changes across your knowledge base.

#### Standard Features

```bash
emdx changelog
# 2024-03-15 14:32  [123] edited (v5)
# 2024-03-15 14:30  [847] created
# 2024-03-15 10:15  [456] tagged +security
# 2024-03-14 16:45  [789] deleted
```

#### Advanced Ideas

**Filtered feeds**:
```bash
emdx changelog --project api
emdx changelog --type edits
emdx changelog --significant  # Only major changes
```

**Digest mode**:
```bash
emdx changelog --daily
# March 15: 12 changes (3 created, 8 edited, 1 deleted)
# March 14: 8 changes (2 created, 6 edited)
```

**Export as RSS/Atom**:
```bash
emdx changelog --format atom > changes.xml
# Subscribe in any feed reader
```

#### Wild Idea: Knowledge Pulse

A daily briefing of your knowledge base:
```bash
emdx pulse
# 📊 Daily Knowledge Pulse - March 15, 2024
#
# Activity:
#   Created: 3 new docs
#   Modified: 7 docs (2 major changes)
#   Completed: 2 gameplans ✅
#
# Attention needed:
#   ⚠️ #42 blocked for 14 days
#   ⚠️ #56 has open questions
#   ⚠️ 3 docs link to deleted #78
#
# Trends:
#   📈 Performance topic growing (5 new docs this week)
#   📉 Frontend topic quiet (no activity in 2 weeks)
```

---

## Actionability

### 23. Checklists / Extractable Tasks

**Basic concept**: Parse and track tasks within documents.

#### Standard Features

```bash
# Document contains:
# - [x] Design OAuth flow
# - [ ] Implement refresh
# - [ ] Write tests

emdx tasks --from-doc 123
# [ ] Implement refresh (from #123)
# [ ] Write tests (from #123)

emdx task complete "Implement refresh"
# ✓ Task completed
# ✓ Checkbox updated in #123
```

#### Advanced Ideas

**Bidirectional sync**: Complete in doc ↔ complete in task list.

**AI extraction from prose**:
```bash
emdx extract-actions 123
# Found action items in "Meeting Notes":
#   "Need to update the API docs" → task?
#   "John will review by Friday" → task for @john?
#   "Should consider caching" → research task?
```

**Progress tracking**:
```
#123 Auth Implementation: 60% complete (3/5 tasks)
```

**Cross-doc task view**:
```bash
emdx tasks --all --status open
# Open tasks across all documents:
#   [#42] Implement refresh tokens
#   [#56] Add rate limiting
#   [#78] Write performance tests
#   ...
```

#### Wild Idea: Living Documents

Documents with auto-updating sections:
```markdown
## Current Tasks
<!-- emdx:tasks project:api status:open -->
- [ ] Implement refresh tokens (#42)
- [ ] Add rate limiting (#56)
<!-- /emdx:tasks -->

## Recent Changes
<!-- emdx:changelog project:api limit:5 -->
- Mar 15: Auth design updated
- Mar 14: Rate limiting added
<!-- /emdx:changelog -->
```

These blocks auto-update when you view the document.

---

## Powerful Combinations

These features become more powerful when combined:

### Links + Graph + Semantic Search
"Find docs related to #42 that aren't linked yet"
- Discovers missing connections in your knowledge graph

### Entity Extraction + Timeline
"Show evolution of 'caching' concept over time"
- Track how your understanding developed

### Smart Folders + Change Feed
"Alert me when 'blocked' folder grows beyond 5"
- Proactive notification of problems

### Revision History + Summary
"What changed in v4?" → "Added PKCE requirement, removed basic auth"
- Understand changes without reading diffs

### Web Clipper + Entity Extraction
Clip article → auto-extract technologies → link to your docs about those technologies
- Automatic knowledge integration

### Tag Analytics + Checklists
"Gameplans with incomplete checklists have 3x failure rate"
- Data-driven process improvement

### Backlinks + Decisions
"Show all docs that reference this decision"
- Impact analysis for changing your mind

### Search + Graph
"Search results as a subgraph"
- Visualize relationships among search results

---

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Semantic Search | ✅ Implemented | `emdx ai search` |
| RAG Q&A | ✅ Implemented | `emdx ai ask` |
| Embedding Index | ✅ Implemented | `emdx ai index` |
| Document Links | 📋 Planned | |
| Backlinks | 📋 Planned | |
| Knowledge Graph | 📋 Planned | |
| Auto-Summary | 📋 Planned | |
| Entity Extraction | 📋 Planned | |
| Web Clipper | 📋 Planned | |
| Smart Folders | 📋 Planned | |
| Revision History | 📋 Planned | |
| Activity Heatmap | 📋 Planned | |
| Tag Analytics | 📋 Planned | |
| Change Feed | 📋 Planned | |
| Checklists | 📋 Planned | |

---

## Philosophy

These features are designed with EMDX's core philosophy in mind:

1. **Local-first**: Data stays on your machine, works offline
2. **AI-native**: Intelligence built in, not bolted on
3. **CLI-friendly**: Power users can script everything
4. **Solo-dev focused**: Features for individual productivity, not team collaboration
5. **Low friction**: Capture knowledge quickly, organize it later

The goal is to transform EMDX from a knowledge *store* into a knowledge *partner* - one that helps you connect ideas, surface forgotten insights, and extract value from what you've written.
