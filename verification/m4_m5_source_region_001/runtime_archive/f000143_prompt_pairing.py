"""Bounded current-snapshot object binding for read-only pair observations.

This is a deliberately small grammar, not a general language interpreter.  A
successful match identifies a measurement pair only.  It neither authorizes a
transform nor certifies that a host display color is a material/rendered color.
"""
from __future__ import annotations

import re


POLICY_REVISION = 'prompt-pair-v1-20261027'
_MAX_TEXT = 4096
_MAX_MESHES = 2048
_MAX_SELECTOR = 512
_QUOTE_OPEN = {'"': '"', "'": "'", '“': '”', '‘': '’', '「': '」', '『': '』'}
_TOKEN_OPEN, _TOKEN_CLOSE = '\ue000', '\ue001'
_CN_REQUEST = re.compile(
    r'(?:请你|请|帮我)?\s*(?:再次|再|现在|先)?\s*'
    r'(?:检查|测量|查看|观察|核实)\s*'
    r'(?:(?:当前\s*)?(?:Blender\s*)?(?:测试场景|当前场景|场景)\s*(?:中的|内的|中|内)\s*)?'
    r'(?P<pair>.+?)(?:之间)?\s*(?:的)?\s*'
    r'(?:间隙|距离|碰撞情况|接触情况|碰撞|接触)', re.IGNORECASE)
_EN_REQUEST = re.compile(
    r'(?:please\s+)?(?:check|measure|inspect|observe|verify)\s+(?:the\s+)?'
    r'(?:gap|clearance|distance|collision|contact)\s+between\s+(?P<pair>.+)', re.IGNORECASE)
_CN_READ_ONLY = re.compile(r'(?:只观察|仅观察|只测量|仅测量|不移动|不要移动|勿移动|保持不动)')
_EN_READ_ONLY = re.compile(r'(?:observe only|measure only|read only|do not move|don[\'’]t move|no movement)', re.IGNORECASE)
_COLORS = {
    '蓝': 'blue', '蓝色': 'blue', 'blue': 'blue',
    '灰': 'gray', '灰色': 'gray', 'gray': 'gray', 'grey': 'gray',
}
_CN_COLOR = re.compile(r'(蓝色?|灰色?)(对象|物体)?')
_EN_COLOR = re.compile(r'(blue|gray|grey)(?:\s+(object|mesh))?', re.IGNORECASE)
_DISCOURSE = re.compile(
    r'如果|假如|假设|若|以后|稍后|明天|将来|计划|示例|例如|举例|比方|'
    r'不要|不用|不必|无需|不需要|禁止|教程|翻译|说明|解释|'
    r'\b(?:if|when|unless|later|tomorrow|should|would|could|example|tutorial|'
    r'translate|explain|never|not|no|don[\'’]t)\b', re.IGNORECASE)


def _result(scene, fingerprint, status, reason, *, focal=None, reference=None, evidence=None):
    return {'policy_revision': POLICY_REVISION, 'status': status,
            'focal_id': focal, 'reference_id': reference,
            'reason_codes': [reason], 'evidence': evidence or [],
            'scene_revision': scene.get('revision') if isinstance(scene, dict) else None,
            'scene_fingerprint': fingerprint,
            'scope': 'current_snapshot_read_only_pair_binding_not_execution_authority',
            'execution_authority': False, 'uses_external_model': False}


def _quote_tokens(text):
    """Protect literal object names without exposing quoted commands as syntax."""
    result, literals = [], {}
    index = 0
    while index < len(text):
        opening = text[index]
        if opening not in _QUOTE_OPEN:
            result.append(opening)
            index += 1
            continue
        # A contraction in a read-only suffix is not an entity quote.
        if opening == "'" and index and text[index - 1].isalnum():
            result.append(opening)
            index += 1
            continue
        end = text.find(_QUOTE_OPEN[opening], index + 1)
        if end < 0:
            return None, None
        value = text[index + 1:end]
        if not value or len(value) > _MAX_SELECTOR or any(c in value for c in '\n\r\\`'):
            return None, None
        token = _TOKEN_OPEN + str(len(literals)) + _TOKEN_CLOSE
        literals[token] = value
        result.append(token)
        index = end + 1
    return ''.join(result), literals


