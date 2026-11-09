"""Optional learned twist-artifact estimate for specified closed arm sections.

The caller supplies a same-index local patch and a short bone chain in metres.
This synthetic-domain expert neither establishes source provenance nor edits a
rig. Its estimates do not replace measured geometry or establish injury.
"""
from functools import lru_cache
import numpy as np
from . import rig_pose

SCHEMA = 'arm-twist-patch-v1'
FEATURE_NAMES = ('covariance_area_ratio','rms_radius_ratio','minor_radius_ratio',
    'major_radius_ratio','perimeter_ratio','centerline_stretch','weight_blend',
    'weight_spread','twist_fraction','swing_fraction')
FLAG_THRESHOLD = .15


def _array(value, name, shape=None):
    try:out=np.asarray(value,dtype=np.float64)
    except (TypeError,ValueError) as exc:raise ValueError(name) from exc
    if not np.isfinite(out).all() or shape is not None and out.shape!=shape:raise ValueError(name)
    return out


def extract_features(patch):
    """Return section features and detached indexing; no labels/reference used."""
    if not isinstance(patch,dict) or patch.get('schema')!=SCHEMA or patch.get('unit')!='m':
        raise ValueError('arm_patch_schema_or_unit')
    rest=_array(patch.get('rest_vertices'),'rest_vertices')
    if rest.ndim!=2 or rest.shape[1:]!=(3,) or not 6<=len(rest)<=8192:raise ValueError('local_patch_vertices')
    current=_array(patch.get('current_vertices'),'current_vertices',rest.shape)
    ids=patch.get('vertex_ids')
    if (not isinstance(ids,list) or len(ids)!=len(rest) or any(type(v) is not int or v<0 for v in ids)
            or len(set(ids))!=len(ids)):raise ValueError('same_index_vertex_ids')
    bones=patch.get('bone_chain')
    if not isinstance(bones,list) or not 2<=len(bones)<=4:raise ValueError('short_local_bone_chain_required')
    names=[];matrices=[]
    for index,bone in enumerate(bones):
        if not isinstance(bone,dict) or not rig_pose.text(bone.get('name')):raise ValueError('bone_chain_name')
        if bone['name'] in names or bone.get('parent')!=(names[-1] if index else None):raise ValueError('bone_parent_chain')
        names.append(bone['name'])
        pair=[]
        for field in ('rest_matrix','pose_matrix'):
            value=_array(bone.get(field),field,(4,4)).tolist()
            rig_pose.matrix(value)
            if not rig_pose.rigid(value):raise ValueError('rigid_bone_matrices_required')
            pair.append(value)
        matrices.append(pair)
    weights=_array(patch.get('weights'),'weights',(len(rest),len(bones)))
    if (weights<0).any() or (weights>1).any() or not np.allclose(weights.sum(axis=1),1.,rtol=0,atol=1e-6):
        raise ValueError('normalized_vertex_weights_required')
    triangles=patch.get('triangles')
    if (not isinstance(triangles,list) or not 1<=len(triangles)<=16384
            or any(not isinstance(t,list) or len(t)!=3 or any(type(i) is not int or not 0<=i<len(rest) for i in t)
                   or len(set(t))!=3 for t in triangles)):raise ValueError('patch_triangles')
    edges={tuple(sorted((t[a],t[b]))) for t in triangles for a,b in ((0,1),(1,2),(2,0))}
    sections=patch.get('sections')
    if not isinstance(sections,list) or not 2<=len(sections)<=128:raise ValueError('closed_sections_required')
    used=set();indices=[]
    for section in sections:
        if (not isinstance(section,list) or not 3<=len(section)<=256
                or any(type(i) is not int or not 0<=i<len(rest) for i in section)
                or len(set(section))!=len(section) or used.intersection(section)
                or any(tuple(sorted((section[i],section[(i+1)%len(section)]))) not in edges for i in range(len(section)))):
            raise ValueError('closed_section_topology')
        used.update(section);indices.append(np.asarray(section,dtype=np.int64))
    angles=[]
    for parent,child in zip(matrices,matrices[1:]):
        rest_relative=rig_pose.multiply(rig_pose.inverse(parent[0]),child[0])
        pose_relative=rig_pose.multiply(rig_pose.inverse(parent[1]),child[1])
        angles.append(rig_pose.angles(rig_pose.multiply(rig_pose.inverse(rest_relative),pose_relative)))
    context={'sections':[list(s) for s in sections], 'vertex_ids':list(ids), 'reason':None,
             'joint_angles':angles}
    if any(angle['twist_deg'] is None for angle in angles):
        context['reason']='bone_twist_branch_unknown';return np.empty((0,len(FEATURE_NAMES))),context
    centers0=np.array([rest[s].mean(axis=0) for s in indices])
    centers1=np.array([current[s].mean(axis=0) for s in indices])
    lengths0=np.linalg.norm(np.diff(centers0,axis=0),axis=1)
    lengths1=np.linalg.norm(np.diff(centers1,axis=0),axis=1)
    scale=max(float(np.linalg.norm(np.ptp(rest,axis=0))),np.finfo(float).tiny)
    if np.any(lengths0<=scale*1e-10):
        context['reason']='section_centerline_degenerate';return np.empty((0,len(FEATURE_NAMES))),context
    axial=lengths1/lengths0
    axial=np.r_[axial[0],(axial[:-1]+axial[1:])*.5,axial[-1]]
    features=[]
    for k,s in enumerate(indices):
        a=rest[s]-centers0[k];b=current[s]-centers1[k]
        eig0=np.maximum(np.linalg.eigvalsh(a.T@a/len(s)),0.)
        eig1=np.maximum(np.linalg.eigvalsh(b.T@b/len(s)),0.)
        if (eig0[1]<=scale*scale*1e-14 or eig0[0]>1e-6*eig0.sum()
                or eig1[0]>1e-6*max(float(eig1.sum()),scale*scale*1e-14)):
            context['reason']='section_nonplanar_or_reference_degenerate';return np.empty((0,len(FEATURE_NAMES))),context
        ratios=np.sqrt(eig1[1:]/eig0[1:])
        perimeter0=np.linalg.norm(a-np.roll(a,1,axis=0),axis=1).sum()
        perimeter1=np.linalg.norm(b-np.roll(b,1,axis=0),axis=1).sum()
        pair_blend=(4*weights[s,:-1]*weights[s,1:]).mean(axis=0)
        blend=2*(1-np.square(weights[s]).sum(axis=1))
        joint_weights=pair_blend/pair_blend.sum() if pair_blend.sum()>1e-12 else np.ones(len(angles))/len(angles)
        twist=sum(w*abs(angle['twist_deg']) for w,angle in zip(joint_weights,angles))/180.
        swing=sum(w*angle['swing_deg'] for w,angle in zip(joint_weights,angles))/180.
        features.append([float(np.prod(ratios)),float(np.sqrt(eig1.sum()/eig0.sum())),
            float(ratios[0]),float(ratios[1]),float(perimeter1/perimeter0),float(axial[k]),
            float(blend.mean()),float(weights[s].std(axis=0).mean()),float(twist),float(swing)])
    features=np.asarray(features,dtype=np.float64)
    if not np.isfinite(features).all():raise ValueError('nonfinite_section_features')
    return features,context


