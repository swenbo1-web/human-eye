"""Trusted public semantics for the six unchanged visual004 tasks.

This stdlib-only module has no asset/truth/product imports or file access.
Digests bind a public supplement; only exact reconstruction from the trusted
public task validates its semantics. A self-rehashed edit is never authority.
Unknown/null is handled by the answer status protocol, not value aliases here.
"""
from __future__ import annotations
import copy,hashlib,json,math

SCHEMA='visual004-public-semantics-v1'
VERSION='004A-R1'
_PUBLIC_FIELDS={'schema','case_id','question','required_roles','required_fact_ids','units','world_axes',
    'identity','numerical_evidence','scope','answer_requirements'}
_REQUIRED_PUBLIC_FIELDS={'schema','case_id','question','required_roles','required_fact_ids'}
_ROLE_TEXT={
    'V01':dict(target='The cyan L-shaped piece described in the question.',
        reference='The orange U-shaped frame described in the question.',
        occluder='The gray frontal panel described in the question.'),
    'V02':dict(target='The purple triangular wedge described in the question.',
        reference='The yellow notched upright described in the question.',
        occluder='The gray occluding strip described in the question.'),
    'V03':dict(target='The red short pin to identify using the question\'s spatial context near the blue collar; do not infer its containment or contact class from this role.',
        reference='The blue annular collar described in the question.'),
    'V04':dict(target='The white octagonal post described in the question.',
        reference='The green U-shaped bracket described in the question.'),
    'V05':dict(target='The orange triangular wedge described in the question.',
        reference='The purple octagonal post described in the question.',
        third='The cyan sloping beam described in the question.'),
    'V06':dict(target='The orange hexagonal core described in the question.',
        reference='The dark opaque shell described in the question.')}


def _definition(kind,value_type,domain,description,*,unit=None,predicate=None,direction_semantics=None):
    return dict(kind=kind,value_type=value_type,domain=domain,unit=unit,predicate=predicate,
        direction_semantics=direction_semantics,description=description)


def _number(kind,description,minimum=None):
    return _definition(kind,'number',dict(finite=True,minimum=minimum,maximum=None,booleans_allowed=False),description,unit='m')


