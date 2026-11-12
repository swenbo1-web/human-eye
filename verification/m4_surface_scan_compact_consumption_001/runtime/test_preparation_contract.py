"""Offline source, schema, sampling and CLI-isolation preparation checks."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def function_ast(path,name):
    tree = ast.parse(path.read_bytes())
    return ast.dump(next(node for node in tree.body if isinstance(node,ast.FunctionDef)
                         and node.name == name),include_attributes=False)


class PreparationTests(unittest.TestCase):
    def test_qualified_input_promises_and_score_materials(self):
        seal = read(BATCH/'QUALIFICATION_SEAL.json')
        self.assertEqual(len(seal['existing_promises']),9)
        for name,digest in seal['existing_promises'].items():
            self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),digest)
        for name,expected in [('ACTUAL_SNAPSHOT.json','f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b'),
            ('TRUTH.json','a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7')]:
            self.assertEqual(hashlib.sha256((BATCH/'scoring'/name).read_bytes()).hexdigest(),expected)

    def test_common_prompt_is_exact_and_contains_no_answer_fields(self):
        prompt = (BATCH/'input/PROMPT.txt').read_bytes()
        self.assertEqual(hashlib.sha256(prompt).hexdigest(),
            '6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc')
        text = prompt.decode()
        for forbidden in ('Obj_', '276','71','24','surface_scan','human_eye_scene_observe',
                          'scoring/','oracle','D:/','C:/'):
            self.assertNotIn(forbidden,text)

    def test_complete_observe_schemas_are_their_frozen_real_tools_lists(self):
        cases = (
            ('O', '860b87138d40de9cc08b01c947dd864d58da9295',
             'verification/m4_surface_scan_001_opt1/engineering/run_01/pair_01/B/TOOLS.json'),
            ('C', '6ab4e53409e539c71a377f48708f2f8725db6dde',
             'verification/m4_surface_scan_compact_facts_001/engineering/run_01/TOOLS.json'),
        )
        for profile, commit, name in cases:
            raw = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
            tools = json.loads(raw)['result']['tools']
            actual = [tool for tool in tools if tool['name'] == 'human_eye_scene_observe']
            self.assertEqual(read(BATCH / ('schemas/' + profile + '_PUBLIC_TOOLS.json')), actual)
            modes = actual[0]['inputSchema']['properties']['query']['properties']['mode']['enum']
            for mode in ('surface_scan', 'mesh_surface', 'overview'):
                self.assertIn(mode, modes)
        old = read(BATCH / 'schemas/O_PUBLIC_TOOLS.json')[0]
        current = read(BATCH / 'schemas/C_PUBLIC_TOOLS.json')[0]
        self.assertNotEqual(old, current)
        self.assertEqual(old['inputSchema']['properties']['response_detail']['default'], 'full')
        self.assertNotIn('default', current['inputSchema']['properties']['response_detail'])

    def test_nine_fixed_slots_and_private_random_labels(self):
        sequence = read(BATCH / 'SEQUENCE.json')['sequence']
        self.assertEqual([row['cell'] for row in sequence], ['N1','O1','C1','O2','C2','N2','C3','N3','O3'])
        self.assertEqual([row['group'] for row in sequence], ['N','O','C','O','C','N','C','N','O'])
        self.assertEqual([row['round'] for row in sequence], [1,1,1,2,2,2,3,3,3])
        rows = read(BATCH / 'private/ANON_MAP.json')['rows']
        self.assertEqual([row['cell'] for row in rows], [row['cell'] for row in sequence])
        self.assertEqual(len({row['anonymous_id'] for row in rows}), 9)
        for row in rows:
            self.assertRegex(row['anonymous_id'], r'^answer_[0-9a-f]{16}$')
        common = read(BATCH / 'schemas/COMMON_NATIVE.json')
        self.assertEqual(read(BATCH / 'schemas/N_CONSUMER_TOOLS.json'), [common])
        for profile in ('O', 'C'):
            self.assertEqual(read(BATCH / ('schemas/' + profile + '_CONSUMER_TOOLS.json')),
                             [common, *read(BATCH / ('schemas/' + profile + '_PUBLIC_TOOLS.json'))])

    def test_each_installation_keeps_its_source_and_common_python(self):
        source = read(BATCH / 'preflight/SOURCE_BINDING.json')['profiles']
        ready = {name: read(BATCH / ('installations/' + name + '_READY.json')) for name in ('O', 'C')}
        self.assertEqual(ready['O']['dependency_python'], ready['C']['dependency_python'])
        self.assertNotEqual(ready['O']['source_sha256'], ready['C']['source_sha256'])
        self.assertNotEqual(ready['O']['entry'], ready['C']['entry'])
        for name in ('O', 'C'):
            self.assertEqual(ready[name]['source_count'], 138)
            self.assertEqual(ready[name]['source_sha256'], source[name]['source_sha256'])
            self.assertEqual(ready[name]['commit'], source[name]['product_commit'])
            for item in source[name]['source_manifest']:
                path = Path(ready[name]['install_root']) / item['path']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item['sha256'])
                if name == 'C':
                    self.assertEqual(path.read_bytes(), (ROOT / item['path']).read_bytes())
        self.assertFalse(source['O']['current_checkout_equal'])
        self.assertTrue(source['C']['current_checkout_equal'])

    def test_cli_executable_is_the_previous_frozen_binary(self):
        previous = read(ROOT / 'verification/m4_surface_scan_consumption_001/PLAN.json')
        record = read(BATCH / 'preflight/CLI_REUSE.json')
        self.assertEqual(record['sha256'], previous['CLI_sha256'])
        self.assertEqual(hashlib.sha256(Path(record['frozen_executable']).read_bytes()).hexdigest(), record['sha256'])
        self.assertEqual(record['new_CLI_processes'], 0)

    def test_consumer_settings_keep_reused_isolation_and_model(self):
        previous = ROOT/'verification/m4_grooved_rail_consumption_001/runtime/consumer_transport.py'
        current = HERE/'consumer_transport.py'
        self.assertEqual(function_ast(current,'settings'),function_ast(previous,'settings'))
        spec = importlib.util.spec_from_file_location('_preflight_pure_transport',current)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        settings = module.settings()
        self.assertEqual(settings['model'],'gpt-6.1-sol')
        self.assertEqual(settings['model_reasoning_effort'],'medium')
        self.assertFalse(settings['features.hooks'])
        self.assertFalse(settings['features.memories'])
        self.assertFalse(settings['features.shell_tool'])
        self.assertEqual(settings['approval_policy'],'never')
        self.assertEqual(settings['web_search'],'disabled')

    def test_recorded_local_cli_help_supports_reused_flags(self):
        help_text = (BATCH/'preflight/CLI_EXEC_HELP.txt').read_text(encoding='utf8')
        for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--strict-config',
                     '--json','--skip-git-repo-check','--output-last-message','--model'):
            self.assertIn(flag,help_text)
        self.assertIn('codex-cli',(BATCH/'preflight/CLI_VERSION.txt').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()
