"""Collect and replay the preregistered bounded-search comparison."""

import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from random import Random
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

import corpus as c
import engine
import native as n

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(n.ROOT/'tools'))
from propose import ollama
MODELS={'qwen2.5-coder:7b':'dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364',
        'starcoder2:3b':'f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c'}
LIMIT=256
WALL=30


def stable(x): return json.dumps(x,sort_keys=True,separators=(',',':'))
def stamp(): return datetime.now(timezone.utc).isoformat()
def millis(start): return round(1000*(monotonic()-start))
def load(p): return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
def append(p,row):
    with p.open('a') as fout:
        fout.write(json.dumps(row,separators=(',',':'))+'\n')
        fout.flush(); os.fsync(fout.fileno())
def hashes():
    return {s:n.digest((HERE/s).read_bytes()) for s in ('corpus.py','engine.py','native.py','study.py','protocol.md','freeze.json','secondary.md')}
def accepted(score): return score is not None and not(score['direct_wrong'] or score['history_wrong'])


def model_prompt(t,l,model):
    rows,_=c.cases(t)
    syntax={'gpp':'if cond { yes } else { no }; &&, ||, !; flag as I64; integer division /',
            'rust':'if cond { yes } else { no }; &&, ||, !; flag as i64; integer division /',
            'python':'yes if cond else no; and, or, not; int(flag); integer division //'}[l]
    text='\n'.join([f'Fill one typed expression in this { {"gpp":"GPT++","rust":"Rust","python":"typed Python"}[l] } function.',
        t.request,'Previous expression: '+engine.render(engine.parse_py(t.old),l,portable=False),
        n.source(t,l,'?change: '+n.TYPES[l][t.result]),
        'Public examples (arguments in declaration order, then expected result):',
        *(f'{json.dumps(r)} => {json.dumps(c.expected(t,r))}' for r in rows),
        'Native operations: '+syntax+'. min(a,b), max(a,b), ordinary arithmetic, comparisons and scalar literals are available.',
        'Return a JSON object with one string property named expression. Supply only the native expression as its value.'])
    return {'model':model,'prompt':text,'stream':False,'keep_alive':'3m',
            'format':{'type':'object','properties':{'expression':{'type':'string'}},'required':['expression'],'additionalProperties':False},
            'options':{'temperature':0,'num_predict':200,'num_ctx':4096,'seed':42}}


def check(ad,expr,trusted=False):
    if expr is None: return {'public_status':'no_selection','detail':'','score':None,'accepted':False,'public_ms':0,'hidden_ms':0}
    start=monotonic(); status,detail=ad.public(expr,trusted=trusted); elapsed=millis(start); score=None; hidden=0
    if status=='pass':
        start=monotonic(); score=ad.hidden(); hidden=millis(start)
    return {'public_status':status,'detail':detail,'score':score,'accepted':accepted(score),'public_ms':elapsed,'hidden_ms':hidden}


def model_runs(old,raw,work,archive,replay):
    if not replay:
        tags={m['name']:m['digest'] for m in ollama(11434,'tags')['models']}
        assert all(tags.get(k)==v for k,v in MODELS.items()),'Pinned model unavailable'
    for model in MODELS:
        order=[(t,l) for t in c.TASKS for l in n.LANGS]
        Random(70511).shuffle(order)
        for t,l in order:
            key=f'{model}/{t.name}/{l}'
            if not replay and ('trial',key) in raw: continue
            request=model_prompt(t,l,model)
            call=raw.get(('call',key))
            if call is None:
                if replay: raise ValueError(f'Missing call: {key}')
                start=monotonic(); data=ollama(11434,'generate',request); elapsed=millis(start)
                if not data.get('done') or not all(type(data.get(k)) is int for k in ('prompt_eval_count','eval_count')):
                    raise ValueError('Incomplete model response')
                call={'kind':'call','key':key,'request':request,'reply':{k:data[k] for k in ('response','done_reason','prompt_eval_count','eval_count')},'model_ms':elapsed}
                append(archive,call)
            if call['request']!=request: raise ValueError('Archived request differs')
            txt=call['reply']['response']
            try:
                obj=json.loads(txt,object_pairs_hook=list)
                if not (len(obj)==1 and obj[0][0]=='expression' and type(obj[0][1]) is str): raise ValueError()
                expr=obj[0][1].strip()
            except (ValueError,TypeError,IndexError): expr=None
            ad=n.Program(t,l,work/l/t.name,old)
            result=check(ad,expr)
            row={'kind':'trial','key':key,'expression':expr,**result}
            admit(row,raw,archive,replay)
        print('Model roster complete:',model,flush=True)


def admit(row,raw,archive,replay):
    if replay:
        orig=raw[(row['kind'],row['key'])]
        if stable({k:v for k,v in row.items() if not k.endswith('_ms')})!=stable({k:v for k,v in orig.items() if not k.endswith('_ms')}):
            raise ValueError(f'Behavior changed in {row["kind"]}/{row["key"]}: {str(row)[:500]}')
    else: append(archive,row)