def _syntax_spaces(text):
    """Linear syntax-only whitespace collapse with exact source spans.

    Adjacent optional whitespace in the grammar must not backtrack over long
    input runs.  Object selectors are later restored from these original spans;
    their identity is never matched against this normalized representation.
    """
    normalized, spans = [], []
    index = 0
    while index < len(text):
        start = index
        if text[index].isspace():
            index += 1
            while index < len(text) and text[index].isspace():
                index += 1
            normalized.append(' ')
        else:
            normalized.append(text[index])
            index += 1
        spans.append((start, index))
    return ''.join(normalized), spans


def _selectors(text):
    protected, literals = _quote_tokens(text)
    if protected is None:
        return None, 'malformed_quoted_selector'
    # Only a complete measurement request with optional explicitly read-only
    # trailing clauses is accepted.  Examples, conditions and extra tasks do
    # not get erased until an apparently executable fragment remains.
    protected = protected.strip().rstrip('。.!！?？').strip()
    clauses = [part.strip() for part in re.split('[，,；;。\n\r]', protected)]
    if not clauses or not clauses[0] or any(not clause for clause in clauses):
        return None, 'unsupported_request_grammar'
    normalized, spans = _syntax_spaces(clauses[0])
    if _DISCOURSE.search(normalized):
        return None, 'conditional_negated_or_discussed_request'
    if any(not (_CN_READ_ONLY.fullmatch(clause) or _EN_READ_ONLY.fullmatch(clause))
           for clause in clauses[1:]):
        return None, 'additional_or_unsupported_clause'
    match = _CN_REQUEST.fullmatch(normalized)
    if match:
        separators = list(re.finditer('[与和]', match.group('pair')))
    else:
        match = _EN_REQUEST.fullmatch(normalized)
        if not match:
            return None, 'unsupported_request_grammar'
        separators = list(re.finditer(r'\s+and\s+', match.group('pair'), flags=re.IGNORECASE))
    if len(separators) != 1:
        return None, 'exactly_two_selectors_required'
    start, end = match.span('pair')
    separator = separators[0]
    intervals = [(start, start + separator.start()), (start + separator.end(), end)]
    selectors = []
    for left, right in intervals:
        # Recover selectors, including their original internal whitespace.  A
        # name "Base  A" must never turn into a different object's "Base A".
        part = clauses[0][spans[left][0]:spans[right - 1][1]].strip() if left < right else ''
        if not part or len(part) > _MAX_SELECTOR:
            return None, 'selector_size_or_missing'
        if part in literals:
            selectors.append((literals[part], True))
        elif _TOKEN_OPEN in part or _TOKEN_CLOSE in part:
            return None, 'unsupported_qualified_selector'
        else:
            selectors.append((part, False))
    return selectors, None


def _color_selector(value):
    match = _CN_COLOR.fullmatch(value) or _EN_COLOR.fullmatch(value)
    if match is None:
        return None
    return _COLORS[match.group(1).lower()], match.group(2)


def _color_class(rgb, color):
    """Return strong, boundary, absent, or invalid under an explicit RGB rule."""
    if (not isinstance(rgb, (list, tuple)) or len(rgb) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in rgb)):
        return 'invalid'
    r, g, b = rgb
    if color == 'blue':
        if b >= 128 and b - max(r, g) >= 64 and b - r >= 96:
            return 'strong'
        if b >= 80 and b - max(r, g) >= 24 and b - r >= 48:
            return 'boundary'
    elif color == 'gray':
        spread, mean = max(rgb) - min(rgb), sum(rgb) / 3
        if spread <= 24 and 64 <= mean <= 192:
            return 'strong'
        if spread <= 48 and 32 <= mean <= 224:
            return 'boundary'
    return 'absent'


