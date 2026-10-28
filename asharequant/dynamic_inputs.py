"""Sealed prediction inputs for the main paper service; no legacy account plans.

Training calls the existing research implementation. Intraday consumers only
load saved parameters. Publishing an input never creates an order or a fill.
"""
import copy
import json
import math
import re
import sqlite3
from pathlib import Path

import pandas as pd

from .core import now, write_json, run_lock
from .paper_account import get, digest
from .research_policy import POLICY


def readonly(root, name):
    return sqlite3.connect((Path(root)/'data'/name).resolve().as_uri()+'?mode=ro', uri=True)


def validate(payload, spec, at, day):
    if not isinstance(payload, dict) or not isinstance(payload.get('forecasts'), list):
        raise ValueError('DYNAMIC_MODEL_INPUT_MISSING')
    stamp = pd.Timestamp(payload.get('generated_at'))
    if pd.isna(stamp) or stamp.tzinfo is None or stamp > at or payload.get('asof') != day:
        raise ValueError('MODEL_SNAPSHOT_STALE_OR_FUTURE')
    rows = payload['forecasts']
    if any(not isinstance(r,dict) for r in rows) or len(rows) != len(spec['universe']) or {r.get('symbol') for r in rows} != set(spec['universe']):
        raise ValueError('DECISION_COVERAGE_INCOMPLETE')
    for row in rows:
        k = row['symbol']
        if not isinstance(row.get('forecasts'), dict) or set(row['forecasts']) != {'1','5','20'}:
            raise ValueError('DYNAMIC_MODEL_SLOT_MISSING:'+k)
        for horizon, f in row['forecasts'].items():
            if not isinstance(f, dict) or not isinstance(f.get('model_parameters'), dict):
                raise ValueError('FROZEN_PARAMETERS_INVALID:'+k)
            cols = f.get('model_features', spec['candidate']['features'])
            if not isinstance(cols,list) or not cols:raise ValueError('FROZEN_PARAMETERS_INVALID:'+k)
            p = f['model_parameters']
            vectors = [p.get(key) for key in ('coefficients','means','scales')]
            if any(not isinstance(v,list) or len(v)!=len(cols) for v in vectors):
                raise ValueError('FROZEN_PARAMETERS_INVALID:'+k)
            values = [p.get('intercept'),f.get('predicted_return'),row.get('close')]+sum(vectors,[])
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values) or min(vectors[2])<=0:
                raise ValueError('FROZEN_PARAMETERS_INVALID:'+k)
            if f.get('final_training_last_label_end','9999') > day or f.get('horizon') != int(horizon):
                raise ValueError('MODEL_LABEL_NOT_MATURE_BEFORE_SESSION:'+k)
        if not payload.get('data_versions',{}).get(k):
            raise ValueError('MODEL_HISTORY_UNAVAILABLE:'+k)


def recipe(root):
    """Read frozen research recipes, never plans, NAV or old account positions."""
    from .research_paper import implementation, reviewed_implementation, engine_version
    from .strategy_experiment import configurations
    from .decision import DEFAULTS, load_fee_config
    with readonly(root,'research_paper.sqlite3') as db:
        db.execute('BEGIN')
        spec=get(db,'spec_revisions').get('v2') or get(db,'spec')['active']
        base=get(db,'meta_revisions').get('v2') or get(db,'meta')['account']
        if reviewed_implementation(db,spec)!=implementation() or base['engine_version']!=engine_version():
            raise ValueError('RESEARCH_IMPLEMENTATION_CHANGED_REQUIRES_REVIEW')
    current={**DEFAULTS,**json.loads((root/'decision_config.json').read_text())};load_fee_config(root,current)
    if any(k in current and current[k]!=v for k,v in base['config'].items()):
        raise ValueError('RISK_OR_FEE_CONFIG_CHANGED_REVIEW_REQUIRED')
    selection=json.loads((root/'active_research_config.json').read_text())
    if selection['variant']!='risk1.5_threshold1' or selection['mode']!='RESEARCH_PAPER_ONLY' or selection['formal_promotion']:
        raise ValueError('RESEARCH_ONLY_AUTHORIZED_VARIANT_REQUIRED')
    settings=json.loads((root/'strategy_experiment_config.json').read_text())
    variant=configurations(base['config'],spec.get('policy',POLICY),settings)[selection['variant']]
    with readonly(root,'dynamic/account.sqlite3') as db:
        meta=get(db,'meta')['account']
    if variant['config']!=meta['config'] or set(spec['universe'])!=set(meta['universe']):
        raise ValueError('RISK_OR_FEE_CONFIG_CHANGED_REVIEW_REQUIRED')
    return spec, base['config'], variant


