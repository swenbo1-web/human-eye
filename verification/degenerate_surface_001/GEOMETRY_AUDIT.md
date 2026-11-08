# Independent T04 geometry audit

Both finished raw socket captures and public stdio returns pass independent geometry checks. No product module or test module was imported; no model, Blender, RPC or test was rerun.

The actual focal vertices are `(0,0,0), (0,1,0), (0,0,0)`, so its closed face hull is a segment. Every actual target face is `(x,0,0), (x,1,0), (x,0,1)`. With focal p=(0,t,0) and target q=(x,s,u), squared distance is x²+(t−s)²+u² ≥ x². The lower bound is attained at paired y=z=0 vertices. This proof uses exact Fractions of the parsed binary64 coordinates, independently of the product distance kernel.

| Actual target | Exact distance metres | Binary64 distance metres |
|---|---:|---:|
| M4_Near | 8589935/2147483648 | 0.004000000189989805 |
| M4_Far_00 | 1/1 | 1.0 |
| M4_Far_01 | 2/1 | 2.0 |
| M4_Far_02 | 3/1 | 3.0 |

The exact nearest distance is 8589935/2147483648 m = `0.004000000189989805` m. The sole nearest object is `M4_Near`; all four actual candidate distances are finite and independently proved. Both public packets report complete, coverage 4 valid / 0 strictly excluded / 0 unresolved, metres, unchanged focal identity and no execution authority. The second request's legacy focal_id is exactly the first return's focal.id; all public semantic fields, including bindings, are identical except trace_id. Captured geometry is identical.

The actual asset has no multiple nearest-object tie and no strict AABB exclusion. Its degenerate focal has no original nondegenerate triangle acquisition witness or finite upper seed, so all four targets remain retained. Multiple exact ties and strict exclusion are demonstrated by the distinct fixed offline variants, not claimed from this real sample.

The original offline record reports 12/12 directed groups passed, 0 failures/errors/skips; 83 related methods overall. The twelve groups cover point/line/face combinations, all collinear vertex orders and zero edges, interior segment/face crossing, coplanar cases, face-union semantics, actual binary64 transforms, near-nonzero geometry, bit/work/deadline limits, real read-only fake-RNA chain and ties/pruning, normal/rank cache identities, and distance/witness separation. That is offline verified-source evidence. These two actual Blender captures establish only this real T04's supported segment-to-triangle geometry and name/legacy equivalence.

Candidate `0ad59befeee43c2fad752e3bad2ee69f87af3136`, raw reported runtime source `82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6`. Source execution proof and owner/asset closure are separate audits; this geometry audit does not substitute for missing receipts. All 61 QA files were hash-inventoried before and after and remained byte-identical. Inputs and exact fractions are retained in GEOMETRY_AUDIT.json. This audit does not claim model adoption, task savings, provider requests or fees.
