"""Join the independent offline verdicts without changing their evidence."""

from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    sources = {}
    results = {}
    for name in ('ASSEMBLY_OFFLINE.json', 'DENSE_OFFLINE.json', 'COMPATIBILITY_OFFLINE.json'):
        path = HERE / name
        data = path.read_bytes()
        receipt = json.loads(data)
        entry = {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}
        results[name] = {'passed': receipt['passed'], 'sha256': entry['sha256']}
        for pin in (entry, *receipt.get('source_pins', [])):
            key = str(Path(pin['path']).resolve())
            if key in sources and sources[key] != pin:
                raise ValueError('conflicting_offline_input_identity/' + key)
            sources[key] = pin
    verdict = {'passed': all(item['passed'] is True for item in results.values()),
               'receipts': results, 'source_pins': list(sources.values())}
    with (HERE / 'OFFLINE_CONTROLS.json').open('x', encoding='utf-8', newline='\n') as output:
        json.dump(verdict, output, ensure_ascii=False, indent=2)
        output.write('\n')
    if not verdict['passed']:
        raise SystemExit('Offline qualification did not pass.')


if __name__ == '__main__':
    main()
