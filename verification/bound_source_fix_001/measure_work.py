"""Count actual helper property accesses and its temporary allocation; no timing."""
import builtins
from collections import Counter
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch

from verification.bound_source_fix_001.test_source_validation import m


def case(name, *, coordinates, invalid=False, nan=False, repeated=1, vertex_count=6):
    reads=Counter();allocations=[]
    points=[(100.,0.,0.),(100.,1.,0.),(100.,0.,1.),(100.,2.,0.),(100.,3.,0.),(100.,4.,0.)]
    if nan:points[3]=(math.nan,2.,0.)
    class Vertex:
        def __init__(self,index):self.index=index
        @property
        def co(self):reads['unique_coordinate_reads']+=1;return points[self.index]
    class Vertices:
        def __len__(self):return vertex_count
        def __getitem__(self,index):return Vertex(index)
    class Loop:
        def __init__(self,index):self.index=index
        @property
        def vertex_index(self):reads['index_reads']+=1;return self.index
    class Face:
        def __init__(self,start):self.start=start
        @property
        def loop_start(self):reads['face_start_reads']+=1;return self.start
        @property
        def loop_total(self):reads['face_total_reads']+=1;return 3
    faces=[(0,1,2),(13 if invalid else 3,4,5)] if repeated==1 else [(0,1,2)]*repeated
    data=NS(vertices=Vertices(), polygons=[Face(i*3) for i in range(len(faces))],
            loops=[Loop(index) for face in faces for index in face])
    def allocate(size):
        result=builtins.bytearray(size);allocations.append(dict(payload_bytes=size, object_bytes=sys.getsizeof(result)));return result
    def checkpoint():reads['checkpoints']+=1
    error=None
    with patch.object(m,'bytearray',side_effect=allocate,create=True):
        try:m._acquisition_validate_triangles(data,check_coordinates=coordinates,checkpoint=checkpoint,object_id=name)
        except m.BlenderHostError as exc:error=str(exc)
    return dict(name=name,counts=dict(reads),allocations=allocations,error=error,
                scope='validator only; original first-face witness and capture coordinate reads excluded')


def main():
    rows=[case('excluded_two_faces',coordinates=True),case('retained_two_faces',coordinates=False),
          case('excluded_nan',coordinates=True,nan=True),case('excluded_bad_index',coordinates=True,invalid=True),
          case('shared_400_faces',coordinates=True,repeated=400),
          case('maximum_vertex_marker',coordinates=True,repeated=2,vertex_count=500000)]
    assert rows[0]['counts']['index_reads']==6 and rows[0]['counts']['unique_coordinate_reads']==6
    assert rows[1]['counts'].get('unique_coordinate_reads',0)==0 and not rows[1]['allocations']
    assert rows[2]['counts']['unique_coordinate_reads']==4
    assert rows[3]['counts']['index_reads']==4 and rows[3]['counts'].get('unique_coordinate_reads',0)==0
    assert rows[4]['counts']['index_reads']==1200 and rows[4]['counts']['unique_coordinate_reads']==3
    assert rows[5]['allocations'][0]['payload_bytes']==500000 and rows[5]['counts']['unique_coordinate_reads']==3
    out=Path(__file__).resolve().parent/'WORK_COUNTS.json'
    out.write_bytes((json.dumps(dict(cases=rows,all_assertions_passed=True,performance_samples=0),indent=2)+'\n').encode())
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
