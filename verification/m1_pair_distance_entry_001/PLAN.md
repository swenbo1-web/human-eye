# M1-PAIR-DISTANCE-ENTRY-001

固定 `95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a`。修正普通整件距离被引向候选关系集合的工具说明。实际 N15 P1/P3 的目标候选请求只给 `surface_proximity`，M09 P2 再加 `nearest_witness`，三者均被当前合同拒绝。原合法 `objects` 对象对请求已经能同一次给距离、当前表面最近点和正距离方向。[本轮证据](PERF050_TARGET_OBSERVATION_FIRST_IMAGE_P2_INDEPENDENT_REVIEW.md)

1. **一个最小候选。** 只改 `human_eye_scene_observe` 的现有公开工具说明，优先展示整件两个对象 A→B 的直接距离请求 `query={mode:task, objects:[A,B], requested_facts:[surface_proximity]}`，无图。说明此事实已含最近点和正距离方向。将候选集合与其关系事实成组的旧合同说明保留为简短文字，用这段替换目前优先出现的关系集合样例及含糊的 legacy pair 字样。原说明为 3,255 B，沿用原篇幅。验证器、输入 schema、strict `nearest_witness` 语义、返回形状和求解沿原逻辑。最短距离不要求额外闭体分类。
2. **用实际原件验契约。** 归档 N15 P1/P3 与 M09 P2 三条实际拒绝的原请求和原回执，复验原错误行为。用同一装配的留存整件来源和两组独立真值，验证建议的现有合法对象对形式能直接返回等价的表面距离、当前点对与 A→B 方向。已支持关系集合、严格见证、非距离入口及四条其它工具定义保留，实际工具目录仅该描述段变化。记录描述、工具目录和正常／错误回包字节。一个隔离候选，零 Blender、零模型、零替补、零资产重建、零额外 API 或费用。
3. **一次之后收口。** 本批判断工具入口是否更直接，不从静态文本推断模型省调用。自然采用和减少拒绝的收益留给另一道新任务的同版对照，沿用 N15／M09 原件做回归。

完成后向 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77` 发 `M1-PAIR-DISTANCE-ENTRY-001_READY`，附候选、源身份、准确原错误、合法回放与实际分母。
