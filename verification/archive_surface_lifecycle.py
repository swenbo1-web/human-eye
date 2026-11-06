"""Replay only the frozen lifecycle evidence archive; run no experiment.

Usage: python verification/archive_surface_lifecycle.py [--verify-only]
Inputs are pinned below before the first archive is produced. The helper itself
is included and hashed in the external index; ZIP/index are excluded to avoid
self-reference. ZIP member order, timestamps and permissions are deterministic.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HELPER = "verification/archive_surface_lifecycle.py"
ZIP_PATH = "docs/surface_lifecycle_evidence.zip"
INDEX_PATH = "docs/surface_lifecycle_evidence_index.json"
DIRECTORIES = (
    "artifacts/integration/managed_current_diagnostic_001",
    "artifacts/integration/production_f_qualification_001",
    "artifacts/integration/root_lifecycle_review_001",
)
IDENTITY_PATHS = tuple(directory + "/artifact-identity.json" for directory in DIRECTORIES[:2])
BC_PATH = "human_eye_fast/fast_bvh_clearance.py"
OLD_BC_PATH = DIRECTORIES[2] + "/bc_before.py"
AUTHOR_SOURCE_ARCHIVES = (
    DIRECTORIES[0] + "/sources.zip",
    DIRECTORIES[1] + "/run_001/sources.zip",
)

# Filled once from the explicitly authorized frozen input list, not at replay.
# The helper's own identity belongs in the external index (not in itself).
FROZEN_RECORDS = {
    "artifacts/integration/managed_current_diagnostic_001/B/launch.json": {
        "bytes": 34577,
        "sha256": "8639ba63ac0ce819cb07862618042d473c65dea10abf31dd577a3dee3074d12f"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/process.json": {
        "bytes": 206,
        "sha256": "637af96c6006bf53dabed16e012e6b17113572646b7e13da6dfd60be1fff0747"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/project-imports.json": {
        "bytes": 3606,
        "sha256": "b8261a29e511aaffc812b11d8d4b68aaec7c9076cbdb13e64bc9173a0bcab9e5"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/camera_ownership.json": {
        "bytes": 2256,
        "sha256": "f374006610963e56ce5ea37a84f8789b0ef3c15f4d3f34e6949baee30554f885"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/cases.jsonl": {
        "bytes": 40341,
        "sha256": "c2de2fef3c9ac4bf28d202d43a81f20ca1bc4255a07837e034ba299e5c63c035"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/checkpoints.jsonl": {
        "bytes": 97313,
        "sha256": "c5e8dfdc1a44908203787da11097b5acae13d08e2f19d701e96125c48ad2573b"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/endpoint.snapshot": {
        "bytes": 285418,
        "sha256": "b697ef4f16127dc94fa71747a49298f5c36101ac7f81c8a740e7d828024bbbce"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/gc_events.jsonl": {
        "bytes": 1972,
        "sha256": "00cec193367d4e1b142a4178f0e254b53816b2929a33227a78b89cb788c3b4db"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/phase_observations.jsonl": {
        "bytes": 4004,
        "sha256": "86cb74ec007cff6b74fd5f9bb0fea9f55341564dbaa208372b941eea5a5180f4"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/snapshot_statistics.json": {
        "bytes": 527031,
        "sha256": "d7e657ae49f19f9f46d7fb47170258854293bea7f76c1987056b351224e8f5ce"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/result/summary.json": {
        "bytes": 2689,
        "sha256": "02760d6692e1b2550578413a4b18221bac7ae1b37ec3688422e20dd38e86bf56"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/runtime.json": {
        "bytes": 2637,
        "sha256": "65bd58761a6f56c99fe828b2c972484b1a439373f212751b8923c382d8ae2809"
    },
    "artifacts/integration/managed_current_diagnostic_001/B/worker.log": {
        "bytes": 78,
        "sha256": "910aa38ae16482fa28bf7298b492e995748b29b486033d02c0c4315a83d0cce9"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/launch.json": {
        "bytes": 34577,
        "sha256": "5f2a76936338b3e0494bfdb053434deae83465fb9748268d2de1b8de6afeadb8"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/process.json": {
        "bytes": 206,
        "sha256": "aae7444107012139d86548e815e74e10c9b045905594bd7c92ee87d837fd5e75"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/project-imports.json": {
        "bytes": 3606,
        "sha256": "b8261a29e511aaffc812b11d8d4b68aaec7c9076cbdb13e64bc9173a0bcab9e5"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/camera_ownership.json": {
        "bytes": 2094,
        "sha256": "82911052360c744791e765e1a3f1b7d241f7d727fe9a7f0bbd6e49ead440d5fb"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/cases.jsonl": {
        "bytes": 40339,
        "sha256": "b09c99d399924cd857d2e3f53bdc85fb62198b25bcb3a204141f694faaa347ec"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/checkpoints.jsonl": {
        "bytes": 97302,
        "sha256": "df92f853f8582ce52362577d489dbcc1969696915d95bf644cca15e51f522969"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/endpoint.snapshot": {
        "bytes": 299994,
        "sha256": "dd8043bef7bfbe02c0e8dc114d188763b0305fdf28209a15fb7a24ea7f176390"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/gc_events.jsonl": {
        "bytes": 1735,
        "sha256": "36fa6155b7834e5e9db83459f4f59f4bff031a0bda36fa20351ed26873940c05"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/phase_observations.jsonl": {
        "bytes": 4000,
        "sha256": "cca0481473daed0edc8f1aa9d06f2eb8db7270cb1b0d25ec1161968fabf83b3c"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/snapshot_statistics.json": {
        "bytes": 521311,
        "sha256": "e6f732083db3f5768ed7d6734b4f61162ab59de24db8c0ac2a44444eee6570d2"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/result/summary.json": {
        "bytes": 2688,
        "sha256": "20028ec7719325b9519dbc9197c1df2a7e829da949a001bd0c563df0ec405d83"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/runtime.json": {
        "bytes": 2636,
        "sha256": "430b2272811173884024f3d9075911b2e9572022f303c023b16e62552c3b3cff"
    },
    "artifacts/integration/managed_current_diagnostic_001/I/worker.log": {
        "bytes": 78,
        "sha256": "910aa38ae16482fa28bf7298b492e995748b29b486033d02c0c4315a83d0cce9"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/README.md": {
        "bytes": 1193,
        "sha256": "68db97c598b5da114dc62e7032ec62fbf313f219e1206772527280f799341759"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/formal-current-unchanged.json": {
        "bytes": 77912,
        "sha256": "296cacf4aa7ff53bd10f4f0ecd207f6185f5c4c4159b1030e3b4113767e082be"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/gc-relationship.json": {
        "bytes": 20389,
        "sha256": "216f98fb8ae6c0853a1de48c3cb835ca52942aa4604c3c8375612f25304057c5"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/phase-comparison.json": {
        "bytes": 24455,
        "sha256": "fc71e12989d8b39d1bb73835a61aea995055f2d5a5da3ed5aff5dfeb8a4acadd"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/snapshot-diff-filename.jsonl": {
        "bytes": 17547,
        "sha256": "eda39fc6d731078cc69a42cf5d9153f8d4e6832a0ba1139a9d137a060363fe3e"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/snapshot-diff-lineno.jsonl": {
        "bytes": 316874,
        "sha256": "ce76d1c8c44dac457e71b4540de93c2c905445c6363fd25df100d72431448985"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/snapshot-diff-traceback.jsonl": {
        "bytes": 316874,
        "sha256": "ce76d1c8c44dac457e71b4540de93c2c905445c6363fd25df100d72431448985"
    },
    "artifacts/integration/managed_current_diagnostic_001/analysis/summary.json": {
        "bytes": 25679,
        "sha256": "97ba3c608fae5ef110ad4ea5d754ef4e0b75da182700467e80a4b30bd3636062"
    },
    "artifacts/integration/managed_current_diagnostic_001/analyze.py": {
        "bytes": 18001,
        "sha256": "809f76eaf48263dfd1a72b65f362aca4ec3e8761cc40f5db0be0525a4053961f"
    },
    "artifacts/integration/managed_current_diagnostic_001/artifact-identity.json": {
        "bytes": 5944,
        "sha256": "48c14b6311e77f5a77172a1196f5309f06da26d9e0b03c515614e2a4c00d4cf0"
    },
    "artifacts/integration/managed_current_diagnostic_001/batch-processes.json": {
        "bytes": 683,
        "sha256": "6f2d66e6c862854258db09d6208f8114b1aa9369616c4d7b3c591637febae81e"
    },
    "artifacts/integration/managed_current_diagnostic_001/batch-started.json": {
        "bytes": 335,
        "sha256": "38d2206cd1f9cbe7b5ae8f29eb6ba5dec3003418b82ad4a829a69bd4657ba38f"
    },
    "artifacts/integration/managed_current_diagnostic_001/manifest.json": {
        "bytes": 144169,
        "sha256": "5349d437ab44fd37ac0bf906bc8d5ed84202bb901b52b653d8b9ae0cc1b1def1"
    },
    "artifacts/integration/managed_current_diagnostic_001/run_diagnostic.py": {
        "bytes": 11427,
        "sha256": "3f2b19fb0c8a676abe3233730d10955ce6e36aa7a18e46f763a8c8af006dc696"
    },
    "artifacts/integration/managed_current_diagnostic_001/sources.zip": {
        "bytes": 2301171,
        "sha256": "d1c5467b07f065312a64b1047e9ea22b21c82e3aa2d907c6ad589150c8a929b8"
    },
    "artifacts/integration/managed_current_diagnostic_001/worker.py": {
        "bytes": 18065,
        "sha256": "920d04ea9965a9a342391aedc5cec48a9b730bc5abdc128634a147b149e087e3"
    },
    "artifacts/integration/production_f_qualification_001/artifact-identity.json": {
        "bytes": 4907,
        "sha256": "0bbd793141d1cf83999096f595b913d3a65e80dc1c2e486d65ef433188803ffc"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/launch.json": {
        "bytes": 6035,
        "sha256": "68db682bf2dd7783d5b7adc99d829bec920f773eac79c72be1faa3998cc52c98"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/observed-project-imports.json": {
        "bytes": 3453,
        "sha256": "433914951c235c173ecfaf845a62c26644ece94b9e78f4ea1532a425d6a0c2c2"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/process.json": {
        "bytes": 350,
        "sha256": "ad7acfd7fae463b1e6ff0b7fc2670841c2a5016316d47a9c6b69763e8507de4d"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/result/observations.jsonl": {
        "bytes": 310544,
        "sha256": "608203fba3b55667c47649dcf1156861d0980f42e6a9eb498bcbb1e0105455f5"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/result/public_outputs.zip": {
        "bytes": 2619513,
        "sha256": "9cd15465274f5a45021beeae41f4a252ee98d0f18c40cdc825644dbeb5b6d9d6"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/result/reads.jsonl": {
        "bytes": 1266,
        "sha256": "c0622fadb700fc3cdbe6b660dfd0751a41d33be51891a1d92b29524c64399b6b"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/result/summary.json": {
        "bytes": 362,
        "sha256": "219b9fd1a731df70a9edb70a6904f23b03237dbadd84cdf1b03aeac8701ed3c4"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/runtime.json": {
        "bytes": 2653,
        "sha256": "fa000b9d5b78927ddf662f2b33d3d674088d5fc086046e338f5f6364bf8b2ea4"
    },
    "artifacts/integration/production_f_qualification_001/run_001/20261105/worker.log": {
        "bytes": 78,
        "sha256": "910aa38ae16482fa28bf7298b492e995748b29b486033d02c0c4315a83d0cce9"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/launch.json": {
        "bytes": 5948,
        "sha256": "11eee2fd366fde35f06436a19489682752517092e861d34507ef03545dd38bbd"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/observed-project-imports.json": {
        "bytes": 3453,
        "sha256": "433914951c235c173ecfaf845a62c26644ece94b9e78f4ea1532a425d6a0c2c2"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/process.json": {
        "bytes": 348,
        "sha256": "81e4bf98135d9baec432ce679e8ccb420ea1ceed6efac9b7de1112c299496668"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/result/observations.jsonl": {
        "bytes": 310576,
        "sha256": "a1fd4fd1c0664af6dc07c7ec8fa982cdb28326a6fa227cb20caf3f3f85df3388"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/result/public_outputs.zip": {
        "bytes": 2615542,
        "sha256": "c475ef1257a61675eab64777daaf84b93b313dab7a42c839f90ddecf017ddc35"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/result/reads.jsonl": {
        "bytes": 1243,
        "sha256": "846840d5a34523046d1c6efd2f2848e7e7c3ea5bc987331424940a8b25e7c760"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/result/summary.json": {
        "bytes": 360,
        "sha256": "5e54eeaaaab60557cd3e82e8654637752a1d3c8237fb3dd7ad15614be246408c"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/runtime.json": {
        "bytes": 2651,
        "sha256": "3d3ba1f622ff707c4bea1e820accdb256f7f1f4bc1b4f271de76f53be14ecd74"
    },
    "artifacts/integration/production_f_qualification_001/run_001/310519/worker.log": {
        "bytes": 78,
        "sha256": "910aa38ae16482fa28bf7298b492e995748b29b486033d02c0c4315a83d0cce9"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/launch.json": {
        "bytes": 5921,
        "sha256": "733f05bd4e09d153c967371c20d6cb48bd63a3869d961b08bac31d19835862f4"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/observed-project-imports.json": {
        "bytes": 3453,
        "sha256": "433914951c235c173ecfaf845a62c26644ece94b9e78f4ea1532a425d6a0c2c2"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/process.json": {
        "bytes": 347,
        "sha256": "742effdbc69db09bd50e5ca73ed6918e5e73c7332bbca3829caa12fcb0810985"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/result/observations.jsonl": {
        "bytes": 310431,
        "sha256": "c8ff891fd93b0a555b8ecaba09e58310056315e42b66e39676259641a4c1d758"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/result/public_outputs.zip": {
        "bytes": 2609451,
        "sha256": "1290e123e2f75e3764d5f00798745378352f74c822b0ac5a30807690dbf57d6a"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/result/reads.jsonl": {
        "bytes": 1237,
        "sha256": "f8123cdb435be0cebd1c2d689feed6646ce4c31c0bfb91a7617ed88504a81978"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/result/summary.json": {
        "bytes": 359,
        "sha256": "cd8e588abc101616232f02079a11ad75fd80d66d17891e7e5bb4e9f032f9cce0"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/runtime.json": {
        "bytes": 2650,
        "sha256": "35ba22912615b818bb295a920ebb7904a587aac70871b1e009bdf8cde49c28a2"
    },
    "artifacts/integration/production_f_qualification_001/run_001/79463/worker.log": {
        "bytes": 78,
        "sha256": "910aa38ae16482fa28bf7298b492e995748b29b486033d02c0c4315a83d0cce9"
    },
    "artifacts/integration/production_f_qualification_001/run_001/manifest.json": {
        "bytes": 88241,
        "sha256": "9c83856999ec0f3a6fc563f2216d480283aa66262e4cbd79cfebe99951949beb"
    },
    "artifacts/integration/production_f_qualification_001/run_001/sources.zip": {
        "bytes": 2237013,
        "sha256": "73d436903a71aa291568bb8e1f084d852db98788d23e6f215f7d55520b9d00f5"
    },
    "artifacts/integration/production_f_qualification_001/run_001/summary.json": {
        "bytes": 1378,
        "sha256": "a185564be1d7f86233bc228a83e924a3f600328a345527770f6da490b7350fb1"
    },
    "artifacts/integration/production_f_qualification_001/run_qualification.py": {
        "bytes": 10409,
        "sha256": "1e05f6a0d7e29e4c203480c8ebf92c8d07d31441725e7e2cbadf0d4fdd3b5711"
    },
    "artifacts/integration/production_f_qualification_001/worker.py": {
        "bytes": 12883,
        "sha256": "94e6dd694f12fcc74b062d0bcbd1550cc5454a0dd8637c9828f65ce2db984890"
    },
    "artifacts/integration/root_lifecycle_review_001/bc_before.py": {
        "bytes": 18452,
        "sha256": "ffc494bf309bb9010854d88007edb54533c9fa9d7fad68905fe0d75663692aeb"
    },
    "artifacts/integration/root_lifecycle_review_001/candidate_equivalence.json": {
        "bytes": 7712,
        "sha256": "4f30e8d49944837a404301dce06537e4db1078812a8fd92d99fe69db11b4291b"
    },
    "artifacts/integration/root_lifecycle_review_001/candidate_equivalence.py": {
        "bytes": 3900,
        "sha256": "9868d36f12d45a9c88534b5f2a746fafdf0fbeea099e5b58e5ba9b03379a3143"
    },
    "artifacts/integration/root_lifecycle_review_001/contract_review.md": {
        "bytes": 7449,
        "sha256": "346e729601439d5b7b2013d344f4bf93d82a804fbe23e721f96e2889e89d81d0"
    },
    "artifacts/integration/root_lifecycle_review_001/diagnostic_probe.json": {
        "bytes": 1158347,
        "sha256": "18bf4f9a7dedd15612f7ab2d79b7a469faa49c9f259f196433cc25c245c4d6d5"
    },
    "artifacts/integration/root_lifecycle_review_001/diagnostic_probe.py": {
        "bytes": 14342,
        "sha256": "eba1c02db354d55176ee26a3a7052fb79356f7dcadce1f143addf026e462e7d2"
    },
    "artifacts/integration/root_lifecycle_review_001/f_recompute.json": {
        "bytes": 174380,
        "sha256": "4d8ba4ebb770f4c8a1f882a8be2d134793be39ec46b7f1756f5b2392709547b8"
    },
    "artifacts/integration/root_lifecycle_review_001/f_recompute.py": {
        "bytes": 15368,
        "sha256": "40939941ccd67b7052007953f92c78b323ecada14e7c06eea0f191951a31e055"
    },
    "artifacts/integration/root_lifecycle_review_001/lifecycle_after_and_numerical.log": {
        "bytes": 4961,
        "sha256": "d3285c4180badbecd2e292e0146d5e722b1fe3c3ca006fed23351d5d1ea6826f"
    },
    "artifacts/integration/root_lifecycle_review_001/lifecycle_before.log": {
        "bytes": 5731,
        "sha256": "b24027956c7fa0bb34138cb623d7ac8290a24fb478cd8d5099d48df70f6b4031"
    },
    "artifacts/integration/root_lifecycle_review_001/provenance_probe.json": {
        "bytes": 4913,
        "sha256": "57f4237d2b0d8252d8f5f2dc6aab825efb3d6c9287d44220093704e19678ace6"
    },
    "artifacts/integration/root_lifecycle_review_001/provenance_probe.py": {
        "bytes": 5275,
        "sha256": "7f18b1a282d718bf9e62043432aff83df2a03ec77b56031294ef74b5d9145b5a"
    },
    "artifacts/integration/root_lifecycle_review_001/review.md": {
        "bytes": 11379,
        "sha256": "17b4a21f9eaea0640533ae13e70ec5923612a985ccce291c90ba98f2d805c3e6"
    },
    "artifacts/integration/root_lifecycle_review_001/state_probe.json": {
        "bytes": 24741,
        "sha256": "3ee069d2cd6201ddd88971ae1068da9de4fe719d805df51480fcbe095eb52d46"
    },
    "artifacts/integration/root_lifecycle_review_001/state_probe.py": {
        "bytes": 11953,
        "sha256": "d677f223686360c9dcb908f755c719d4934ed30a5baf86fc95ada458965e5c3f"
    },
    "artifacts/integration/root_lifecycle_review_001/state_review.md": {
        "bytes": 9159,
        "sha256": "b6ae1563080352a99e6d32b8307bdd37615d6d9a602c0fdbb602b7d2483549eb"
    },
    "docs/MANAGED_CURRENT_RECHECK_PROTOCOL.md": {
        "bytes": 4926,
        "sha256": "d65d29910acffa38da701a339e96ae042146408ccb0b103ed46fbb76c7a7de00"
    },
    "docs/SURFACE_INDEX_LIFECYCLE_REVIEW.md": {
        "bytes": 5849,
        "sha256": "0073064779cbc0278b8e23df2367005fcbdc97b5842198d2d916e59c0916ad71"
    },
    "human_eye_fast/fast_bvh_clearance.py": {
        "bytes": 18475,
        "sha256": "76b25ff24cbde8433bcf700f8b45e3dfe8fefa8737425ef992ff7d1f3b8bebc1"
    },
    "verification/test_surface_index_lifecycle.py": {
        "bytes": 1454,
        "sha256": "74774e62cbd355555b2b783d47a2e9204bc71eaf9cc88128665ffb41d5934a67"
    }
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def record(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def read_frozen_inputs():
    require(len(FROZEN_RECORDS) == 95, "Unexpected frozen input count")
    require(HELPER not in FROZEN_RECORDS, "Do not self-hash helper source")
    require(ZIP_PATH not in FROZEN_RECORDS and INDEX_PATH not in FROZEN_RECORDS, "Self-reference")
    for directory in DIRECTORIES:
        current = {path.relative_to(ROOT).as_posix()
                   for path in (ROOT / directory).rglob("*") if path.is_file()}
        expected = {path for path in FROZEN_RECORDS if path.startswith(directory + "/")}
        require(current == expected, "Directory input list drift: " + directory)
    payloads = {}
    for relative, expected in FROZEN_RECORDS.items():
        path = ROOT / relative
        require(path.resolve().is_relative_to(ROOT), "Input outside repository")
        data = path.read_bytes()
        require(record(data) == expected, "Frozen input identity changed: " + relative)
        payloads[relative] = data
    payloads[HELPER] = (ROOT / HELPER).read_bytes()
    return payloads


def verify_author_identities(payloads):
    results = []
    for identity_path in IDENTITY_PATHS:
        directory = identity_path.rsplit("/", 1)[0]
        identity = json.loads(payloads[identity_path])
        expected_files = identity["files"]
        require(identity["file_count"] == len(expected_files), "Author declared count mismatch")
        listed = {directory + "/" + relative for relative in expected_files}
        actual = {path for path in payloads if path.startswith(directory + "/") and path != identity_path}
        require(listed == actual, "Author identity coverage mismatch: " + identity_path)
        for relative, expected in expected_files.items():
            require(record(payloads[directory + "/" + relative]) == expected,
                    "Author identity mismatch: " + relative)
        results.append({"path": identity_path, **record(payloads[identity_path]),
                        "listed_files": len(listed), "verified_files": len(listed),
                        "missing": [], "unlisted_except_identity_itself": [], "mismatches": []})
    return results


def source_identities(payloads):
    old_data = payloads[OLD_BC_PATH]
    historical = []
    for archive in AUTHOR_SOURCE_ARCHIVES:
        with zipfile.ZipFile(io.BytesIO(payloads[archive])) as source_zip:
            require(source_zip.namelist().count(BC_PATH) == 1, "Ambiguous archived BC member")
            archived_bc = source_zip.read(BC_PATH)
        require(archived_bc == old_data, "Author run did not use the archived original BC")
        historical.append({"archive": archive, "member": BC_PATH, **record(archived_bc)})
    needle = b"            split(0, count, depth)\r\n"
    require(old_data.count(needle) == 1, "Unexpected original constructor shape")
    current = payloads[BC_PATH]
    require(old_data.replace(needle, needle + b"            del split\r\n") == current,
            "Current BC is not exactly the one-line lifetime repair")
    require(old_data != current, "Old author source and new repair must remain distinct")
    return {
        "historical_author_runs": historical,
        "archived_original_bc": {"path": OLD_BC_PATH, **record(old_data)},
        "new_lifecycle_repair": {"path": BC_PATH, **record(current)},
        "relationship": "Historical author runs use the old BC source. Current BC differs only by del split after successful split. Historical measurements are not measurements of this repaired source.",
        "exact_one_line_byte_transformation_verified": True,
    }


def build_zip(payloads):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(payloads):
            entry = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, payloads[relative], compresslevel=9)
    return buffer.getvalue()


def verify_archive(path, records):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Duplicate ZIP members")
        require(names == sorted(records), "ZIP member list/order mismatch")
        for relative, expected in records.items():
            # Reading every member verifies ZIP CRC as well as SHA256 and size.
            require(record(archive.read(relative)) == expected, "ZIP read-back mismatch: " + relative)
    return {"verified_members": len(records), "bytes_sha256_crc_all_match": True,
            "duplicate_members": 0, "missing_members": [], "extra_members": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Read/verify existing ZIP/index without rewriting")
    args = parser.parse_args()
    payloads = read_frozen_inputs()
    author_checks = verify_author_identities(payloads)
    source_identity = source_identities(payloads)
    records = {path: record(data) for path, data in sorted(payloads.items())}
    paths = sorted(records)
    zip_path, index_path = ROOT / ZIP_PATH, ROOT / INDEX_PATH
    if args.verify_only:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        require(index["files"] == [{"path": path, **records[path]} for path in paths], "External index file identities differ")
        require(index["archive"] == {"path": ZIP_PATH, **record(zip_path.read_bytes())}, "External ZIP identity differs")
        require(index["author_identity_checks"] == author_checks, "Author verification index differs")
        require(index["source_identity"] == source_identity, "Source identity index differs")
        verified = verify_archive(zip_path, records)
        require(index["zip_readback"] == verified, "Read-back summary differs")
    else:
        archive_bytes = build_zip(payloads)
        # Before any output is written, detect source changes since freezing/reading.
        require(read_frozen_inputs() == payloads, "Input changed while constructing ZIP")
        zip_path.write_bytes(archive_bytes)
        verified = verify_archive(zip_path, records)
        require(zip_path.read_bytes() == archive_bytes, "ZIP output bytes changed")
        require(read_frozen_inputs() == payloads, "Input changed during ZIP read-back")
        index = {
            "schema": "human-eye-surface-lifecycle-evidence-v1",
            "scope": "Frozen author diagnostic/F qualification and completed independent lifecycle reviews, plus the limited recheck protocol, repair review, regression source, repaired BC and archive helper. No experiments run by this helper.",
            "frozen_input_list": paths,
            "frozen_input_list_sha256": hashlib.sha256(canonical(paths)).hexdigest(),
            "file_count": len(paths),
            "uncompressed_file_bytes": sum(row["bytes"] for row in records.values()),
            "files": [{"path": path, **records[path]} for path in paths],
            "archive": {"path": ZIP_PATH, **record(archive_bytes)},
            "author_identity_checks": author_checks,
            "source_identity": source_identity,
            "zip_readback": verified,
            "inputs_unchanged_before_and_after_zip_readback": True,
            "archive_format": {"compression": "DEFLATE", "level": 9,
                               "member_timestamp": "1980-01-01T00:00:00", "member_mode": "100644",
                               "member_order": "repository-relative path sorted lexically"},
            "exclusions": ["artifacts/integration/managed_current_recheck_001", "User specification documents", "Later root decision/progress files not in the frozen list", ZIP_PATH, INDEX_PATH],
            "replay": "python verification/archive_surface_lifecycle.py",
            "read_only_verification": "python verification/archive_surface_lifecycle.py --verify-only",
            "self_reference_policy": "The helper is an archive member. The generated ZIP and its external index are not archive members. No helper hash is embedded in its own source.",
        }
        index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": index["file_count"], "uncompressed_file_bytes": index["uncompressed_file_bytes"],
                      "zip_bytes": index["archive"]["bytes"], "zip_sha256": index["archive"]["sha256"],
                      "author_verified_files": sum(row["verified_files"] for row in author_checks),
                      "zip_verified_files": verified["verified_members"], "verification": "PASS",
                      "mode": "verify-only" if args.verify_only else "archive"}))


if __name__ == "__main__":
    main()
