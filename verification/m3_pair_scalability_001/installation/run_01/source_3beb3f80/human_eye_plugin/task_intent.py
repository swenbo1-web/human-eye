"""Conservative, local task intent for deciding whether to read a 3D host.

This classifier never infers geometry, grants execution authority, remembers a
previous task, or calls a model. Trusted host metadata can correct uncertain
language. Quoted/code instructions are data rather than automatic host requests.
"""
from __future__ import annotations

import re


POLICY_REVISION = "task-intent-v1.1-20261023"
_KINDS = {"spatial_3d", "image_2d", "general", "unknown"}
_MAX_TEXT = 65536
_NEGATOR = (r"(?:不要|不用|不必|无需|不需要|不打算|不想|禁止|(?<![识区鉴类级差个分特])别"
            r"(?=把|将|让|沿|再|继续|急着|马上|移动|旋转|读取|观察|检查|比较|调用|使用|启用|打开|执行|转动|看|挪|放|摆|插|装)"
            r"|\bdo\s+not\b|\bdon['’]t\b|\bnever\b)")


def _result(kind, source, *reasons):
    return {"kind": kind, "source": source, "reason_codes": list(reasons),
            "requires_scene_capture": kind == "spatial_3d", "policy_revision": POLICY_REVISION,
            "execution_authority": False, "uses_external_model": False}


def _matches(pattern, text):
    return re.search(pattern, text, re.IGNORECASE) is not None


_IMAGE_CONTEXT = (r"图片|照片|截图|海报|二维|平面图|图表|扫描|发票|插画|渲染图|"
                  r"\b(?:image|photo(?:graph)?|screenshot|poster|diagram|chart|plot|scan|2[- ]?d)\b")
_SPATIAL_OPERATION = (r"测量|量一下|量一量|检查|核实|查看|看看|看一下|观察|定位|判断|比较|确认|"
                      r"移动|平移|上移|下移|旋转|转动|转到|对齐|对准|调整|微调|恢复|贴合|保留|"
                      r"挪|放置|放到|放在|摆放|插入|装入|有没有|是不是|是否|"
                      r"\b(?:move|translate|rotate|align|inspect|measure|check|verify|observe|position|"
                      r"orient|compare|look|place|seat|put|insert)\b")
_QUOTED_COMMAND = (r"\b(?:move|rotate|translate|place|seat|put|insert|inspect|look|check|measure|read|"
                   r"write|explain|ignore|run|execute|call|delete|do|never|not|then|must|should|please)\b"
                   r"|不要|不用|禁止|忽略|移动|旋转|平移|挪|放置|插入|检查|读取|观察|调用|执行|删除|解释|请|把|将")


def _quoted_entity(match):
    """Retain short object labels, never an instruction inside quotation marks."""
    fragment = next((group for group in match.groups() if group is not None), "")
    opening = match.group(0)[0]
    closing = {'"': '"', "“": "”", "‘": "’", "「": "」", "『": "』", "'": "'"}[opening]
    if (len(match.group(0)) < 2 or not match.group(0).endswith(closing)
            or not 0 < len(fragment.strip()) <= 80
            or not re.fullmatch(r"[\w .:/()\[\]-]+", fragment)
            or _matches(_SPATIAL_OPERATION, fragment)
            or _matches(_QUOTED_COMMAND, fragment)):
        return " "
    return " " + fragment + " "


def _unquoted(text, *, retain_entities=False):
    text = re.sub(r"```[\s\S]*?(?:```|\Z)|~~~[\s\S]*?(?:~~~|\Z)", " ", text)
    text = re.sub(r"(?m)^\s*>[^\n]*$", " ", text)
    text = re.sub(r"(?m)`[^`\n]*(?:`|$)", " ", text)
    replacement = _quoted_entity if retain_entities else " "
    text = re.sub(r'(?m)"([^"\n]*)(?:"|$)|“([^”\n]*)(?:”|$)|‘([^’\n]*)(?:’|$)|「([^」\n]*)(?:」|$)|『([^』\n]*)(?:』|$)', replacement, text)
    # Apostrophes in don't/it's are not quotation boundaries.
    text = re.sub(r"(?m)(?<!\w)'([^'\n]*)(?:'(?!\w)|$)", replacement, text)
    return text.strip()


