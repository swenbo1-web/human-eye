# Independent static qualification

The frozen geometry contains 9 objects, 54 vertices and 56 ordered triangles. The oracle imports Python standard-library modules only. It reads fixed geometry and the private neutral-name role map. It reads no runtime evidence and calls no product function.

## Surface components

Each source face contributes its exact oriented plane and directed edges. Only faces with the same oriented plane and a shared source edge join. Boundary cancellation produces maximal component boundary cycles. A supported rectangle requires one cycle with four corners after removing forward collinear vertices, opposite equal edges, orthogonal adjacent edges and matching exact vector area. Coincident coordinates with separate source indices do not invent adjacency.

The resulting 24 components contain 22 rectangles and two unsupported components. The ring has two boundary loops. The L has one concave six-corner boundary. Their 12 triangles remain in the scene as occluders. The three qualifying rectangles have local source triangles 0 and 1. Horizontal area squared is 1/4096 square metres squared. The inclined area squared is 5/32768. The exact oriented-normal threshold uses positive z and 16cz² ≥ 9|c|².

## Occlusion

Every ray from the covered rectangle towards a registered camera first crosses the bottom cover plane at z=9/8. The ray parameter is positive. The largest horizontal displacement is 1/6 metres in SCENE. Including the rectangle half-width gives 11/48 metres about its centre, strictly less than the cover half-width 1/2. The report records per-direction intersections and strict margins. This proves full positive-area occlusion without running the production visibility classifier.

For the open horizontal rectangle, the ring lies below its plane. Every other object that could be higher has a strict separating x or y interval under TOP. Its entire TOP-facing surface is unobstructed. Actual image readability awaits the local positive control.

## Global pixel bound

Use the declared six camera directions and the original square fit with 5% margin per side. Integer axes R=cross(-D,seed) and U=cross(R,-D) avoid irrational comparisons. The exact squared unpadded half-span is the larger of max|p·R|²/|R|² and max|p·U|²/|U|² about the common centre. It is 512 in SCENE and 256 in each other view. The padded squared half-span multiplies this by 121/100.

The oracle independently propagates outward rational intervals through direction normalization, cross products, both basis constructions, global fitting, eye placement, view translation, both affine projection stages and pixel conversion. Each arithmetic operation includes binary64 round-to-nearest relative and subnormal error. Dot products include an order-independent gamma4 bound. Interval endpoints round outward to a 2^-96 grid. This interval construction evaluates no product code and creates no image.

All small projected triangle determinants exceed 1/2 pixel squared, including the interval uncertainty. All projected rectangle widths remain strictly below two pixels on each axis. The separate rational error certificate bounds the existing barycentric -1e-10 acceptance and the computed third weight. Its induced axis extension is below the fixed 2^-16-pixel analysis enclosure. This enclosure changes no renderer threshold or camera span.

Count the half-integer pixel centres in each outward interval using exact floor and ceiling. The 18 region-view bounds are one or two pixels in total, each strictly below the required 16 surface pixels. These are upper bounds on possible surface samples before occluders remove samples. Neither projected area rounding nor raster output supplies this answer.

## Actual qualification boundary

The three saved sessions must retain their own published matrices and capture order. A fresh host is bound within its session by document epoch, real host/object instance, ordered world geometry and local capture triangle. Cross-scope correspondence uses the fixed fixture geometry after these current bindings pass. This batch adds no product parent-child relation and promises no generic original mesh ID mapping.

Saved checks will compare actual published matrices against the static interval enclosure, verify actual source faces, image delivery and all saved buffers, and independently count readable samples. Unconstructed directions stay unrun. Static six-direction occlusion and actual image evidence remain individually attributable. The positive control must produce a real current readable witness. Failure closes this recipe with its original evidence.
