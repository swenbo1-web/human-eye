"""One offline library cross-check of the saved-format reader, without product."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output = HERE / 'admin/DECODER_CROSSCHECK.json'
    if output.exists():
        raise FileExistsError('single_offline_decoder_crosscheck_already_exists')

    def guard(event, arguments):
        if event in ('subprocess.Popen', 'os.system', 'socket.connect', 'socket.bind'):
            raise RuntimeError('offline_decoder_process_network_forbidden')
        if event == 'import' and str(arguments[0]).split('.')[0] in ('human_eye_plugin', 'human_eye_module1_operators', 'bpy'):
            raise RuntimeError('offline_decoder_product_import_forbidden')

    sys.addaudithook(guard)
    binding_path = HERE.with_name('m4_view_reuse_001') / 'build/RUN_BINDING.json'
    binding = json.loads(binding_path.read_bytes())
    sys.path.insert(0, binding['dependency_root'])
    import numpy as np
    import PIL
    from PIL import Image

    specification = importlib.util.spec_from_file_location('_offline_decoder_oracle', HERE / 'oracle.py')
    oracle = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(oracle)
    result_path = Path('D:/he_view_reuse_001/run/integration_01/product_then_reuse/o/product_call_01/SERVICE_RESULT.json')
    frame = json.loads(result_path.read_bytes())['frames'][0]
    png = Path(frame['image_path'])
    npz = Path(frame['arrays_path'])
    with Image.open(png) as image:
        image.load()
        library_rgb = image.convert('RGB').tobytes()
    checks = {'PNG_RGB_all_bytes': oracle.png_rgb(png) == library_rgb}
    with zipfile.ZipFile(npz) as raw_archive, np.load(npz, allow_pickle=False) as library:
        for name in library.files:
            header, payload = oracle.npy(raw_archive.read(name + '.npy'))
            values = library[name]
            checks[name] = (header['shape'] == values.shape
                            and header['descr'] == values.dtype.str
                            and header['fortran_order'] is False
                            and payload == values.tobytes(order='C'))
    result = {
        'schema': 'complete-witness-offline-decoder-crosscheck-v1',
        'passed': all(checks.values()),
        'checks': checks,
        'one_saved_frame': {'PNG': str(png), 'PNG_sha256': digest(png),
                            'NPZ': str(npz), 'NPZ_sha256': digest(npz)},
        'source_service_result': {'path': str(result_path), 'sha256': digest(result_path)},
        'numpy': {'path': np.__file__, 'version': np.__version__, 'init_sha256': digest(np.__file__)},
        'pillow': {'path': PIL.__file__, 'version': PIL.__version__, 'init_sha256': digest(PIL.__file__)},
        'oracle_sha256': digest(HERE / 'oracle.py'),
        'checker_sha256': digest(__file__),
        'new_product_raster_model_calls': 0,
        'scope': 'Exact bytes and headers of one already sealed VIEW512 frame. No new scene, pixel alteration, rendering or qualification.'
    }
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'sha256': digest(output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
