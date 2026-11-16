# M4-GLOBAL-LOCAL-QUALIFICATION-001 independent geometry review

## Judgment

PASS for the frozen geometry, task qualification, actual source correspondence and global-to-local geometric opportunity at author commit `99f939513111637b76a1d486622b4841cad9ccda`.

The independent standard-library checker passed 830 assertions. A separate outward binary64 interval certificate excluded 413 candidate triangle samples outside the asserted integer pixel bounds. Both scripts read original geometry and saved evidence, and import no author oracle or product implementation.

This review performed zero live Blender, MCP, model, API or render operations. PNG/NPZ pixel quality and total lifecycle costs are separate parent-review assignments. This geometry result supports the next bounded cross-scale strategy experiment. Automatic selection and model benefit remain unmeasured.

## Exact geometry and task denominator

The frozen point/face JSON SHA256 is `34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8`. The checker independently reads each rational coordinate, reconstructs oriented face planes and shared-edge adjacency, obtains maximal connected coplanar components, cancels interior edges and traces boundary cycles.

Rectangle qualification requires one boundary loop with four corners after forward-collinear simplification, opposite equal edges, orthogonal adjacent edges and agreement between polygon cross-product area and the summed source-triangle area vector.

| Reconstructed quantity | Independent result |
| --- | --- |
| Objects / vertices / triangles | 9 / 54 / 56 |
| Maximal oriented coplanar components | 24 |
| Supported rectangular components / their triangles | 22 / 44 |
| Unsupported components / their triangles | 2 / 12 |
| Unsupported objects | Obj_05 square ring and Obj_07 L shape |
| Task-eligible components | Obj_02, Obj_06, Obj_09 |
| Eligible source triangle rows per object | 0 and 1 |

Area comparisons use squared Fraction values and the normal threshold uses positive cz and `16*cz² >= 9*(cx²+cy²+cz²)`. Both horizontal small rectangles have area squared `1/4096`. The inclined rectangle has area squared `5/32768`, with unit normal `(0,-1,3)/sqrt(10)`. All three meet the fixed area and oriented-normal conditions. The L and ring remain part of the occluding source geometry.

## Current source correspondence

Before-save and after-reload original/evaluated world vertices and ordered triangles were checked against the frozen JSON for every object.

For each actual session, the checker independently decodes the original native WIRE response, reconstructs its resident resources using the actual resource ID, revision, matrix and scale, and compares the resulting world vertices and source triangle rows exactly to the fixture.

It then checks the capture document_epoch, capture_state and scene revision against the producer binding. Each captured object's name, host ID, instance ID, object_index and ordered triangles agree with its binding entry and the separately saved current raw-source read. Frame source-parent fields and the actual frame matrices agree with the current producer binding and camera plan.

The global session contains 9 captured objects and 22 represented rectangular regions. The local-open session contains 2 captured objects and 1 target region. The local-covered session contains 3 captured objects and 1 target region. Occluder-only retained objects keep their source geometry while their faces stay outside target coverage accounting.

All scopes retain their own capture order and source identity. This fixture provides exact cross-scope geometry correspondence. A product-level parent/child evidence relation awaits the next candidate.

## Eighteen actual global pixel bounds

The six actual published global matrices were independently checked against a 90-digit Decimal construction of the declared direction, camera basis, common full-scene center, 1.1 padded square fit and eye placement. The qualification then projects the actual eligible corners using exact Fraction interpretations of the published binary64 matrices.

Each axis interval is expanded outward by `1/65536` pixel. The checker counts half-integer pixel centers through exact floor/ceiling arithmetic. The resulting surface-sample bounds precede any occluder removal.

| Actual global camera | Obj_02 | Obj_06 | Obj_09 |
| --- | --- | --- | --- |
| SCENE | 1 | 1 | 2 |
| TOP | 1 | 1 | 1 |
| LEFT | 1 | 2 | 2 |
| RIGHT | 1 | 2 | 2 |
| FRONT | 1 | 2 | 1 |
| BACK | 1 | 2 | 1 |

Every bound is strictly below the fixed 16-pixel threshold. Projected triangle determinants exceed 1/2 pixel squared and projected axis widths remain below two pixels.

`pixel_enclosure_certificate.py` propagates gamma16 affine-dot roundoff through the actual view/projection matrices and then uses outward binary64 intervals for screen conversion and the raster's complete barycentric arithmetic expression. The maximum derived coordinate error is `2.0673341557979254e-13` pixel. Every candidate triangle sample outside the expanded intervals is provably rejected by at least one barycentric upper bound below `-1e-10`. This verifies that rounding and the unchanged raster edge allowance cannot add a sample beyond the table's bounds.

