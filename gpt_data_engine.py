#!/usr/bin/env python3
"""Optional GPT/Code Interpreter data engine. Production TCG data is read-only by default."""
from __future__ import annotations
import io, json, logging, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import KNNImputer, SimpleImputer
    from sklearn.metrics import accuracy_score, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
except ImportError:
    np = pd = None
    RandomForestClassifier = RandomForestRegressor = None
    KNNImputer = SimpleImputer = None
    accuracy_score = r2_score = train_test_split = Pipeline = None

logging.basicConfig(level=logging.INFO, format='[%(asctime)s][%(levelname)s] %(message)s')
PROTECTED_RE = re.compile(r'(?:^|_)(?:id|key|name|card|number|cert|grade|price|amount|value|currency|fx|date|time|source|url|region|language|condition|variant|quantity|unit|sold|release|event|promo|status|lineage)(?:_|$)', re.I)

@dataclass(frozen=True)
class CorrectionPolicy:
    allow_numeric_imputation: bool = False
    allow_categorical_imputation: bool = False
    allow_outlier_clipping: bool = False
    knn_neighbors: int = 3

def is_protected_column(name: Any) -> bool:
    return bool(PROTECTED_RE.search(str(name or '')))

def _need_tabular():
    if pd is None or np is None:
        raise RuntimeError('Use this optional engine in GPT/Code Interpreter with pandas and numpy available.')

def _need_ml():
    _need_tabular()
    if Pipeline is None:
        raise RuntimeError('Model training requires scikit-learn in GPT/Code Interpreter.')

