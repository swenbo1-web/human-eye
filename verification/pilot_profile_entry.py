"""QA-only observation of the unchanged fixed installed reader.

Function spans overlap; complete subprocess wall time is the cost denominator.
No production function is patched and no additional worker command is sent.
"""
import collections
import json
import os
from pathlib import Path
import runpy
import sys
import time


def main():
    entry, timing, *args = sys.argv[1:]
    active = {}
    records = collections.defaultdict(lambda: [0, 0])
    names = {'__init__', '_inspect', 'validate', 'analyze', 'describe_anchors',
             'close', 'verify_inputs', 'bind_selection', 'bind_anchor_selection',
             'bind_context_selection', '_geometry_rows', 'encoded', 'write_bytes',
             'write_text', 'dump', 'dumps', 'run_reader'}

    def observe(frame, event, arg):
        filename = frame.f_code.co_filename.replace('\\', '/')
        if frame.f_code.co_name not in names:
            return
        if '/human_eye_plugin/' not in filename and frame.f_code.co_name not in {'write_bytes', 'write_text', 'dump', 'dumps'}:
            return
        key = id(frame)
        if event == 'call':
            active[key] = (time.perf_counter_ns(), filename + ':' + frame.f_code.co_name)
        elif event == 'return' and key in active:
            start, label = active.pop(key)
            records[label][0] += 1
            records[label][1] += time.perf_counter_ns() - start

    sys.argv = [entry, *args]
    started = time.perf_counter_ns()
    sys.setprofile(observe)
    try:
        runpy.run_path(entry, run_name='__main__')
    finally:
        sys.setprofile(None)
        value = dict(schema='readonly-pilot-profile-v1', fixed_entry=entry,
                     entry_sha256=__import__('hashlib').sha256(Path(entry).read_bytes()).hexdigest(),
                     wrapper_elapsed_ns=time.perf_counter_ns() - started,
                     spans={k: dict(calls=v[0], inclusive_ns=v[1]) for k, v in records.items()},
                     scope='same QA instrumentation for all arms; inclusive spans overlap; not uninstrumented latency',
                     unseparated=['threaded transport versus worker computation', 'individual OS flush latency'])
        with Path(timing).open('x', encoding='utf8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())


if __name__ == '__main__':
    main()