def prepare(root, day=None):
    """Reuse a sealed forecast or train after today's close, without old settlement.

    A missing past forecast cannot be refitted using later snapshots. The old
    research ledger is read-only; new inputs have their own immutable versions.
    """
    from .core import cutoff
    from .intraday_data import days
    from .research_paper import predict_day
    from .connections import market_environment
    from .intraday_inference import model_snapshot
    root=Path(root);at=pd.Timestamp(now());day=day or str(cutoff(at).date());cal=days(root)
    if pd.Timestamp(day) not in cal or pd.Timestamp(day)>cutoff(at):
        raise ValueError('DYNAMIC_COMPLETED_SESSION_REQUIRED')
    with run_lock(root/'logs/dynamic_inputs'):
        spec,base,variant=recipe(root)
        pointer=root/'data/dynamic/model_inputs/latest.json'
        if pointer.exists() and json.loads(pointer.read_text()).get('asof')==day:
            existing=load(root,at,day)
            if existing['predictions']['asof']==day and existing['spec']==spec and existing['meta']['config']==variant['config']:
                return dict(status='ALREADY_PREPARED',asof=day,sha256=digest(existing))
        with readonly(root,'research_paper.sqlite3') as db:
            payload=get(db,'predictions').get(day)
        reused=payload is not None
        if payload is None:
            if day!=str(at.date()) or (at.hour,at.minute)<(15,5):
                raise ValueError('MISSING_SAVED_MODEL_NO_RETROSPECTIVE_TRAINING')
            payload=predict_day(root,cal,day,spec)
        validate(payload,spec,at if reused else pd.Timestamp(now()),day)
        for symbol,version in payload['data_versions'].items():
            model_snapshot(root,symbol,version,payload['generated_at'],pd.Timestamp(now()))
        env=market_environment(root,day)
        if env.get('state') not in ('risk_off','neutral','risk_on'):
            raise ValueError('DYNAMIC_MARKET_ENVIRONMENT_UNAVAILABLE')
        bundle=dict(version=1,available_at=now().isoformat(),predictions=payload,spec=spec,
                    meta=dict(config=variant['config']),base_config=base,variant=variant,
                    environment=env['state'],environment_evidence=env,
                    prediction_origin='EXISTING_SEALED_FORECAST' if reused else 'DAILY_ORIGINAL_RESEARCH_TRAINING',
                    mode='PAPER_ONLY',legacy_plan_required=False)
        checksum=digest(bundle);target=pointer.parent/'versions'/(checksum+'.json')
        if target.exists() and digest(json.loads(target.read_text()))!=checksum:
            raise ValueError('DYNAMIC_MODEL_INPUT_TAMPERED')
        if not target.exists():write_json(target,bundle)
        write_json(pointer,dict(asof=day,sha256=checksum))
        return dict(status='PREPARED',asof=day,sha256=checksum,prediction_origin=bundle['prediction_origin'],stocks=len(payload['forecasts']))


def load(root, at, day):
    try:
        folder=Path(root)/'data/dynamic/model_inputs'
        pointer=json.loads((folder/'latest.json').read_text())
        checksum=pointer['sha256']
        if not isinstance(checksum,str) or not re.fullmatch('[a-f0-9]{64}',checksum):
            raise ValueError('DYNAMIC_MODEL_INPUT_TAMPERED')
        bundle=json.loads((folder/'versions'/(checksum+'.json')).read_text())
        if digest(bundle)!=checksum:raise ValueError('DYNAMIC_MODEL_INPUT_TAMPERED')
        available=pd.Timestamp(bundle['available_at'])
        if available.tzinfo is None or available>at:raise ValueError('MODEL_SNAPSHOT_STALE_OR_FUTURE')
        validate(bundle['predictions'],bundle['spec'],at,day)
        if bundle['environment'] not in ('risk_off','neutral','risk_on') or bundle['environment_evidence']['asof']!=day:
            raise ValueError('DYNAMIC_MARKET_ENVIRONMENT_UNAVAILABLE')
        return bundle
    except (OSError,KeyError,TypeError,AttributeError,json.JSONDecodeError) as exc:
        raise ValueError('DYNAMIC_MODEL_INPUT_MISSING') from exc
