from pathlib import Path
import json
import numpy as np
from pc.model import read_windows, quantize, write_json
params=json.loads(Path('models/mlp-v1/audit.json').read_text())['input']
results={}
for split in ('train','validation'):
 x,y,ids,manifest=read_windows('data/generated/dataset-v2',split,purpose='reference')
 result={}
 for name,a in [('float32',x),('int8',quantize(x,params['scales'][0],params['zero_points'][0]))]:
  keys=np.ascontiguousarray(a).view(np.dtype((np.void,a.dtype.itemsize*a.shape[1]))).ravel()
  _,inverse=np.unique(keys,return_inverse=True)
  counts=np.bincount(inverse*3+y,minlength=(inverse.max()+1)*3).reshape(-1,3)
  conflicts=(counts>0).sum(axis=1)>1
  result[name]={'unique_inputs':len(counts),'conflicting_inputs':int(conflicts.sum()),'conflicting_class_supports':counts[conflicts].sum(axis=0).tolist(),'unavoidable_errors_lower_bound':int((counts.sum(axis=1)-counts.max(axis=1)).sum())}
 recent=x.reshape(-1,20,5).astype(np.float64)[:,-5:,:3].mean(axis=1)*[80,1,10]
 margin=recent[:,0]-(30+20*recent[:,1]+.5*recent[:,2])+10*(x[:,-2]>.5)
 result['threshold_margins']=[{'class_index':k,'support':int((y==k).sum()),'within_1e_5_kmh':int(((y==k)&(abs(margin)<1e-5)).sum()),'within_0_25_kmh':int(((y==k)&(abs(margin)<.25)).sum())} for k in range(3)]
 results[split]=result
write_json('results/issue-6/quality/alias-probe.json',results)
