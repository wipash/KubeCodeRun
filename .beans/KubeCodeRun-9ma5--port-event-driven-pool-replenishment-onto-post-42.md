---
# KubeCodeRun-9ma5
title: Port event-driven pool replenishment onto post-#42 pool.py
status: todo
type: task
priority: high
created_at: 2026-05-04T21:37:25Z
updated_at: 2026-05-04T22:27:56Z
parent: KubeCodeRun-1ue3
blocked_by:
    - KubeCodeRun-p391
---

**Highest-risk task in this integration.** Both fork and upstream addressed pool replenishment. Upstream's #39 is less polished and over-provisions; fork has better semantics from the review-fix pass. Upstream's #42 then rewrote pool.py to use a Go runner (runner_port instead of sidecar_image/sidecar_url), so a straight cherry-pick won't work.

## Source commits to port

- `ed6fbe5 fix: event-driven pool replenishment, parallel creation, acquire retry, faster health checks`
- `5d3b8df fix: address review findings — lost wakeup, lock scope, over-provisioning, test leak, error backoff`

## What to keep from fork's version (algorithmic correctness)

| Concern | Upstream #39 | Fork (with review fixes) | Decision |
|---------|--------------|--------------------------|----------|
| Over-provisioning during in-flight creates | uses `available_count < pool_size` (over-provisions) | uses `total_count < pool_size` (correct) | **Keep fork** |
| Lost wakeup if event arrives during `gather()` | Yes (clears event after wait) | Fixed in 5d3b8df | **Keep fork** |
| Error backoff on exception | None | `asyncio.sleep(1)` | **Keep fork** |
| Test leak on cancel | Possible | Fixed in 5d3b8df | **Keep fork** |
| Lock scope | Held across creates | Released for parallel creates | **Keep fork** |

## Tunables — relax to upstream values

These were aggressive in the fork; user opted to relax them now that the algorithm itself is solid:

| Tunable | Fork value | Upstream value | Decision |
|---------|------------|----------------|----------|
| Health-check interval | 15s | 30s | **30s (upstream)** |
| Health-check failure-strikes-to-remove | 2 | 3 | **3 (upstream)** |
| Replenish parallel batch size | 3 | 5 | **5 (upstream)** |

## Why straight cherry-pick fails

Upstream #42 changed:
- `PodSpec` constructor: removed `sidecar_image`, `sidecar_*_limit/request` params, added `runner_port`, `runtime_class_name`, `pod_node_selector`, `pod_tolerations`, `image_pull_secrets`
- Readiness check: `sidecar` container → `main` container
- URL property: `sidecar_url` → `runner_url`
- Pool config: dropped sidecar_image / sidecar resource fields

## Approach

Don't cherry-pick — re-implement the fork's algorithm on the post-#42 pool.py:

1. Pick one consistent event-field name (`_replenish_needed`)
2. Replace the replenish loop body with fork's correctness fixes (total_count guard, no-lost-wakeup, error backoff, parallel creates with released lock); use upstream's batch-size 5
3. Keep upstream's health-check loop interval (30s) and threshold (3 strikes), but signal replenish on removal (fork addition)
4. Add an acquire-retry path that signals replenish if there are no available pods
5. Keep upstream's #48 imagePullSecrets and #42 PodSpec plumbing intact

## Tests

- tests/unit/test_pool.py — already updated by #42, may need fork-side adjustments
- tests/unit/test_pool_replenishment.py — present in upstream from #39; replace with fork's expectations

## Todo

- [ ] Read post-#42 pool.py end-to-end to understand new shape
- [ ] Open ed6fbe5 + 5d3b8df side-by-side
- [ ] Re-implement event-driven replenish with total_count guard
- [ ] Re-implement health-check loop (keep upstream 30s interval and 3-strike threshold; add fork's replenish-on-removal signal)
- [ ] Re-implement acquire retry / signal-on-acquire-fail
- [ ] Run tests/unit/test_pool.py and test_pool_replenishment.py
- [ ] Smoke-test against real cluster: kill pods, watch replenishment latency
