# VISUAL-BENEFIT-004: common consumer contract

This is a future paired, read-only pilot. 004A prepares and qualifies it; no
formal consumer is run in 004A. The public task/asset is identical within a
pair. No correct object pair, core, best viewpoint, answer, private reference
or prepared task solver is supplied. Read the public task and the neutral
native README, this contract and the supplied public semantic supplement only.
Root keeps the owner broker/Popen alive until cleanup.

## Formal scene entry: owner broker only

The only permitted formal scene-execution or observation entry is:

```powershell
python -I -B verification/visual004_session.py --workspace <own workspace> --requestJSON <own request.json>
```

All native code runs as the broker's `native_run` operation, including P's
fallback. P observation runs only as its P-only `observe` operation. Formal
consumers must not use `visual004_native.py --script`, `NativeSession.start`,
`NativeSession.open/run`, worker sockets, direct broker sockets, a direct
product wrapper or another adapter. Low-level examples in the native README
are coordinator qualification/debug only. Preparing owned request/code files
and the approved reserved-image forwarding wrapper below remain permitted.
Do not use a low-level path because a public budget or transport refused work.

The immutable task window is 600 seconds starting at broker entry **before**
asset read/copy, not at initial-report delivery. The same common initial code
renders the saved asset camera at 768x768, gives neutral mesh names/types,
units and camera matrix; it performs no object selection or spatial solution.
Its startup, render, output, one image reservation and actual delivery count.
There is no cached HE report prepared before the task window. Model identity
and orchestration waiting also consume the same window. Do not reset/restart
a consumer, worker, deadline or spent ledger.

P additionally may use the actual read-only observe interface. All six cases
allow `auto` with SCENE/XY/XZ or explicit `projection` with SCENE. Projection
means the existing fixed Q1-Q4 composition; it is not an XY/XZ single-view
selector. Modes are alternatives, not a clean attention on/off ablation.
Existing native or analytical branches may refuse a pair or decline detail.
P may use exactly the same generic native fallback as N, and every fallback
script, failure, image and roundtrip counts. Do not call setters or write tools.

N authors its own ordinary Blender/Python scripts. It may inspect meshes,
matrices/materials, compute locally, retain Python state/cache, choose more
than one view, zoom, or form a montage using normal Blender image/Python
facilities. No Human Eye capture/validation/summary/render/solver may be used.
It is not required to dump all vertices or use only a perspective screenshot.
Necessary temporary camera/light/render configuration and workspace PNG
products are allowed; source geometry, transforms, materials, visibility,
animation and .blend files are not edited or saved. Generic execution and
terminal fingerprints are not a strong Python sandbox or proof of no reverted
transient edits; actual scripts and host tool paths are audited.

Budgets are identical:48 public attempts; data text262144 bytes plus at most
98304 control/error bytes (actual wire always recorded); at most8 displayed
images, each width/height<=1024 and area<=1048576, cumulative display area
<=2359296 pixels. The common initial image uses589824 pixels. Each redisplay
needs a new reservation and costs again. Montages count their whole area, not
one constituent frame. Constructed or failed/undelivered renders cost CPU,
storage and time even when no image enters the model. The neutral image ledger
enforces count/area; the host forwarding gate below also enforces dimensions.
Budget refusal is not free retry authorization; failed scripts may be repaired
with a new request only inside the original remaining budgets and deadline.
These are **48 broker attempts in total**, including the common initial
operation and failures; owner `close` is separately available cleanup. The
64-default/128-maximum internal worker RPC counters do not add public attempts
or authorize bypassing the broker.

Code must be no larger than 262144 UTF-8 bytes, and its actual serialized
request must also fit. The neutral broker request ceiling is 294912 bytes;
the internal neutral `execute_code` request ceiling is 266240 bytes. Neutral
serialization uses `ensure_ascii=True`, including escaping/framing and a
terminal LF. P's existing connector separately caps complete product requests
at 32768 bytes. Arbitrary Unicode code below 256 KiB is not guaranteed to fit
these wire envelopes. Retain encoding/size failures; do not modify the
transport, change its serialization, or add a compatibility shim. An ordinary
code revision is allowed only if the same broker remains usable within its
original budgets and deadline.

An operation file has exactly `request_id`, `operation`, `args`. It must be
inside the owned workspace; request IDs are not replayed. Native code is a
consumer-authored string, with optional explicitly chosen workspace PNG paths:

