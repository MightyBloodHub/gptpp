"""Native validation and independent bulk scoring. No hidden inputs enter proposal search."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from corpus import cases, expected, histories, history_expected
from engine import render

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'Cargo.toml').is_file())
sys.path.insert(0,str(ROOT/'bench/stateful'))
from adapters import authorize  # repository's previously published expression boundary

LANGS=('gpp','rust','python')
PYTHON=ROOT/'target/empirical-venv/bin/python'
TYPES={'gpp':{'I64':'I64','Bool':'Bool'},'rust':{'I64':'i64','Bool':'bool'},'python':{'I64':'int','Bool':'bool'}}
PY_HELPERS="""def quotient(a: int, b: int) -> int:
    return (1 if (a < 0) == (b < 0) else -1) * (abs(a) // abs(b))
def remainder(a: int, b: int) -> int:
    return a - b * quotient(a, b)
"""


def digest(b):
    return hashlib.sha256(b).hexdigest()


def run(argv, stdin=None, timeout=30):
    return subprocess.run(list(map(str,argv)), text=True, input=stdin, capture_output=True, timeout=timeout)


def source(t,l,expression):
    args=', '.join(f'{a}: {TYPES[l][ty]}' for a,ty in t.args)
    ret=TYPES[l][t.result]
    if l=='python': return f'def transition({args}) -> {ret}:\n    return {expression}\n'
    pre='module study.search;\n' if l=='gpp' else 'use std::cmp::{min,max};\n'
    return pre+f'fn transition({args}) -> {ret}'+(' !{}' if l=='gpp' else '')+' {\n    return '+expression+';\n}\n'


def gpp(t):
    public,_=cases(t)
    src=source(t,'gpp','?change: '+t.result)+'pub fn main() -> I64 !{} { return 0; }\n'
    for i,args in enumerate(public):
        values=', '.join(render(v,'gpp') for v in args)
        ans=render(expected(t,args),'gpp')
        src+=f'contract sample_{i}() {{ transition({values}) == {ans} }}\n'
    return src


def rc(p):
    return (p.stderr or p.stdout).strip()[:450]


class Program:
    def __init__(self,t,l,work,compiler):
        self.t,self.l,self.work,self.compiler=t,l,work,compiler
        self.work.mkdir(parents=True,exist_ok=True)
        self.file=work/('program.'+{'gpp':'gpp','python':'py','rust':'rs'}[l])
        self.executable=work/'program'
        self.sketch=work/'sketch.gpp'
        if l=='gpp': self.sketch.write_text(gpp(t))

    def public(self,expression,*,trusted=False):
        if not trusted:
            try: authorize(expression,SimpleNamespace(fields=self.t.args),self.l)
            except (ValueError,SyntaxError,RecursionError) as ex: return 'syntax', str(ex)
        t,l=self.t,self.l
        if l=='gpp':
            patch=self.work/'patch.expr'; patch.write_text(expression)
            p=run([self.compiler,'complete',self.sketch,'--hole','change','--fill',patch,'--stdout'])
            if p.returncode:
                return ('public_or_type_failure',rc(p).replace(str(self.work)+'/',''))
            body=p.stdout
            if t.events: body+=self.gpp_history()
            self.file.write_text(body+'fn probe_marker() -> I64 !{} { return 0; }\n')
        elif l=='python':
            self.file.write_text((PY_HELPERS if trusted else '')+source(t,l,expression))
            p=run([PYTHON,'-m','mypy','--strict','--no-error-summary','--cache-dir',self.work/'mypy',self.file])
            if p.returncode: return 'type_error',rc(p).replace(str(self.work)+'/','')
            with self.file.open('a') as fout:
                fout.write('import json, sys\nfor line in sys.stdin:\n    f, xs = json.loads(line)\n    try:\n        if f == "direct":\n            v = transition(*xs)\n        else:\n            v = '+repr(t.initial)+'\n            for e in xs:\n                v = transition(v, e)\n        print(json.dumps(v))\n    except ArithmeticError:\n        print("null")\n')
        else:
            pars=', '.join(f'x[{i}].parse::<{TYPES[l][ty]}>().unwrap()' for i,(_,ty) in enumerate(t.args))
            hist=''
            if t.events:
                ty=TYPES[l][t.args[1][1]]; start=render(t.initial,l)
                hist=f'if f=="history" {{ let mut a={start}; for e in &x {{ a=transition(a,e.parse::<{ty}>().unwrap()); }} return a; }}'
            body=source(t,l,expression)+'''use std::io::{self,BufRead};
fn main() {
 std::panic::set_hook(Box::new(|_| {}));
 for line in io::stdin().lock().lines() {
 let line=line.unwrap(); let mut words=line.split_whitespace(); let f=words.next().unwrap();
 let x:Vec<_>=words.collect(); let value=std::panic::catch_unwind(|| { HIST transition(PARS) });
 match value { Ok(v)=>println!("{}",v), Err(_)=>println!("null") }
 }
}
'''.replace('HIST',hist).replace('PARS',pars)
            self.file.write_text(body)
            p=run(['rustc','--edition=2024','-A','warnings','-C','overflow-checks=yes',self.file,'-o',self.executable])
            if p.returncode: return 'type_error',rc(p).replace(str(self.work)+'/','')
        public,_=cases(t)
        out=self.observe([('direct',r) for r in public]); good=[expected(t,r) for r in public]
        if json.dumps(out)!=json.dumps(good):
            i=next(j for j,(a,b) in enumerate(zip(out,good,strict=True)) if type(a)!=type(b) or a!=b)
            return 'public_failure',f'{public[i]} expects {good[i]}, observed {out[i]}'
        return 'pass',''

    def gpp_history(self):
        t=self.t
        e=render(t.events[-1],'gpp')
        for i,v in reversed(list(enumerate(t.events[:-1]))):
            e=f'if digit == {i} {{ {render(v,"gpp")} }} else {{ {e} }}'
        return f'fn history(code: I64, n: I64) -> {t.result} !{{}} {{ var state = {render(t.initial,"gpp")}; var word = code; var remaining = n; while remaining > 0 {{ let digit = word % {len(t.events)}; state = transition(state, {e}); word = word / {len(t.events)}; remaining = remaining - 1; }} return state; }}\n'

    def observe(self,items):
        if self.l=='gpp':
            rows=[]
            for f,xs in items:
                if f=='history':
                    xs=[sum(self.t.events.index(e)*len(self.t.events)**i for i,e in enumerate(xs)),len(xs)]
                rows.append('\t'.join(['transition' if f=='direct' else 'history',*(render(x,'gpp') for x in xs)]))
            tape=self.work/'inputs.tsv'; tape.write_text('\n'.join(rows)+'\n')
            b=self.file.read_bytes(); start=b.index(b'fn probe_marker()')+len(b'fn probe_marker() -> I64 !{} { return ')
            p=run([self.compiler,'probe',self.file,'--function','probe_marker','--expect','sha256:'+digest(b),'--cases',tape],f'{start}:{start+1} 1\n0')
            if p.returncode: raise RuntimeError(rc(p))
            response=json.loads(p.stdout.splitlines()[1])
            if response['status']!='ok': raise RuntimeError(response)
            out=[v.get('result') for v in response['outcomes']]
        else:
            data='\n'.join(json.dumps((f,row)) if self.l=='python' else ' '.join([f,*(render(v,'rust') for v in row)]) for f,row in items)+'\n'
            cmd=[PYTHON,'-I',self.file] if self.l=='python' else [self.executable]
            p=run(cmd,data)
            if p.returncode: raise RuntimeError(rc(p))
            out=[json.loads(x) for x in p.stdout.splitlines()]
        if len(out)!=len(items): raise RuntimeError('Observer lost cases')
        return out

    def hidden(self):
        _,direct=cases(self.t); traces=histories(self.t)
        items=[('direct',row) for row in direct]+[('history',row) for row in traces]
        expected_values=[expected(self.t,row) for row in direct]+[history_expected(self.t,row) for row in traces]
        actual=self.observe(items)
        errors=[(i,items[i],b,a) for i,(a,b) in enumerate(zip(actual,expected_values,strict=True)) if type(a)!=type(b) or a!=b]
        return {'direct':len(direct),'histories':len(traces),'direct_wrong':sum(i<len(direct) for i,*_ in errors),
                'history_wrong':sum(i>=len(direct) for i,*_ in errors),'first_error':list(errors[0]) if errors else None,
                'outcomes_sha256':digest(json.dumps(actual).encode())}
