# ARM-CORRECTION-PREVIEW-OPT-001

2026-11-10。本模块一次优化已收口，待管理员深审：修复微量第三骨权重导致的假不可达，候选全点骨变换6→4，并首次用真实 `BoundArmPatch.capture → preview` 跑通同八任务。四正例完成QA两骨赋值及实际回读，另外四例零候选写入。产品仍只有纯预览，没有新增MCP、scheduler、产品setter或学习模块；不追加第三轮预览调优。

基线612e4fe900f14cb8caa5be4752665436161bd02e，当前分支codex/architecture-arm-correction。唯一产品改动为arm_twist_correction.py，最终SHA `4d127c56b44747beed38462422abc4b6e9233ec7a32162b95e007d0893186eda`。source/expert/weights/rig_pose及旧验证字节保持；全源137，canonical `9505440e7a56555fbb5be7101ecc2fca8dc82742f3c0b7ab811ae800889ac941`。旧失败与原批结果沿Git和根审核路径引用，没有重写。

## 正确性与精度

旧WEIGHT_ATOL会把真实的第三骨贡献当零，但随后仍把θ/2宣称为精确最优。现把结构支持与数值精度分开：非相邻两端都有任何正权重即域外；同圈权重、50/50见证及纯端点完整行要求实际相等，不修改权重、目标或area_tolerance来迎合闭式解。普通source对同圈的有效权重归一化输出保持适用。

保留根微量第三骨反例：epsilon=5e-11，原θ/2结果J≈.250000000075超过原目标.250000000055+1e-12；独立见证u=59.999999995的J≈.25000000003778733满足同一任务。现在该输入明确not_applicable/non_adjacent_weights，不再声称不可达；可行见证的几何事实仍成立。根原12方法11通过/1失败及FEASIBLE_WITNESS原件及SHA保留在 `D:/hefe/verification/fixes/20261109_architecture_completion/correction_preview_review/behavior/`，未改成成功。

仅严格权重还不足以对极紧目标作不可达判断，因为原域仍允许小幅非轴与近平面误差。因此仅在实际候选未满足目标时，用两个实际半权截面面积向量计算保守下界：cofactor映射面积向量，分别界定首骨坐标框架、末骨偏离理想轴向旋转及浮点舍入的影响；含实际半权环法向、逆矩阵残差、环点数/半径/周长/坐标相对面积的条件量。只有下界超过原target+area_tolerance才返回unreachable；否则not_applicable/area_target_below_supported_precision。没有新优化器、重试、误差服务或放宽任务。

最终CPU13/13、0失败/错误/跳过：原10方法+根共同全局运动与微三权2例+数值守卫1例。额外守卫只复用原round120几何，target=.24999999999999、tol=1e-16保持原值，实际候选约.2500000000000002，下界约.2499999999996279不足以证明不可达，准确不适用并无候选；原[110,120]/目标.4仍准确不可达。八个效果任务及资产未增加。cpu_01是早期f34b5923的12方法；cpu_02是最终4d127c56的13方法，结果分开保留。两者均核源原字节并编译同一变量，原数据/监督标签不进入求解参数。

## 调用内复用与一次完整函数对照

当前与候选的首末绝对pose不变，因此当前LBS读取时保存这两骨的加权贡献；候选只变换中骨。三份rest inverse在同调用内复用，局部basis补偿沿相同矩阵代数，不建跨请求缓存或新准备层。实际未计时profile证实：需候选的输入旧6次全点骨变换，新3次当前+1次候选；no_op仍3，非共轴域外0。一次八任务合计36→26。rest坐标框架的402点变换与25点中心参考另记，不偷算为骨变换收益。

唯一benchmark事先固定：每实现/任务一次预热16调用，八任务各5对交替先后80计时调用，随后16调用追踪，共112；主计时没有profile/wrapper。旧函数来自Git612e4fe，解析与矩阵依赖逐字节相同；输入完全相同且未改，所有旧输出字段（除work）最大数差3.33e-16，旧门1e-11；新下界字段明确新增、实际数值保留，没有从比较中删除不利旧字段。

完整preview中位毫秒，每态5样本：

| 原固定任务 | 旧 | 新 | 变化 |
| --- | ---: | ---: | ---: |
| round120 | 4.2046 | 4.2528 | +1.15% |
| round-150 | 4.2349 | 4.1634 | -1.69% |
| elliptic120 | 4.2839 | 4.1112 | -4.03% |
| elliptic-150 | 4.2206 | 4.1048 | -2.74% |
| balanced | 3.2894 | 3.2768 | -.38% |
| small30 | 3.3017 | 3.2473 | -1.65% |
| unreachable | 4.0740 | 4.2140 | +3.44% |
| noncoaxial | .9954 | 1.0215 | +2.62% |

