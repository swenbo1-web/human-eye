# Preserved offline audit attempts

These attempts added no product imports, Blender sessions, RPC, models, or PID
queries. They read existing archived evidence and wrote only new audit artifacts.

1. `ENTRY_AUDIT_ATTEMPT_01.py/json/md`: 383 of 385 checks passed. The two failures
   came from an incorrect audit assumption that every pre-close event had status
   `completed`. Both original sequence-9 events are the successful typed status
   `qa_patch_applied`, with the original patch hash and four vertices. Final audit
   checks this exact status and binding; it does not relax the operation count.
2. `ENTRY_AUDIT_FAILURE_01.py/json`: adding public-response ID checks encountered
   the legitimate `notifications/initialized` frame, which has no response file.
   The exception and exact failing script bytes are retained. Final audit requires
   that exact notification without an ID when RX is absent.
3. `ENTRY_AUDIT.py/json/md`: passed, 427 arm checks, 18 public observations,
   28 physical RPC, all 36 original-surface witness checks and all 461 sealed raw
   files unchanged. This is the final offline audit; no additional live run occurred.

Final script SHA256: `2ef53df6594686f74a4e4e45edf32f7483a10ca377feb85af6e919ff2aa8269e`.
Final JSON SHA256: `065518161506401ce0bf3d5dcfb8026b71d99c748d811be1f9939981347e43b5`.
