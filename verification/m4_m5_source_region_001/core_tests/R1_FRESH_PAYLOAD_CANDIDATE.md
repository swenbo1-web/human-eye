# R1 fresh source-frame payload candidate

The root froze `FIRST_CORRECTED_HOTSPOT.json` after the corrected local qualification passed. R0F already reused region preparation and its frame across the two references. Fresh validation took 10.7086 ms. First rendering and publication took 67.7766 ms, including 33.7577 ms combined PNG/NPZ publication, 10.9476 ms metadata and 4.7424 ms raster. This candidate removes the repeated NPZ decode from that fresh validation.

## Scope and integrity

`SceneObservationImages` adds a private `_reuse_published_payload` constructor option with a false default. The source-region adapter enables it. Original Active/default/cross-scale adapters retain their existing persisted-array decode.

The enabled publisher encodes its NPZ through the fixed NumPy encoder into a private `BytesIO`, obtains immutable encoded bytes and fixes their SHA256 before writing them. It writes those bytes, releases the private encoded payload and compares the first file readback against the producer digest. The frame's later file hash remains bound to that producer value.

The publisher retains a private proof for the original frame object. It snapshots the original verification-related frame metadata as a fingerprint and the original complete payload metadata as immutable tuples. Frame identity, paths, hashes, source/camera/owner identities, pose and array declarations participate. The source adapter's image reference and additional host annotations continue through its existing delivery path.

Each validation still reads and hashes the PNG and NPZ files. Fresh reuse requires the original registered frame object, matching original metadata, and fresh dtype/shape/byte-count/content-hash checks for every RGB/depth/object-owner/triangle-owner/patch-owner buffer and every patch/owner metadata array. It continues through the original owner consistency checks and PNG decode/pixel equality check. Changed references or metadata, foreign frame objects, copied frames and persisted frames use the original NPZ decode and comparisons.

The source work records `frame_array_decodes` and `fresh_payload_reuses` for the current request. A fresh valid source frame records zero decodes and one payload reuse. The repeated already-observed source result records zero for both, with the existing frame reuse counter.

## Temporary payload cost

`temporary_encoded_archive_bytes` records the immutable compressed payload length. `frame.stages.private_encoded_archive` records its encoding/write interval, byte count, release before disk readback and zero retained encoded bytes. BytesIO allocator overhead and peak process RSS remain unmeasured. Existing publication and service stages include this work, and root-owned paired service/owned measurements decide whether to retain the candidate.

## Preserved failed candidate and correction

The initial candidate acquired its original NPZ hash from its first file read. Transport independently reproduced a publication-window failure by replacing a correctly written NPZ with another valid archive immediately before that first hash. The initial fresh path accepted its original buffers while the persisted colors differed. The original full decoder rejected the mismatch.

`opt_initial_source` preserves both initial product files and their hashes. `PUBLICATION_WINDOW_FIX.diff` records the narrow correction to producer-owned immutable encoding bytes plus initial readback verification. Transport preserves its initial counterexample. This integrity correction belongs to the same decode-removal candidate.

`runs/R1_02` passed 61 current checks, including six focused test methods for original/foreign/copied/persisted frames, changed path/identity/array declarations, all current buffer values and dtype/shape, patch/owner mapping arrays, disk PNG/NPZ bytes, coordinated public hash/buffer changes and the precise publication-window replacement. The window replacement is rejected by both the old decoder and corrected fresh path.

The run recorded 62 synthetic PNG publications taking 55,207,900 ns. Its source pins bind the corrected product. `runs/R1_01` preserves the earlier 60-check result before the additional publication-window counterexample. All worker Blender starts, actual raster calls, model calls and paid calls remain zero. Actual paired performance acceptance is pending in the root task.