```json
{"request_id":"unique-id","operation":"native_run","args":{"code":"print('my own code')","deliver_paths":[]}}
```

P only can send actual observation arguments, using IDs obtained from evidence:

```json
{"request_id":"unique-id","operation":"observe","args":{"arguments":{"include_image":true,"query":{"native_visual":{"mode":"auto","view":"SCENE"}}}}}
```

The model may answer/abstain immediately after its first actual input. There
are no forced extra rounds, automatic target corrections or silent fallbacks.
Do not inspect private truth/specification, source, qualification artifacts,
another task/condition, historical answers, shared GUI or learning knowledge.
If a consumer violates a frozen entry/tool/budget rule, preserve its sample,
raw answer, refusals, costs and evidence with a protocol-deviation flag. Do not
rerun or replace it, silently switch allowances, or repair its submitted answer.

Use the same image-forwarding pattern for either condition. Replace only the
owned workspace/request file paths. Check the original deadline before and
after tool work. A truncated result/invalid JSON is a real failure; retain it
and do not claim its data was delivered. Prefer local calculations and compact
stdout when useful; the maximum text budget does not guarantee one host tool
can display a payload of that size without truncation.

```javascript
// @exec: {"max_output_tokens": 62000}
const result = await tools.exec_command({
  cmd: "& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B 'D:/hefe/verification/visual004_session.py' --workspace '<OWNED_WORKSPACE>' --requestJSON '<OWNED_REQUEST_JSON>'",
  workdir: "D:/hefe", max_output_tokens: 60000
});
text(result);
if (result.exit_code !== 0) exit();
const reply = JSON.parse(result.output);
if (!reply.ok) exit();
for (const row of (reply.result.image_refs || [])) {
  if (!row.reservation_id || row.width > 1024 || row.height > 1024 ||
      row.pixels !== row.width * row.height || row.pixels > 1048576)
    throw new Error("Reserved image violates the common forwarding gate");
  const picture = await tools.view_image({path: row.path, detail: "original"});
  image(picture.image_url, "original");
}
```

The root controller verifies actual agent/thread/event/block index, PNG bytes
and original task gate from real host `input_image` records. Hash alone is
insufficient when repeated PNGs occur across requests/runs. A path, reserved
ledger, MCP `delivered`, broker `ok` or self-written `shown` is not this proof.
No image-specific token count is inferred from pixels or PNG bytes. Host usage
uses real per-event increments; cached counts and reasoning-as-output subset
are retained. Unexposed provider calls/image tokens/dollars remain unknown.

Return the frozen `visual004-answer-v2` schema with exact case/run/asset/task
bindings and the supplied `public_contract_sha256`, object roles and every
requested fact. The same public semantic supplement is supplied to P and N for
all six cases: it defines each required role/fact, value type, exact enums,
units/tolerances and predicate polarity. V06's inverse predicate is explicit
there; do not silently answer its affirmative inverse instead. Read the
provided definitions and echo the exact digest rather than guessing semantics
or deriving a replacement contract from an image or question wording. The
supplement supplies no correct values, target IDs, best views or solver.

Identity may be null and facts
unknown rather than invented, but safe uncertainty can still be incomplete.
Use actual evidence IDs. Describe what an image visibly supports separately
from geometry-derived facts. A closed opaque shell can hide an internal part
while complete geometry remains measurable. Free-text local-region reasoning
and evidence sufficiency require independent blind review. Seeing an image,
or a correct answer, does not prove a visual mechanism caused the benefit.

Evidence IDs are public deterministic symbols. Use unique request IDs matching
`[A-Za-z0-9_-]{1,64}`. Text actually received from a reply is referenced as
`text:<request_id>`. A shown image from that reply is referenced as
`image:<request_id>:<reservation_id>:<image_id>`, copying its returned values;
for example `image:inspect-1:delivery-2:image-3`. The common initial reply uses
`common-initial` and its supplied image/reservation IDs. Redisplay uses the new
reserve request ID and reservation. Do not invent host event IDs. Root maps
these public symbols into the bound registry only after verifying current
run/task, actual host event/slot, text or PNG bytes and original deadline.
The symbol itself, an error reply, or a ledger reservation proves no geometry
and does not prove that the associated image entered the model.
