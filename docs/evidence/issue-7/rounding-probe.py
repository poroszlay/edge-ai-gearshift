import json, math
import numpy as np
import tensorflow as tf
from pathlib import Path
w=json.loads(Path('docs/evidence/issue-7/numeric-regression-windows.jsonl').read_text())
i=tf.lite.Interpreter(model_path='models/mlp-v2/model.tflite',num_threads=1,experimental_preserve_all_tensors=True,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
i.allocate_tensors();i.set_tensor(0,np.array([w['input_int8']],dtype=np.int8));i.invoke()
audit=json.loads(Path('models/mlp-v2/audit.json').read_text());ts=audit['tensors']
def mul(x,m,s,single):
 if single:return (x*m+(1<<(30-s)))>>(31-s)
 x=x*(1<<max(s,0));prod=x*m
 nudge=(1<<30) if prod>=0 else 1-(1<<30)
 high=abs(prod+nudge)//(1<<31)*(1 if prod+nudge>=0 else -1)
 right=max(-s,0);mask=(1<<right)-1
 return (high>>right)+((high&mask)>((mask>>1)+(1 if high<0 else 0)))
for single in (False,True):
 values=np.array(w['input_int8'],dtype=np.int64);prev=0;rows=[]
 for wi,bi,oi in ((6,5,7),(4,3,8),(2,1,9)):
  weights=i.get_tensor(wi).astype(np.int64);bias=i.get_tensor(bi).astype(np.int64)
  acc=weights@(values-ts[prev]['zero_points'][0])+bias
  result=[]
  for x,scale in zip(acc,ts[wi]['scales']):
   q,s=math.frexp(ts[prev]['scales'][0]*scale/ts[oi]['scales'][0]);m=int(math.floor(q*(1<<31)+.5))
   if m==(1<<31):m//=2;s+=1
   result.append(max(-128,min(127,mul(int(x),m,s,single)+ts[oi]['zero_points'][0])))
  values=np.array(result,dtype=np.int64)
  actual=i.get_tensor(oi).reshape(-1)
  rows.append(dict(tensor=oi,different=int(np.count_nonzero(values!=actual)),pc=actual.tolist() if oi==9 else None,emulated=values.tolist() if oi==9 else None))
  prev=oi
 print(json.dumps(dict(single_rounding=single,layers=rows)))
print('PC output',i.get_tensor(10).tolist())
