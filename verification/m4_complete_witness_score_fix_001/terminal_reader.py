"""Bind only the current single-formal producer's saved terminal fields."""


SCHEMA = 'complete-witness-single-formal-v1'


def terminal_binding(run_result, consumer):
    failed = []

    def check(field, condition):
        if not condition:
            failed.append(field)

    if type(run_result) is not dict:
        return {'schema': 'complete-witness-terminal-binding-v1', 'passed': False,
                'failed_fields': ['RUN_RESULT']}
    check('RUN_RESULT.schema', run_result.get('schema') == SCHEMA)
    for name in ('planned_routes', 'actual_routes', 'actual_CLI_processes'):
        check('RUN_RESULT.' + name,
              type(run_result.get(name)) is int and run_result[name] == 1)
    check('RUN_RESULT.outer_retries',
          type(run_result.get('outer_retries')) is int and run_result['outer_retries'] == 0)
    check('RUN_RESULT.execution_state', run_result.get('execution_state') == 'completed')
    check('RUN_RESULT.launcher_succeeded', run_result.get('launcher_succeeded') is True)
    check('RUN_RESULT.terminal_errors',
          type(run_result.get('terminal_errors')) is list and run_result['terminal_errors'] == [])

    records = run_result.get('records')
    one_record = type(records) is list and len(records) == 1 and type(records[0]) is dict
    check('RUN_RESULT.records', one_record)
    if one_record:
        row = records[0]
        check('RUN_RESULT.records[0].slot', row.get('slot') == 'P1')
        check('RUN_RESULT.records[0].group', row.get('group') == 'P')
        check('RUN_RESULT.records[0].outer_valid_completion', row.get('outer_valid_completion') is True)

    if type(consumer) is not dict:
        check('CONSUMER', False)
    else:
        check('CONSUMER.valid_completion', consumer.get('valid_completion') is True)
        for name in ('runtime_binding', 'runtime_exit'):
            proof = consumer.get(name)
            check('CONSUMER.' + name + '.confirmed',
                  type(proof) is dict and proof.get('confirmed') is True)
    return {'schema': 'complete-witness-terminal-binding-v1', 'passed': not failed,
            'failed_fields': failed}
