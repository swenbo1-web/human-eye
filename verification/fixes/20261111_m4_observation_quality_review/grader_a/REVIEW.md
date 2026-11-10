# M4 observation baseline — independent blind grader A

Final quality: **6/6 complete_correct**. Scoring was fixed before unblinding. No group mapping, costs, private cells, author scores or other grader results were read. Tool names/content make this a limited blind review; no route attribution was inferred.

The immutable detailed record is `GRADES.json`, SHA256 `d579c3b15dc9acc8b9d1450ce57c180fdab279e81ad61dcaaed659047cd9f059`. It binds each original final answer, tool evidence and source-consistency file. Public INDEX SHA256: `e950da63c0b61ddf2b3938b92a7ac443ead08524797330ced86f7e876be861cf`.

| Anonymous answer | Target | Conditions | Roles | Relations | Local evidence | Complete |
|---|---:|---:|---:|---:|---:|---|
| answer_07229f7fac18446d | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |
| answer_16cc0a01c1667547 | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |
| answer_635fcb52c8009303 | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |
| answer_69cc9ae597e60afa | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |
| answer_ae6684a89ddc7a0e | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |
| answer_e85f06af4348d600 | 1/1 | 3/3 | 3/3 | 3/3 | 3/3 | Yes |

Unknown, missing, wrong, unsupported and material-contradiction counts are all zero. No refusal or infrastructure failure prevents completion.

## Decisive evidence

All six identify N16 and establish the three selection conditions from actual geometry: center Z about 0.36 is below the two-rail mid-height 0.46; center Y about 0.10 is behind the front beam's rear surface at about -0.1025; distance to the two-pipe XY midpoint is about 0.256, within 0.70. Other candidate frames fail at least one condition.

N13 is the right vertical separator, with actual interior intersection. The common point `(0.245, 0.100, 0.360)` lies strictly inside the frame's right material bar and the separator. Full local mesh evidence, or the source-bound exact closed-solid certificate together with local material features, supports this claim. AABB overlap or unsigned distance zero alone was not credited.

N08 is the left locator. Positive X separation plus overlapping facing Y/Z patches gives a realizable minimum gap of about 0.100007–0.100009 mm. All finals correctly classify this as contact under the specified 0.25 mm tolerance and distinguish it from exact physical touching. The approximately 1.86e-9 m difference between the native float transform read and the frozen double-precision truth is immaterial to the contract; no hidden tighter precision requirement was imposed.

N28 is the through-hole probe. Its entire polygonal XZ section lies within the frame opening, including while it crosses frame thickness. Its minimum gap is about 23 mm. The finals provide local hole/material evidence and attainable surface locations rather than treating overlapping bounds as penetration.

Detailed quotations, call references and reasons are recorded per answer in `GRADES.json`. One final calls a valid section surface point a “vertex”; it is not an original end-cap mesh vertex. This is recorded as imprecise wording, not a material geometric error or a new grading requirement.

## Verification scope and limits

Read all six original finals, real requests/returns and source-consistency records. Pure JSON comparison independently found that every owner request's arguments and tool name match its public completed event, and the response content is equal. Source records agree on the frozen asset and report equal initial/final file and geometry identities. Visible native code only reads scene geometry/state and computes local arrays; it does not modify the scene or read private truth. Cleanup receipts are not treated as continuous proof against unrecorded transient writes.

The initial image was prepared and attached to the launched CLI, but provider delivery and actual model view remain unknown. No visual-consumption or active-vision benefit is inferred from these quality results.

No model, Blender or product execution was performed for this grading. This review concerns semantic correctness and evidence adequacy only; it makes no performance or group-comparison claim.
