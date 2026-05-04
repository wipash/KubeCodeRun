---
# KubeCodeRun-1ue3
title: Integrate upstream KubeCodeRun changes
status: in-progress
type: epic
priority: high
created_at: 2026-05-04T21:36:06Z
updated_at: 2026-05-04T22:28:13Z
---

Bring upstream/main (aron-muon/KubeCodeRun) into the fork after 14 commits of divergence. Upstream's #42 replaces the nsenter sidecar with a Go runner binary — this is the architectural change driving the integration. Approach: rebase a fresh integration branch on upstream/main and re-apply only the fork-only changes worth keeping.

## Background

- Merge base: 53e445d (your PR #32 filename sanitize, already merged upstream)
- Upstream commits since: 14 (3 features, 8 fixes, 1 breaking, 2 docs/Redis)
- Fork commits since: ~18 non-merge commits across pool replenishment, generated-files capture, mount safety, socket-hangup mitigations, Python packages

## Strategy

**Don't merge upstream into main.** Conflicts are semantic, not just textual. Instead, branch off upstream/main and cherry-pick / re-apply fork-only work.

## Drop entirely (do not re-apply)

- 55bc877 filename sanitize — duplicate of merge-base #32, already in upstream
- 0429769 diagnostic logging — leftover from socket-hangup investigation
- 8ac5e1e investigation*.md — investigation artifacts

## Merge mechanics

- Branch: `integration/upstream-2026-05` (off `upstream/main`)
- Land via direct merge into `main` (no PR required)
- Delete `origin/integration/upstream-plus-fork-{core,full}` after the integration lands
- No fork→upstream contributions planned — accept that we'll re-port these on every future integration
