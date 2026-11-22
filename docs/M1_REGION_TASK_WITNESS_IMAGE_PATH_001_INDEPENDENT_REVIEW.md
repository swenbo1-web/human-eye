# M1 区域任务首包原图路径独立复核

2026-11-22。接受隔离候选 `1535d08ac5124b5fe117101806ae3c85d47247fe`。公开路径只出现在既有证据端点的成功区域简报。现有 ReadContext 在当前捕获代按查询找唯一保留结果，不增加缓存或修改淘汰顺序。使用原 frame/ref、局部构造序号、见证像素行、原生 PNG 与规范路径对应。缺证明则省略路径，原图照常。标准入口及各表 schema 沿原合同。 [产品差分](https://github.com/swenbo1-web/human-eye/commit/1535d08ac5124b5fe117101806ae3c85d47247fe)

从 Git ZIP 核对 807 个唯一成员的长度、SHA-256 和 CRC。ZIP 4,676,866 B，摘要 `81fbd1d8aec972efb353285c7496c53f9901bc1988ab732d4ab5ac2b1ee047ce`。固定冻结 829 项、摘要 `455754ea88d61ecb66530775ea61559116730708518ebb67d7bbef88699b7a8b`；候选 143 源 `cdee32540b54f3278619305b23f28a646dba90d80212708ed3baf928514e2acd`、wheel `c2370f67569d1ac84ad8bf77c09d73942b06d22562bb2bceb34b9cced3b5b814`。 [封存索引](https://github.com/swenbo1-web/human-eye/tree/4279bcc430c07980ecbade5c7298e758f2adfe2f/verification/m1_region_task_witness_image_path_001)

冷、热四对真实 stdio 回复逐条核同三张原 PNG，共 7,918 B。两份局部见证各自附原链接，闭槽后实际按链接从磁盘读出同图块的原字节，和旧消费者 `read_images` 收据中的四个地址一致。首包 **7,564→8,144 B**，增加 580 B，原线包增加 594 B。正式回放进程 4/4 正常 EOF、退出码 0 及句柄回收。固定 CLI 预算重放 24/24。路径核验 0.473–0.512 ms，无额外 PNG 内容读。实际正常及边界合同 30/30、产品定向检查 15/15。首次依赖路径预飞失败保留。 [结果与分段](https://github.com/swenbo1-web/human-eye/blob/4279bcc430c07980ecbade5c7298e758f2adfe2f/verification/m1_region_task_witness_image_path_001/REPORT.md)

用冻结解释器只读重验公开见证。原 QA/QB/A1/B1 4/4。每份 QB/A1/B1 错绑只改 1 字节，将 R 的局部 SCENE 换成同名全场 SCENE，均保持原 18,912 B 长度、图块和像素。原验收误收 3/3，替代检查拒绝 3/3。未来构造未交付帧可能进入公开帧表，应按实际 `constructed_frames` 核全表、按 `frames` 核原生交付，不能把两者假定始终等长。 [公开见证反例](https://github.com/swenbo1-web/human-eye/blob/4279bcc430c07980ecbade5c7298e758f2adfe2f/verification/m1_region_task_witness_image_path_001/checks/PUBLIC_WITNESS_CONTROLS.json)

本批零新模型、Blender 或构图。历史各有一次读图重传 5,069 B，此次仅证实首包能提供同路径。下一项用[单对消费者](M1_REGION_TASK_WITNESS_IMAGE_PATH_CONSUMPTION_001_PLAN.md)考察自然采用和是否实际删除路径补取。