class ArmTwistExpert:
    """One small trained tanh network; preprocessing is fitted on train only."""
    def __init__(self,parameters):
        if parameters.get('schema')!='arm-twist-mlp-v1' or tuple(parameters.get('feature_names',()))!=FEATURE_NAMES:
            raise ValueError('arm_expert_weights_schema')
        width=len(parameters.get('b1',()))
        for field,shape in [('mean',(len(FEATURE_NAMES),)),('scale',(len(FEATURE_NAMES),)),
                ('w1',(len(FEATURE_NAMES),width)),('b1',(width,)),('w2',(width,)),('b2',(1,))]:
            value=np.array(_array(parameters.get(field),field,shape),copy=True)
            value.setflags(write=False);setattr(self,'_'+field,value)
        if not 1<=width<=64 or np.any(self._scale<=0):raise ValueError('arm_expert_weights_shape')
        self.model_id=str(parameters.get('model_id','arm-twist-mlp-v1'))

    def predict(self,patch):
        features,context=extract_features(patch)
        report={'schema':'arm-twist-expert-report-v1','status':'unknown' if context['reason'] else 'estimated',
            'assessment':'synthetic_twist_collapse_estimate_not_damage','model_id':self.model_id,
            'scope':'specified_closed_arm_sections_synthetic_training',
            'source_binding':'caller_supplied_patch_not_verified_scene','execution_authority':False,
            'reason':context['reason'],'regions':[]}
        if context['reason']:return report
        standardized=(features-self._mean)/self._scale
        scores=np.clip(np.tanh(standardized@self._w1+self._b1)@self._w2+self._b2[0],0.,1.)
        report['regions']=[{'section_index':i,'vertex_ids':[context['vertex_ids'][j] for j in section],
            'predicted_severity':float(scores[i]),'flagged':bool(scores[i]>=FLAG_THRESHOLD)}
            for i,section in enumerate(context['sections'])]
        report['max_severity']=float(scores.max())
        return report


@lru_cache(maxsize=1)
def get_default_expert():
    # The learned tensors are imported only for an explicit expert request.
    from .arm_twist_weights import PARAMETERS
    return ArmTwistExpert(PARAMETERS)


def analyze(patch):return get_default_expert().predict(patch)
