"""Independent authored GLB packets verify the offline inventory reader."""
import copy,json,struct,unittest
from verification.inspect_deformation_asset_intake import inspect,parse_glb,accessor_rows


def fixture(*,normalized=False,strided=False):
    binary=bytearray(struct.pack('<9f',0,0,0,1,0,0,0,1,0));views=[dict(buffer=0,byteOffset=0,byteLength=36)]
    accessors=[dict(bufferView=0,componentType=5126,count=3,type='VEC3')]
    indices=struct.pack('<3H',0,1,2);start=len(binary);binary.extend(indices);binary.extend(b'\0\0');views.append(dict(buffer=0,byteOffset=start,byteLength=6))
    accessors.append(dict(bufferView=1,componentType=5123,count=3,type='SCALAR'))
    start=len(binary);binary.extend(bytes([0,1,0,0])*3);views.append(dict(buffer=0,byteOffset=start,byteLength=12));accessors.append(dict(bufferView=2,componentType=5121,count=3,type='VEC4'))
    start=len(binary)
    if normalized:
        for i in range(3):binary.extend(bytes([128,127,0,0]));binary.extend(b'\xff'*4 if strided else b'')
        view=dict(buffer=0,byteOffset=start,byteLength=len(binary)-start)
        if strided:view['byteStride']=8
        component=5121
    else:
        binary.extend(struct.pack('<12f',*([.25,.75,0,0]*3)));view=dict(buffer=0,byteOffset=start,byteLength=48);component=5126
    views.append(view);accessors.append(dict(bufferView=3,componentType=component,count=3,type='VEC4',normalized=normalized))
    doc=dict(asset=dict(version='2.0',generator='independent unit fixture'),buffers=[dict(byteLength=len(binary))],bufferViews=views,accessors=accessors,
        meshes=[dict(name='AuthoredTriangle',primitives=[dict(attributes=dict(POSITION=0,JOINTS_0=2,WEIGHTS_0=3),indices=1)])],
        skins=[dict(joints=[1,2],skeleton=1)],nodes=[dict(name='Mesh',mesh=0,skin=0),dict(name='Root',children=[2]),dict(name='Tip')],
        animations=[dict(samplers=[dict(input=0,output=0)],channels=[dict(sampler=0,target=dict(node=2,path='rotation'))])])
    return doc,bytes(binary)


def glb(doc,binary):
    text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*((-len(text))%4);data=binary+b'\0'*((-len(binary))%4)
    chunks=struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(data),0x004e4942)+data
    return struct.pack('<4sII',b'glTF',2,12+len(chunks))+chunks


class AssetIntakeTests(unittest.TestCase):
    def test_known_original_counts_weights_nodes_and_animation(self):
        doc,binary=fixture();blob=glb(doc,binary);before=blob[:];out=inspect(blob);p=out['meshes'][0]['primitives'][0]
        self.assertEqual((p['vertices'],p['triangles'],p['max_positive_influences']),(3,1,2))
        self.assertEqual((p['positive_weight_sum_min'],p['positive_weight_sum_max']),(1,1))
        self.assertEqual(out['skins'][0]['joints'],2);self.assertEqual(out['animations'][0]['target_paths'],['rotation'])
        self.assertEqual(out['nodes'][2]['parent'],1);self.assertFalse(out['cleanup_performed']);self.assertFalse(out['product_support_certified']);self.assertEqual(blob,before)
    def test_normalized_unsigned_weights_and_interleaved_stride(self):
        doc,binary=fixture(normalized=True,strided=True);rows=accessor_rows(doc,binary,3)
        self.assertEqual(rows,[[128/255,127/255,0.,0.]]*3)
        p=inspect(glb(doc,binary))['meshes'][0]['primitives'][0]
        self.assertEqual(p['max_positive_influences'],2);self.assertEqual(p['positive_weight_sum_max'],1.)
    def test_header_total_truncation_and_nonfinite_rejected(self):
        doc,binary=fixture();blob=glb(doc,binary)
        for bad in (blob[:-1],b'BAD!'+blob[4:],blob+b'\0'*4):
            with self.subTest(length=len(bad)):
                with self.assertRaisesRegex(ValueError,'header'):inspect(bad)
        changed=bytearray(binary);struct.pack_into('<f',changed,doc['bufferViews'][3]['byteOffset'],float('nan'))
        with self.assertRaisesRegex(ValueError,'nonfinite'):inspect(glb(doc,changed))
    def test_index_out_of_range_is_not_a_valid_triangle(self):
        doc,binary=fixture();changed=bytearray(binary);struct.pack_into('<H',changed,doc['bufferViews'][1]['byteOffset'],3)
        with self.assertRaisesRegex(ValueError,'indices'):inspect(glb(doc,changed))
    def test_sparse_external_buffers_and_nontriangles_refused(self):
        doc,binary=fixture()
        for change,reason in ((lambda d:d['buffers'][0].update(uri='external.bin'),'buffer_binding'),
            (lambda d:d['accessors'][1].update(sparse={}), 'sparse_or_missing_view'),
            (lambda d:d['meshes'][0]['primitives'][0].update(mode=5),'nontriangle_primitive')):
            d=copy.deepcopy(doc);change(d)
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError,reason):inspect(glb(d,binary))
    def test_accessor_must_fit_its_own_view_not_only_the_binary(self):
        doc,binary=fixture();doc['bufferViews'][3]['byteLength']=4
        with self.assertRaisesRegex(ValueError,'accessor_bounds'):inspect(glb(doc,binary))
    def test_declared_joint_weight_lengths_must_match_positions(self):
        doc,binary=fixture();doc['accessors'][3]['count']=2
        with self.assertRaisesRegex(ValueError,'weight_shape'):inspect(glb(doc,binary))


if __name__=='__main__':unittest.main()
