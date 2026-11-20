"""Print a retrospective v5/v6 public caller-obligation audit. Requires the built caller-obligation CLI."""
from collections import Counter
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / 'target/caller-obligation'


def load_corpus(directory):
    tasks = []
    for name in ('cases_a', 'cases_b'):
        spec = spec_from_file_location(name, directory / (name + '.py'))
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        tasks.extend(module.TASKS)
    return tasks


def literal(arg):
    return str(arg).lower()


def call(name, args):
    return f'{name}({", ".join(map(literal, args))})'


def failures(directory):
    archive = directory / 'results' / (directory.name + '.jsonl')
    meta, *rows = map(json.loads, archive.read_text().splitlines())
    tasks = load_corpus(directory)
    digest = sha256(json.dumps(tasks, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != meta['corpus_sha256']:
        raise ValueError(f'Corpus hash mismatch for {archive}')
    by_id = {t['id']: t for t in tasks}
    roster = {(key, arm) for key in by_id for arm in meta['conditions']}
    if {(r['task'], r['condition']) for r in rows} != roster or len(rows) != len(roster):
        raise ValueError(f'Incomplete or duplicated assignments for {archive}')
    categories, cases = Counter(), Counter()
    for row in rows:
        task = by_id[row['task']]
        attempt = row['attempts'][0]
        status = attempt['public_outcome']
        if status in ('pass', 'check_error'):
            categories[status] += 1
            continue
        if status != 'wrong_answer':
            raise ValueError(f'Unclassified first failure {status!r} in {archive}')
        diagnostic = re.fullmatch(r'(.+) returned (-?\d+)\. Expected (-?\d+)\.', attempt['public_detail'])
        if not diagnostic:
            raise ValueError(f'Unrecognized public mismatch: {attempt["public_detail"]!r}')
        failed_call, actual, expected = diagnostic.groups()
        matching = [(name, args, want) for name, args, want in task['public']
                    if call(name, args) == failed_call.lower() and want == int(expected)]
        if len(matching) != 1 or int(actual) == int(expected):
            raise ValueError(f'Public assertion mismatch: {failed_call}')
        name, args, want = matching[0]
        if 'public_failed_entry' in attempt and attempt['public_failed_entry'] != name:
            raise ValueError(f'Archived caller label disagrees with {failed_call}')
        if name == task['target']:
            categories['target mismatch'] += 1
        else:
            categories['caller mismatch'] += 1
            cases[(task['id'], name, tuple(args), want)] += 1
    return by_id, categories, cases


def derive(workdir, task, caller, args, expected):
    path = workdir / 'baseline.gpp'
    path.write_text('module audit;\n' + task['starter']['gpp'] + task['callers']['gpp']
                    + '\npub fn main() -> I64 !{} { return 0; }\n')
    # This process receives only the checked starter module, caller/target names and public assertion.
    result = subprocess.run([BINARY, path, '--caller', caller, '--target', task['target'], '--expect',
                             str(expected), '--', *map(literal, args)], check=True, capture_output=True,
                            text=True, timeout=3)
    return json.loads(result.stdout)


def frozen_value(task, variant, args):
    # Trusted, hash-checked offline reference/starter code. No snippets from model responses are executed.
    namespace = {}
    exec(task[variant]['python'] + task['callers']['python'], namespace)
    return namespace[task['target']](*args)


def audit():
    studies = [('v5', ROOT / 'bench/maintenance'), ('v6', ROOT / 'bench/adaptive')]
    summaries = {}
    recorded = []
    with TemporaryDirectory(prefix='obligation-audit-') as temp:
        for study, directory in studies:
            tasks, summary, cases = failures(directory)
            summaries[study] = summary
            for (task_id, caller, args, expected), arms in sorted(cases.items()):
                task = tasks[task_id]
                result = derive(Path(temp), task, caller, args, expected)
                recorded.append((study, task, caller, args, expected, arms, result))
    # Complete all derivations before querying either frozen implementation.
    records = []
    for study, task, caller, args, expected, arms, result in recorded:
        record = {'study': study, 'task': task['id'], 'caller': call(caller, args), 'expected': expected,
                  'arms': arms, 'status': result['status']}
        if result['status'] == 'exact':
            target_args, answer = tuple(result['args']), result['expected']
            if result['target'] != task['target']:
                raise ValueError('Wrong target name in obligation')
            reference = frozen_value(task, 'reference', target_args)
            starter = frozen_value(task, 'starter', target_args)
            record.update(obligation=call(task['target'], target_args) + f' = {answer}',
                          verified=reference == answer, changed=starter != answer,
                          distinct_value=expected != answer,
                          overlap=(task['target'], target_args, answer) in task['public'])
        elif result['status'] == 'unsupported':
            record['reason'] = result['reason']
        else:
            raise ValueError(f'Unexpected obligation result: {result}')
        records.append(record)
    return summaries, records


def report(summaries, rows):
    print('# Archived public caller failures and exact obligations\n')
    print('These are retrospective coverage results across all v5 and v6 arms. Each assigned task and arm contributes its first attempt. A repeated failure means that several arms failed the same first public assertion on the same task.\n')
    print('| Study | Assignments | Public pass | Check error | Target mismatch | Caller mismatch | Distinct caller cases | Exact per arm | Exact per case |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    for study, summary in summaries.items():
        cases = [r for r in rows if r['study'] == study]
        exact = [r for r in cases if r['status'] == 'exact']
        print(f"| {study} | {sum(summary.values())} | {summary['pass']} | {summary['check_error']} | {summary['target mismatch']} | {summary['caller mismatch']} | {len(cases)} | {sum(r['arms'] for r in exact)} | {len(exact)} |")
    print('\n| Study | Public caller assertion | Arms | Derived target obligation or reason | Target differs from starter | Already public directly |')
    print('|---|---|---:|---|---|---|')
    for row in rows:
        result = row.get('obligation', row.get('reason'))
        def label(k):
            return ('Yes' if row[k] else 'No') if k in row else '—'
        print(f"| {row['study']} | `{row['caller']} = {row['expected']}` | {row['arms']} | {result} | {label('changed')} | {label('overlap')} |")
    exact = [r for r in rows if r['status'] == 'exact']
    arms = sum(r['arms'] for r in rows)
    ex_arms = sum(r['arms'] for r in exact)
    print(f"\n{len(exact)} of {len(rows)} distinct caller assertions yielded an exact obligation ({ex_arms} of {arms} arm-level failures). All derivations ran before the post hoc reference comparisons. {sum(r['verified'] for r in exact)} of {len(exact)} distinct results matched the frozen Python target at the derived input. {sum(r['distinct_value'] for r in exact)} inferred target values differed numerically from the caller expectation. {sum(r['overlap'] for r in exact)} obligations duplicated a direct public target assertion.")
    print('\nReading the eight declined caller paths identifies six that compare the unknown target result before choosing a branch, one that takes the unknown modulo seven, and one that combines two distinct target inputs. Some guarded paths could still admit an exact solution. For example, the DNS review flag equals one only when the serial ordering result equals two. The current affine analysis declines that comparison.')
    print('\nThe audit supplied each obligation process with the checked baseline GPT++ module and one recorded public assertion. It used the frozen reference and starter afterward to check agreement and identify changed results. All 19 extra arm-level observations repeat one of the 12 caller assertions. Repair effectiveness requires a prospective trial.')
    print('\nReproduce with `python3 -B bench/policy/audit_obligations.py` after building the [obligation CLI](../../tools/caller_obligation.md). [v5 raw trials](../maintenance/results/maintenance.jsonl) · [v6 raw trials](../adaptive/results/adaptive.jsonl)')


if __name__ == '__main__':
    summaries, rows = audit()
    report(summaries, rows)
    if any(row.get('verified') is False for row in rows):
        raise SystemExit('Derived obligation disagrees with the frozen reference.')
