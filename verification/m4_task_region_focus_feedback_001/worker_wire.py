"""Record exact raw bytes on the installed BlenderProcessHost pipe seam."""
import hashlib
import io
import json
import time
from pathlib import Path


class RecordedPipe(io.RawIOBase):
    def __init__(self, pipe, capture, events, direction):
        super().__init__()
        self.pipe = pipe
        self.capture = capture
        self.events = events
        self.direction = direction
        self.offset = 0

    def readable(self):
        return self.pipe.readable()

    def writable(self):
        return self.pipe.writable()

    def fileno(self):
        return self.pipe.fileno()

    def _record(self, buffer, size, started):
        if size:
            self.capture.write(memoryview(buffer)[:size])
        if size is not None:
            self.events.append({'direction': self.direction, 'offset': self.offset, 'bytes': size,
                                'started_ns': started, 'ended_ns': time.perf_counter_ns()})
            self.offset += size

    def readinto(self, buffer):
        started = time.perf_counter_ns()
        size = self.pipe.readinto(buffer)
        self._record(buffer, size, started)
        return size

    def write(self, buffer):
        started = time.perf_counter_ns()
        size = self.pipe.write(buffer)
        self._record(buffer, size, started)
        return size

    def close(self):
        if not self.closed:
            try:
                self.pipe.close()
            finally:
                self.capture.close()
                super().close()


class WorkerWire:
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir()
        self.events = []
        self.protocol = b'HUMAN_EYE_RPC:'

    def attach(self, process):
        self._attach_direction(process, 'stdin', 'TX', io.BufferedWriter)
        self._attach_direction(process, 'stdout', 'RX', io.BufferedReader)

    def _attach_direction(self, process, name, direction, buffer):
        stream = getattr(process, name)
        options = {k: getattr(stream, k) for k in ('encoding', 'errors', 'line_buffering', 'write_through')}
        raw = stream.detach().detach()
        capture = (self.folder / (direction + '.bin')).open('xb')
        recorder = RecordedPipe(raw, capture, self.events, direction)
        setattr(process, name, io.TextIOWrapper(buffer(recorder), **options))

    def publish(self):
        result = {'raw_event_spans': sorted(self.events, key=lambda x: x['ended_ns']), 'lines': {}}
        for direction in ('TX', 'RX'):
            file = self.folder / (direction + '.bin')
            parsed = []
            offset = 0
            for line in file.read_bytes().splitlines(keepends=True) if file.is_file() else ():
                row = {'offset': offset, 'bytes': len(line), 'sha256': hashlib.sha256(line).hexdigest(),
                       'terminated': line.endswith(b'\n'), 'kind': 'non_rpc'}
                offset += len(line)
                value = line if direction == 'TX' else line.removeprefix(self.protocol)
                if direction == 'TX' or line.startswith(self.protocol):
                    try:
                        obj = json.loads(value)
                        row.update(id=obj['id'], kind='request' if direction == 'TX' else 'response')
                        if direction == 'TX':
                            row['command'] = obj['command']
                        else:
                            row['state'] = 'error' if 'error' in obj else 'result'
                    except (ValueError, TypeError, KeyError):
                        row['kind'] = 'malformed_rpc'
                parsed.append(row)
            result['lines'][direction] = parsed
        with (self.folder / 'INDEX.json').open('x', encoding='utf8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write('\n')
