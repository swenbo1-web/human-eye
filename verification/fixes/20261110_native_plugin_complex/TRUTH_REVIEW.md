# Independent archived truth review

Reviewer: /root/complex_spatial_fixture_review. Read-only subagent; no Blender, product or consumer was launched by this reviewer. This document records the reviewer's actual reruns, not only author claims.

- Archived scene SHA256: a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb.
- Archived snapshot SHA256: 5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14.
- Archived truth SHA256: d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff.
- Oracle source SHA256: ff40dd38aac728f7a516201cb20973b2811eca7472a882c1b5d8cac9815f5f4f.

Executed the existing stdlib oracle truth_for_state('assembly','initial',snapshot); the returned certificate exactly matched the archived initial truth. Three additional certificate self-checks passed. All four local vertices multiplied by matrix and units exactly matched archived world coordinates; all three world AABB pairs overlap.

Separately implemented an in-memory Fraction ray parity check without importing author oracle or product kernel. Three non-degenerate ray directions each confirmed the archived shared point is strictly inside Object_01 and Object_03 (six checks). World shared point approximately (-0.2033333333333333,-0.4066666666666666,-0.4066666666666666); ideal target/probe margins 0.01 m and 0.006 m exceed corresponding source perturbation bounds.

The oracle uses 80-digit Decimal for radical construction constants, then stdlib float geometry with explicit perturbation/arithmetic error certificates. It is not an all-Decimal computation.

Model scoring uses abs(answer-d0)+E<=1e-6 m, with d0=0.010000000000000009 and E=2.0446606626675212e-7 for Object_02; d0=0.040000000000000036 and E=3.0142333402758355e-7 for Object_04. Rounded answers 0.01 and 0.04 pass. The narrower geometric truth intervals are not an extra answer-rounding constraint.

Object_03 is the only penetrating candidate; Object_02 is nearest separated. Equivalent verifiable penetration evidence is allowed; the consumer need not repeat this particular witness. A zero unsigned distance, AABB overlap, or BVH overlap alone cannot distinguish touching from positive-volume penetration. This initial task contains no touching pair and does not test that class.

Current-run evaluated geometry still requires matching against the archived snapshot. Require objects, units, local/world vertices, matrices and oriented triangle lists; pure triangle order differences can use oriented triangle multisets, with cyclic permutations allowed and reversed orientation forbidden. Different vertices or retriangulation need a renewed source certificate.

World-vertex canonical JSON SHA256 (sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False):

- Object_01: 8a650595adff26a1e8b034169916d5215edff50cc1184b6c72d7932e7e6a469d
- Object_02: a1eb240bc81f0a7fbfa50fe696f1e50835abca829172a97792d95fc54309bc42
- Object_03: c8b5775a50f0ae78e2618c16e03eea68471ef9c4f3625b60746a22039586f0da
- Object_04: 4ec9065242d668a5b643e56fa544da5a9af14e2f1f521785fe841ace455c4880