def _resolve(meshes, selector, literal):
    if not literal and re.fullmatch(r'[AB]|R[0-9A-Fa-f]{4,8}', selector):
        return None, 'display_alias_requires_quoted_current_name', None
    # Namespace collisions are ambiguous even if one field normally has higher
    # priority.  Never let a name that happens to equal somebody else's ID bind
    # to a different object silently.
    exact = [(mesh, field) for field in ('object_id', 'name', 'mark_label')
             for mesh in meshes if mesh.get(field) == selector]
    exact_ids = {mesh['object_id'] for mesh, _ in exact}
    if len(exact_ids) > 1:
        return None, 'ambiguous_exact_selector', None
    color = None if literal else _color_selector(selector)
    if exact and color is None:
        mesh, field = exact[0]
        return mesh['object_id'], None, {'match_kind': field, 'selector': selector,
                                       'quoted_literal': literal, 'object_id': mesh['object_id']}
    if color is None:
        return None, 'selector_not_found_or_unsupported', None
    color_name, noun = color
    classes = [(mesh, _color_class(mesh.get('color_rgb'), color_name)) for mesh in meshes]
    if any(state == 'invalid' for _, state in classes):
        return None, 'color_inventory_incomplete', None
    strong = [mesh for mesh, state in classes if state == 'strong']
    boundary = [mesh for mesh, state in classes if state == 'boundary']
    if boundary:
        return None, 'color_boundary_ambiguous', None
    if len(strong) != 1:
        return None, 'color_not_unique' if strong else 'color_not_found', None
    mesh = strong[0]
    if exact_ids and exact_ids != {mesh['object_id']}:
        return None, 'selector_name_color_conflict', None
    return mesh['object_id'], None, {
        'match_kind': 'host_color_rgb', 'selector': selector, 'object_id': mesh['object_id'],
        'color_category': color_name, 'actual_rgb': list(mesh['color_rgb']),
        'color_policy': 'separated_integer_rgb_categories_v1',
        'color_scope': 'host_object_display_color_not_material_or_rendered_appearance',
        'generic_object_noun': noun, 'semantic_object_class_certified': False,
        'unique_among_current_mesh_count': len(meshes),
    }


def resolve_prompt_pair(scene, task_instruction, *, scene_fingerprint=None):
    """Resolve two explicitly described current objects, or report no binding.

    First textual selector is the focal object and the second is the reference.
    This order applies only to symmetric pair inspection and is not a transform
    role.  Unknown words/attributes, ambiguous names/colors and stale display
    aliases are not guessed.  No previous observation or active selection is
    consulted.  Color nouns are restricted to object/mesh: type claims such as
    part/base are not silently treated as generic object words.
    """
    if not isinstance(task_instruction, str):
        return _result(scene, scene_fingerprint, 'unresolved', 'instruction_must_be_text')
    if not task_instruction.strip():
        return _result(scene, scene_fingerprint, 'not_applicable', 'empty_instruction')
    if len(task_instruction) > _MAX_TEXT:
        return _result(scene, scene_fingerprint, 'unresolved', 'instruction_budget_exceeded')
    if (any(char in task_instruction for char in (_TOKEN_OPEN, _TOKEN_CLOSE, '`', '\x00'))
            or '~~~' in task_instruction or re.search(r'(?m)^\s*>', task_instruction)):
        return _result(scene, scene_fingerprint, 'unresolved', 'code_or_quoted_instruction')
    meshes = scene.get('meshes') if isinstance(scene, dict) else None
    if (not isinstance(meshes, list) or not 0 < len(meshes) <= _MAX_MESHES
            or any(not isinstance(mesh, dict) or not isinstance(mesh.get('object_id'), str)
                   or not mesh['object_id'] or not isinstance(mesh.get('name'), str) for mesh in meshes)
            or len({mesh['object_id'] for mesh in meshes}) != len(meshes)):
        return _result(scene, scene_fingerprint, 'unresolved', 'invalid_or_over_budget_inventory')
    selectors, error = _selectors(task_instruction)
    if error:
        return _result(scene, scene_fingerprint, 'unresolved', error)
    ids, evidence = [], []
    for selector, literal in selectors:
        object_id, error, proof = _resolve(meshes, selector, literal)
        if error:
            return _result(scene, scene_fingerprint, 'unresolved', error)
        ids.append(object_id)
        evidence.append(proof)
    if ids[0] == ids[1]:
        return _result(scene, scene_fingerprint, 'unresolved', 'same_object_selected_twice')
    return _result(scene, scene_fingerprint, 'resolved', 'two_current_objects_uniquely_resolved',
                   focal=ids[0], reference=ids[1], evidence=evidence)


__all__ = ['POLICY_REVISION', 'resolve_prompt_pair']
