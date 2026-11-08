# Directed correctness checks

The nine groups in `tests/test_zero_witness.py` target the private witness handoff, without repeating the earlier full regression matrix. This agent performed only syntax compilation; the parent owns execution through the verified source loader.

1. A crossing box pair and face, edge, and point tangencies in both orders retain the public zero-distance contract and avoid `_nearest`. Published points independently lie on both original surfaces.
2. Complete containment retains a positive 1.5 m surface gap despite `penetrating`; a disjoint pair retains 2 m. Reusing the holder across these calls must remove the earlier boundary contact.
3. Coincident shells retain conservative solid `unknown`, while genuine boundary evidence still measures surface distance zero.
4. Wrong witness pair, invalid triangle references, an off-surface point, float private coordinates, stale preparation, and reversed ordered preparation fall back to the actual current pair. The deliberately gapped current pair must remain 2 m.
5. A large-world analytic intersection point exercises the existing witness publication refusal while retaining valid zero distance and undefined zero direction. Independent exact barycentric membership identifies its original triangles; the point is not chosen from an implementation result.
6. Runtime cancellation, deadline, and request-budget errors at publication propagate through the reused path.
7. Standalone measurement still invokes `_nearest`; explicit exact rank remains `[0,1,0]` and the public method and topology agree.
8. Mixed cold and changed calls reuse only their own witness; an unchanged call uses both existing caches. Public and cached results contain no private contact point, frame, or triangle references.
9. Both asymmetric cache combinations remain correct. A closed hit with a surface miss computes nearest normally; a surface hit with a closed miss retains the cached public result. Mutating a returned result cannot mutate its cache.

No live session, Blender call, socket, subprocess, model call, or original asset mutation is part of these checks. Test expectations come from analytic boxes, exact original-surface membership, and existing public contracts.
