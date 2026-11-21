"""Expose the same ordinary tools and one real read-only installed P tool."""

import json
from pathlib import Path

from common import FORMAL, SLOTS, load, load_retained


bridge = load_retained('_perf050_dense_common_bridge', FORMAL / 'bridge.py')
if bridge.SLOTS is not SLOTS:
    raise ValueError('bridge_loaded_wrong_experiment')
DISCOVERY, TOOL_LIMIT, MAX_FRAME, PRODUCT_TOOL = (
    bridge.DISCOVERY, bridge.TOOL_LIMIT, bridge.MAX_FRAME, bridge.PRODUCT_TOOL,
)
TOOLS, TOOL_NAMES, VIEWS = bridge.TOOLS, bridge.TOOL_NAMES, bridge.VIEWS
SOURCE_REGION = bridge.SOURCE_REGION
encoded, save, remaining = bridge.encoded, bridge.save, bridge.remaining
IMAGES = bridge._prior.IMAGES


class Owner(bridge.Owner):
    def handle(self, request, attempt=None):
        reply = super().handle(request, attempt)
        if request.get('method') == 'initialize' and reply is not None:
            reply['result']['serverInfo']['name'] = 'perf050-readonly-product-transfer'
        return reply

    def images(self, refs, row):
        result = []
        for ref in refs:
            spec, directory = self.runtime.image_specification(ref)
            slot = self.runtime.folder.resolve(strict=True)
            declared = Path(directory) / spec['file']
            path = declared.resolve(strict=True)
            if (not declared.is_absolute() or path != declared or not path.is_relative_to(slot)
                    or path.suffix.lower() != '.png'):
                raise ValueError('current_slot_original_png_path_required')
            try:
                image, receipt = IMAGES.image_content(spec, directory, self.deadline_ns)
            except IMAGES.ImageContentError as error:
                row['image_attachments'].append(error.receipt)
                raise
            row['image_attachments'].append(receipt)
            delivery = {'local_image_path': path.as_posix(), 'image_sha256': receipt['PNG_sha256']}
            row.setdefault('local_image_delivery', []).append({'ref': ref, **delivery})
            caption = f'{ref} ({spec["width"]}x{spec["height"]}, image/png)\n'
            result.extend([{'type': 'text', 'text': caption + json.dumps(delivery, ensure_ascii=False)}, image])
        return result
