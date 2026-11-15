# M6-MATCHED-REFINE-003 勘误

固定作者提交 `c58e464d454c83b90b3c9baa026478c590e578e6` 的 `verification/m6_matched_refine_003/REPORT.md` 中，消费者方法表将V1 native写为“提交positions”。实际最终程序调用 `save_edit(active, displacements, mode='displacements_world')`，载荷元数据也记录 `displacements_world`。本勘误保存在004新增目录。

- 固定旧报告SHA256为 `13dad024704b33fe6f8182579061a575fa0f349b6913800bd2612e718501b02b`。
- 旧最终程序路径为 `private/consumers/v1/matched/native/bridge/tool_08/python/CODE.py`，SHA256为 `4f78b35a0fc33c6a41b48b0c7de862afbe89807a5d3a47d172eadbe859017f07`。
- 旧载荷路径为 `private/sessions/v1_matched_native/payloads/p500318f92dc449cc8b9ef6b63208aeb4.npz`，SHA256为 `1578788a1ac1107bf6c3b3df67c3fea4b9d7bbc77411522c07b99a8dfba7cbd0`。
- 旧载荷元数据路径为 `private/sessions/v1_matched_native/payloads/p500318f92dc449cc8b9ef6b63208aeb4.json`，SHA256为 `b3fd0e1c72c0016da40908484520ab9267e484ad7fbc850deae563df9e838174`。

CODE和载荷的字节身份逐项匹配固定c58提交的003 MANIFEST，私有副本位于 `private/diagnostics/frozen/`。规划复核提交 `f974cf88ecdb0ccc3677aa204d7bba02521841ec` 的 `verification/m6_matched_refine_003_review/PEER_REVIEWS.json` 同时记录了这一勘误，003原报告和证据保持固定字节。
