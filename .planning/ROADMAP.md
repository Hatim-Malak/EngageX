# EngageX — Project Roadmap

## Overview

EngageX is a RAG-powered video engagement analysis tool. Two videos (YouTube + Instagram Reel) are ingested, embedded, and stored. A creator then chats with an AI that compares them, explains engagement differences, and suggests improvements.

## Milestones

### Milestone 1: Foundation
- Backend AI services operational
- Frontend core UI built and functional

---

## Phase 1: Frontend Build

**Goal:** Complete frontend for EngageX with landing page (URL input + ingestion), chat interface (video comparison + AI query), and all shared components. Uses existing Zustand store and API layer.

**Requirements:**
- [ ] FE-01: Landing page with URL input form for two videos
- [ ] FE-02: Video ingestion flow with progress indicator
- [ ] FE-03: Session restore from localStorage
- [ ] FE-04: Chat page with three-panel layout (Video A, Video B, Chat)
- [ ] FE-05: Video cards showing metadata, stats, engagement rate, hashtags
- [ ] FE-06: Engagement comparison bar (pure CSS, no chart libs)
- [ ] FE-07: Chat panel with message list, streaming response, input
- [ ] FE-08: Citations from AI responses as clickable timestamp chips
- [ ] FE-09: Suggested questions when chat is empty
- [ ] FE-10: Rate limit badge, error handling, loading states
- [ ] FE-11: CSS-only responsive layout (desktop 3-panel, mobile stacked)
- [ ] FE-12: Utility functions (formatNumber, formatDuration)

**Plans:** 5 plans (3 waves)

Plans:
- [ ] 01-frontend-build-01-PLAN.md — Foundation: routing, utilities, shared components (FE-10, FE-12)
- [ ] 01-frontend-build-02-PLAN.md — Landing page: URL form, ingestion progress, session restore (FE-01, FE-02, FE-03)
- [ ] 01-frontend-build-03-PLAN.md — Chat analytics: header, video cards, engagement comparison (FE-05, FE-06, FE-10)
- [ ] 01-frontend-build-04-PLAN.md — Chat conversation: input, messages, streaming, citations, questions (FE-07, FE-08, FE-09)
- [ ] 01-frontend-build-05-PLAN.md — Chat page wire-up: session lifecycle, responsive layout, lazy loading (FE-04, FE-11)

### Phase 2: (Future)
- *TBD*

---

## Milestone Schedule

| Milestone | Phases | Status |
|-----------|--------|--------|
| Foundation | 1 | Planning |

---
*Last updated: 2026-05-31*
