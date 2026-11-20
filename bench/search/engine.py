"""Portable typed-expression search using public example vectors and a bounded beam."""

import ast
from itertools import islice, product
from operator import add, sub, mul, lt, le, eq, ne, ge, gt, and_, or_, not_
from time import monotonic

INT, BOOL = 'I64','Bool'
LOW, HIGH = -(1 << 63), (1 << 63) - 1
OPS_I = ('+','-','min','max','*','/','%')
OPS_B = ('<','==','<=','!=','>=','>')
FUNCTIONS = {'+':add,'-':sub,'*':mul,'min':min,'max':max,'<':lt,'<=':le,'==':eq,'!=':ne,'>=':ge,'>':gt,
             'and':and_,'or':or_,'not':not_, 'int':int}
COMMUTE = {'+','*','==','!=','min','max','and','or'}


def trunc(a,b):
    return (1 if (a >= 0) == (b >= 0) else -1) * (abs(a)//abs(b))


def operation(op, vals):
    if op == 'if':
        return vals[1 if vals[0] else 2] if vals[0] is not None else None
    if op == 'and' and vals[0] is False:
        return False
    if op == 'or' and vals[0] is True:
        return True
    if None in vals:
        return None
    if op in ('/','%'):
        a,b = vals
        if not b or (a == LOW and b == -1):
            return None
        q = trunc(a,b)
        return q if op=='/' else a-q*b
    value = FUNCTIONS[op](*vals)
    return value if LOW <= value <= HIGH else None


def render(n, lang, portable=True):
    if not isinstance(n,tuple):
        if type(n) is bool:
            return str(n) if lang=='python' else str(n).lower()
        return str(n)
    op,*kids=n
    a,*rest=[render(k,lang,portable) for k in kids]
    if op=='int':
        return f'int({a})' if lang=='python' else f'(({a}) as {"I64" if lang=="gpp" else "i64"})'
    if op=='not':
        return f'(not {a})' if lang=='python' else f'!({a})'
    b=rest[0]
    if op=='if':
        return f'({b} if {a} else {rest[1]})' if lang=='python' else f'(if {a} {{ {b} }} else {{ {rest[1]} }})'
    if op in ('min','max'):
        return f'{op}({a}, {b})'
    if lang=='python' and portable and op in ('/','%'):
        return f'{"quotient" if op=="/" else "remainder"}({a}, {b})'
    sym=({'and':'&&','or':'||'}.get(op,op) if lang!='python' else ('//' if op=='/' else op))
    return f'({a} {sym} {b})'


def parse_py(s):
    def expr(n):
        if isinstance(n, ast.Name): return n.id
        if isinstance(n, ast.Constant): return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op,ast.USub): return -n.operand.value
        if isinstance(n, ast.Call): return (n.func.id,*(expr(v) for v in n.args))
        if isinstance(n, ast.IfExp): return ('if',expr(n.test),expr(n.body),expr(n.orelse))
        if isinstance(n, ast.Compare): return ({ast.Lt:'<',ast.GtE:'>=',ast.Gt:'>',ast.Eq:'=='}[type(n.ops[0])],expr(n.left),expr(n.comparators[0]))
        if isinstance(n, ast.BoolOp): return ('and' if isinstance(n.op,ast.And) else 'or',*(expr(v) for v in n.values))
        return ({ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Mod:'%'}[type(n.op)],expr(n.left),expr(n.right))
    return expr(ast.parse(s,mode='eval').body)


def probes(args):
    columns=[(False,True) if t==BOOL else (-1,0,1,2,8) for _,t in args]
    return list(islice(product(*columns),128))


