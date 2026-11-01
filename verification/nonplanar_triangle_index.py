"""Bounded per-view triangle BVH, verification-only and source-bound."""
import json
import math
import time

LEAF_SIZE=8
AUTO_FACE_THRESHOLD=26  # Frozen by two adjacent paired crossover groups, 2026-11-01.
MAX_BUILD_UNITS=65536
MAX_NODE_SLOTS=4096
MAX_PACKET_BYTES=512*1024


class IndexBudgetError(ValueError):pass


def limits_for_faces(count):
    depth=0
    while count>LEAF_SIZE*(1<<depth):depth+=1
    nodes=(1<<(depth+1))-1
    return count*(depth+3)+nodes,nodes


class IndexBudget:
    def __init__(self,deadline,*,max_build=MAX_BUILD_UNITS,max_nodes=MAX_NODE_SLOTS,max_bytes=MAX_PACKET_BYTES):
        if any(type(v) is not int or v<0 for v in (max_build,max_nodes,max_bytes)):
            raise ValueError('invalid_triangle_index_budget')
        if max_build>MAX_BUILD_UNITS or max_nodes>MAX_NODE_SLOTS or max_bytes>MAX_PACKET_BYTES:
            raise ValueError('triangle_index_budget_cannot_expand')
        self.deadline=deadline;self.max_build=max_build;self.max_nodes=max_nodes;self.max_bytes=max_bytes
        self.build_reserved=0;self.nodes_reserved=0;self.node_tests_reserved=0;self.packet_bytes=0
        self.reservations=[]
        self.box_limit=32768

    def check(self):
        if time.perf_counter_ns()>=self.deadline:raise IndexBudgetError('triangle_index_deadline')

    def reserve_build(self,count,object_id,right,up):
        self.check();units,nodes=limits_for_faces(count)
        if self.build_reserved+units>self.max_build or self.nodes_reserved+nodes>self.max_nodes:
            raise IndexBudgetError('triangle_index_build_budget')
        self.build_reserved+=units;self.nodes_reserved+=nodes
        self.reservations.append({'object_id':object_id,'face_count':count,'right':right,'up':up,
            'build_units_reserved':units,'node_slots_reserved':nodes})
        return units,nodes

    def test_node(self):
        self.check()
        if self.node_tests_reserved+2>self.box_limit:
            raise IndexBudgetError('triangle_index_traversal_budget')
        self.node_tests_reserved+=2

    def publish_bytes(self,value):
        size=len(json.dumps(value,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8'))
        if self.packet_bytes+size>self.max_bytes:raise IndexBudgetError('triangle_index_packet_budget')
        self.packet_bytes+=size


def triangle_box(face,intervals):
    result=[]
    for axis in (0,1):
        low=min(intervals[axis][v][0] for v in face);high=max(intervals[axis][v][1] for v in face)
        if not math.isfinite(low) or not math.isfinite(high):raise IndexBudgetError('triangle_index_nonfinite_bounds')
        # Retain the tolerated barycentric halo as well as arithmetic edge cases.
        pad=4e-12*(high-low)+32*math.ulp(max(1.,abs(low),abs(high)))
        result.append((math.nextafter(low-pad,-math.inf),math.nextafter(high+pad,math.inf)))
    box=[result[0][0],result[1][0],result[0][1],result[1][1]]
    if not all(math.isfinite(v) for v in box):raise IndexBudgetError('triangle_index_nonfinite_bounds')
    return box


def build_index(obj,intervals,right,up,binding,budget):
    units,node_bound=budget.reserve_build(len(obj['faces']),obj['object_id'],right,up)
    boxes=[triangle_box(face,intervals) for face in obj['faces']]
    nodes=[]
    def build(ids):
        budget.check();index=len(nodes);nodes.append(None)
        bound=[min(boxes[i][0] for i in ids),min(boxes[i][1] for i in ids),
            max(boxes[i][2] for i in ids),max(boxes[i][3] for i in ids)]
        if len(ids)<=LEAF_SIZE:
            nodes[index]=bound+[-1,-1,sorted(ids)]
        else:
            axis=0 if bound[2]-bound[0]>=bound[3]-bound[1] else 1
            ids.sort(key=lambda i:(boxes[i][axis]/2+boxes[i][axis+2]/2,i))
            cut=len(ids)//2;left=build(ids[:cut]);right_id=build(ids[cut:])
            nodes[index]=bound+[left,right_id,[]]
        return index
    build(list(range(len(boxes))))
    assert len(nodes)<=node_bound
    result={'schema':'projected-triangle-bvh-v1','object_id':obj['object_id'],
        'face_count':len(obj['faces']),'vertex_count':len(obj['world_vertices']),
        'source_binding':binding,'right':right,'up':up,'leaf_size':LEAF_SIZE,
        'reservation_index':len(budget.reservations)-1,
        'build_units_reserved':units,'node_slots_reserved':node_bound,'nodes':nodes}
    budget.publish_bytes(result)
    return result


def traverse(index,point_intervals,budget,trace,selected):
    pending=[0]
    while pending:
        budget.test_node();number=pending.pop();node=index['nodes'][number]
        active=not any(point_intervals[k][1]<node[k] or point_intervals[k][0]>node[k+2] for k in (0,1))
        trace.append([number,active])
        if not active:continue
        if node[4]==-1:selected.extend(node[6])
        else:pending.extend((node[5],node[4]))
    selected.sort()


def filter_view(native,staged,vertex_intervals,right,up,binding,counts,budget,point_interval,threshold):
    """Publish partial traversal only as incomplete evidence; no rays yet."""
    used={name for sample in staged for names in sample['possible_objects'] for name in names}
    wanted={name for name in used if counts[name]>=threshold}
    if not wanted:return None
    result={'schema':'triangle-index-view-v1','indices':{},'queries':[],'complete':False,'reason':None}
    try:
        for obj in native['objects']:
            if obj['object_id'] in wanted:
                result['indices'][obj['object_id']]=build_index(obj,vertex_intervals[obj['object_id']],right,up,binding,budget)
        for sample in staged:
            refs=[]
            for point,names in zip(sample['pair'],sample['possible_objects']):
                query={'point':point,'possible_objects':names,'filters':{},'traces':{},'complete':False}
                refs.append(len(result['queries']));result['queries'].append(query)
                intervals=[point_interval(point,axis) for axis in (right,up)]
                for name in names:
                    if name not in result['indices']:continue
                    trace=[];selected=[];query['traces'][name]=trace;query['filters'][name]=selected
                    traverse(result['indices'][name],intervals,budget,trace,selected)
                query['complete']=True
            sample['index_queries']=refs
        result['complete']=True
    except IndexBudgetError as exc:
        result['reason']=str(exc)
        for query in result['queries']:
            for selected in query['filters'].values():selected.sort()
    # Query traces also occupy the bounded outgoing certificate envelope.
    budget.publish_bytes(result['queries'])
    return result
