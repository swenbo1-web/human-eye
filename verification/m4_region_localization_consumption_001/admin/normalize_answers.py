"""Normalize this fixed batch's quoted consumer facts without reading costs.

This script reads only public final answers, matched original tool responses,
and P3's explicitly cited current-session JSON. It imports no product modules.
It retains native surface identities and never uses administrator target maps
to fill a missing answer. Entailment remains subject to independent review.
"""
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_loc_001/formal')
ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
INPUTS = {}


def read_raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def excerpt_line(text, marker):
    lines = [line for line in text.splitlines() if marker in line]
    if len(lines) != 1:
        raise ValueError('unique_final_excerpt_required:'+marker)
    return lines[0]


class Slot:
    def __init__(self, name):
        self.name = name
        self.owner = RUNTIME/name/'o'
        self.final_path = RUNTIME/name/'c/PUBLIC_FINAL.txt'
        answer = read_raw(self.final_path)
        self.final = answer.decode('utf8')
        self.row = dict(slot_id=name, raw_answer_path=str(self.final_path.resolve()),
            raw_answer_sha256=hashlib.sha256(answer).hexdigest(), sources=[], panels=[], unsupported=[], questions={},
            finite_pool_scope_correct=True, global_invisibility_overclaim=False)
        self.tools = {}
        self.sources = {}

    def tool(self, number):
        identifier = 'tool_'+str(number).zfill(2)
        if identifier not in self.tools:
            path = self.owner/identifier/'RESPONSE.json'
            value = json.loads(read_raw(path))
            text = '\n'.join(block['text'] for block in value['result']['content'] if block.get('type') == 'text')
            try:
                parsed = json.loads(text)
                stdout = parsed.get('stdout', '') if type(parsed) is dict else ''
            except ValueError:
                stdout = ''
            self.tools[identifier] = (text, stdout)
            self.row['sources'].append(dict(id=identifier, kind='tool_result', path=str(path.resolve()),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            self.sources[identifier] = text
        return identifier, *self.tools[identifier]

    def row_support(self, identifier, row, body):
        compact = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
        escaped = json.dumps(compact, ensure_ascii=False)[1:-1]
        for candidate in (escaped, compact):
            if candidate in body:
                return dict(source_id=identifier, excerpt=candidate)
        raise ValueError('exact_table_row_excerpt_not_found:'+self.name)

    def add_panel(self, identity, status, view, reference, support, reason=''):
        row = dict(identity=identity, status='covered' if status == 'observed' else 'unknown',
                   views=[dict(view=view, ref=reference)] if status == 'observed' else [], support=support)
        if status != 'observed':
            row['reason_code'] = ('back_facing_all_views' if 'back' in reason.lower()
                                  else 'positive_area_occlusion_all_front_views' if 'occlu' in reason.lower()
                                  else 'finite_pool_no_complete_readable_view')
            row['original_reason'] = reason
        self.row['panels'].append(row)

    def table(self, number, layout):
        identifier, body, stdout = self.tool(number)
        if layout == 'N2':
            table = json.loads(stdout)['rows']
        else:
            start = stdout.index('[[')
            table, end = json.JSONDecoder().raw_decode(stdout, start)
        for native in table:
            support = self.row_support(identifier, native, body)
            if layout == 'N1':
                identity = {'source_triangle_indices': [index for first, last in native[1] for index in range(first, last+1)]}
                status, view_offset = native[2], 3
            elif layout in ('N2', 'P1'):
                interval = native[1]
                if interval[0] == 'inclusive':
                    first, last = interval[1:]
                else:
                    first, last = interval
                identity = {'source_triangle_indices': list(range(first, last+1))}
                status, view_offset = native[2], 3
            elif layout == 'P2':
                identity = {'source_triangle_indices': list(range(native[1], native[2]+1))}
                status, view_offset = native[3], 4
            elif layout == 'N3':
                source = native[1]
                identity = ({'source_triangle_indices': source['triangles']} if 'triangles' in source
                            else {'quad_world_m': source['corners']})
                status, view_offset = native[2], 3
            else:
                raise ValueError('fixed_table_layout')
            if status == 'observed':
                self.add_panel(identity, status, native[view_offset], native[view_offset+1], support)
            else:
                reason = native[view_offset] if len(native) > view_offset else status
                if type(reason) is not str:
                    reason = status
                if status == 'remaining-B':
                    reason = 'back-facing in every camera'
                elif status == 'remaining-O':
                    reason = 'occluded in every camera'
                self.add_panel(identity, status, None, None, support, reason)
        return stdout

    def cited_artifact(self):
        citation = excerpt_line(self.final, 'scene_inspection.json')
        path = self.owner/'scratch/scene_inspection.json'
        data = read_raw(path)
        body = data.decode('utf8')
        self.row['sources'].append(dict(id='artifact', kind='cited_artifact', path=str(path.resolve()),
            sha256=hashlib.sha256(data).hexdigest(), final_citation_excerpt=citation))
        value = json.loads(body)
        for native in value['surfaces']:
            needle = '"surface_id": '+str(native['surface_id'])+','
            excerpt = None
            for match in re.finditer(re.escape(needle), body):
                start = body.rfind('{', 0, match.start())
                parsed, end = json.JSONDecoder().raw_decode(body, start)
                if parsed == native:
                    excerpt = body[start:end]
                    break
            if excerpt is None:
                raise ValueError('cited_surface_span')
            support = dict(source_id='artifact', excerpt=excerpt)
            views = native['readable_views']
            if native['status'] == 'observed':
                # The original artifact asserts every readable view. Retain all.
                panel = dict(identity={'source_triangle_indices': native['source_triangle_indices']},
                    status='covered', views=[dict(view=view, ref=native['evidence_by_view'][view]['image_ref']) for view in views],
                    support=support)
                self.row['panels'].append(panel)
            else:
                self.add_panel({'source_triangle_indices': native['source_triangle_indices']}, 'remaining',
                    None, None, support, native['reason'])
        return body, value

    def positions(self):
        click = excerpt_line(self.final, '1.')
        origin = excerpt_line(self.final, '2.')
        bottom = excerpt_line(self.final, '3.')
        center = [0.15625, -0.15625, 0.11865234375]
        # All six finals explicitly state this center, +Z, and the full X/Y
        # width 0.0703125. Center +/- half-width is an exact representation of
        # their stated extent, with no administrator geometry substituted.
        self.row['questions']['click'] = dict(identity={'center_world_m': center, 'front_direction_world': [0, 0, 1]},
            center_world_m=center, front_direction_world=[0, 0, 1],
            half_edge_u_world_m=[0.03515625, 0, 0], half_edge_v_world_m=[0, 0.03515625, 0],
            view='SCENE', ref='image-01', support={'source_id': 'final', 'excerpt': click})
        pixel = [327, 415] if self.name in ('P1', 'P2') else [327, 427]
        if str(pixel).replace(' ', '') not in origin.replace(' ', ''):
            raise ValueError('origin_pixel_not_in_final:'+self.name)
        self.row['questions']['origin'] = dict(identity={'center_world_m': [0, 0, 0], 'front_direction_world': [0, 0, 1]},
            SCENE_visible_pixels=0, SCENE_front_facing=True, SCENE_occluded=True,
            witness={'view': 'LEFT', 'ref': 'image-03', 'pixel_xy': pixel},
            support={'source_id': 'final', 'excerpt': origin})
        self.row['questions']['bottom'] = dict(
            identity={'center_world_m': [0.15625, -0.15625, 0.11572265625], 'front_direction_world': [0, 0, -1]},
            finite_pool_no_front_readable=True, finite_pool_only=True, global_invisibility_claim=False,
            support=[{'source_id': 'final', 'excerpt': bottom}, {'source_id': 'final', 'excerpt': self.final.splitlines()[-1]}])

    def unsupported(self, source=None):
        final = excerpt_line(self.final, '48')
        supports = [{'source_id': 'final', 'excerpt': final}]
        if source is not None:
            supports.append(source)
        self.row['unsupported'] = [dict(component_count=1, source_triangle_indices=[48], status='unsupported',
            shape='nonrectangular', domain='outside_supported_rectangle_domain', support=supports)]


def main():
    output, notes = [], []
    for name in ORDER:
        slot = Slot(name)
        if name == 'N1':
            slot.table(8, 'N1')
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'VERIFIABLE_COVERAGE_ROWS')
            slot.unsupported()
        elif name == 'P1':
            slot.table(7, 'P1')
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'COMPLETE COVERAGE TABLE')
            slot.unsupported()
        elif name == 'P2':
            stdout = slot.table(8, 'P2')
            correction_id, correction_body, _ = slot.tool(9)
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'COMPLETE COVERAGE TABLE')
            slot.unsupported({'source_id': 'tool_08', 'excerpt': slot.sources['tool_08']})
            notes.append(dict(slot_id=name, issue='One intermediate prose range for surface 93 was incorrect.',
                retained_original=stdout[stdout.index('Remaining surface 93'):],
                correction={'source_id': correction_id, 'excerpt': correction_body},
                disposition='The table has the correct native range. A subsequent current tool fact explicitly corrects the prose. Final does not repeat the incorrect range.'))
        elif name == 'N2':
            slot.table(8, 'N2')
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'complete-coverage-rows')
            identifier, body, _ = slot.tool(6)
            slot.unsupported({'source_id': identifier, 'excerpt': body})
        elif name == 'N3':
            slot.table(8, 'N3')
            slot.table(9, 'N3')
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'VERIFIABLE_COVERAGE_ROWS_PART_1')
            slot.unsupported({'source_id': 'tool_09', 'excerpt': slot.sources['tool_09']})
        else:
            body, artifact = slot.cited_artifact()
            slot.row['coverage_use_excerpt'] = excerpt_line(slot.final, 'Full evidence:')
            token = '"unsupported_remainder"'
            start = body.index(token)
            end = body.index('"limitations"', start)
            slot.unsupported({'source_id': 'artifact', 'excerpt': body[start:end]})
        slot.positions()
        if len(slot.row['panels']) != 138:
            raise ValueError('parsed_full_table_row_count:'+name)
        output.append(slot.row)
        notes.append(dict(slot_id=name, parsed_panels=len(slot.row['panels']),
            covered=sum(panel['status'] == 'covered' for panel in slot.row['panels']),
            remaining=sum(panel['status'] != 'covered' for panel in slot.row['panels']),
            scope_excerpt=slot.final.splitlines()[-1],
            extent_derivation='Exact half of the final stated full width 0.0703125 in X and Y.',
            raw_answer_sha256=slot.row['raw_answer_sha256']))
    save(HERE/'NORMALIZED.json', dict(schema='region-localization-normalized-v1',
        scoring_role='Independent administrator normalization before cost analysis', slots=output))
    save(HERE/'NORMALIZATION_REVIEW_NOTES.json', dict(schema='region-localization-normalization-review-v1',
        notes=notes, inputs_sha256=INPUTS, cost_analysis_performed=False,
        limitations=['Raw excerpts and source claims require independent entailment review.',
            'N2 and N3 say classification has no unknowns while explicitly retaining 23 unobserved supported surfaces. They do not claim all supported surfaces were observed.',
            'No task values were filled from administrator target maps. All final numeric location values are explicit, with full width exactly converted to half-edge vectors.']))
    print(json.dumps({'normalized_slots': len(output), 'cost_analysis_performed': False}))


if __name__ == '__main__':
    main()
