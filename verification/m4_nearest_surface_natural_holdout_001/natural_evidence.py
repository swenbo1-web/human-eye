"""Record current frame custody on top of the unchanged natural read-only tools."""
import base64
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm4_reference_only_intent_holdout_001'))
from natural_bridge import Bridge as HistoricalBridge, append, pin, require, write


class RecordingBridge(HistoricalBridge):
    """Record actual image positions without modifying the product reply."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bound_this_request = []

    def bind_frame(self, frame, source, delivered=False):
        known = frame['image_ref'] in self.frames
        super().bind_frame(frame, source, delivered)
        if not known:
            self.bound_this_request.append({'source': source, 'frame': frame, 'delivered': delivered})

    def product_call(self, message):
        self.ordinal_source = 'product'
        self.recorded = []
        try:
            packet = self.product_server.handle_jsonrpc_message(message)
        finally:
            self.ordinal_source = 'ordinary'
        require(len(self.recorded) <= 1, 'multiple_producer_returns_in_one_public_request')
        if not self.recorded:
            return packet
        value, = self.recorded
        folder = self.folder / 'wire' / f'{self.ordinal:03d}'
        write(folder / 'PRODUCER.json', value)
        selected = value.get('frames', [])
        constructed = value.get('constructed_frames', selected)
        blocks = [(i, block) for i, block in enumerate(packet.get('result', {}).get('content', []))
                  if block.get('type') == 'image']
        published = {}
        bound = (len(selected) == len(blocks) and all(block['mimeType'] == 'image/png' and
                 hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest() == frame['image_sha256']
                 for frame, (_, block) in zip(selected, blocks)))
        if bound:
            published = {frame['image_ref']: i for frame, (i, _) in zip(selected, blocks, strict=True)}
        unique = {}
        for frame in (*constructed, *selected):
            ref = frame['image_ref']
            previous = unique.setdefault(ref, frame)
            require(previous['frame_identity'] == frame['frame_identity'], 'different_physical_frames_same_reference')
        for ref, frame in unique.items():
            self.bind_frame(frame, 'product', ref in published)
        write(folder / 'PRODUCT_FRAME_DELIVERY.json', {
           'bound': bound, 'images': [{'image_ref': ref, 'content_index': i,
                    'frame_identity': unique[ref]['frame_identity']} for ref, i in published.items()],
           'constructed_refs': [frame['image_ref'] for frame in constructed],
           'selected_refs': [frame['image_ref'] for frame in selected],
           'native_blocks': [i for i, _ in blocks]})
        return packet

    def dispatch(self, raw):
        self.bound_this_request = []
        start = len(self.rasters)
        try:
            return super().dispatch(raw)
        finally:
            new = self.rasters[start:]
            completed = sum(r['complete'] for r in new)
            parsed = iter(self.bound_this_request) if completed == len(self.bound_this_request) else iter(())
            for n, raster in enumerate(new, start + 1):
                handoff = next(parsed, None) if raster['complete'] else None
                item = {**raster, 'construction_index': n,
                        'frame_status': 'bound' if handoff else
                            ('built_frame_not_available' if raster['complete'] else 'incomplete_raster'),
                        'frame': None}
                if handoff is not None:
                    frame = handoff['frame']
                    item['frame'] = {key: frame.get(key) for key in ('image_ref', 'frame_identity', 'view_name',
                                      'scope_id', 'source_revision', 'camera_identity', 'host_binding_sha256')}
                    item['frame'].update(image=pin(frame['image_path']), arrays=pin(frame['arrays_path']),
                                         delivered=handoff['delivered'], source=handoff['source'])
                append(self.folder / 'physical_frames.jsonl', item)
