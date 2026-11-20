"""Check hand-authored policy patches offline against the frozen v7 fixtures.

These examples are evaluator controls. They are never included in scored prompts.
Run with target/empirical-venv/bin/python bench/policy/witnesses.py on the benchmark host.
"""
from run_policy import ROOT, Tools, evaluate, patch, source_for
from fresh import TASKS


# Each document adds rules above the original checked target without replacing its fallback.
WITNESSES = {
    'timesheet_overtime_premium': '''when eligible and hours > 40 => (2 * hours + hours - 40) * (rate // 2)
else => @keep''',
    'rail_delay_claim': '''when minutes >= 120 and not refunded => fare // 2
else => @keep''',
    'release_candidate_order': '''when patch_a == patch_b and rc_a != rc_b and (rc_a == -1 or (rc_b != -1 and rc_a > rc_b)) => 1
when patch_a == patch_b and rc_a != rc_b => -1
else => @keep''',
    'cron_restricted_days': '''when wanted_day >= 0 and wanted_weekday >= 0 and (day == wanted_day or weekday == wanted_weekday) => 1
else => @keep''',
    'permission_class_precedence': '''when owner => owner_mask
else => @keep''',
    'nullable_unique_key': '''when nulls_equal and tenant_a == tenant_b and code_a == -1 and code_b == -1 => 1
else => @keep''',
    'tenpin_final_rack': '''when frame == 10 and balls == 1 and first == 10 => 10
when frame == 10 and balls == 2 and first == 10 and second < 10 => 10 - second
when frame == 10 and balls == 2 and (first == 10 or first + second == 10) => 10
else => @keep''',
    'midi_zero_velocity_release': '''when status >= 144 and status <= 159 and velocity == 0 => -1
else => @keep''',
}


def main():
    if set(WITNESSES) != {task['id'] for task in TASKS}:
        raise ValueError('The witness set must cover the entire corpus.')
    tools = Tools(ROOT, ROOT / 'target/debug/gpp')
    checked = 0
    for task in TASKS:
        name = task['id']
        # Reproduce the scored rule arm's fixed prefix and protected suffix.
        policy = WITNESSES[name]
        if not policy.startswith('when ') or not policy.endswith('\nelse => @keep'):
            raise ValueError(f'{name}: missing fixed edit boundaries')
        insertion = policy.removeprefix('when ').removesuffix('\nelse => @keep')
        status, detail, source = patch(tools, task, 'gpp_rules', source_for(task, 'gpp'), insertion)
        if status != 'pass':
            raise ValueError(f'{name}: {status} {detail}')
        for split in ('public', 'heldout'):
            cases = task[split]
            status, detail = evaluate(tools, 'gpp', source, cases)
            if status != 'pass':
                raise ValueError(f'{name} {split}: {status} {detail}')
            checked += len(cases)
        print(f'{name}: {len(task["public"])} public, {len(task["heldout"])} withheld passed')
    print(f'{len(TASKS)} policy witnesses passed {checked} cases.')


if __name__ == '__main__':
    main()
