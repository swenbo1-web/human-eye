# Root blind review notes

Read before opening the group/cost mapping: all 18 final answers, the original rubric and binding, the 18 tool-call/check summaries, and complete evidence packets for `425c329dbb104cbea457b46656e308b4`, `ef2ab372adc042db83b2d2f38539fdf6`, `ab4e992c0b7242f1969c981e993446d6`, and `9ef0bb6c079d47eaa364dacfacf7c630`. Dedicated reviewers separately inspect all assembly and discovery tool/code packets. No model or Blender execution was performed by this review.

The answers/task/index hashes match the implementation completion message. All nine assembly final answers report the correct separated/penetrating/separated classification, 0.01/0.04 m gaps, and Object_02 as nearest separated. Eight discovery answers report Peer_000 at approximately 0.003000006 m; one reports Near_017 at zero.

`425c329dbb104cbea457b46656e308b4` is a definite factual failure: its second native call applies a small absolute determinant threshold (`1e-18`) and accepts a false Near_017 intersection, which is repeated in the final answer. The frozen truth is Peer_000 with distance in [0.0030000059049561864, 0.0030000059049562497] m; Near_017 is about 0.026 m away. Coverage of all 47 candidates does not rescue the incorrect winner/distance.

`ef2ab372adc042db83b2d2f38539fdf6` illustrates a corrected intermediate error: the initial intersection is re-examined, its barycentric coefficient is about -1.3, the crossing routine is changed to use a scale-relative test plus residual, and all 47 distances are recomputed. The final correct result is supported. Keep intermediate failures without scoring a corrected final as wrong merely because an earlier intermediate was wrong.

`ab4e992c0b7242f1969c981e993446d6` receives all three closed-solid relations, minimum distances, witnesses, and complete coverage directly in one task-query result. This is sufficient evidence under the frozen rubric; no additional native call is required.

`9ef0bb6c079d47eaa364dacfacf7c630` reads actual vertices/triangles and transforms, computes full vertex-face and edge-edge distances for the separated pairs, and locates Object_03's strict common interior in the ring material. Its approximately 0.005 m interior-point clearance is described as such, not as a global escape distance.

Across the blind packets there are 59 tool attempts, including three errors: two task requests add an unsupported fact combination, and one surface_nearest request omits session_id. Those failed attempts remain part of the cost denominator. Every discovery final is derived from native computation in these packets; no discovery answer is backed by a completed plugin surface_nearest query. This observation precedes group/cost unblinding and does not establish why a model chose a particular tool.

Method names and descriptions can reveal capabilities, so this is partial blinding to arm labels and cost, not perfect blinding. The absent thin-client EXIT receipts are separate operational evidence, not a new quality requirement. Final quality acceptance remains tied to the two complete criterion-level reviews.
