"""Replay archived responses in the shipping maintenance CLI; print a Markdown parity report."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import run_policy as study
import run_transfer as transfer
from evaluate_project import ENTRY, MODULE, evaluate, source_for
from fresh import TASKS as DEVELOPMENT
from test_propose import mock_ollama
from upstream import TASKS as TRANSFER

HERE, ROOT = study.HERE, study.ROOT
GPP = ROOT / 'target/debug/gpp'


def json_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def public_file(path, task):
    path.write_text(json.dumps([dict(function=name, args=args, expected=want)
                                for name, args, want in task['public']]))


def generation_fields(request, star):
    if star:
        if request.get('raw') is not True or 'suffix' in request:
            raise ValueError('StarCoder2 replay did not use raw FIM')
        wire = request['prompt']
        if not wire.startswith('<fim_prefix>') or not wire.endswith('<fim_middle>'):
            raise ValueError('Missing prefix/middle transport markers')
        return tuple(wire.removeprefix('<fim_prefix>').removesuffix('<fim_middle>').rsplit('<fim_suffix>', 1))
    if any(key in request for key in ('raw', 'system', 'template')):
        raise ValueError('Qwen replay did not use the installed suffix template')
    return request['prompt'], request['suffix']


def normalized_inputs(task, arm, source, row, i, is_transfer):
    if not i:
        return study.render(task, arm, source)
    prev = row['attempts'][i - 1]
    if is_transfer:
        prompt, suffix, note = transfer.feedback(task, arm, source, (
            prev['response'], prev['public_detail'], prev['public_failed_entry']))
        if note != row['attempts'][i]['obligation']:
            raise ValueError('Normalized caller changed the derived obligation')
        return prompt, suffix
    return study.render(task, arm, source, (prev['response'], prev['public_detail']))


def replay(tools, meta, row, task, is_transfer):
    model, arm, attempts = row['model'], row['condition'], row['attempts']
    star = model == 'starcoder2:3b'
    base = MODULE + source_for(task, 'gpp') + ENTRY
    with TemporaryDirectory(prefix='product-replay-') as temp:
        work = Path(temp)
        source, cases, fragment = [work / name for name in ('project.gpp', 'public.json', 'result.body')]
        source.write_text(base)
        public_file(cases, task)
        normalized = subprocess.check_output([GPP, 'ast', source], text=True)
        normalized = normalized.split('\n', 1)[1].rsplit('\npub fn main()', 1)[0].strip() + '\n'
        options = ['--prepend'] if arm == 'gpp_guard' else []
        if is_transfer:
            options += ['--caller-obligation', transfer.HELPER]
        defaults = '\n'.join('stop ' + json.dumps(v) for v in meta['model_default_stops'][model])
        # Only fixed archived response strings and metadata reach the loopback fixture.
        with mock_ollama([a['response'] for a in attempts], model_name=model,
                         digest=meta['model_digests'][model], infill=not star, parameters=defaults) as (port, calls):
            run = subprocess.run([sys.executable, '-B', ROOT / 'tools/propose.py', source, '--function', task['target'],
                                  '--task', task['description'], '--maintenance', '--model', model, '--gpp', GPP,
                                  '--cases', cases, '--port', str(port), '-o', fragment, *options],
                                 capture_output=True, text=True, timeout=30)
        if source.read_text() != base:
            raise ValueError('CLI edited the input source')
        requests = [request for path, request in calls if path == '/api/generate']
        if len(requests) != len(attempts):
            raise ValueError(f'{task["id"]} {arm}: CLI requested {len(requests)} calls; archive has {len(attempts)}')
        prompts = []
        for i, (request, a) in enumerate(zip(requests, attempts)):
            if (request['options'] != a['sampling'] or request['model'] != model
                    or request['keep_alive'] != '3m' or request['stream'] is not False):
                raise ValueError('Model transport options differ from study')
            fields = generation_fields(request, star)
            prompts.append((fields == (a['prompt'], a['suffix']),
                            fields == normalized_inputs(task, arm, normalized, row, i, is_transfer)))
        # Withheld data enter only after the actual CLI has finished and published its native fragment.
        if run.returncode == 0:
            revision = subprocess.check_output([GPP, 'revision', source], text=True).strip()
            candidate = subprocess.check_output([GPP, 'edit', source, '--function', task['target'],
                                                '--body', fragment, '--expect', revision, '--stdout'], text=True)
            if not candidate.startswith(MODULE) or not candidate.endswith(ENTRY):
                raise ValueError('Published preview changed module/entry boundaries')
            status, _ = evaluate(tools, 'gpp', candidate[len(MODULE):-len(ENTRY)], task['heldout'])
            outcome = 'accepted' if status == 'pass' else 'heldout_' + status
        else:
            if fragment.exists() or 'failed validation' not in run.stderr and 'passed validation' not in run.stderr:
                raise ValueError(f'Unexpected CLI failure: {run.stderr}')
            if 'raised fault:' in run.stderr:
                outcome = 'runtime_error'
            elif ' returned ' in run.stderr and '; expected ' in run.stderr:
                outcome = 'wrong_answer'
            else:
                outcome = 'check_error'
        return dict(task=task['id'], model=model, arm=arm, outcome=outcome,
                    archive=attempts[-1]['outcome'], prompts=prompts, attempts=len(requests))


def run_archive(study_name, selected, tools):
    development = study_name == 'v7'
    tasks = DEVELOPMENT if development else TRANSFER
    path = HERE / 'results' / ('policy.jsonl' if development else 'transfer.jsonl')
    meta, *rows = map(json.loads, path.read_text().splitlines())
    if meta['corpus_sha256'] != json_hash(tasks):
        raise ValueError('Corpus changed since scoring')
    ids = {t['id']: t for t in tasks}
    roster = {(m, task, arm) for m in study.MODELS for task in ids for arm in study.ARMS}
    if len(rows) != len(roster) or {(r['model'], r['task'], r['condition']) for r in rows} != roster:
        raise ValueError(f'{study_name} archive incomplete')
    if not development and selected != meta['selected']:
        raise ValueError('Selected arm differs from transfer archive')
    return [replay(tools, meta, r, ids[r['task']], not development) for r in rows
            if r['condition'] == selected[r['model']]['gpp']]


def report(groups):
    print('# Replaying selected native arms through the product CLI\n')
    print('Archived responses were replayed through `tools/propose.py --maintenance` with a loopback Ollama stub and the real compiler. Qwen used full-body editing. StarCoder2 used `--prepend` and its raw FIM transport. The transfer replay also enabled `--caller-obligation`. The CLI received public cases only. A separate interpreter run evaluated withheld cases against its revision-checked preview.\n')
    print('| Study | Model | Trials | Calls | Archive accepted | CLI accepted | Terminal outcomes matched | Exact prompt and suffix | After AST normalization |')
    print('|---|---|---:|---:|---:|---:|---:|---:|---:|')
    differences = []
    for name, group in groups.items():
        for model in study.MODELS:
            rows = [r for r in group if r['model'] == model]
            pairs = [pair for r in rows for pair in r['prompts']]
            matching = sum(r['archive'] == r['outcome'] for r in rows)
            print(f"| {name} | {model} | {len(rows)} | {len(pairs)} | {sum(r['archive'] == 'accepted' for r in rows)} | {sum(r['outcome'] == 'accepted' for r in rows)} | {matching}/{len(rows)} | {sum(p[0] for p in pairs)}/{len(pairs)} | {sum(p[1] for p in pairs)}/{len(pairs)} |")
            differences.extend((name, r) for r in rows if r['archive'] != r['outcome'] or not all(p[1] for p in r['prompts']))
    print('\nExact prompt equality compares the prefix and suffix sent by the CLI to the saved study fields, including caller feedback on retries. The normalized comparison rerenders the study prompt with the compiler’s canonical GPT++ spelling, which expands compact blocks and spaces operators. The verified transport checks cover model, token limits, seeds, temperature, stop sequences, and raw versus templated FIM. Replaying fixed text measures patch and evaluator parity; new generations could change with prompt formatting.')
    if differences:
        print('\n| Study | Task | Arm | Archived outcome | CLI outcome | Normalized prompts matched |')
        print('|---|---|---|---|---|---:|')
        for name, r in differences:
            print(f"| {name} | {r['task']} | {r['arm']} | {r['archive']} | {r['outcome']} | {sum(p[1] for p in r['prompts'])}/{len(r['prompts'])} |")
    print('\nRun `target/empirical-venv/bin/python -B bench/policy/replay_product.py` after building `gpp` and the [caller obligation analyzer](../../tools/caller_obligation.md). [v7 raw trials](results/policy.jsonl) · [v8 raw trials](results/transfer.jsonl)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development-only', action='store_true')
    args = parser.parse_args()
    selections = transfer.selections()
    tools = study.Tools(ROOT, GPP)
    names = ('v7',) if args.development_only else ('v7', 'v8')
    report({name: run_archive(name, selections, tools) for name in names})
