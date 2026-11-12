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


def _rigid_matrix(value, field):
    value=_array(value,field,(4,4)).tolist()
    rig_pose.matrix(value)
    if not rig_pose.rigid(value):raise ValueError('rigid_bone_matrices_required')
    return value


def _parse_patch(patch, *, dynamic):
    """Share static parsing while preserving the original raw error order."""
    if not isinstance(patch,dict) or patch.get('schema')!=SCHEMA or patch.get('unit')!='m':
        raise ValueError('arm_patch_schema_or_unit')
    rest=_array(patch.get('rest_vertices'),'rest_vertices')
    if rest.ndim!=2 or rest.shape[1:]!=(3,) or not 6<=len(rest)<=8192:raise ValueError('local_patch_vertices')
    current=_array(patch.get('current_vertices'),'current_vertices',rest.shape) if dynamic else None
    ids=patch.get('vertex_ids')
    if (not isinstance(ids,list) or len(ids)!=len(rest) or any(type(v) is not int or v<0 for v in ids)
            or len(set(ids))!=len(ids)):raise ValueError('same_index_vertex_ids')
    bones=patch.get('bone_chain')
    if not isinstance(bones,list) or not 2<=len(bones)<=4:raise ValueError('short_local_bone_chain_required')
    names=[];rest_matrices=[];poses=[]
    for index,bone in enumerate(bones):
        if not isinstance(bone,dict) or not rig_pose.text(bone.get('name')):raise ValueError('bone_chain_name')
        if bone['name'] in names or bone.get('parent')!=(names[-1] if index else None):raise ValueError('bone_parent_chain')
        names.append(bone['name'])
        rest_matrices.append(_rigid_matrix(bone.get('rest_matrix'),'rest_matrix'))
        if dynamic:poses.append(_rigid_matrix(bone.get('pose_matrix'),'pose_matrix'))
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
    used=set()
    for section in sections:
        if (not isinstance(section,list) or not 3<=len(section)<=256
                or any(type(i) is not int or not 0<=i<len(rest) for i in section)
                or len(set(section))!=len(section) or used.intersection(section)
                or any(tuple(sorted((section[i],section[(i+1)%len(section)]))) not in edges for i in range(len(section)))):
            raise ValueError('closed_section_topology')
        used.update(section)
    return rest,ids,rest_matrices,weights,sections,current,poses


def _section_geometry(points, groups, count, *, centers=None, errors=None):
    """Batch equal-length sections, placing results back in caller order."""
    supplied_centers=centers is not None
    if centers is None:centers=np.empty((count,3))
    eig=np.empty((count,3));perimeter=np.empty(count)
    for rows,indices in groups:
        selected=points[indices]
        center=centers[rows] if supplied_centers else selected.mean(axis=1)
        centered=selected-center[:,None,:]
        centers[rows]=center
        covariance=centered.swapaxes(1,2)@centered/indices.shape[1]
        try:eig[rows]=np.maximum(np.linalg.eigvalsh(covariance),0.)
        except np.linalg.LinAlgError:
            if errors is None:raise
            # Batch failure must not jump ahead of an earlier section's
            # unknown. Only this exceptional path identifies failing rows.
            for row,matrix in zip(rows,covariance):
                try:eig[row]=np.maximum(np.linalg.eigvalsh(matrix),0.)
                except np.linalg.LinAlgError as exc:
                    errors[int(row)]=(type(exc),str(exc));eig[row]=np.nan
        perimeter[rows]=np.linalg.norm(centered-np.roll(centered,1,axis=1),axis=2).sum(axis=1)
    return centers,eig,perimeter


