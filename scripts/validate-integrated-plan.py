"""Read-only consistency check for the integrated plan; no application/DB imports."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'docs'/'plano-integrado'
data=json.loads((root/'onda1-tarefas.json').read_text())
rows=data['tasks'];tasks={r['id']:r for r in rows};assert len(tasks)==len(rows)
for r in rows:
 assert r['executor_agent_slug'] and r['reviewer_agent_slug'],r['id']
 assert r['executor_agent_slug']!=r['reviewer_agent_slug'],r['id']
 assert r['status']=='planned' and r['project_task_id'] is None,r['id']
 assert all(d in tasks for d in r['depends_on']),(r['id'],r['depends_on'])
visiting=set();visited=set();order=[]
def visit(t):
 assert t not in visiting,('cycle',t)
 if t in visited:return
 visiting.add(t)
 for d in tasks[t]['depends_on']:visit(d)
 visiting.remove(t);visited.add(t);order.append(t)
for t in tasks:visit(t)
def ancestors(t):
 result=set()
 for d in tasks[t]['depends_on']:result|={d}|ancestors(d)
 return result
for t in ('V-a','N.0','M0.0','C.2','A.1','A.2'):
 assert {'T.2','T.3'}<=ancestors(t),t
assert 'M0.5' in ancestors('C.0')
assert 'C.0' not in ancestors('M0.5')
assert {'M0.6a','M0.6b'}<=ancestors('M0.2c')
# Source table and detailed matrix must match; only historical 0.13 sits outside matrix.
source={}
for line in (root/'07-fases-de-implementacao.md').read_text().splitlines():
 if not line.startswith('| '):continue
 c=[x.strip() for x in line.strip('|').split('|')]
 if len(c)==7 and c[0]=='N.0':c=c[:4]+c[5:]
 if len(c)==6 and c[0] in tasks:
  assert c[0] not in source,('duplicate canonical row',c[0]);source[c[0]]=c
assert set(source)==set(tasks)
for tid,c in source.items():
 if tid!='0.14':assert [x.strip() for x in c[4].split(',') if x.strip()!='—']==tasks[tid]['depends_on'],tid
 assert c[5]==tasks[tid]['acceptance'],tid
# Relative document links, including the generated review artifact.
errors=[]
for file in root.rglob('*.md'):
 for link in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',file.read_text()):
  target=link.split('#')[0]
  if not target or ':' in target or '<' in target:continue
  if not (file.parent/target).exists():errors.append((str(file.relative_to(root)),target))
assert not errors,errors
for file in root.rglob('*.md'):
 cols=None
 for n,line in enumerate(file.read_text().splitlines(),1):
  if line.startswith('|'):
   count=len(re.split(r'(?<!\\)\|',line))-2
   if cols is None:cols=count
   assert count==cols,(str(file.relative_to(root)),n,count,cols)
  else:cols=None
print(json.dumps({'tasks':len(tasks),'dag_acyclic':True,'distinct_owner_reviewer':True,'test_prerequisites':True,'mission_open_before_C0':True,'canonical_matrix_matches':True,'relative_links':True,'table_shapes':True,'topological_order':order},ensure_ascii=False,indent=2))