_DEFINITIONS={
    'separation_class':_definition('separation_class','enum',['separated','contact','penetration'],
        'Classify the target and reference solids. separated: positive empty clearance; contact: boundaries touch without interior overlap; penetration: their material interiors overlap. Use these exact case-sensitive strings.'),
    'minimum_surface_distance_m':_number('minimum_surface_distance_m',
        'Minimum Euclidean distance between target and reference material boundary surfaces, in metres. Surface intersection has distance zero; distance zero alone does not distinguish contact from penetration.',0),
    'target_to_reference_world_axis':_definition('target_to_reference_world_axis','enum',['+X','-X','+Y','-Y','+Z','-Z'],
        'World-axis direction from the nearest target surface toward the corresponding reference surface. It is not the direction of target center minus reference center.',
        direction_semantics='nearest target surface -> nearest reference surface, right-handed world XYZ; +Z is up, not screen up'),
    'closest_local_region':_definition('closest_local_region','text',dict(min_length=1,max_length=4096,nonblank=True,nul_allowed=False),
        'Describe the closest local feature or surface on the identified target and corresponding reference surface. Any bounded nonempty description is syntactically allowed; correctness and evidence sufficiency require the fixed independent reference and blind review, not automatic full credit.'),
    'pin_location_relative_to_hole':_definition('pin_location_relative_to_hole','enum',
        ['inside_hole_without_contact','inside_hole_contact','intersects_ring_material','outside_hole'],
        'Classify the pin relative to the collar: inside_hole_without_contact means fully within the hole with positive clearance; inside_hole_contact means in the hole with boundary contact and no material penetration; intersects_ring_material means pin material overlaps ring material; outside_hole means not in the hole and not intersecting ring material. The ambiguous string inside_hole is invalid; there are no aliases.'),
    'opposite_side_clearance_m':_number('opposite_side_clearance_m',
        'Signed local normal clearance on the side opposite the nearest reported target-to-reference direction, in metres. Positive means a gap, zero means boundary contact, and negative means overlap along that normal; normal overlap alone is not a complete 3D penetration test.'),
    'aabb_center_direction_xyz':_definition('aabb_center_direction_xyz','axis_vector',
        [['+X','-X','0'],['+Y','-Y','0'],['+Z','-Z','0']],
        'A three-element array in X,Y,Z order describing the signs of target full-geometry AABB center minus reference full-geometry AABB center. The string 0 means equal coordinates on that axis; it is not a numerical tolerance or an unknown value.',
        direction_semantics='target AABB center - reference AABB center; array slots exactly X,Y,Z; equality uses string "0"'),
    'vertical_clearance_m':_number('vertical_clearance_m',
        'Signed world-Z interval clearance min_Z(third) - max_Z(target), in metres. Positive means disjoint vertical intervals; negative means vertical interval overlap. This scalar is not automatically the shortest three-dimensional surface distance or a contact test.'),
    'vertical_is_not_minimum_3d_distance':_definition('vertical_is_not_minimum_3d_distance','boolean',[False,True],
        'Evaluate the named inequality predicate for the requested vertical quantity and the full 3D geometry; both boolean values are allowed.',
        predicate=dict(true_means='The requested vertical clearance is not equal to the minimum three-dimensional target-to-third surface distance.',
            false_means='The requested vertical clearance equals that minimum three-dimensional target-to-third surface distance.')),
    'internal_surface_not_visible_from_external_opaque_view':_definition('internal_surface_not_visible_from_external_opaque_view','boolean',[False,True],
        'Evaluate non-visibility of the internal target and inner reference surfaces from the specified external opaque view. This does not determine what complete mesh geometry can measure.',
        predicate=dict(true_means='The internal target and inner reference surfaces are NOT visible from the specified external opaque view.',
            false_means='That internal-surface non-visibility predicate does NOT hold. This is not an ordinary visibility=false answer.'))}
_FACT_KINDS={
    'relation':'separation_class','minimum_gap_m':'minimum_surface_distance_m','direction':'target_to_reference_world_axis',
    'closest_region':'closest_local_region','containment':'pin_location_relative_to_hole',
    'opposite_gap_m':'opposite_side_clearance_m','centroid_direction':'aabb_center_direction_xyz',
    'vertical_clearance_m':'vertical_clearance_m','vertical_is_not_euclidean':'vertical_is_not_minimum_3d_distance',
    'visual_visibility':'internal_surface_not_visible_from_external_opaque_view'}
_CASE_FACTS={
    'V01':('relation','minimum_gap_m','direction','closest_region'),
    'V02':('relation','minimum_gap_m','direction','closest_region'),
    'V03':('containment','relation','minimum_gap_m','direction'),
    'V04':('relation','minimum_gap_m','direction','opposite_gap_m'),
    'V05':('centroid_direction','vertical_clearance_m','vertical_is_not_euclidean'),
    'V06':('relation','minimum_gap_m','direction','visual_visibility')}


def _need(value,reason):
    if not value:raise ValueError('visual004_contract_'+reason)


def _canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError) as exc:
        raise ValueError('visual004_contract_noncanonical_value') from exc


def _text(value,maximum=4096):return type(value) is str and 0<len(value)<=maximum and bool(value.strip()) and '\x00' not in value


def _requested(value,allowed,reason):
    _need(type(value) is list and value and all(type(item) is str for item in value),reason)
    _need(len(value)==len(set(value)) and set(value)<=set(allowed),reason)
    return value


