"""Shared ordered reply consumption and actual-PNG checks for both observers."""
import base64,hashlib,io,json,math
from pathlib import Path


class ArchiveCursor:
    def __init__(self,folder):self.folder=Path(folder);self.next=0;self.bytes=0
    def collect(self):
        values=[]
        while True:
            path=self.folder/('WIRE_'+str(self.next)+'.json')
            if not path.exists():break
            raw=path.read_bytes();values.append(json.loads(raw));self.bytes+=len(raw);self.next+=1
        return values


def raw_frames(wires,arm):
    from human_eye_plugin.blender_mcp_host import RPC_PREFIX
    found=[]
    for wire in wires:
        if arm=='native':
            native=wire.get('native')
            if native is not None and native.get('images'):found.append(native['images'])
        elif arm=='he' and wire.get('status')=='success':
            text=wire['result']['result']
            if not text.startswith(RPC_PREFIX):raise ValueError('evidence_envelope_prefix')
            value=json.loads(text[len(RPC_PREFIX):]).get('result')
            if type(value) is dict and value.get('frames'):found.append(value['frames'])
    if len(found)>1:raise ValueError('multiple_host_image_results')
    return found[0] if found else []


def check_images(case,arm,reply,wires,output):
    from PIL import Image
    from verification.run_native_engineering_preflight import actual_camera,pixel_check
    blocks=[b for b in reply['content'] if b['type']=='image'];sources=raw_frames(wires,arm)
    if len(blocks)!=len(sources):raise ValueError('evidence_image_count')
    output=Path(output);output.mkdir(exist_ok=False);frames=[];total=0
    for index,(block,source) in enumerate(zip(blocks,sources)):
        if block['mimeType']!='image/png':raise ValueError('evidence_mime')
        png=base64.b64decode(block['data'],validate=True);total+=len(png)
        if arm=='native':
            original=base64.b64decode(source['data'],validate=True);frame={k:v for k,v in source.items() if k!='data'}
            if hashlib.sha256(original).hexdigest()!=source['sha256']:raise ValueError('evidence_original_hash')
        else:
            original=base64.b64decode(source['picture']['image_base64'],validate=True)
            if hashlib.sha256(original).hexdigest()!=source['png_sha256']:raise ValueError('evidence_original_hash')
            proof=source['frustum'];matrix=proof['camera_matrix_host_units'];span=proof['ortho_scale_bu']
            if proof['resolution_px']!=[384,384] or proof['unit_scale_m']!=1:raise ValueError('evidence_scope')
            frame=dict(camera_matrix=matrix,actual_ortho_scale=span,span=span,location=[matrix[k][3] for k in range(3)],
                right=[matrix[k][0] for k in range(3)],up=[matrix[k][1] for k in range(3)],direction=[matrix[k][2] for k in range(3)])
            # Independent actual-RNA matrix vs requested chosen view, not just
            # normalization of the matrix against itself.
            host=next(json.loads(w['result']['result'].split(':',1)[1])['result'] for w in wires
                if arm=='he' and w.get('status')=='success' and '"frames":' in w['result']['result'])
            selected=host['plan']['selected'] or host['plan']['candidates'][0]
            for column,key in enumerate(('right','up','direction')):
                if any(abs(matrix[k][column]-selected[key][k])>2e-6 for k in range(3)):raise ValueError('evidence_camera_axes')
        with Image.open(io.BytesIO(png)) as public,Image.open(io.BytesIO(original)) as private:
            if public.size!=(384,384) or private.size!=(384,384) or public.convert('RGBA').tobytes()!=private.convert('RGBA').tobytes():
                raise ValueError('evidence_pixels_changed')
        matrix=frame['camera_matrix'];axes=[[matrix[k][j] for k in range(3)] for j in range(3)]
        if any(abs(sum(v*v for v in a)-1)>1e-5 for a in axes) or any(abs(sum(x*y for x,y in zip(axes[i],axes[j])))>1e-5 for i in range(3) for j in range(i)):
            raise ValueError('evidence_camera_not_orthonormal')
        actual_camera(frame);path=output/(str(index)+'.png');path.write_bytes(png)
        frame.update(path=str(path),sha256=hashlib.sha256(png).hexdigest());frames.append(frame)
    if len(frames)>2 or total>16*1024*1024:raise ValueError('evidence_image_budget')
    pixels=pixel_check(case,dict(images=frames)) if frames else None
    return dict(images=len(frames),png_bytes=total,pixels=pixels)
