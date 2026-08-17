#!/usr/bin/env python3
"""Score a human-reviewed correspondence benchmark JSON."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def norm(v:str)->str:return ' '.join(v.casefold().replace('-',' ').split())
def score_case(case):
    gt={norm(v) for v in case.get('ground_truth_corresponding_authors',[]) if v};pred={norm(v) for v in case.get('predicted_corresponding_authors',[]) if v}
    return {'paper_id':case.get('paper_id'),'tp':len(gt&pred),'fp':len(pred-gt),'fn':len(gt-pred),'ground_truth':sorted(gt),'predicted':sorted(pred)}
def summarize(payload):
    reviewed=[c for c in payload.get('cases',[]) if c.get('review_status') in {'PASS','REVIEWED'}]
    rows=[score_case(c) for c in reviewed];tp=sum(r['tp'] for r in rows);fp=sum(r['fp'] for r in rows);fn=sum(r['fn'] for r in rows);precision=tp/(tp+fp) if tp+fp else 1.0;recall=tp/(tp+fn) if tp+fn else 1.0
    return {'reviewed_cases':len(reviewed),'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'hard_gate_fp_zero':fp==0,'recall_gate_0_90':recall>=0.90,'pass':fp==0 and recall>=0.90,'failures':[r for r in rows if r['fp'] or r['fn']]}
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('benchmark',type=Path);a=p.parse_args();payload=json.loads(a.benchmark.read_text(encoding='utf-8'));result=summarize(payload);print(json.dumps(result,indent=2,ensure_ascii=False));return 0 if result['pass'] else 1
if __name__=='__main__':raise SystemExit(main())
