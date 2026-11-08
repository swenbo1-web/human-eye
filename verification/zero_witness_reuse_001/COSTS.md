# Fixed paired costs

One fresh baseline `b60dd327e3926a06b73d77b37be7b63c50a3939a` / `1545da06b415864cf3f666f3a56432e91689d1a0565ea8589a19e3ecfff2b459` ran first; fixed candidate `c08d882b030ad08390fd4b3e28c068dd5ea6251d` / `ec3ac8c9dd83137e1d6cb5371fe4c2bc15ac56d34aafcb6933e8f76c07e897ae` ran second. Each arm used one private session and all nine observations; all 18 public contracts and six aggregate checks passed. There were 28 physical RPCs (14+14), zero experiment failures, retries, adapter corrections, or model consumers. The new-candidate count is one.

Times are seconds. Full observe wall intervals determine acceptance. All profile and trace durations are inclusive: preparation is inside the classifier, nearest/publication inside the surface kernel, and kernels inside wrappers. These rows are attribution, never additive lifecycle components. Profiler callback overhead remains in measured walls.

| Lifecycle | Baseline | Candidate |
|---|---:|---:|
| Outer command | 6.9801242 | 5.2260720 |
| Controller | 6.7158759 | 4.9562613 |
| Native startup | 1.1920367 | 1.2230275 |
| Stdio lifetime | 5.3451465 | 3.5605466 |
| Native close owner | 0.1523790 | 0.1331582 |
| Close transaction | 0.1620090 | 0.1490341 |
| Nine full observes | 4.5682130 | 2.8196866 |
| Capture span inclusive | 0.2725112 | 0.2650611 |
| Product socket intervals | 0.2617632 | 0.2551117 |
| Profiler callback overhead | 0.0001720 | 0.0001540 |

| Phase: three full observes | Baseline | Candidate |
|---|---:|---:|
| initial | 2.2904411 | 1.4926307 |
| unchanged_current | 0.1334898 | 0.1327982 |
| changed_current | 2.1442821 | 1.1942577 |

Cold+changed: 4.4347232 → 2.6868884, reduction 39.412489% (minimum 10%): PASS. Unchanged: 0.1334898 → 0.1327982; change -0.0006916, allowed regression 0.0133490: PASS. All three designated zero-distance paths use the real boundary witness and skip `_nearest`; candidate triangle-pair visits are zero on those paths: PASS.

| Observe order | Baseline full wall | Candidate full wall | Baseline / candidate nearest calls |
|---|---:|---:|---:|
| 1 initial Object_03 | 1.0734705 | 0.2851229 | 1 / 0 |
| 2 initial Object_02 | 0.5808811 | 0.5713967 | 1 / 1 |
| 3 initial Object_04 | 0.6360895 | 0.6361111 | 1 / 1 |
| 4 unchanged_current Object_02 | 0.0443559 | 0.0448661 | 0 / 0 |
| 5 unchanged_current Object_03 | 0.0446536 | 0.0434721 | 0 / 0 |
| 6 unchanged_current Object_04 | 0.0444803 | 0.0444600 | 0 / 0 |
| 7 changed_current Object_02 | 0.5004137 | 0.2743086 | 1 / 0 |
| 8 changed_current Object_03 | 1.0043394 | 0.2705947 | 1 / 0 |
| 9 changed_current Object_04 | 0.6395290 | 0.6493544 | 1 / 1 |

| Inclusive profile attribution | Baseline calls / seconds | Candidate calls / seconds |
|---|---:|---:|
| `_closed_solid_pair_measurement` | 9 / 1.3992521 | 9 / 1.3594329 |
| `classify_closed_solids` | 6 / 1.3969714 | 6 / 1.3572182 |
| `_surface_pair_measurement` | 9 / 2.7326240 | 9 / 1.0184181 |
| `measure_surface_proximity` | 6 / 2.7302605 | 6 / 1.0161895 |
| `_nearest` | 6 / 2.7279287 | 3 / 1.0131630 |
| `_admit` | 6 / 0.0086035 | 6 / 0.0086792 |
| `_integer_frame` | 6 / 0.0913334 | 6 / 0.0908027 |
| `_publish_points` | 6 / 0.0015211 | 6 / 0.0014677 |

Each arm computes six closed and six surface kernels, with three cache hits for each on unchanged geometry. Admission/frame preparation runs six times per arm and is shared within each query; this preexisting reuse is not claimed as a new saving. `_publish_points` still executes six times per arm. The candidate reduces `_nearest` calls from six to three. Per-phase capture/socket/kernel/preparation/publication/wrapper costs and all byte boundaries are in `COSTS.json`.

| Byte boundary | Baseline TX / RX | Candidate TX / RX |
|---|---:|---:|---:|
| Control socket | 2760 / 34498 | 2760 / 34498 |
| Product socket | 33498 / 71964 | 33516 / 71964 |
| MCP stdio | 3023 / 39996 | 3023 / 39992 |

These are distinct boundaries of the same work; bytes are not added across stdio and downstream sockets. All raw input artifacts remained unchanged during extraction. One Markdown formatter attempt raised a Decimal/float TypeError after JSON creation; the renderer was corrected without running product code or changing raw evidence. This is one local engineering comparison, with no extra sampling or model-benefit claim.