def classify_task_intent(task_instruction, *, task_kind=None):
    """Return JSON-compatible intent; unknown metadata never silently overrides.

    A valid explicit kind wins, including ``unknown``. ``ocr`` is a compatible
    alias for ``image_2d``. None means no metadata; malformed or unsupported
    non-None metadata returns unknown so callers must correct it explicitly.
    Without metadata, only combined physical context and requested geometry work
    select 3D. Scene availability by itself is not a task-intent signal.
    """
    if task_kind is not None:
        if not isinstance(task_kind, str):
            return _result("unknown", "invalid_host_metadata", "task_kind_must_be_a_string")
        if task_kind == "ocr":
            return _result("image_2d", "explicit_host_metadata", "explicit_ocr_task")
        if task_kind in _KINDS:
            return _result(task_kind, "explicit_host_metadata", "explicit_task_kind")
        return _result("unknown", "invalid_host_metadata", "unsupported_task_kind")
    if not isinstance(task_instruction, str):
        return _result("unknown", "invalid_instruction", "task_instruction_must_be_text")
    if len(task_instruction) > _MAX_TEXT:
        return _result("unknown", "local_rules", "task_instruction_exceeds_classification_budget")
    # Quoted names can supply a subject only when the user requests an
    # affirmative operation outside quoted/code material. Quoted commands
    # never create that request; entity exclusion shares the operation rule.
    outside = _unquoted(task_instruction)
    outside_affirmative = re.sub(_NEGATOR + r"[^，。；！？,;.!?\n]*", " ", outside, flags=re.IGNORECASE)
    text = _unquoted(task_instruction,
                     retain_entities=_matches(_SPATIAL_OPERATION, outside_affirmative))
    if not text:
        return _result("unknown", "local_rules", "no_unquoted_task_instruction")
    affirmative = re.sub(_NEGATOR + r"[^，。；！？,;.!?\n]*", " ", text, flags=re.IGNORECASE)
    if _matches(r"(?:不要|不用|不必|无需|不需要|(?<!识)别(?=调用|使用|启用)).{0,8}(?:调用|使用|启用).{0,12}(?:引擎|插件|human.?eye)|\b(?:do\s+not|don['’]t|never)\b.{0,12}\b(?:use|call|invoke)\b.{0,24}\b(?:engine|plugin|human.?eye)\b", text):
        return _result("general", "local_rules", "explicit_engine_opt_out")
    tutorial = _matches(r"(?:如何|怎么|怎样).{0,48}(?:移动|旋转|对齐|贴合|操作|建模)|教程|\b(?:tutorial|how\s+to)\b", affirmative)
    current_subject = _matches(r"当前|这个|这些|我的|本场景|\b(?:this|these|my|current|live)\b", affirmative)
    if tutorial and not current_subject:
        return _result("general", "local_rules", "generic_how_to_or_tutorial")

    # A sequence may ask for explanation and an actual current-scene operation.
    # Keep code-writing descriptions whole; their described steps are not host
    # actions. Image context carries across a sequence unless a later clause
    # explicitly names a current/live subject.
    code_prose = (r"(?:写|编写|生成|修复|优化|审查|调试|解释|讲解).{0,48}(?:脚本|代码|函数|正则|程序)"
                  r"|\b(?:write|debug|review|implement|fix|generate|optimi[sz]e|explain|describe)\b.{0,48}\b(?:code|script|function|regex|program)\b")
    clauses = re.split(r"[;；。!?！？\n]|\b(?:then|afterwards|after\s+that)\b|然后|随后|接着", affirmative,
                       flags=re.IGNORECASE)
    if len(clauses) > 1 and not _matches(code_prose, affirmative):
        image_subject = _matches(_IMAGE_CONTEXT, affirmative)
        for clause in clauses:
            clause = clause.strip(" ,，")
            if not clause:
                continue
            live_subject = _matches(r"当前|本场景|\b(?:current|live)\b", clause)
            if image_subject and not live_subject:
                continue
            if classify_task_intent(clause)["kind"] == "spatial_3d":
                return _result("spatial_3d", "local_rules", "spatial_request_in_sequential_clause")

    # Discussing code, a quoted instruction, a theory or a model's training is
    # ordinary work even when spatial keywords occur in the discussed material.
    meta = (r"(?:解释|讲解|讨论|介绍|说明|描述).{0,64}(?:概念|原理|算法|数学|区别|学习|代码|函数|报错|这段|这句话|含义|意思)"
            r"|(?:写|编写|生成|修复|优化|审查|调试).{0,48}(?:脚本|代码|函数|正则|测试|程序)"
            r"|(?:设计|实现|优化|审查|调试|修复|研究|评估).{0,64}(?:算法|引擎|插件|架构|调度|路由|缓存|接口|测试|流程|方法)"
            r"|(?:解释|讲解).{0,32}(?:如何|怎么|怎样)"
            r"|\b(?:explain|discuss|teach|describe)\b.{0,64}\b(?:concept|theory|algorithm|code|function|meaning|difference|how)\b"
            r"|\b(?:write|debug|review|implement|fix|generate|optimi[sz]e|design|research)\b.{0,48}\b(?:code|script|function|regex|test|program|algorithm|architecture|runtime|scheduler|routing|cache)\b"
            r"|\bobject\b.{0,16}\b(?:type|dtype|attribute|method|class)\b"
            r"|(?:模型|\bmodel\b).{0,32}(?:训练|权重|推理性能|training|weights|inference performance)"
            r"|(?:AI|GPT|LLM|LoRA|语言模型|神经网络|训练|权重|数据集|\b(?:language|neural|training|weights|dataset)\b).{0,40}(?:微调|fine[- ]?tun)"
            r"|(?:微调|fine[- ]?tun).{0,40}(?:GPT|LLM|LoRA|语言模型|神经网络|训练|权重|数据集|\b(?:AI|language|neural|training|weights|dataset)\b)")
    writing = (r"(?:翻译|润色|改写|总结|整理).{0,80}(?:文章|文字|这段|邮件|会议|开发|事项|清单|句|词|段落|单词|日志|报错)"
               r"|(?:给|为).{0,24}(?:文章|项目|变量).{0,24}(?:标题|简介|名字|起名)"
               r"|\b(?:translate|rewrite|proofread|paraphrase)\b"
               r"|\b(?:summari[sz]e|draft|write)\b.{0,40}\b(?:email|article|paragraph|meeting|text|report)\b")
    if _matches(meta, affirmative) or _matches(writing, affirmative):
        return _result("general", "local_rules", "discussion_or_text_work")

    image_context = _matches(_IMAGE_CONTEXT, affirmative)
    image_request = _matches(r"识别|读取|读出|描述|总结|分析|文字|检查|解释|找出|比较|对比|看看|看一下|\b(?:read|recognize|recognise|describe|identify|extract|analy[sz]e|summari[sz]e|find|compare|look|inspect)\b|\bwhat\b.{0,30}\b(?:color|text|say|show)", affirmative)
    ocr = _matches(r"\bocr\b|识别文字|读取.{0,24}(?:序列号|标签|配料表)|\b(?:read|extract)\b.{0,36}\b(?:text|label|serial number)\b", affirmative)
    if image_context and image_request or ocr:
        return _result("image_2d", "local_rules", "image_or_text_recognition_request")

    # Only affirmative clauses supply operations. Objects in a negated clause
    # may provide context for a following affirmative measurement, never motion.
    physical = _matches(r"零件|底座|支架|基准|插销|孔|轴|螺母|齿轮|机械臂|托盘|积木|桌腿|桌面|台面|花瓶|杯子|书本|接触点|接触面|支撑柱|装配|实体|(?<![a-z0-9_])(?:cubes?|mesh(?:es)?|parts?|bases?|brackets?|pegs?|holes?|shafts?|gears?|assembly|contact|surfaces?|robots?|axis|axes|pivot|vertices|faces?)(?![a-z0-9_])", text)
    weak_object = _matches(r"模型|物体|对象|场景|三维|\b(?:models?|scenes?|blender|3d|objects?)\b", text)
    geometry = _matches(r"三维|空间|世界|坐标|姿态|偏航|法线|接触|相交|碰撞|碰上|穿透|距离|间隙|有缝|贴合|包围盒|装配|沿.{0,3}[xyzXYZ]轴|毫米|厘米|\b(?:clearance|collision|intersect|penetrat|distance|gap|align|orientation|pose|normal|world|coordinates?|pivot|degrees?|millimet(?:er|re)s?|mm|cm|3d)\b", affirmative)
    operation = _matches(_SPATIAL_OPERATION, affirmative)
    scene_query = _matches(r"(?:检查|查看|观察|inspect|observe|check).{0,24}(?:当前)?(?:场景|\bscene\b)", affirmative)
    if operation and (physical or weak_object and geometry or scene_query):
        return _result("spatial_3d", "local_rules", "physical_context_and_spatial_request")
    if affirmative != text and not operation:
        return _result("unknown", "local_rules", "spatial_request_negated_or_no_affirmative_operation")
    if _matches(r"翻译|计算|解释|整理|润色|改写|总结|起名|列表|变量|JSON|排序|邮箱|预算|阅读计划|标题|项目简介|合并.{0,32}(?:句|段)|\b(?:calculate|explain|translate|summari[sz]e|sort|email|budget|schedule|joke)\b", affirmative):
        return _result("general", "local_rules", "ordinary_text_or_calculation")
    return _result("unknown", "local_rules", "insufficient_task_context_use_explicit_task_kind")


__all__ = ["POLICY_REVISION", "classify_task_intent"]
