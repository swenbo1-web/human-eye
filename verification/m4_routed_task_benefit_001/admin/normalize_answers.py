"""Source-bound normalization of the six actual routed-task finals.

Only current final answers, tool originals and a final-cited current artifact
are read. Administrator geometry truth is used by the frozen scorer later.
"""
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_routed_001/formal')
ORDER = ('N1','P1','P2','N2','N3','P3')
INPUTS, NOTES = {}, []


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_bytes()) == value:
            return
        raise FileExistsError('different_existing_normalization_artifact:'+str(path))
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def strip(value):
    if type(value) is dict:
        return {key:strip(item) for key,item in value.items()
                if not re.search(r'(^|_)(ns|ms|seconds|elapsed|duration|usage|tokens|cost|timing|metrics|stages|perf)(_|$)',key)}
    if type(value) is list:
        return [strip(item) for item in value]
    return value


def tabulate(value):
    if any(len(row) != len(value['columns']) for row in value['rows']):
        raise ValueError('source_table_column_count')
    return [dict(zip(value['columns'], row)) for row in value['rows']]


class Slot:
    def __init__(self, name):
        self.name = name
        self.owner = RUNTIME/name/'o'
        path = RUNTIME/name/'c/PUBLIC_FINAL.txt'
        answer = raw(path)
        self.final = answer.decode('utf8')
        self.row = dict(slot_id=name,raw_answer_path=str(path.resolve()),raw_answer_sha256=hashlib.sha256(answer).hexdigest(),
            sources=[],panels=[],unsupported=[],questions={},finite_pool_scope_correct=True,global_invisibility_overclaim=False)
        self.tools, self.used_sources, self.claims = {}, set(), []

    def tool(self, number, used=False):
        if number not in self.tools:
            folder = self.owner/('tool_'+str(number).zfill(2))
            request, response = read(folder/'REQUEST.json'), read(folder/'RESPONSE.json')
            texts = [block['text'] for block in response['result']['content'] if block.get('type')=='text']
            body = '\n'.join(texts)
            values = [json.loads(text) if text.startswith('{') else text for text in texts]
            value = next((v for v in values if type(v)is dict),{})
            self.tools[number] = dict(attempt=number,tool=request['params']['name'],arguments=request['params']['arguments'],
                is_error=response['result']['isError'],raw_text=body,value=value,public_text=[strip(v) for v in values],
                response_path=str((folder/'RESPONSE.json').resolve()),response_sha256=INPUTS[str((folder/'RESPONSE.json').resolve())])
        item = self.tools[number]
        if used and number not in self.used_sources:
            self.row['sources'].append(dict(id='tool_'+str(number).zfill(2),kind='tool_result',
                path=item['response_path'],sha256=item['response_sha256']))
            self.used_sources.add(number)
        return item

    def support(self, number, value, nested=True):
        item = self.tool(number,used=True)
        text = compact(value)
        if nested:
            text = json.dumps(text,ensure_ascii=False)[1:-1]
        if text not in item['raw_text']:
            raise ValueError('actual_row_excerpt:'+self.name+':'+str(number))
        return dict(source_id='tool_'+str(number).zfill(2),excerpt=text)

    def source_body_support(self,number):
        return dict(source_id='tool_'+str(number).zfill(2),excerpt=self.tool(number,used=True)['raw_text'])

    def final_line(self,marker):
        found=[line for line in self.final.splitlines() if marker in line]
        if len(found)!=1:
            raise ValueError('unique_final_line:'+self.name+':'+marker)
        return found[0]

    def add(self,identity,status,views,support,reason='',source_basis='native'):
        observed=status in ('observed','covered')
        row=dict(identity=identity,status='covered' if observed else 'unknown',views=views if observed else [],support=support)
        if not observed:
            row['reason_code']=('positive_area_occlusion_all_front_views' if 'occlu' in reason.lower()
                                else 'back_facing_all_views' if 'back' in reason.lower()
                                else 'finite_pool_no_complete_readable_view')
            row['original_reason']=reason
        self.row['panels'].append(row)
        self.claims.append(dict(identity=identity,status=row['status'],basis=source_basis,
            views=row['views'],reason=reason,source_ids=sorted({item['source_id'] for item in support})))

    def array(self,number,objects=False):
        text=self.tool(number,used=True)['value']['stdout']
        at=text.index('[{' if objects else '[[')
        return json.JSONDecoder().raw_decode(text,at)[0]

    def native(self):
        if self.name=='N1':
            for item in self.array(9):
                identity={'source_triangle_indices':[face for first,last in item[1] for face in range(first,last+1)]}
                views=[{'view':item[3],'ref':item[4]}] if item[2]=='observed' else []
                self.add(identity,item[2],views,[self.support(9,item)],item[3] if not views else '')
            self.row['coverage_use_excerpt']=self.final_line('COMPLETE COVERAGE TABLE')
            unsupported_source=self.source_body_support(4)
        elif self.name=='N2':
            for number in (11,12):
                for item in self.array(number):
                    identity={'source_triangle_indices':list(range(item[1][0],item[1][1]+1))}
                    evidence=item[3]
                    views=[{'view':evidence[0],'ref':evidence[1]}] if item[2]=='observed' else []
                    self.add(identity,item[2],views,[self.support(number,item)],evidence if not views else '')
            self.row['coverage_use_excerpt']=self.final_line('coverage_v1.rows')
            unsupported_source=self.source_body_support(4)
        else:
            latest={}
            for number in (8,9,10,11):
                for item in self.array(number,objects=True):
                    key=item['id']
                    if key in latest:
                        NOTES.append(dict(slot=self.name,repeated_id=key,previous_tool=latest[key][0],new_tool=number,
                            same_claim=latest[key][1]==item,previous=latest[key][1],current=item,
                            scope='Explicit current UNTRUNCATED restatement of existing target ID. Retained as one target claim.'))
                    latest[key]=(number,item)
            for key in sorted(latest):
                number,item=latest[key]
                identity={'source_triangle_indices':[face for first,last in item['tri_ranges'] for face in range(first,last+1)]}
                views=[dict(view=e['view'],ref=e['ref']) for e in item['evidence']]
                self.add(identity,item['status'],views,[self.support(number,item)],item['status'] if not views else '')
            self.row['coverage_use_excerpt']=self.final_line('COVERAGE_ROWS_*')
            unsupported_source=self.source_body_support(4)
        self.unsupported(unsupported_source)

    def product(self):
        p=self.tool(1,used=True)['value']
        regions,pixels,images=tabulate(p['regions']),tabulate(p['pixels']),tabulate(p['images'])
        if self.name=='P1':
            text=self.tool(6,used=True)['value']['stdout']
            native=json.JSONDecoder().raw_decode(text,text.index('{'))[0]
            for item in native['rows']:
                region=regions[item[0]]
                identity={'roi_id':region['roi_id'],'source_triangle_indices':[face for first,last in item[1] for face in range(first,last+1)]}
                views=[dict(view=native['images'][entry[0]][0],ref=native['images'][entry[0]][1]) for entry in item[4]]
                supports=[self.support(6,item),self.support(1,p['regions']['rows'][item[0]],nested=False)]
                self.add(identity,item[2],views,supports,item[3] or '',source_basis='mixed native discovery/source ranges with product status and actual product image/pixel evidence')
            self.row['coverage_use_excerpt']=self.final_line('independently-discovered-surface-coverage-v1')
            self.unsupported(self.support(6,native['unsupported'][0]))
        else:
            for index,region in enumerate(regions):
                views=[];supports=[self.support(1,p['regions']['rows'][index],nested=False)]
                if region['status']=='covered':
                    witness=pixels[region['complete_witness_pixel_index']]
                    image=images[witness['image_index']]
                    views=[dict(view=image['view_name'],ref=image['image_ref'])]
                    supports.append(self.support(1,p['pixels']['rows'][region['complete_witness_pixel_index']],nested=False))
                self.add({'roi_id':region['roi_id']},region['status'],views,supports,
                    region['unobserved_reason'] or '',source_basis='product current public v4 region/complete-witness facts')
            self.row['coverage_use_excerpt']=self.final_line('- **Observed:**')
            self.unsupported(self.support(1,p['scope']['patch_support']['unsupported_components']['rows'][0],nested=False))

    def artifact(self):
        path=self.owner/'scratch/surface_inspection.json'
        body=raw(path).decode('utf8');value=json.loads(body)
        citation=self.final_line(str(path))
        self.row['sources'].append(dict(id='artifact',kind='cited_artifact',path=str(path.resolve()),
            sha256=INPUTS[str(path.resolve())],final_citation_excerpt=citation))
        for item in value['supported_surfaces']:
            needle='"roi_id": '+json.dumps(item['roi_id'])
            excerpt=None
            for match in re.finditer(re.escape(needle),body):
                start=body.rfind('{',0,match.start());parsed,end=json.JSONDecoder().raw_decode(body,start)
                if parsed==item:
                    excerpt=body[start:end];break
            if excerpt is None:raise ValueError('cited_artifact_surface_span')
            views=[dict(view=e['view'],ref=e['image_ref']) for e in item['actual_observations'] if e['complete_readable_witness']]
            identity=dict(roi_id=item['roi_id'],quad_world_m=item['world_corners_m'])
            self.add(identity,item['status'],views,[dict(source_id='artifact',excerpt=excerpt)],
                item['unobserved_reason'] or '',source_basis='product facts parsed/formatted into final explicitly cited current artifact')
        self.row['coverage_use_excerpt']=citation
        start=body.index('"unsupported_remainder"');end=body.index('"unobserved_view_groups"',start)
        self.unsupported(dict(source_id='artifact',excerpt=body[start:end]))

    def unsupported(self,support):
        found=[text for text in self.final.splitlines() if 'unsupported' in text.lower()
               and re.search(r'(?<!\d)48(?!\d)',text)]
        if len(found)!=1:raise ValueError('unique_actual_unsupported_48_excerpt')
        excerpt=found[0]
        self.row['unsupported']=[dict(component_count=1,source_triangle_indices=[48],status='unknown',
            shape='nonrectangular',domain='outside_supported_rectangle_domain',
            support=[dict(source_id='final',excerpt=excerpt),support])]

    def positions(self):
        position={}
        for text in self.final.splitlines():
            match=re.match(r'^(?:- \*\*)?([123])(?:\.| —)',text)
            if match:position[int(match.group(1))]=text
        if set(position)!={1,2,3}:raise ValueError('three_actual_position_answers')
        def vectors(text):
            return [json.loads(value.replace('−','-')) for value in re.findall(r'\[[^\]]+\]',text)]
        def reference(text):
            found=re.findall(r'active-host-image:[0-9a-f]+|image-\d+',text)
            if len(set(found))!=1:raise ValueError('unique_actual_question_image_reference')
            return found[0]
        click=position[1];center=next(v for v in vectors(click) if len(v)==3)
        size=re.search(r'(\d+\.\d+)\s*×\s*(\d+\.\d+)',click)
        width,height=map(float,size.groups())
        origin=position[2];origin_vectors=vectors(origin)
        origin_center=next((v for v in origin_vectors if len(v)==3),[0,0,0])
        origin_pixel=[v for v in origin_vectors if len(v)==2][-1]
        view='BACK' if 'BACK' in origin else 'LEFT'
        bottom=position[3];bottom_center=next(v for v in vectors(bottom) if len(v)==3)
        scope=next((text for text in reversed(self.final.splitlines())
            if ('finite' in text.lower() and 'pool' in text.lower()) or 'unregistered' in text.lower()
            or 'Conclusions apply only' in text),None)
        if not scope:raise ValueError('actual_bounded_scope_excerpt')
        self.row['questions']=dict(
            click=dict(identity={'center_world_m':center,'front_direction_world':[0,0,1]},
                center_world_m=center,front_direction_world=[0,0,1],half_edge_u_world_m=[width/2,0,0],half_edge_v_world_m=[0,height/2,0],
                view='SCENE',ref=reference(click),support=dict(source_id='final',excerpt=click)),
            origin=dict(identity={'center_world_m':origin_center,'front_direction_world':[0,0,1]},
                SCENE_visible_pixels=0,SCENE_front_facing=True,SCENE_occluded=True,
                witness={'view':view,'ref':reference(origin),'pixel_xy':origin_pixel},support=dict(source_id='final',excerpt=origin)),
            bottom=dict(identity={'center_world_m':bottom_center,'front_direction_world':[0,0,-1]},
                finite_pool_no_front_readable=True,finite_pool_only=True,global_invisibility_claim=False,
                support=[dict(source_id='final',excerpt=bottom),dict(source_id='final',excerpt=scope)]))
        return dict(click_ref=reference(click),origin_view=view,origin_ref=reference(origin),origin_pixel=origin_pixel,
            extent_derivation='Exact stated XY full widths divided by two. Origin word denotes [0,0,0] when coordinates are implicit.',scope_excerpt=scope)

    def publish_tools(self):
        for item in read(self.owner/'TOOLS.json')['tools']:
            self.tool(item['attempt'])
        rows=[{k:v for k,v in self.tools[n].items() if k not in ('raw_text','value')} for n in sorted(self.tools)]
        save(HERE/'TOOL_EVIDENCE'/f'{self.name}.json',dict(schema='routed-task-quality-tool-evidence-v1',slot_id=self.name,
            tools=rows,cost_fields_removed=True))


