"""Recompute the published tables from the raw archive."""

import argparse
from collections import Counter
from pathlib import Path

from corpus import TASKS, cases, histories
from native import LANGS
from study import MODELS, load


def print_report(path):
    archive = load(path)
    by = {(r['kind'], r.get('key')): r for r in archive}
    expected = {'manifest': 1, 'compiler': 1, 'call': 54, 'trial': 54, 'solver': 27, 'shared': 9}
    if Counter(r['kind'] for r in archive) != expected:
        raise ValueError('Missing or extra measurement rows')
    if len(by) != sum(expected.values()):
        raise ValueError('Duplicated archive keys')

    def native(arm, t):
        return by['solver', f'{arm}/{t.name}']

    def shared(t):
        return by['shared', f'shared/{t.name}']

    def mark(row):
        if row['accepted']:
            return 'correct'
        return 'wrong' if row['score'] else '—'

    print('# Bounded completion on nine fresh task families\n')
    print('The primary endpoint counts a task only when the solver publishes a typed expression and every withheld check agrees. Nine families include four history-dependent transitions. The corpus contains 156 public input/output pairs, 1,774 withheld direct calls and 12,125 withheld event histories. A single incorrect outcome fails the entire task.\n')
    print('| Solver | Correct / 9 | Published | Published wrong | Ambiguous | Search wall, total |')
    print('|---|---:|---:|---:|---:|---:|')
    names = [('previous', 'Previous GPT++'), ('grammar', 'New GPT++, grammar only'), ('hybrid', 'New GPT++, default')]
    for arm, title in names:
        rows = [native(arm,t) for t in TASKS]
        print(f"| {title} | {sum(r['accepted'] for r in rows)} | "
              f"{sum(r['expression'] is not None for r in rows)} | "
              f"{sum(r['score'] is not None and not r['accepted'] for r in rows)} | "
              f"{sum(r['report']['status']=='ambiguous' for r in rows)} | "
              f"{sum(r['search_ms'] for r in rows)/1000:.3f} s |")
    for arm, title in [('first', 'Portable search, first passing'), ('conservative', 'Portable search, probe consensus')]:
        rows = [shared(t)['selections'][arm]['gpp'] for t in TASKS]
        ambiguous = sum(shared(t)['stats'].get('distinct_public_passing_probe_behaviors', 0)>1 for t in TASKS)
        print(f"| {title} | {sum(r['accepted'] for r in rows)} | {sum(r['expression'] is not None for r in rows)} | "
              f"{sum(r['score'] is not None and not r['accepted'] for r in rows)} | "
              f"{ambiguous if arm=='conservative' else 'n/a'} | "
              f"{sum(shared(t)['search_ms'] for t in TASKS)/1000:.3f} s |")
    print('\nThe portable search ran once per task and its selected abstract expressions were independently rendered, type-checked and executed by all three backends. Its two rows share the same search work. Search times are single-host, one run per solver and family. Native CLI times include internal public verification. The portable row times cover enumeration and internal public evaluation. Its separate backend validation costs are in the archive.\n')
    print('| Family | Previous | New grammar | New default | Portable first | Portable consensus | Direct withheld | Histories |')
    print('|---|---|---|---|---|---|---:|---:|')
    for t in TASKS:
        cells=[]
        for arm,_ in names:
            row=native(arm,t); cells.append(mark(row) if row['expression'] is not None else row['report']['status'])
        for selector in ('first','conservative'):
            outcomes=[mark(shared(t)['selections'][selector][l]) for l in LANGS]
            cells.append(outcomes[0] if len(set(outcomes))==1 else '/'.join(outcomes))
        print(f"| {t.name} | "+' | '.join(cells)+f" | {len(cases(t)[1])} | {len(histories(t)):,} |")
    print('\n## Paired outcomes and advisory candidates\n')
    all_new=[native('hybrid',t)['accepted'] for t in TASKS]
    for arm,other in [('previous compiler',[native('previous',t)['accepted'] for t in TASKS]),
                      ('new grammar only',[native('grammar',t)['accepted'] for t in TASKS]),
                      ('portable first passing',[shared(t)['selections']['first']['gpp']['accepted'] for t in TASKS]),
                      ('portable probe consensus',[shared(t)['selections']['conservative']['gpp']['accepted'] for t in TASKS])]:
        w=sum(a and not b for a,b in zip(all_new,other)); l=sum(b and not a for a,b in zip(all_new,other))
        print(f'- Against {arm}, the default compiler had {w} '+('win' if w==1 else 'wins')+f', {l} '+('loss' if l==1 else 'losses')+f' and {len(TASKS)-w-l} ties.')
    print('\n| Solver | First public-passing expression correct, out of 9 |')
    print('|---|---:|')
    for arm,title in names:
        print(f"| {title} | {sum(native(arm,t)['advisory_only']['accepted'] for t in TASKS)} |")
    print('\nThe advisory row scores the first candidate passing public checks even if the actual solver asked a question. It gives no credit in the primary endpoint. A single public gate can fit multiple expressions. On the fan task, even the deliberately defective starter passed every sampled public example while failing held-out behavior. That family remains in every denominator.\n')
    print('## Matched local model generation\n')
    print('| Model | Language | Correct / 9 | Passed public | Calls | Input | Output | Model seconds | Public validation seconds |')
    print('|---|---|---:|---:|---:|---:|---:|---:|---:|')
    for m in MODELS:
        for l in LANGS:
            calls=[by['call',f'{m}/{t.name}/{l}'] for t in TASKS]
            trials=[by['trial',f'{m}/{t.name}/{l}'] for t in TASKS]
            print(f"| {m} | {l} | {sum(r['accepted'] for r in trials)} | "
                  f"{sum(r['public_status']=='pass' for r in trials)} | {len(calls)} | "
                  f"{sum(r['reply']['prompt_eval_count'] for r in calls):,} | "
                  f"{sum(r['reply']['eval_count'] for r in calls):,} | "
                  f"{sum(r['model_ms'] for r in calls)/1000:.2f} | {sum(r['public_ms'] for r in trials)/1000:.2f} |")
    print('\nOne model call per task and language, with identical sampling settings and a native syntax card. There were no retries or external clarifications. Withheld checks followed the public gate. Payloads, including failed replies, are in the archive. The GPT++ model arm used the previous shipped type checker and manual hole-fill path. The matched model arms measure single-expression generation independently of automatic search.\n')
    print('## Search work\n')
    print('| Family | Previous tested | New grammar tested | Hybrid tested | Portable intermediate vector evaluations | Portable branch tests | Portable root candidates |')
    print('|---|---:|---:|---:|---:|---:|---:|')
    for t in TASKS:
        st=shared(t)['stats']
        work=[native(arm,t)['report'].get('tested','—') for arm,_ in names]
        print(f"| {t.name} | "+' | '.join(map(str,work))+f" | {st['vector_evaluations']:,} | {st['branch_partition_tests']:,} | {st['completed_candidates']} |")
    print('\nAll search arms had a 256 completed-candidate ceiling and a 30-second deadline. The portable solver uses public examples to prune intermediate values, compare branch partitions, and identify public-fitting root expressions. It checks many more intermediate vectors than the number of roots. The new native compiler also uses internal evaluations to construct candidates. The counters reflect different units of work and should be read with the wall-time measurements. See the raw native reports for the compiler guidance counters.\n')
    print('| Native guidance work | Total across nine tasks |')
    print('|---|---:|')
    for field in ('contract_runs','examples','value_vectors','branch_joins','proposals'):
        print(f"| {field} | {sum(native('hybrid',t)['report']['guidance'][field] for t in TASKS):,} |")
    print('\nThe native CLI and portable solver timings were recorded while the independent local model collection was finishing on the same host. Host load was uncontrolled. The archive records separate public validation time for each native rendering.\n')
    print('The corpus covers small scalar rules and four bounded event folds. The public labels and complete reference behavior represent shared specification effort. No human authoring time was measured. The finite cases and repeated model calls do not constitute evidence about general-purpose software maintenance. [Frozen protocol](protocol.md) · [Full replay instructions and provenance](README.md)')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    print_report(p.parse_args().archive)
