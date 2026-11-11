# 受控实际入口

`INPUT_BINDINGS.json` 固定七个成功会话和所有源摘要。每次运行使用新输出目录，拥有的 Blender 启动累计上限为 10，包括失败准备占位。候选源码为 a81e530a，137 源摘要为 9f287f28…f504。基线使用既有 e077fce3 隔离安装，源摘要为 53db4197…f732。

入口直接复用已核验的 `Peer` 实际产品 stdio 和 `NativeSession` 拥有的后台 Blender。元数据初始化、工具目录和 ping 先完成，随后才发出首次应用几何请求。冷态指本会话首次应用请求。实际 schema、请求、响应、TCP worker 事件及 stdio TX/RX 均保存。

```text
python -I -B -X utf8 entry/run_entry.py --output run_01
```

七个会话按 Boff、Coff、Con、Con、Coff、Boff、刚体 Con 排列。原状态候选的五轮 warm 依次轮换 OFF、vertices、full，且每次 OFF 后紧接同字段原生补读。基线每轮先一次普通 warm OFF，再一次 OFF 加原生补读用于工程比较。每会话 cold 后另有一次当前宿主的独立坐标与三角面 oracle，共七次；登记变更后再有一次 oracle。这些控制读取在会话 RPC 和耗时中计入。

原生脚本按实际成功的 to_mesh、calc_loop_triangles 和世界映射增加计数，经 worker 私有事件返回。cold 与变更 oracle 另保存原局部坐标、实际世界矩阵、米制比例、实际 loop triangles、对象实例和数据用户。公开原生补读内容只包含请求的几何及合同字段。候选 full 的坐标和三角面与这份独立读回逐值比较。

QA helper 从既有 accepted_native 原件保留主体，差异见 `QA_NATIVE.diff`。它在所有 arm 上对 worker RPC 添加相同的 profile 与宿主 residency 前后计数。宿主按对象身份去重，保留模块 aliases 和真实 generation。profile 开销计入实际入口时间，前后探测开销分别记录。宿主 world_transforms 表示资源姿态准备。产品实际 scene.hash 成功 span 记录归一化和 hash 的执行次数，scene.validate 保留其原包围范围。生产 request_trace 继续提供编码 spans 与进程生命周期 peak RSS。

第七会话在初始 fingerprint 前执行合同登记的世界刚体映射，保存实际矩阵读回，坐标容差为 1e-6 米。最后一个原状态候选会话通过原有单次 qa_advance 对唯一 probe 数据的全部局部 z 坐标加 0.01，原 helper 以 float32 归一化并核对完整读回。该会话的最终 fingerprint 按已登记变更验证。源 blend 和工作副本文件保留原字节。

`run_case.passed` 表示本地入口、几何对照、来源与关闭检查完成。根协调者另从保存的实际计数核对同代显示选项的新增工作为零、warm 缓存、变更后的新代与关系重算，以及刚体 nominal 映射。这些门限核完后再形成整体工程判定。RPC 区间、stdio Peer 时间和 request_trace 具有包含关系，各自保留原始范围。
