"""Offline quality-contract regression aid. Formal free-text judgment is manual.

The packer never imports this module. Unparsed presentation remains available
to an independent reviewer alongside the exact original answer and evidence.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re


TOLERANCE_MM = Fraction('0.000500001')
UNIT_TO_MM = {'mm': Fraction(1), '毫米': Fraction(1), 'm': Fraction(1000),
              '米': Fraction(1000), 'cm': Fraction(10), '厘米': Fraction(10),
              'um': Fraction(1,1000), 'µm': Fraction(1,1000), '微米': Fraction(1,1000)}
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
LABEL = re.compile(r'blender:[0-9a-f]{64}|\bobj[_\s-]*0*\d+\b', re.I)
DISTANCE = re.compile(r'(?P<value>'+NUMBER+r')\s*(?P<unit>毫米|厘米|微米|mm|cm|µm|um|米|m)?',re.I)


def namespace(snapshot):
    names = {obj['name'] for obj in snapshot['objects']}
    aliases = {name.casefold():name for name in names}
    for name in names:
        payload = json.dumps(['',name],ensure_ascii=False,separators=(',',':')).encode()
        aliases['blender:'+hashlib.sha256(payload).hexdigest()] = name
        numeric = re.fullmatch(r'Obj_(\d+)',name)
        if numeric:
            aliases['obj'+str(int(numeric[1]))] = name
    return aliases


def resolve(label, aliases):
    if isinstance(label,dict):
        label = label.get('name',label.get('id'))
    if not isinstance(label,str):
        return None
    exact = label.strip().strip('`"\'').casefold()
    if exact in aliases:
        return aliases[exact]
    numeric = re.fullmatch(r'obj[_\s-]*0*(\d+)',exact)
    return aliases.get('obj'+str(int(numeric[1]))) if numeric else None


def distance_valid_mm(value, exact_squared_m2):
    """Compare the stated rounding interval with the exact squared oracle."""
    value = Fraction(str(value))
    if value < 0:
        return False
    lower = max(Fraction(0),value-TOLERANCE_MM)/1000
    upper = (value+TOLERANCE_MM)/1000
    exact = Fraction(int(exact_squared_m2['numerator']),int(exact_squared_m2['denominator']))
    return lower*lower <= exact <= upper*upper


def presentation_met(value, unit, exact_squared_m2):
    if unit not in ('mm','毫米'):
        return False
    try:
        stated = Decimal(str(value))
    except InvalidOperation:
        return False
    if not stated.is_finite():
        return False
    if stated.is_zero() and int(exact_squared_m2['numerator']) == 0:
        return True
    return stated.as_tuple().exponent <= -3


def completeness(text, document=None):
    if isinstance(document,dict):
        if type(document.get('complete')) is bool:
            return 'complete' if document['complete'] else 'incomplete'
        status = document.get('status')
        if status == 'complete':
            return 'complete'
        if status in ('incomplete','partial','unknown'):
            return 'incomplete'
    negative = re.search(r'不完整|未完成|(?:无法|不能|未能).{0,12}(?:完整|查全|全部)|'
        r'尚未.{0,12}(?:全部|全场)|\bincomplete\b|\bnot\s+complete\b|'
        r'\b(?:cannot|unable to)\s+(?:confirm|determine).{0,20}complete',text,re.I)
    positive = re.search(r'检查完整|完整检查|已查全|已完成(?:检查|扫描)|'
        r'完整性\s*[:：=]?\s*(?:完整|是|已完成)|'
        r'\b(?:check|scan|inspection)\s+(?:(?:is|was)\s+)?complete\b|'
        r'\bcomplete(?:ness)?\s*[:=]\s*(?:true|yes)\b',text,re.I)
    if negative and positive:
        return 'ambiguous'
    return 'incomplete' if negative else 'complete' if positive else 'not_stated'


def extract_answer(text, snapshot):
    """Extract common explicit rows without requiring them from consumers."""
    aliases = namespace(snapshot)
    claims,unparsed = [],[]
    document = None
    stripped = text.strip()
    candidates = [stripped] if stripped.startswith(('{','[')) else re.findall(r'```(?:json)?\s*([\s\S]*?)```',text,re.I)
    for candidate in candidates:
        try:
            document = json.loads(candidate,parse_float=Decimal)
        except (ValueError,TypeError):
            continue
        rows = document if isinstance(document,list) else next((document[key] for key in ('matches','pairs','results')
            if isinstance(document,dict) and isinstance(document.get(key),list)),None)
        if rows is None:
            continue
        default_unit = document.get('unit') if isinstance(document,dict) else None
        for index,row in enumerate(rows):
            if not isinstance(row,dict):
                unparsed.append(dict(row=index,reason='structured_row_needs_review'))
                continue
            objects = row.get('objects',row.get('pair'))
            if objects is None:
                objects = [row.get('object_a',row.get('a')),row.get('object_b',row.get('b'))]
            if not isinstance(objects,list) or len(objects) != 2:
                unparsed.append(dict(row=index,reason='pair_labels_need_review'))
                continue
            unit = row.get('unit',default_unit)
            value = row.get('distance')
            for field,field_unit in (('distance_mm','mm'),('distance_m','m')):
                if field in row:
                    value,unit = row[field],field_unit
                    break
            if isinstance(value,Decimal):
                value = str(value)
            claims.append(dict(labels=objects,value=value,unit=unit,
                kind='nonmatch' if row.get('matches_threshold') is False else 'match',source_row=index))
        return dict(claims=claims,unparsed=unparsed,
                    completeness=completeness(text,document),aliases=aliases)
    default_unit = None
    if re.search(r'(?:距离|distance)[^\n]{0,24}(?:\(mm\)|（mm）|\[mm\]|单位\s*[:：]?\s*毫米|单位\s*[:：]?\s*mm)',text,re.I):
        default_unit = 'mm'
    for line_number,line in enumerate(text.splitlines(),1):
        found = list(LABEL.finditer(line))
        if len(found) != 2:
            if len(found) > 2:
                unparsed.append(dict(line=line_number,reason='multi_pair_or_explanatory_line_needs_review'))
            continue
        tail = line[found[-1].end():]
        number = DISTANCE.search(tail)
        if number is None or re.search(r'[<>≤≥]',tail[:number.start()]):
            unparsed.append(dict(line=line_number,reason='distance_needs_review'))
            continue
        claims.append(dict(labels=[item.group() for item in found],value=number['value'],
            unit=number['unit'] or default_unit,kind='match',source_line=line_number))
    return dict(claims=claims,unparsed=unparsed,completeness=completeness(text),aliases=aliases)


def assess_claims(claims, coverage, truth, snapshot, *, unparsed=(), additional_errors=()):
    aliases = namespace(snapshot)
    expected = {tuple(sorted((row['object_a'],row['object_b']))):row for row in truth['pairs']}
    matching = {pair for pair,row in expected.items() if row['matches_threshold']}
    assert len(expected) == len(truth['pairs']) == 276 and len(matching) == 71
    exact_threshold = Fraction(.002)**2
    for row in expected.values():
        value = row['exact_squared_distance_m2']
        assert row['matches_threshold'] == (Fraction(int(value['numerator']),int(value['denominator'])) <= exact_threshold)
    errors = list(additional_errors)
    unresolved = list(unparsed)
    seen = Counter()
    distance_correct = 0
    presentation_issues = []
    for ordinal,claim in enumerate(claims):
        labels = claim.get('labels')
        if not isinstance(labels,(list,tuple)) or len(labels) != 2:
            unresolved.append(dict(claim=ordinal,reason='pair_labels_need_review'))
            continue
        resolved = [resolve(label,aliases) for label in labels]
        if None in resolved or resolved[0] == resolved[1]:
            errors.append(dict(claim=ordinal,reason='unknown_or_invalid_scene_pair'))
            continue
        pair = tuple(sorted(resolved))
        row = expected[pair]
        is_match = claim.get('kind','match') == 'match'
        if not is_match:
            if row['matches_threshold']:
                errors.append(dict(pair=pair,reason='true_match_claimed_nonmatch'))
            continue
        seen[pair] += 1
        if not row['matches_threshold']:
            errors.append(dict(pair=pair,reason='false_positive_pair'))
        unit = claim.get('unit')
        unit = unit.casefold().strip() if isinstance(unit,str) else None
        if unit not in UNIT_TO_MM:
            unresolved.append(dict(pair=pair,reason='distance_unit_unresolved'))
            continue
        try:
            value = Fraction(str(claim.get('value')))*UNIT_TO_MM[unit]
        except (ValueError,ZeroDivisionError,OverflowError):
            unresolved.append(dict(pair=pair,reason='distance_value_unresolved'))
            continue
        if distance_valid_mm(value,row['exact_squared_distance_m2']):
            distance_correct += 1
        else:
            errors.append(dict(pair=pair,reason='wrong_shortest_surface_distance'))
        if not presentation_met(claim.get('value'),unit,row['exact_squared_distance_m2']):
            presentation_issues.append(dict(pair=pair,reason='presentation_incomplete'))
    duplicates = sorted(pair for pair,count in seen.items() if count > 1)
    if duplicates:
        errors.append(dict(reason='duplicate_pair_rows',pairs=duplicates))
    missed = sorted(matching-set(seen))
    if missed and coverage == 'complete':
        errors.append(dict(reason='claimed_complete_with_omissions',pairs=missed))
    status = ('incorrect' if errors else 'incomplete' if missed or unresolved or presentation_issues or coverage != 'complete'
              else 'complete_correct')
    return dict(status=status,claimed_pairs=len(seen),true_positive_pairs=len(set(seen)&matching),
        false_positive_pairs=len(set(seen)-matching),missing_pairs=missed,duplicates=duplicates,
        distance_correct_rows=distance_correct,completeness=coverage,errors=errors,
        presentation_issues=presentation_issues,
        review_required=bool(unresolved) or coverage == 'ambiguous',unresolved=unresolved,
        parser_scope='Regression aid; independent reviewers adjudicate equivalent free-form answers.')


def score_answer(text, truth, snapshot, *, additional_errors=()):
    if not isinstance(text,str) or not text.strip():
        return dict(status='execution_failure',reason='confirmed_final_answer_missing')
    extracted = extract_answer(text,snapshot)
    if extracted['unparsed'] or (not extracted['claims'] and extracted['completeness'] != 'incomplete'):
        return dict(status=None,review_required=True,reason='free_form_or_referenced_evidence_requires_review',
            extracted_claims=extracted['claims'],unparsed=extracted['unparsed'],
            completeness=extracted['completeness'])
    return assess_claims(extracted['claims'],extracted['completeness'],truth,snapshot,
                         unparsed=extracted['unparsed'],additional_errors=additional_errors)


def score_slots(sequence, records, truth, snapshot):
    """Synthetic six-slot binding checks; the formal pack does no scoring."""
    if len(sequence) != 6 or len({row['cell'] for row in sequence}) != 6:
        raise ValueError('expected_exactly_six_unique_planned_slots')
    if len(records) > 6 or len({row['cell'] for row in records}) != len(records):
        raise ValueError('duplicate_or_extra_result_row')
    expected = {row['cell']:row for row in sequence}
    for row in records:
        slot = expected.get(row['cell'])
        if slot is None or any(row.get(key) != slot.get(key) for key in ('task','round','group')):
            raise ValueError('result_row_not_bound_to_frozen_slot')
    by_cell = {row['cell']:row for row in records}
    result = []
    for slot in sequence:
        row = by_cell.get(slot['cell'])
        if row is None:
            result.append(dict(cell=slot['cell'],status='not_run'))
            continue
        answer = score_answer(row.get('final'),truth,snapshot)
        if row.get('execution_status') == 'failed':
            result.append(dict(cell=slot['cell'],status='execution_failure',partial_answer=answer))
        else:
            result.append(dict(cell=slot['cell'],**answer))
    return result