五态改善、三态回退都保留。不可达新增两截面下界检查有成本，其余状态并无此检查；不把不同功能质量的成本全部算成LBS优化效果。减少33%的候选骨变换不等于完整函数或整任务快33%；样本少、增益小，不能据此保证总体延迟。没有事后性能门、追加采样或新调优轮。保留简单调用内复用的确定工作量收益，完整速度收益如表，由根审核取舍。

## 真实来源→预览→QA回读

一次独占Blender5.2.1 LTS后台进程，factory-startup/disable-autoexec、不打开/保存blend。原eight-case recipe只用于构建生成夹具，随后每例真实构造BlenderSceneHost与ArmTwistSource.bind，恰好一次BoundArmPatch.capture。预览输入直接取capture的static_patch、current_vertices和pose_matrices，仅组装原packet字段，没有再生成double输入代替采集值，也没有QA归一化器。

原生raw RNA权重与source导出的有效权重分别保存，最大差约2.03e-8；后者来自原source已有的value/math.fsum(row)语义，不是本批改动。静态数据、原始/有效权重、完整capture、实际preview输入/task、source epoch/实例/选择/坐标/单位以及logical→native ID映射全部存档。任务绑定实际捕获的端姿态与原有纯端点194 IDs；目标.4和原区间未变。preview容差测前固定角.001°/位置5e-6m/面积1e-6（不超原cap），独立RNA回读仍为.001°/5e-6m/2e-5，没有后调。

| 实际来源任务 | preview | 实际场景J前→后 | QA候选赋值 |
| --- | --- | ---: | ---: |
| round120 | candidate | .7500000252→.2500001908 | 2 |
| round-150 | candidate | .9330126980→.3705905457 | 2 |
| elliptic120 | candidate | .7499999943→.2500001585 | 2 |
| elliptic-150 | candidate | .9330127006→.3705904424 | 2 |
| balanced | no_op | .2500001240→同值 | 0 |
| small30 | no_op | .0669874013→同值 | 0 |
| unreachable | unreachable | .7500000252→同值 | 0 |
| noncoaxial | not_applicable | 域外，不推断目标；原几何保持 | 0 |

不可达任务预览的最佳允许J约.671010，下界约.6710096505>.4+1e-6；因为未执行，实际场景J仍.75，不能把预测最佳值冒称实际改善。四正例实现已声明的中/末两条basis后，首末全局姿态、头尾、194保护点、完整静态数据和选区外sentinel均过原门；最大头尾变化8.72e-8m、保护位移1.79e-7m、原生点对预测误差2.36e-7m、实际J误差1.91e-7，端姿态角差约1.49e-5°。其余四例没有候选写入且实际点精确保持。

这次完整保存static_before/static_after、sentinel_before/sentinel_after和保护点前后原值，关闭原证据只能读相等断言的缺口；每例raw还包含实际source输出和preview输入，能复核是否直接消费，并非仅字节哈希。八source capture各1静态读取/1prepare/402rest+weight+current行/3rest+pose骨/1topology；没有多取一个capture来修补字段。8次preview模型调用0，Source的静态prepare不算模型推理或训练。

独立标准库审计7434项通过，未导入产品或既有oracle：重新枚举137源并重算canonical，逐值绑定完整capture与实际输入，按既有source语义检查原始/有效权重而不创建新patch，重算面积、LBS、端点/头尾/保护和完整静态/sentinel原件。独立LBS最大差约2.482e-7m，保护最大位移约1.789e-7m；不可达下界独立重算.6710096505028615，与记录相符。也核原微权重见证仍满足原任务、旧失败未改。`audit_native.py`及`INDEPENDENT_NATIVE_AUDIT.json`封存；没有新增效果、producer或Blender调用。

八次完整source capture合计102.43ms，八次preview合计34.06ms，彼此分开。原生probe主段672.49ms另含夹具建立/独立原生读取/检查/JSON存档；含Blender启动退出launcher1514.90ms，两者嵌套不能相加。所有值是一次工程观察，不是MCP完整任务或agent成本收益。无模型调用、训练、Google、付费API、图片或用户GUI操作。

本批实际preview分母为143调用：早期12方法调用11次、最终13方法调用12次、固定old/new benchmark112次、原生8次。其中最终源76次、旧基线56次、早期开发源11次；正确性重验不累计为新资产覆盖。独立见证与artifact审不调用preview。全批模型调用0、原生进程1个。

PID17732 returncode0/closed=true且根实际查无进程。八例host residency及全部handler关闭，生成object/mesh/rig移除，运行源字节不变，文件未保存；窗口已释放。产品setter=0；QA仅24次初始化骨姿和8次候选骨姿、16次独立RNA回读。原资产、正式配置和竞争分支未变。

本批达到真实来源预览的工程入口；正式骨姿写入、当前Codex MCP消费与共享反馈尚未实现，也未证明通用人物/动画/体积或学习净收益。根通过后应直接进入现有入口的一次paired骨姿写入与共享实际回读，不重新开预览、LBS或拓扑热点。