def search(args,result,rows,labels,deadline,limit=256):
    """Intermediate vectors are bounded separately from final root validations."""
    grid=probes(args); inputs=rows+grid
    stats={'vector_evaluations':0,'distinct_vectors':0,'completed_candidates':0,'probe_rows':len(grid)}
    seen={INT:{},BOOL:{}}
    # Preserve candidates that agree publicly but differ on the fixed independent probes.
    solutions=[]
    def put(typ,n,values):
        if values in seen[typ]: return
        seen[typ][values]=n
        if typ==result and values[:len(labels)]==labels and len(solutions)<limit:
            solutions.append((n,values[len(labels):]))
            stats['completed_candidates']+=1
    for j,(name,typ) in enumerate(args):
        put(typ,name,tuple(p[j] for p in inputs))
    values={0,1,2,-1}
    values.update(x for r in rows for x in r if type(x) is int)
    values.update(x for x in labels if type(x) is int)
    for v in sorted(values,key=lambda x:(abs(x),x))[:14]: put(INT,v,(v,)*len(inputs))
    for v in (False,True): put(BOOL,v,(v,)*len(inputs))
    def emit(typ,op,*kids):
        stats['vector_evaluations']+=1
        n=(op,*(k[1] for k in kids))
        vals=tuple(operation(op,v) for v in zip(*(k[0] for k in kids)))
        put(typ,n,vals)
    def grade(item):
        v,n=item
        visible=v[:len(labels)]
        hits=sum(type(x) is type(y) and x==y for x,y in zip(visible,labels))
        distance=sum(10000 if x is None else min(10000,abs(int(x)-int(y))) for x,y in zip(visible,labels))
        return (-hits,distance,len(str(n)),str(n))
    seed={k:list(d.items()) for k,d in seen.items()}
    def level(pool,cap):
        for f in pool[BOOL]:
            if stats['vector_evaluations']>=cap: return
            emit(BOOL,'not',f); emit(INT,'int',f)
        # Interleave operator families for each operand pair to avoid exhausting a level on one operator.
        groups=[(INT,INT,OPS_I),(INT,BOOL,OPS_B),(BOOL,BOOL,('and','or','==','!='))]
        for idx in range(max(len(pool[INT]),len(pool[BOOL]))):
            for typ,out,ops in groups:
                if idx>=len(pool[typ]): continue
                a=pool[typ][idx]
                for j,b in enumerate(pool[typ]):
                    for op in ops:
                        if op in COMMUTE and j<idx: continue
                        if stats['vector_evaluations']>=cap or monotonic()>deadline: return
                        emit(out,op,a,b)
    level(seed,5000)
    ranked={t:sorted(d.items(),key=grade) for t,d in seen.items()}
    # Numeric and Boolean intermediates each get a target-guided beam and a structurally diverse prefix.
    pool={}
    for typ in (INT,BOOL):
        kept=dict(seed[typ]+ranked[typ][:25]+list(seen[typ].items())[:38])
        pool[typ]=list(dict(ranked[typ][:25]+list(kept.items())).items())
    level(pool,13500)
    # Conditional joins match target values on each branch, so unnecessary Cartesian triples can be skipped.
    ranked={k:sorted(d.items(),key=grade) for k,d in seen.items()}
    stats['branch_partition_tests']=0
    for cv,cond in ranked[BOOL][:160]:
        if monotonic()>deadline: break
        if None in cv[:len(labels)] or len(set(cv[:len(labels)]))<2: continue
        yes=[]; no=[]
        for v,node in ranked[result][:300]:
            stats['branch_partition_tests']+=1
            if all(x==y for flag,x,y in zip(cv,v,labels) if flag): yes.append((v,node))
            if all(x==y for flag,x,y in zip(cv,v,labels) if not flag): no.append((v,node))
        for a in yes[:3]:
            for b in no[:3]:
                emit(result,'if',(cv,cond),a,b)
    stats['distinct_vectors']=sum(map(len,seen.values()))
    stats['time_limit_hit']=monotonic()>deadline
    if stats['time_limit_hit']: return None,None,stats
    candidate=solutions[0][0] if solutions else None
    conservative=candidate if len({v for _,v in solutions})<=1 else None
    stats['distinct_public_passing_probe_behaviors']=len({v for _,v in solutions})
    return candidate,conservative,stats
