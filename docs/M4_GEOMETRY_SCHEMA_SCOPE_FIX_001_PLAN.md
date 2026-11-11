# M4-GEOMETRY-SCHEMA-SCOPE-FIX-001

## 唯一问题

固定证据be2de48b、产品a81e530a/137源9f28中，通用human_eye_scene_observe.query公开schema允许geometry用于overview及旧task objects/aabb，但runtime只支持target/candidates的task-set。根独立反例位于 `D:/hefe/verification/fixes/20261111_m4_relation_selected_review/code/SCHEMA_SCOPE_REPRO.json`；报告 `D:/hefe/docs/M4_RELATION_SELECTED_EVIDENCE_001_REVIEW.md`。

## 最小修改

在实施分支的通用 `_QUERY_SCHEMA.allOf` 限定：包含geometry时必须有mode/target/candidates，mode为task。复用原target/candidates分支约束requested_facts和排除objects。优先一个schema条件解决，不改task_query、live_service、compact工具字段、运行时校验或几何实现，不扩修其他历史schema问题。

## 验收

- 保留原两个错误允许案例；修改后schema和runtime都拒绝。合法target/candidates+geometry控制两侧均接受。
- 旧overview与旧task objects/aabb在不带geometry时继续接受；surface_nearest带geometry继续拒绝。精简关系工具默认/vertices/full的公开定义和runtime行为保持。
- 使用现有可用验证器；不为三条规则引入新运行依赖。若使用定向静态规则求值，明确其范围、保存完整schema，并实际调用原runtime校验核对，不冒称完整JSON Schema实现。
- 以AST/字节对比证明仅新字段适用域元数据改变，几何/绑定/缓存/求解代码不变。记录新固定提交及canonical来源身份，相关定向离线验证即可，不机械重跑七Blender会话或整个性能矩阵。
- 公开接口修复不使原a81候选的默认+3.57%未决结果转为通过；新版本的未运行项单列，不能拼成同版本完整验收。

本批产品/Blender业务会话、模型消费者、图片和付费API为0。只允许本最小源码修正、离线协议/默认回归及Git证据；不新增安装或默认切换，不改原资产/共享GUI/竞争分支。所有旧原件与失败保留。

## 完成与停止

一个最小修正，完成一次简化审查确认没有额外层；提交后主动回报 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77`：cycle_id、本批 `SCHEMA_FIX_READY`、commit/source、最小diff、反例/合法/缺省控制的结果及未运行项，然后结束。不得自行启动延时归因、消费者或下一个模块。AL只用自身合法句柄，缺失如实记录，不借根句柄。