class GPTDataOptimizationEngine:
    def __init__(self, target_column=None, correction_policy=None):
        self.target_column = target_column
        self.policy = correction_policy or CorrectionPolicy()
        self.raw_df = self.clean_df = self.best_model = None
        self.diagnostics_report = {}
        self.correction_log = []

    def collect_data(self, source):
        _need_tabular()
        if isinstance(source, pd.DataFrame):
            df = source.copy(deep=True)
        elif isinstance(source, Path) or (isinstance(source, str) and Path(source).is_file()):
            p = Path(source)
            if p.suffix.lower() == '.csv': df = pd.read_csv(p)
            elif p.suffix.lower() in {'.json', '.jsonl', '.ndjson'}: df = pd.read_json(p, lines=p.suffix.lower() != '.json')
            else: raise ValueError(f'unsupported file extension: {p.suffix}')
        elif isinstance(source, str):
            try:
                data = json.loads(source)
                if isinstance(data, dict): data = [data]
                df = pd.DataFrame(data)
            except json.JSONDecodeError:
                df = pd.read_csv(io.StringIO(source))
        else:
            df = pd.DataFrame(source)
        if not len(df.columns): raise ValueError('dataset has no columns')
        self.raw_df = df.copy(deep=True)
        return df

    def diagnose_errors(self, df=None):
        _need_tabular(); df = self.raw_df if df is None else df
        if df is None: raise RuntimeError('collect_data must run first')
        report = {'rows': int(len(df)), 'columns': int(len(df.columns)), 'missing': {}, 'outliers': {}, 'duplicates': int(df.duplicated().sum()), 'protected_columns': []}
        for col in df.columns:
            name = str(col); missing = int(df[col].isna().sum())
            if missing: report['missing'][name] = missing
            if is_protected_column(name): report['protected_columns'].append(name)
        for col in df.select_dtypes(include=[np.number]).columns:
            finite = df[col].replace([np.inf, -np.inf], np.nan).dropna()
            if len(finite) < 4: continue
            q1, q3 = finite.quantile(.25), finite.quantile(.75); iqr = q3-q1
            if not np.isfinite(iqr) or iqr <= 0: continue
            lb, ub = q1-1.5*iqr, q3+1.5*iqr; count = int(((finite < lb)|(finite > ub)).sum())
            if count: report['outliers'][str(col)] = {'count': count, 'lower': float(lb), 'upper': float(ub), 'protected': is_protected_column(col)}
        report['total_findings'] = sum(report['missing'].values()) + sum(x['count'] for x in report['outliers'].values()) + report['duplicates']
        self.diagnostics_report = report
        return report

    def auto_correct(self, df=None):
        _need_tabular(); df = self.raw_df if df is None else df
        if df is None: raise RuntimeError('collect_data must run first')
        if not self.diagnostics_report: self.diagnose_errors(df)
        clean = df.copy(deep=True); self.correction_log = []
        numeric = [str(c) for c in clean.select_dtypes(include=[np.number]).columns if not is_protected_column(c)]
        if self.policy.allow_outlier_clipping:
            for col in numeric:
                item = self.diagnostics_report['outliers'].get(col)
                if item:
                    before = clean[col].copy(); clean[col] = clean[col].clip(item['lower'], item['upper'])
                    changed = int((before != clean[col]).fillna(False).sum())
                    if changed: self.correction_log.append({'action':'clip_iqr','column':col,'rows':changed})
        if self.policy.allow_numeric_imputation:
            cols = [c for c in numeric if clean[c].isna().any() and clean[c].notna().any()]
            if cols:
                n = max(1, min(self.policy.knn_neighbors, max(1, len(clean)-1))); before = {c:int(clean[c].isna().sum()) for c in cols}
                clean[cols] = KNNImputer(n_neighbors=n).fit_transform(clean[cols])
                for c in cols: self.correction_log.append({'action':'knn_impute','column':c,'rows':before[c]-int(clean[c].isna().sum())})
        if self.policy.allow_categorical_imputation:
            for col in clean.select_dtypes(include=['object','category']).columns:
                if is_protected_column(col) or not clean[col].isna().any(): continue
                mode = clean[col].mode(dropna=True); value = mode.iloc[0] if not mode.empty else 'Unknown'; count = int(clean[col].isna().sum())
                clean[col] = clean[col].fillna(value); self.correction_log.append({'action':'mode_impute','column':str(col),'rows':count})
        self.clean_df = clean
        return clean

    def learn_and_optimize(self, target_column=None):
        _need_ml(); target = target_column or self.target_column
        if self.clean_df is None: raise RuntimeError('auto_correct must run first')
        if not target or target not in self.clean_df.columns: return {'status':'cleaned_without_model_training'}
        X = self.clean_df.drop(columns=[target]).select_dtypes(include=[np.number]); y = self.clean_df[target]
        valid = y.notna(); X, y = X.loc[valid], y.loc[valid]
        if X.shape[1] == 0: return {'status':'no_numeric_features'}
        if len(X) < 10: return {'status':'insufficient_rows','rows':int(len(X))}
        classification = str(y.dtype) in {'object','category','bool'} or y.nunique() <= min(20, max(2, int(len(y)*.1)))
        stratify = y if classification and y.value_counts().min() >= 2 else None
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.2, random_state=42, stratify=stratify)
        model = RandomForestClassifier(random_state=42, n_estimators=150, max_depth=10, n_jobs=-1) if classification else RandomForestRegressor(random_state=42, n_estimators=150, max_depth=10, n_jobs=-1)
        base = Pipeline([('imputer',SimpleImputer(strategy='median')),('model',model)]); opt = Pipeline([('imputer',KNNImputer(n_neighbors=max(1,min(3,len(Xtr)-1)))),('model',model)])
        base.fit(Xtr,ytr); opt.fit(Xtr,ytr); bp = base.predict(Xte); op = opt.predict(Xte)
        score = accuracy_score if classification else r2_score; bs, os = float(score(yte,bp)), float(score(yte,op)); self.best_model = opt
        return {'status':'trained','task':'classification' if classification else 'regression','metric':'accuracy' if classification else 'r2','baseline':round(bs,6),'optimized':round(os,6),'improvement':round(os-bs,6)}

def run_gpt_pipeline(data_source, target_column=None, *, correction_policy=None, train_model=False):
    engine = GPTDataOptimizationEngine(target_column, correction_policy); raw = engine.collect_data(data_source); diagnostics = engine.diagnose_errors(raw); clean = engine.auto_correct(raw)
    optimization = engine.learn_and_optimize(target_column) if train_model and target_column else {}
    return {'engine':engine,'clean_dataframe':clean,'diagnostics':diagnostics,'optimization':optimization,'corrections':engine.correction_log}

if __name__ == '__main__':
    print('GPT Data Engine v2.5-safe loaded; TCG source-of-truth fields are diagnosis-only by default.')
