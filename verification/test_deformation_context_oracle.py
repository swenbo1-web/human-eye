"""Small analytic task-core checks for the independent context oracle."""
import hashlib,unittest
from verification import deformation_context_oracle as oracle


class ContextOracleTests(unittest.TestCase):
    def test_publication_ascii_and_identity_utf8_are_separate_protocols(self):
        value=dict(部位='左臂')
        self.assertEqual(oracle.digest(value),hashlib.sha256('{"部位":"左臂"}'.encode('utf8')).hexdigest())
        self.assertTrue(oracle.payload(value).isascii())
        self.assertNotEqual(oracle.canonical(value),'{"部位":"左臂"}'.encode('utf8'))

    def test_focus_empty_precedes_background_measurability(self):
        self.assertEqual(oracle.primary_gate(dict(core_members=[],core_facts={},primary_surplus=9),dict(max_surplus_members=0)),'focus_empty')

    def test_unknown_core_cannot_be_diluted_by_measurable_context(self):
        value=dict(core_members=[0],core_facts={0:dict(state='unknown')},primary_surplus=8)
        self.assertEqual(oracle.primary_gate(value,dict(max_surplus_members=0)),'focus_all_unknown')

    def test_collapsed_core_is_a_fact_not_an_empty_or_all_unknown_region(self):
        value=dict(core_members=[0],core_facts={0:dict(state='collapsed')},primary_surplus=8)
        self.assertEqual(oracle.primary_gate(value,dict(max_surplus_members=0)),'needs_candidates')

    def test_normal_core_avoids_optional_work(self):
        value=dict(core_members=[0],core_facts={0:dict(state='measured')},primary_surplus=0)
        self.assertEqual(oracle.primary_gate(value,dict(max_surplus_members=0)),'within_surplus_budget')

    def test_canonical_bytes_include_one_lf_and_full_trace(self):
        plain=dict(region_query=dict(matched_triangle_indices=list(range(100))))
        traced=dict(region_query=dict(matched_triangle_indices=[0]),context_quality=dict(trace='x'*800))
        self.assertTrue(oracle.payload(plain).endswith(b'\n'));self.assertFalse(oracle.payload(plain).endswith(b'\n\n'))
        self.assertGreater(len(oracle.payload(traced)),len(oracle.payload(plain)))

    def test_reduced_surplus_alone_cannot_pass_net_byte_gate(self):
        primary=dict(region_query=dict(matched_triangle_indices=[0,1,2]))
        selected=dict(region_query=dict(matched_triangle_indices=[0]),context_quality=dict(trace='x'*500))
        expected=dict(core_members=[0],primary_surplus=2)
        with self.assertRaises(AssertionError):oracle.required_gain(primary,selected,expected,dict(max_surplus_members=0,min_saved_bytes=256))


if __name__=='__main__':unittest.main()
