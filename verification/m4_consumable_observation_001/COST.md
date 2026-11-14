# 可直接消费观察单槽成本

原任务质量与产品事实采用通过，消费效率因重复SCENE失败，整体机制未通过。此处只列当前单槽已保存原值。

| 嵌套时界 | 秒 |
| --- | ---: |
| parent | 141.1133463 |
| launch | 141.0454885 |
| route | 138.4381683 |
| consumer | 137.1918579 |

launcher的route调用包容时界为138.4388121秒，与原route记录相差643800纳秒，口径分别保留。这四层和产品/工具子阶段均存在嵌套，不叠加为总耗时。

实际7次工具请求均进入业务入口，没有guard拒绝。4次raster为产品3次和重复原生SCENE1次，4个PNG块实际构造、发送并到达CLI。重放1次、产品与prepare各1次，准备raster及Blender采集为0。

实际公开v4 JSON为44873字节，同状态已保存v3为42049字节，增加2824字节。桥接仅绑定同一字符串，独立赋值CPU时间和实际namespace独立dump/hash未测。tool2包含json.loads及打印，包容时长0.0012327秒；tool3已有JSON查询为0.0010555秒，均没有被标成纯解析CPU。

重复SCENE的tool4为0.2461134秒。tool5转换错误0.0013779秒，tool6恢复后的已有region引导全网格身份核对0.0571725秒，tool7整幅SCENE像素/边界验证与表格输出0.0206188秒。本次没有重新发现所有区域或重算六相机遮挡。

产品scope_and_facts阶段为0.0028039秒。MCP投影、公开序列化及图片处理的包容阶段为0.0129916秒；各自独立CPU未测。prepare/index、缓存标记、光栅、联合PNG/NPZ发布、图片read/validate/base64与像素反馈均保留原时界。

CLI原始usage记录input 144766、cached input 118528、output 2616、reasoning output 213、cache write 0。cached和reasoning分别是input/output子集，未重复相加。仅一条usage事件不等于一次provider请求，turn/session聚合范围仍未确认。图像token、现金费用与provider内部请求未测。

CLI、actor、launcher均exit0。thin持有句柄确认exit1并关闭，EXIT/正常EOF回执仍未知。未知模型metadata回退警告原样保留，未据此推断provider切换或重试。

1746份冻结来源、16份质量文件及289份归档原件/副本已复核。无新模型、产品、测试、光栅或时钟采样，没有使用旧失败任务作收益分母。数组、PNG、base64、JSON、stdio和ZIP逐层列在COST.json，峰值内存与缓存总量保持未知。