def solve(old,new,raw,work,archive,replay):
    for t in c.TASKS:
        for arm,binary,opts in [('previous',old,[]),('grammar',new,['--search','grammar']),('hybrid',new,[])]:
            key=f'{arm}/{t.name}'
            if not replay and ('solver',key) in raw: continue
            ad=n.Program(t,'gpp',work/arm/t.name,binary)
            start=monotonic()
            try:
                p=n.run([binary,'complete',ad.sketch,'--hole','change','--limit',str(LIMIT),'--budget','10000',*opts],timeout=WALL)
                if p.returncode not in (0,1,3): raise ValueError(n.rc(p))
                report=json.loads(p.stdout)
            except subprocess.TimeoutExpired:
                report={'status':'timeout'}
            elapsed=millis(start); expr=report.get('selected')
            result=check(ad,expr,trusted=True)
            first=report.get('first_passing') or expr
            if not first and arm=='previous' and report['status']=='ambiguous':
                # Every candidate in these leaf functions terminates with a scalar or a fault.
                # Previous gpp thus stored the first passing candidate at every ambiguity probe.
                first=report['question']['alternatives'][0]['expression']
            advisory=check(ad,first,trusted=True) if first!=expr else result.copy()
            advisory={k:v for k,v in advisory.items() if not k.endswith('_ms')}
            row={'kind':'solver','key':key,'report':report,'expression':expr,'search_ms':elapsed,'first_passing':first,'advisory_only':advisory,**result}
            admit(row,raw,archive,replay)
        sharedkey=f'shared/{t.name}'
        if not replay and ('shared',sharedkey) in raw: continue
        rows,_=c.cases(t); labels=tuple(c.expected(t,x) for x in rows); start=monotonic()
        first,strict,stats=engine.search(t.args,t.result,rows,labels,start+WALL,LIMIT); elapsed=millis(start)
        selections={}
        for label,tree in [('first',first),('conservative',strict)]:
            selections[label]={}
            for l in n.LANGS:
                expr=engine.render(tree,l) if tree is not None else None
                # Both selectors can choose the same native expression.
                if label=='conservative' and first==strict: result=selections['first'][l].copy()
                else: result={'expression':expr,**check(n.Program(t,l,work/l/t.name,old),expr,trusted=True)}
                selections[label][l]=result
        row={'kind':'shared','key':sharedkey,'stats':stats,'search_ms':elapsed,'selections':selections}
        if replay:
            orig=raw[('shared',sharedkey)]
            for label in selections:
                for l in n.LANGS:
                    for k in ('public_ms','hidden_ms'): selections[label][l][k]=orig['selections'][label][l][k]
        admit(row,raw,archive,replay)
        print('Search cell complete',len([r for r in load(archive) if r['kind']=='shared']),flush=True)


def preflight(old,work):
    rows=[]
    for t in c.TASKS:
        for l in n.LANGS:
            ad=n.Program(t,l,work/l/t.name,old)
            starter=check(ad,engine.render(engine.parse_py(t.old),l),trusted=True)
            reference=check(ad,engine.render(engine.parse_py(t.reference),l),trusted=True)
            if not reference['accepted']: raise ValueError((t.name,l,reference))
            rows.append({'task':t.name,'language':l,'starter_public':starter['public_status'],'starter_accepted':starter['accepted'],'reference':reference['score']})
    return rows


def main():
    import platform
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['preflight','models','solvers','replay']); p.add_argument('archive',type=Path)
    p.add_argument('--old',required=True,type=Path); p.add_argument('--new',type=Path)
    args=p.parse_args(); replay=args.phase=='replay'; raw={}
    with TemporaryDirectory(prefix='gpp-bounded-search-') as tmp:
        work=Path(tmp); old=work/'previous-gpp'; shutil.copy2(args.old,old)
        new=None
        if args.phase in ('solvers','replay'):
            if not args.new: p.error('--new is required for solvers/replay')
            new=work/'new-gpp'; shutil.copy2(args.new,new)
        if args.phase=='preflight':
            if args.archive.exists(): raise ValueError('Preflight path already exists')
            args.archive.write_text(json.dumps(preflight(old,work),indent=2)+'\n'); return
        rows=load(args.archive)
        if not rows:
            if replay: raise ValueError('Archive does not exist')
            append(args.archive,{'kind':'manifest','time_utc':stamp(),'files':hashes(),'old_binary_sha256':n.digest(old.read_bytes()),'models':MODELS,'host':platform.platform(),'rust':n.run(['rustc','-V']).stdout.strip(),'python':n.run([n.PYTHON,'-V']).stdout.strip(),'mypy':n.run([n.PYTHON,'-m','mypy','--version']).stdout.strip()})
        else:
            if rows[0]['files']!=hashes(): raise ValueError('Frozen runner changed')
            if not replay and rows[0]['old_binary_sha256']!=n.digest(old.read_bytes()): raise ValueError('Prior binary changed')
        for row in rows:
            if 'key' in row:
                key=row['kind'],row['key']
                if key in raw: raise ValueError('Duplicate archive key')
                raw[key]=row
        if args.phase in ('models','replay'): model_runs(old,raw,work,args.archive,replay)
        if args.phase in ('solvers','replay'):
            prior=[r for r in rows if r['kind']=='compiler']
            if prior:
                if not replay and prior[0]['new_binary_sha256']!=n.digest(new.read_bytes()): raise ValueError('Study binary changed')
            elif replay: raise ValueError('Compiler manifest missing')
            else: append(args.archive,{'kind':'compiler','new_binary_sha256':n.digest(new.read_bytes()),'time_utc':stamp()})
            solve(old,new,raw,work,args.archive,replay)
    if replay: print('Replayed all original model outputs and search selections without inference.')


if __name__=='__main__': main()
