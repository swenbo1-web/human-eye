# Product fallback static review R2

The missing-image_ref fallback fix has no identified static blocker. The original STATIC_PRODUCT_REVIEW.json and .md retain their recorded bytes.

The first focused run used images source `22414d9e74e39c012988a638d50f72e43551a447d4ee747cef8a99ee3947b113`. The final images source is `c66ac2ae5ac0c147990763973fc6bc13cbf4162f7ba4770cceb0fe858cebe697`. Undoing exactly the new fallback block and receipt assignment reconstructs the earlier source SHA. Host and MCP product files remain at their originally reviewed hashes.

- Explicit existing refs remain intact.
- Raw-capable fallback refs include owner schema, validated owner mapping and the retained producer frame identity when present.
- Legacy patch-only fallback uses the exact former tuple and retains its old ref.
- Raw/patch derivation, NPZ persistence/readback, cache publication and brief-v4 projection have no additional changes in this patch.

## Preserved evidence

The saved before case reproduces the raw/legacy ref collision. The first after case already returned correct distinct refs, while one mock unit failed because its raster-forbidden guard omitted the original function signature. That failed attempt remains preserved. Correcting the harness guard left product bytes unchanged. The second after case passed the saved-byte replay and all 31 mock units.

All three fallback replay records report zero new product rasters and zero direct rasters. The same protected PNG/NPZ bytes were verified before and after. The original focused run's 19 raster calls remain bound to the earlier images source and are not represented as a new full matrix on the final source.

This review performed one AST check and zero candidate imports, product calls, tests, model calls, Blender calls or renders. Installed integration and bounded paired measurement remain separately owned.
