"""Apply the isolated first-packet treatment to the established owned runtime."""

from copy import deepcopy
from pathlib import Path

from common import DETAILS, DUAL, append, load_retained, read
from treatment import Treatment


previous = load_retained('_first_packet_retained_runtime', DUAL/'harness/runtime.py')
transport = previous.previous.transport


class Runtime(previous.Runtime):
    def capture_initial(self):
        receipt = super().capture_initial()
        snapshot = read(Path(receipt['path']))
        objects = {item['name']: item for item in snapshot['objects']}
        self.target = objects['Obj_09']
        self.reference = objects['Obj_04']
        self.treatment = Treatment(DETAILS[self.label], self.target['object_id'], self.reference['object_id'])
        self.known_current_refs = []
        self.current_generation = None
        return receipt

    def remember_current_reference(self, request_row):
        archive = request_row.get('producer_archive')
        if not archive:
            return
        value = read(Path(archive['path']))
        binding = value.get('binding', {})
        if not isinstance(binding, dict):
            return
        state = binding.get('capture_state')
        if type(state) is not dict or not {'instance_id','epoch','revision'} <= set(state):
            return
        generation = {key: state[key] for key in ('instance_id','epoch','revision')}
        if generation != self.current_generation:
            self.known_current_refs.clear()
            self.current_generation = generation
        ref = value.get('region_ref')
        if (value.get('result_kind') == 'source_region' and isinstance(ref, dict)
                and ref.get('host_id') == self.target['object_id']
                and ref.get('instance_id') == self.target['instance_id']
                and ref.get('capture_generation') == generation
                and ref.get('document_epoch') == binding.get('document_epoch')
                and ref.get('source_triangle_indices') == [0,1]
                and ref not in self.known_current_refs):
            self.known_current_refs.append(deepcopy(ref))

    def public_request(self, arguments):
        number = len(self.public_requests) + 1
        downstream, verdict = self.treatment.arguments(arguments, self.known_current_refs)
        receipt = {'index': number, 'original_arguments': deepcopy(arguments), 'product_arguments': deepcopy(downstream),
                   'decision': verdict}
        response = None
        try:
            response = super().public_request(downstream)
            return response
        finally:
            receipt['outcome'] = self.treatment.accept(verdict, response)
            append(self.folder/'FIRST_PACKET_TREATMENT.jsonl', receipt)
            if len(self.public_requests) >= number:
                self.remember_current_reference(self.public_requests[number-1])
