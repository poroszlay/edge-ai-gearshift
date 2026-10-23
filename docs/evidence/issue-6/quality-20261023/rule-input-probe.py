import json
from pathlib import Path
import numpy as np
from pc.model import read_windows, quantize, classification_report, write_json
params=json.loads(Path('models/mlp-v1/audit.json').read_text())['input']
results={}
for split in ('train','validation'):
    x,y,ids,manifest=read_windows('data/generated/dataset-v2',split,purpose='reference')
    q=quantize(x,params['scales'][0],params['zero_points'][0])
    restored=(q.astype(np.float32)-params['zero_points'][0])*params['scales'][0]
    def rule(a):
        a=a.reshape(-1,20,5).astype(np.float64)
        recent=a[:,-5:,:3].mean(axis=1)*[80,1,10]
        margin=recent[:,0]-(30+20*recent[:,1]+.5*recent[:,2])
        gear=a[:,-1,3]>.5
        active=a[:,-1,4]>=.1
        p=np.ones(len(a),dtype=np.int64)
        p[active & ~gear & (margin>0)]=2
        p[active & gear & (margin< -10)]=0
        return p,margin+10*gear
    original,margin=rule(x)
    approximate,_=rule(restored)
    results[split]={'dataset_id':manifest['dataset_id'],'original_scaled_rule':classification_report(y,original), 'input_quantized_rule':classification_report(y,approximate)}
    results[split]['errors_by_true_class']=[{'class_index':k,'count':int(((y==k)&(approximate!=y)).sum()),'within_0_25_kmh':int(((y==k)&(approximate!=y)&(abs(margin)<.25)).sum())} for k in range(3)]
write_json('results/issue-6/quality/rule-input-probe.json',results)
