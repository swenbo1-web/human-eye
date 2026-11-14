# Root offline checker correction

The first root_contract_check.py execution exited 1 before producing its result file. ast.literal_eval was applied to the entire tool definition; an enum built with list(VIEW_NAMES) is an AST Call and is not a literal. The traceback ended with `ValueError: malformed node or string on line 71: <ast.Call ...>`.

The checker was narrowed to the literal name/description fields it actually examines. It does not import or execute the bridge or product. This is a reviewer script error, not a product or formal-slot failure; the original tool transcript retains the traceback. The corrected run and its actual counts are reported separately.
