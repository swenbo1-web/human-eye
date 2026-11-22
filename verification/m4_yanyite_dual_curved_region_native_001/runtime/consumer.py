"""Run the retained cold ephemeral CLI with the shared natural task."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2]/'perf050_readonly_product_pilot_001/consumer/driver.py'
_text = _source.read_text(encoding='utf8')
for _old,_new in (
    ("HARNESS = NS / 'harness'","HARNESS = NS / 'native'"),
    ("'PERF050-READONLY-PRODUCT-PILOT-001-'","'M4-YANYITE-DUAL-CURVED-REGION-NATIVE-001-'"),
):
    if _text.count(_old)!=1:
        raise ValueError('retained_consumer_anchor_changed')
    _text = _text.replace(_old,_new)
exec(compile(_text,str(_source),'exec'))
