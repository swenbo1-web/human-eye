# 043 isolated R3 candidate

The candidate is installed at:

`D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region`

`PINS.json` records the exact original 041 installed R3 binding, all 143 runtime source hashes, deterministic wheel, candidate binding, administration and launcher hashes, and the actual isolated `identity` startup receipt. The original 041 installation was read only. No default installation, dependency environment, GUI, Hook registration or product configuration was changed.

## Single runtime-source change

Only `human_eye_plugin/surface_proximity.py` changes; the AST difference is confined to `_nearest_tree`. `C.patch` is the complete unified source difference.

Let `lo0,hi0` and `lo1,hi1` be the existing exact world-integer root bounds. The query-local condition is:

`shift == 0 and ((lo0[k] < lo1[k] and hi1[k] < hi0[k] for every k) or the symmetric alternative)`.

The condition is computed once. At the existing `push_pair`, only a zero exact lower key under that condition replaces `cdist` with zero. The resulting tuple remains `(key, secondary, serial, left, right)`, so serial orders the zero-key ties in their existing enqueue order. Nonzero keys retain their old secondary key. A touched root boundary, lack of containment, or a shifted queue retains the old secondary key for every entry. There is no shape name, triangle count, frame, asset, tolerance, threshold or result condition.

The two initial greedy child comparisons, their stored sibling values, BVH construction/leaf size, exact distance/pruning/canonical witness operations, projection mechanism, query budgets, checkpoint calls and public interfaces are unchanged. This patch changes traversal scheduling only. It makes no claim that changing the schedule preserves work counts for activated inputs; the independent controls must check results, budgets and inactive-input work. The local containment checks add bounded CPU operations but no new `Work` charge, as specified in the frozen 043 contract.

## Identity and normal route

Candidate aggregate: `b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e`.

Candidate kernel: `f1925d3a1b1ea796b8df0b5275f020b0586f64f9cf8726de5c9a0657542e776e`.

The exact 041 wheel builder was copied unchanged from `M6-041-KERNEL-HOOK/install/r3/source/verification/build_candidate_release.py`. Its deterministic wheel was extracted into the new managed candidate release. The normal 041 fixed launcher was changed only for the distribution name and candidate aggregate hash; the original administration helper was changed only for the new launcher hash. These installation metadata changes do not add runtime-source changes.

Use the bound interpreter and normal launcher:

```powershell
& 'D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe' -I -B 'D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region/admin/target_runtime_entry.py' identity
```

The unchanged launcher also dispatches `serve --config <candidate-config>` to `human_eye_plugin.production_server.main` and `hook ...` to the original Hook handler. A candidate business configuration must bind the candidate `site-packages` as its `project_root` and the candidate source hash as its expected identity. A configuration still pinned to the original R3 identity must reject this candidate; the build does not weaken that check. The candidate is not automatically activated or registered.

For independent untimed imports, prepend the candidate `site-packages` in a fresh process, then import `human_eye_plugin.surface_proximity`. The complete existing API and cache-facing functions remain available. No diagnostic helper or alternate solver entry was added. A diagnostic can inspect the actual integer roots, `shift`, and original `heapq.heappush` calls without changing the installed source.

## Verification scope

The builder verified all 143 original installed hashes, the original binding/launcher/administration hashes, one changed runtime source, the `_nearest_tree`-only AST difference, deterministic wheel contents, candidate distribution identity, full fixed-launcher startup and source/module-origin checks. Original and candidate source hashes were rechecked after startup. Independent numerical, lifecycle, near-budget and inactive-work controls are owned by the other 043 agents. No actual mesh solve, Blender, model, official timing or broader rollout was run by this builder.

Reproduce the isolated installation using `build.py` with the bound interpreter and `-I -B`. Existing artifact bytes must match; a changed existing artifact is rejected rather than overwritten.
