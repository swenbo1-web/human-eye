# 仅离线诊断的内存差异

产品文件、安装与冻结源码没有修改。`SOURCE_BINDING.json` 记录137项源码和安装逐字节核对，以及实际 entry 哈希；两个 `.py.snapshot` 是原样字节。脚本均 `compile` 这些已核对字节，随后对自己进程里的模块常量赋值。以下 diff 只表示对应内存覆盖的含义，**不是产品补丁、候选或正式验收**。

1. `diagnose.py` 的 `fixed_product_baseline`：无覆盖；`diagnostic_pre_gate_removed_only`：

```diff
--- surface_proximity.py (verified snapshot, diagnostic equivalent only)
-MAX_TRIANGLE_PAIRS = 16384
+MAX_TRIANGLE_PAIRS = 1000000000
```

2. `closed_tail.py` 为看清后续瓶颈，除上述覆盖，再在内存设：

```diff
--- surface_geometry.py (verified snapshot, diagnostic equivalent only)
-CLOSED_SOLID_MAX_PAIR_TESTS = 16384
+CLOSED_SOLID_MAX_PAIR_TESTS = 1000000000
```

`262144` 总工作门、射线门和位宽保持原值。该脚本重复计算平面侧别以分类原 `_intersection` 早退，额外分类不计入旧工作账本，耗时不能作为性能收益。

3. `cheap_contact_potential.py` 和 `final_bound_potential.py` 枚举静态工作结构，另设 `CLOSED_SOLID_MAX_WORK = 1000000000`。它们不返回产品测量结果、不判定准入通过；分别统计潜在便宜证书/最终距离下界能排除多少，以及哪些访问仍存在。`final_bound_potential.py` 的 best 来自已完成的离线穷举结果，是事后理想上限，不能用作未来产品初始距离。

所有脚本仍使用原 `MAX_BITS=4096`、原整数局部原点和原三角坐标。诊断的放开上限只用来定位真实剩余工作；不能将其交付成已扩大支持域的产品版本。