class PreparedArmPatch:
    """Own static patch statistics; changes to topology/rest/weights need prepare.

    Dynamic pose matrices must retain the original ``bone_chain`` order. No
    input packet is retained or consulted during a subsequent pose request.
    """
    def __init__(self,patch):
        self._prepare(_parse_patch(patch,dynamic=False))

    @classmethod
    def _from_validated(cls,parsed):
        prepared=cls.__new__(cls);prepared._prepare(parsed);return prepared

    def _prepare(self,parsed):
        rest,ids,matrices,weights,sections,_,_=parsed
        self._shape=rest.shape;self._ids=tuple(ids)
        self._sections=tuple(tuple(s) for s in sections);self._count=len(sections)
        self._bones_count=len(matrices)
        buckets={}
        for row,section in enumerate(sections):buckets.setdefault(len(section),[]).append(row)
        self._groups=tuple((np.asarray(rows,dtype=np.int64),
                            np.array([sections[r] for r in rows],dtype=np.int64)) for rows in buckets.values())
        self._scale=max(float(np.linalg.norm(np.ptp(rest,axis=0))),np.finfo(float).tiny)
        self._centers0=np.empty((self._count,3))
        for rows,indices in self._groups:self._centers0[rows]=rest[indices].mean(axis=1)
        self._lengths0=np.linalg.norm(np.diff(self._centers0,axis=0),axis=1)
        self._rest_reason='section_centerline_degenerate' if np.any(self._lengths0<=self._scale*1e-10) else None
        self._rest_errors={}
        if self._rest_reason:
            self._eig0=np.zeros((self._count,3));self._perimeter0=np.zeros(self._count)
        else:
            _,self._eig0,self._perimeter0=_section_geometry(rest,self._groups,self._count,
                centers=self._centers0,errors=self._rest_errors)
        self._rest_bad=(self._eig0[:,1]<=self._scale*self._scale*1e-14)|(self._eig0[:,0]>1e-6*self._eig0.sum(axis=1))
        self._rest_inverse=tuple(rig_pose.inverse(rig_pose.multiply(rig_pose.inverse(a),b))
                                 for a,b in zip(matrices,matrices[1:]))
        self._blend=np.empty(self._count);self._spread=np.empty(self._count)
        self._joint_weights=np.empty((self._count,len(matrices)-1))
        for rows,indices in self._groups:
            w=weights[indices]
            pair=(4*w[:,:,:-1]*w[:,:,1:]).mean(axis=1);total=pair.sum(axis=1)
            self._joint_weights[rows]=np.divide(pair,total[:,None],out=np.full_like(pair,1/(len(matrices)-1)),
                                                where=total[:,None]>1e-12)
            self._blend[rows]=(2*(1-np.square(w).sum(axis=2))).mean(axis=1)
            self._spread[rows]=w.std(axis=1).mean(axis=1)
        arrays=[self._centers0,self._eig0,self._perimeter0,self._lengths0,self._blend,self._spread,self._joint_weights,self._rest_bad]
        arrays.extend(array for group in self._groups for array in group)
        for array in arrays:array.setflags(write=False)

    def extract_features(self,current_vertices,pose_matrices):
        current=_array(current_vertices,'current_vertices',self._shape)
        try:count=len(pose_matrices)
        except TypeError:raise ValueError('pose_matrix_count') from None
        if not isinstance(pose_matrices,(list,tuple,np.ndarray)) or count!=self._bones_count:
            raise ValueError('pose_matrix_count')
        poses=[_rigid_matrix(pose,'pose_matrix') for pose in pose_matrices]
        return self._features(current,poses)

    def _features(self,current,poses):
        angles=[rig_pose.angles(rig_pose.multiply(rest,rig_pose.multiply(rig_pose.inverse(a),b)))
                for rest,a,b in zip(self._rest_inverse,poses,poses[1:])]
        context={'sections':[list(s) for s in self._sections],'vertex_ids':list(self._ids),
                 'reason':None,'joint_angles':angles}
        if any(a['twist_deg'] is None for a in angles):context['reason']='bone_twist_branch_unknown'
        elif self._rest_reason:context['reason']=self._rest_reason
        if context['reason']:return np.empty((0,len(FEATURE_NAMES))),context
        errors={}
        centers,eig,perimeter=_section_geometry(current,self._groups,self._count,errors=errors)
        bad=self._rest_bad|(eig[:,0]>1e-6*np.maximum(eig.sum(axis=1),self._scale*self._scale*1e-14))
        if self._rest_errors or errors:
            row=min((*self._rest_errors,*errors,*np.flatnonzero(bad)))
            failure=self._rest_errors.get(row) or errors.get(row)
            if failure:raise failure[0](failure[1])
        if np.any(bad):
            context['reason']='section_nonplanar_or_reference_degenerate'
            return np.empty((0,len(FEATURE_NAMES))),context
        axial=np.linalg.norm(np.diff(centers,axis=0),axis=1)/self._lengths0
        axial=np.r_[axial[0],(axial[:-1]+axial[1:])*.5,axial[-1]]
        ratios=np.sqrt(eig[:,1:]/self._eig0[:,1:])
        twist=self._joint_weights@np.array([abs(a['twist_deg']) for a in angles])/180.
        swing=self._joint_weights@np.array([a['swing_deg'] for a in angles])/180.
        features=np.column_stack((ratios.prod(axis=1),np.sqrt(eig.sum(axis=1)/self._eig0.sum(axis=1)),
            ratios[:,0],ratios[:,1],perimeter/self._perimeter0,axial,self._blend,self._spread,twist,swing))
        if not np.isfinite(features).all():raise ValueError('nonfinite_section_features')
        return features,context

    def analyze(self,current_vertices,pose_matrices,model=None):
        if model is None:model=get_default_expert()
        return model.predict_prepared(self,current_vertices,pose_matrices)


def prepare_patch(patch):
    """Prepare static fields only; current vertices/pose matrices are optional."""
    return PreparedArmPatch(patch)


def extract_features(patch):
    """Keep the raw contract, sharing preparation and the dynamic kernel."""
    parsed=_parse_patch(patch,dynamic=True)
    return PreparedArmPatch._from_validated(parsed)._features(parsed[5],parsed[6])


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
        return self._report(*extract_features(patch))

    def predict_prepared(self,prepared,current_vertices,pose_matrices):
        if not isinstance(prepared,PreparedArmPatch):raise ValueError('prepared_arm_patch_required')
        return self._report(*prepared.extract_features(current_vertices,pose_matrices))

    def _report(self,features,context):
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
