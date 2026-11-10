# LRC-PREP-001 定向独立复核

结论：**原零启动失败交接缺口已修复；本分项通过，无新增阻断，可进入根其余核查通过后的既定 GO。** 固定提交 `db4ec4c4e0fa3cbf44a8f57fb3f4826730432e81`；打包器 SHA256 `3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365`。完整 PLAN 摘要见 `RESULTS.json`。

## 实际独立执行

运行本目录 `check_fix.py`，只导入旧/新纯后处理打包器。**15 个定向合成案例、51 项检查全过**；未重跑作者310项矩阵，未导入消费者、actor、产品或 Blender，没有模型/产品/Blender调用、没有修改实施树。禁止 subprocess/socket 的哨兵未触发。

- `consumer=None`：第一格保留 `failed_before_consumer/missing`，后八格 `not_run/not_run`。
- 失败 consumer 的 PID 为 null 或缺省：第一格保留 `failed/missing`，后八格未运行；原 null/缺省不填成虚构 PID。
- 三条通过路径均没有合成答案；RUN_RESULT、GO、STARTED 原始字节随交接归档。此前简版反例缺少的时钟/计数字段，本次只按既有 driver 实际输出结构补齐；没有加入真实消费者或虚构真实执行证据，所有输入明确为合成数据。
- 缺 GO、GO摘要错误、缺 STARTED、STARTED摘要错误、未终止、时钟顺序错误、错误计数、缺失败依据都被对应断言拒绝，不产生公开 INDEX。
- null PID 却声称成功、missing PID 却存在 thread_id 的未知执行记录也被拒绝，没有被转成“已确认无人启动”。
- 对同一正 PID 合成前缀，旧/新打包器均沿原路径工作；不提供 GO/STARTED，新版也没有额外索取。两份公开目录全部文件的相对路径与字节完全相等。
- 独立 AST 比较：全部旧有 payload/helper 函数相同，只有 main 接入新零启动分支，新增函数仅 `validate_zero_launch_failure`。原 final、错误、合法嵌套事实和未确认输出的投影规则未改。

## 与真实记录结构的对应

只读核对既有 `driver.run_models`：batch起点在 STARTED 前，cell起止在其后，最终 RUN_RESULT含相同计数和时界字段；首格输入/actor/快照失败以 row.consumer=None、row.errors 保存。`consumer_transport.consume` 的 Popen 异常以失败 consumer、null PID、null thread/final、valid_completion=false 与 errors 返回；外层 row.errors 可以为空。新分支正确覆盖这些字段组合，没有要求任意增加一条外层错误。

新分支只用于没有记录正 PID 的一次首格失败。GO/STARTED与固定PLAN绑定，终止计数及原时钟自洽；它不证明世界上没有发生过进程启动，而是忠实保全已有失败记录。含未知 thread 的情况继续拒绝，原始未知状态没有被吞掉。

## 作者记录与本轮结果分开

作者报告310项通过（原231＋79新增检查），根另行复放；该数字不是本子代理的实测数量。本子代理实际执行的是上列15案例/51检查。作者早期 wrapper 的输入基路径错误及静态摘要错误材料继续保留；本次未重做封存、安装或来源矩阵。

独立结果 `RESULTS.json` SHA256：`dd9eb15df2713add6af1d83459d1d05a8a14d2b01b5a137b965b17c41b557e41`。测试及完整合成交接都仅写本独立目录。