def main():
    slots,provenance=[],[]
    for name in ORDER:
        slot=Slot(name)
        if name.startswith('N'):slot.native()
        elif name=='P3':slot.artifact()
        else:slot.product()
        locations=slot.positions()
        slot.publish_tools()
        slots.append(slot.row)
        provenance.append(dict(slot_id=name,raw_answer_path=slot.row['raw_answer_path'],raw_answer_sha256=slot.row['raw_answer_sha256'],
            complete_region_claims=slot.claims,location_claims=locations,
            normalized_panel_count=len(slot.row['panels']),covered=sum(r['status']=='covered' for r in slot.row['panels']),
            unknown=sum(r['status']=='unknown' for r in slot.row['panels']),
            adoption_scope='Independent P actual-call/JSON/fact adoption audit retained separately. Quality does not substitute for adoption.'))
    save(HERE/'NORMALIZED.json',dict(schema='region-localization-normalized-v1',scoring_role='Six actual finals and quoted current-slot facts before cost ranking',slots=slots))
    save(HERE/'CLAIM_PROVENANCE.json',dict(schema='routed-task-quality-claim-provenance-v1',slots=provenance,
        source_restatements_and_corrections=NOTES,inputs_sha256=INPUTS,cost_analysis_performed=False,
        normalization_scope='No administrator truth used to construct claims. Original geometry/pixel truth remains exclusively in the frozen scorer.'))
    print(json.dumps(dict(slots=len(slots),panels=[len(s['panels']) for s in slots],cost_analysis_performed=False)))


if __name__=='__main__':main()