## Strict cover and open-surface proofs

The actual cover bottom is independently recovered as a complete rectangle at z=`9/8`, spanning x,y=`[3/2,5/2]`, with area squared 1.

For every covered-target corner and each registered direction, the ray reaches that bottom at a strictly positive parameter, inside the bottom's strict XY interior. Convexity extends this conclusion to the entire rectangle. The smallest strict footprint margins are `13/48 m` for SCENE, `7/16 m` for TOP and `5/16 m` for each remaining direction. Thus all six directions strictly occlude the entire covered face.

The open horizontal rectangle is independently unobstructed in TOP and in the actual local SCENE direction `(4,-4,3)`. Each triangle from the full frozen scene is clipped to the target-facing half-space, projected along the exact direction onto the target plane, and intersected with the target rectangle using Fraction polygon clipping. All projected intersections are empty, including boundaries. Its actual local frame also places every target corner strictly inside the viewport.

At the parent's request, the inclined Obj_09 rectangle received the same full-scene exact projection/intersection proof in its own orthogonal edge coordinates. Its oriented normal has dot product 13 with the SCENE direction, and every projected occluder intersection is empty, including boundaries. This establishes a realizable geometric SCENE candidate for the next batch. Its actual locally fitted image and readability remain unrun.

## Saved-checker corrections

The author preserved the initial scorer, derived R1 scorer, initial result, patch and file hashes. The reviewed changes are consistent with the actual data contract.

- Converting frozen rational center strings to Fraction restores exact comparisons.
- Public front_direction_world is an oriented rational direction. Exact positive parallelism with the independently reconstructed geometric normal is appropriate. The task's unit-normal threshold is independently evaluated from that geometric normal.
- Selecting explicit final R2 frame-report paths preserves the earlier reports and their failure history.
- Parsing a rational direction such as `-1/3` through Fraction preserves its represented value.
- Inverse-camera rays must respect the published XY frustum. With the declared 511-based mapping, pixel indices 0 through 510 have centers inside NDC, and the final row/column centers lie outside. The independently derived excluded count is `512²-511² = 1023`, matching the correction's geometry.

The R1 binding-hash correction removes runtime source-attestation fields from the earlier hash preimage and checks those appended fields separately. The parent frame reviewer owns the complete binding/hash verification. This geometry review found no change to the frozen layout, thresholds or task denominator in these adapters.

## Reviewer's initial failure and correction

The first independent checker counted all rectangular faces of retained local occluders as target coverage regions and failed on local_covered. The original script and failure are preserved as `independent_geometry_R0.py` and `R0_FAILURE.json`.

The corrected checker derives coverage targets from binding.observation_target while continuing to reconstruct every retained source object. This matches the actual target-versus-occluder source contract. The frozen product evidence was unchanged.

The Agent Learning session showed the current parent task `312a5056-6564-4416-82d2-c11af3fc81fe` revision 1, while this continuing subagent's fixed historical assignment remained attached to its earlier parent task with parent_read_only access. This review's authorization and evidence attribution follow the explicit current parent delegation. No parent task record was overwritten.

## Next-strategy findings

The two open qualified regions have a demonstrated full-scene pixel shortage and exact SCENE geometric visibility. A candidate can select these task-qualified regions from the existing capture, fit one bounded local camera per region, retain the complete captured geometry for occlusion, and bind each new witness back to the original object and local triangle rows.

The covered eligible region has a strict six-direction geometric obstruction. It should retain its specific unresolved cause. The policy must keep task targets distinct from occluder-only source objects and preserve complete unsupported-source denominators.

## Independently executed and unrun

- PASS for exact components, rectangle classification, eligibility, source ordering, current capture correspondence, 18 global integer bounds, cover proof, open-horizontal SCENE/TOP proof and inclined SCENE geometric proof.
- PASS for the independent outward arithmetic exclusion certificate.
- REVIEWED for the preserved saved-checker adapter changes described above.
- UNRUN here for new Blender acquisition, actual raster construction, fresh model consumers, total lifecycle costs and full pixel-array QA.
- UNRUN in the existing qualification batch for the locally fitted Obj_09 image, automatic cross-scale target selection, product parent/child binding and end-to-end model benefit.

The independent artifacts are `independent_geometry.py`, `RESULT.json`, `pixel_enclosure_certificate.py`, `PIXEL_CERTIFICATE.json`, `independent_geometry_R0.py` and `R0_FAILURE.json`, all under this review's geometry directory.