def public_supplement(public_task):
    """Derive generic case semantics from a trusted public task, not its truth.

    Authored portable task subsets are accepted; matching a real task's frozen
    digest remains the caller's separate responsibility. No exact original
    question, source object names, numbers, views or support results are read.
    """
    _need(type(public_task) is dict and _REQUIRED_PUBLIC_FIELDS<=set(public_task)<=_PUBLIC_FIELDS,'public_task_fields')
    _need(public_task['schema']=='visual004-public-task-v1','public_task_schema')
    case=public_task['case_id'];_need(type(case) is str and case in _ROLE_TEXT,'case_id')
    _need(_text(public_task['question'],16384),'public_question')
    roles=_requested(public_task['required_roles'],_ROLE_TEXT[case],'requested_roles')
    facts=_requested(public_task['required_fact_ids'],_CASE_FACTS[case],'requested_fact_ids')
    if 'units' in public_task:_need(public_task['units'] in ('metres','m'),'public_units')
    for field in ('world_axes','identity','numerical_evidence','scope'):
        if field in public_task:_need(_text(public_task[field],16384),'public_'+field)
    if 'answer_requirements' in public_task:
        value=public_task['answer_requirements']
        _need(type(value) is list and len(value)<=32 and all(_text(row) for row in value),'public_answer_requirements')
    return dict(schema=SCHEMA,version=VERSION,case_id=case,task_sha256=hashlib.sha256(_canonical(public_task)).hexdigest(),
        roles={role:_ROLE_TEXT[case][role] for role in roles},
        facts={fact:copy.deepcopy(_DEFINITIONS[_FACT_KINDS[fact]]) for fact in facts})


def supplement_sha256(supplement):
    """Byte digest only, not semantic validation or source admission."""
    _need(type(supplement) is dict,'supplement_type')
    return hashlib.sha256(_canonical(supplement)).hexdigest()


def validate_supplement(supplement,public_task,expected_sha256):
    """Reject a wrong template even if its attacker-controlled hash is self-consistent."""
    _need(type(expected_sha256) is str and len(expected_sha256)==64
        and all(char in '0123456789abcdef' for char in expected_sha256),'expected_digest')
    trusted=public_supplement(public_task)
    _need(type(supplement) is dict and _canonical(supplement)==_canonical(trusted),'template_mismatch')
    _need(supplement_sha256(supplement)==expected_sha256,'supplement_digest_binding')
    return copy.deepcopy(trusted)


def normalize_value(value,fact_definition):
    """Validate one known-status value using an exact trusted public definition.

    There are no enum aliases, string-to-number coercions, bool-to-number
    coercions or unknown/null fallbacks. Region prose stays prose for blind
    review; this function only validates its syntax. Scalars normalize to float.
    """
    _need(type(fact_definition) is dict and type(fact_definition.get('kind')) is str,'fact_definition')
    kind=fact_definition['kind'];_need(kind in _DEFINITIONS,'unknown_kind')
    definition=_DEFINITIONS[kind]
    _need(_canonical(fact_definition)==_canonical(definition),'fact_definition_mismatch')
    value_type=definition['value_type'];domain=definition['domain']
    if value_type=='enum':
        _need(type(value) is str and value in domain,'enum_value');return value
    if value_type=='boolean':
        _need(type(value) is bool,'boolean_value');return value
    if value_type=='axis_vector':
        _need(type(value) is list and len(value)==3 and all(type(item) is str and item in domain[index]
            for index,item in enumerate(value)),'axis_vector_value');return value[:]
    if value_type=='number':
        _need(type(value) in (int,float),'number_value')
        try:number=float(value)
        except (ValueError,TypeError,OverflowError) as exc:raise ValueError('visual004_contract_number_value') from exc
        _need(math.isfinite(number) and (domain['minimum'] is None or number>=domain['minimum'])
            and (domain['maximum'] is None or number<=domain['maximum']),'number_value')
        return 0. if number==0 else number
    _need(value_type=='text' and _text(value,domain['max_length']),'text_value')
    return value
