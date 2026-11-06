import hashlib, importlib.util
from pathlib import Path
here = Path(__file__).resolve().parent
source = here / "extract_usage.py"
assert hashlib.sha256(source.read_bytes()).hexdigest() == "86ecb964892ee6be2ce705b28e2152e7e371fd4e3c3771060ba4b30c06458242"
spec = importlib.util.spec_from_file_location("perf000_usage_reused", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE, module.BASE, module.PLAN_SHA256 = here, here.parent, "921298e2da3275812d7a7a64befa42ce91aa95022192534927c4a373423e4f7e"
module.main()
