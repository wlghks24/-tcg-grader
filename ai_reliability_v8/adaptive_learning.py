"""Leakage-resistant model selection for advisory review ranking.

The neural candidate is deliberately small because the inputs are six bounded,
tabular evidence-quality features.  No model produced here may verify a claim.
"""
import hashlib
import json
import math
import random

try:
    from .evidence_learning import (
        FEATURES, MAX_REAL_LABELS, MIN_REAL_LABELS, EvidenceLearner,
        logit, sigmoid, timestamp, vector, wilson_upper,
    )
except ImportError:  # Support running the copied module's tests from its own folder.
    from evidence_learning import (
        FEATURES, MAX_REAL_LABELS, MIN_REAL_LABELS, EvidenceLearner,
        logit, sigmoid, timestamp, vector, wilson_upper,
    )


ALLOWED_HIDDEN_SIZES = (4, 8, 12)
ALLOWED_MLP_SEEDS = (20260907, 20260917, 20260927)


def _brier(model, rows):
    return sum((_raw_probability(model, x) - y) ** 2 for _, x, y, _ in rows) / len(rows)


def _raw_probability(model, x):
    kind = model.get("kind")
    if kind == "l2_logistic":
        return sigmoid(logit(model["weights"], x))
    if kind == "mlp_ensemble":
        members = model.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError("INVALID_MODEL")
        return sum(_raw_probability(member, x) for member in members) / len(members)
    if kind != "shallow_mlp":
        raise ValueError("INVALID_MODEL")
    hidden = [math.tanh(b + sum(w * v for w, v in zip(ws, x)))
              for ws, b in zip(model["hidden_weights"], model["hidden_bias"])]
    return sigmoid(model["output_bias"] + sum(w * v for w, v in zip(model["output_weights"], hidden)))


def _finite(value,low=-1_000_000,high=1_000_000):
    return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def validate_prediction_model(model,*,require_operational=True):
    """Reject malformed, oversized or non-finite JSON models before inference."""
    if not isinstance(model,dict) or model.get('schema_version') not in (5,7,8):
        raise ValueError('INVALID_MODEL')
    schema_version=model.get('schema_version')
    if schema_version==8 and (
        type(model.get('training_label_count')) is not int
        or model.get('training_label_count') < MIN_REAL_LABELS
        or model.get('temporal_split_policy') != '50_15_15_20'
    ):
        raise ValueError('MODEL_TRAINING_POLICY_MISMATCH')
    if require_operational and model.get('operational') is not True:
        raise ValueError('MODEL_NOT_OPERATIONAL')
    if model.get('verification_authority') is not False or model.get('features')!=list(FEATURES):
        raise ValueError('INVALID_MODEL')
    if not _finite(model.get('calibration_slope'),.01,10) or not _finite(model.get('calibration_offset'),-10,10):
        raise ValueError('INVALID_MODEL')
    def check_core(core,depth=0):
        if not isinstance(core,dict) or depth>1: raise ValueError('INVALID_MODEL')
        kind=core.get('kind')
        if kind=='l2_logistic':
            weights=core.get('weights')
            if not isinstance(weights,list) or len(weights)!=len(FEATURES)+1 or not all(_finite(x) for x in weights):
                raise ValueError('INVALID_MODEL')
        elif kind=='shallow_mlp':
            size=core.get('hidden_size');hw=core.get('hidden_weights');hb=core.get('hidden_bias');ow=core.get('output_weights')
            if type(size) is not int or size not in ALLOWED_HIDDEN_SIZES or not isinstance(hw,list) or len(hw)!=size or not isinstance(hb,list) or len(hb)!=size or not isinstance(ow,list) or len(ow)!=size:
                raise ValueError('INVALID_MODEL')
            if depth==0 and require_operational:
                raise ValueError('UNENSEMBLED_NEURAL_MODEL_NOT_OPERATIONAL')
            values=[core.get('output_bias')]+hb+ow+[x for row in hw if isinstance(row,list) for x in row]
            if any(not isinstance(row,list) or len(row)!=len(FEATURES) for row in hw) or not all(_finite(x) for x in values):
                raise ValueError('INVALID_MODEL')
        elif kind=='mlp_ensemble':
            members=core.get('members'); size=core.get('hidden_size'); seeds=core.get('seeds')
            if (type(size) is not int or size not in ALLOWED_HIDDEN_SIZES or not isinstance(members,list) or len(members)!=3
                    or not isinstance(seeds,list) or tuple(seeds)!=ALLOWED_MLP_SEEDS or len(set(seeds))!=3):
                raise ValueError('INVALID_MODEL')
            for member in members:
                if not isinstance(member,dict) or member.get('kind')!='shallow_mlp' or member.get('hidden_size')!=size:
                    raise ValueError('INVALID_MODEL')
                check_core(member,depth+1)
        else: raise ValueError('INVALID_MODEL')
    check_core(model)
    return True


def _train_logistic(rows):
    weights = [0.0] * (len(FEATURES) + 1)
    for _ in range(350):
        gradient = [0.0] * len(weights)
        for _, x, y, _ in rows:
            error = sigmoid(logit(weights, x)) - y
            gradient[0] += error
            for j, value in enumerate(x, 1):
                gradient[j] += error * value
        for j in range(len(weights)):
            weights[j] -= .35 * (gradient[j] / len(rows) + (.01 * weights[j] if j else 0))
    return {"kind": "l2_logistic", "weights": weights}


def _train_mlp(rows, hidden_size=8, seed=20260907):
    rng = random.Random(seed)
    hw = [[rng.uniform(-.18, .18) for _ in FEATURES] for _ in range(hidden_size)]
    hb = [0.0] * hidden_size
    ow = [rng.uniform(-.18, .18) for _ in range(hidden_size)]
    ob = 0.0
    for _ in range(280):
        ghw = [[0.0] * len(FEATURES) for _ in range(hidden_size)]
        ghb = [0.0] * hidden_size
        gow = [0.0] * hidden_size
        gob = 0.0
        for _, x, y, _ in rows:
            hidden = [math.tanh(hb[h] + sum(hw[h][j] * x[j] for j in range(len(x)))) for h in range(hidden_size)]
            error = sigmoid(ob + sum(ow[h] * hidden[h] for h in range(hidden_size))) - y
            gob += error
            for h in range(hidden_size):
                gow[h] += error * hidden[h]
                delta = error * ow[h] * (1 - hidden[h] ** 2)
                ghb[h] += delta
                for j, value in enumerate(x):
                    ghw[h][j] += delta * value
        rate = .18
        inv_n = 1.0 / len(rows)
        ob -= rate * gob * inv_n
        for h in range(hidden_size):
            # Keep L2 on the same scale as the logistic baseline. The previous
            # implementation divided the regularizer by n a second time.
            ow[h] -= rate * (gow[h] * inv_n + .01 * ow[h])
            hb[h] -= rate * ghb[h] * inv_n
            for j in range(len(FEATURES)):
                hw[h][j] -= rate * (ghw[h][j] * inv_n + .01 * hw[h][j])
    return {"kind": "shallow_mlp", "hidden_size": hidden_size,
            "hidden_weights": hw, "hidden_bias": hb, "output_weights": ow, "output_bias": ob}


class AdaptiveEvidenceLearner(EvidenceLearner):
    """Select logistic or shallow MLP without looking at calibration/test results."""

    def fit(self, rows):
        if not isinstance(rows, list) or len(rows) < MIN_REAL_LABELS:
            return {
                "status": "MODEL_UPDATE_SKIPPED_KEEP_EXISTING",
                "minimum": MIN_REAL_LABELS,
                "maximum": MAX_REAL_LABELS,
                "label_count": len(rows) if isinstance(rows, list) else 0,
                "model": None,
                "existing_model_preserved": True,
                "selection": {"policy": "NO_MODEL_UPDATE_BELOW_1000_REAL_LABELS", "candidates": []},
            }
        if len(rows) > MAX_REAL_LABELS:
            return {
                "status": "INSUFFICIENT_OR_EXCESSIVE_LABELS",
                "minimum": MIN_REAL_LABELS,
                "maximum": MAX_REAL_LABELS,
                "label_count": len(rows),
                "model": None,
                "existing_model_preserved": True,
            }
        data, ids, groups, label_times = [], set(), set(), {}
        synthetic = False
        for row in rows:
            if any(row.get(k) != v for k, v in self.scope.items()):
                raise ValueError("TRAINING_SCOPE_MISMATCH")
            if row.get("label_source") not in ("human_audit", "external_outcome") or not row.get("label_reference"):
                raise ValueError("INDEPENDENT_LABEL_REQUIRED")
            if type(row.get("label")) is not int or row["label"] not in (0, 1):
                raise ValueError("BINARY_LABEL_REQUIRED")
            if not row.get("id") or not row.get("origin_group"):
                raise ValueError("IDENTITY_REQUIRED")
            if row["id"] in ids or row["origin_group"] in groups:
                raise ValueError("DUPLICATE_ORIGIN_GROUP")
            if type(row.get("synthetic")) is not bool:
                raise ValueError("DATA_PROVENANCE_REQUIRED")
            ids.add(row["id"]); groups.add(row["origin_group"]); synthetic |= row["synthetic"]
            observed, labeled = timestamp(row["observed_at"]), timestamp(row["labeled_at"])
            if labeled < observed:
                raise ValueError("LABEL_PRECEDES_OBSERVATION")
            label_times[row["id"]] = labeled
            data.append((observed, vector(row["features"]), row["label"], row["id"]))
        if synthetic:
            return {
                "status": "SYNTHETIC_LABELS_FORBIDDEN",
                "minimum": MIN_REAL_LABELS,
                "maximum": MAX_REAL_LABELS,
                "label_count": len(rows),
                "model": None,
                "existing_model_preserved": True,
            }
        data.sort(key=lambda item: item[0])
        a, b, c = int(len(data) * .5), int(len(data) * .65), int(len(data) * .8)
        train, tune, calibration, test = data[:a], data[a:b], data[b:c], data[c:]
        parts = (train, tune, calibration, test)
        if any(parts[i][-1][0] >= parts[i + 1][0][0] for i in range(3)):
            raise ValueError("TIME_SPLIT_OVERLAP")
        if any(max(label_times[r[3]] for r in parts[i]) >= parts[i + 1][0][0] for i in range(3)):
            raise ValueError("FUTURE_LABEL_LEAKAGE")
        if any(min(sum(r[2] == 0 for r in part), sum(r[2] == 1 for r in part)) < 20 for part in parts):
            return {"status": "INSUFFICIENT_CLASS_COVERAGE", "model": None}
        owner_counts={}
        for row in rows:
            owner=row.get('owner_group')
            if not isinstance(owner,str) or not owner: raise ValueError('OWNER_GROUP_REQUIRED')
            owner_counts[owner]=owner_counts.get(owner,0)+1
        dominance=max(owner_counts.values())/len(rows)
        if len(owner_counts)<3 or dominance>.7:
            return {'status':'INSUFFICIENT_SOURCE_DIVERSITY','model':None,
                    'data_quality':{'owner_groups':len(owner_counts),'owner_dominance':dominance}}
        logistic = _train_logistic(train)
        logistic_score = _brier(logistic,tune)
        seeds=ALLOWED_MLP_SEEDS
        families=[]
        for hidden_size in ALLOWED_HIDDEN_SIZES:
            members=[_train_mlp(train,hidden_size,seed) for seed in seeds]
            scores=[_brier(member,tune) for member in members]
            families.append({'hidden_size':hidden_size,'members':members,'scores':scores,
                             'mean':sum(scores)/len(scores),'range':max(scores)-min(scores)})
        best=min(families,key=lambda family:(family['mean']+.0002*family['hidden_size'],family['hidden_size']))
        stable=best['range']<=.03 and max(best['scores'])<=logistic_score+.01
        improved=best['mean']+.005<logistic_score
        selected={'kind':'mlp_ensemble','hidden_size':best['hidden_size'],'seeds':list(seeds),'members':best['members']} if stable and improved else logistic
        tune_scores={'l2_logistic':logistic_score,'shallow_mlp':best['mean']}
        logits = []
        for _, x, y, _ in calibration:
            p = max(1e-9, min(1-1e-9, _raw_probability(selected, x)))
            logits.append((math.log(p / (1-p)), y))
        slope, offset = 1.0, 0.0
        for _ in range(220):
            ga = gb = 0.0
            for z, y in logits:
                error = sigmoid(slope * z + offset) - y
                ga += error * z; gb += error
            slope = max(.01, min(10, slope - .05 * ga / len(logits)))
            offset = max(-10, min(10, offset - .05 * gb / len(logits)))
        def predict(x):
            p = max(1e-9, min(1-1e-9, _raw_probability(selected, x)))
            return sigmoid(slope * math.log(p / (1-p)) + offset)
        prevalence = sum(r[2] for r in train) / len(train)
        test_predictions = [(predict(x), y) for _, x, y, _ in test]
        brier = sum((p-y)**2 for p, y in test_predictions) / len(test_predictions)
        baseline = sum((prevalence-y)**2 for _, y in test_predictions) / len(test_predictions)
        negatives = sum(y == 0 for _, y in test_predictions)
        false_high = sum(y == 0 and p >= .9 for p, y in test_predictions)
        upper = wilson_upper(false_high, negatives)
        ece = 0.0
        for low in (0, .2, .4, .6, .8):
            high = low + .2
            pairs = [(p, y) for p, y in test_predictions
                     if low <= p < high or (low == .8 and p <= high and p >= low)]
            if pairs:
                ece += len(pairs)/len(test_predictions) * abs(sum(p for p, _ in pairs)/len(pairs)-sum(y for _, y in pairs)/len(pairs))
        drift = max(abs(sum(r[1][j] for r in train)/len(train)-sum(r[1][j] for r in test)/len(test)) for j in range(len(FEATURES)))
        passed = brier < baseline and upper <= .2 and ece <= .15 and drift <= .25
        model = dict(selected, schema_version=8, scope=self.scope, features=list(FEATURES),
                     calibration_slope=slope, calibration_offset=offset, threshold=.9,
                     operational=passed, verification_authority=False,
                     training_label_count=len(rows), temporal_split_policy='50_15_15_20',
                     candidate_hidden_sizes=list(ALLOWED_HIDDEN_SIZES), candidate_seeds=list(ALLOWED_MLP_SEEDS),
                     training_fingerprint=hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())
        return {"status": "READY_FOR_REVIEW_RANKING" if passed else "REJECTED",
                "model": model, "selection": {"policy": "MULTI_SEED_TUNE_ONLY_MIN_IMPROVEMENT_0.005", "tune_brier": tune_scores,
                "mlp_families": [{"hidden_size":f['hidden_size'],"seed_brier":f['scores'],"mean_brier":f['mean'],"range":f['range']} for f in families],
                "mlp_stable":stable,"mlp_improved":improved,"selected": selected["kind"], "test_was_used_for_selection": False},
                "data_quality":{"owner_groups":len(owner_counts),"owner_dominance":dominance},
                "metrics": {"brier": brier, "constant_brier": baseline, "ece_5_bins": ece,
                "false_high": false_high, "test_negatives": negatives, "false_high_wilson95_upper": upper,
                "feature_mean_drift": drift, "train": len(train), "tune": len(tune),
                "calibration": len(calibration), "test": len(test), "statistical_gates_passed": passed}}

    def save_model(self, report, path):
        model = report.get("model") if isinstance(report, dict) else None
        if isinstance(model, dict) and model.get("schema_version") in (5, 7, 8):
            try:
                validate_prediction_model(model)
            except ValueError:
                return {"status": "MODEL_NOT_PROMOTED"}
        return super().save_model(report, path)

    def rank(self, features, model=None):
        if not model or model.get("schema_version") not in (5,7,8):
            return super().rank(features, model)
        x = vector(features)
        if model.get("operational") is not True:
            return super().rank(features, None)
        if model.get("scope") != self.scope or model.get("features") != list(FEATURES) or model.get("verification_authority") is not False:
            raise ValueError("MODEL_SCOPE_OR_SCHEMA_MISMATCH")
        validate_prediction_model(model)
        p = max(1e-9, min(1-1e-9, _raw_probability(model, x)))
        score = sigmoid(model["calibration_slope"] * math.log(p/(1-p)) + model["calibration_offset"])
        return {"status": "ADVISORY_ONLY", "estimated_label_probability": score,
                "review_priority": "HIGH" if features["conflict"] or features["field_completeness"] < 1 or score < .9 else "NORMAL",
                "can_verify": False}

    def select_review_batch(self,candidates,model=None,*,limit=20):
        """Choose uncertain/conflicting rows while avoiding one-owner domination."""
        if not isinstance(candidates,list) or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('INVALID_REVIEW_BATCH')
        prepared=[];ids=set()
        for item in candidates:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'] or item['id'] in ids:
                raise ValueError('CANDIDATE_ID_REQUIRED')
            if not isinstance(item.get('owner_group'),str) or not item['owner_group']:
                raise ValueError('OWNER_GROUP_REQUIRED')
            ids.add(item['id']);features=item.get('features');vector(features)
            ranked=self.rank(features,model)
            probability=ranked.get('estimated_label_probability',.5)
            priority=(1.0 if features['conflict'] else 0.0)+(1-abs(probability-.5)*2)+(.5 if features['field_completeness']<1 else 0)
            prepared.append((priority,item))
        prepared.sort(key=lambda pair:(-pair[0],pair[1]['id']))
        selected=[];owner_counts={};owner_cap=max(1,math.ceil(limit*.4))
        for priority,item in prepared:
            owner=item['owner_group']
            if owner_counts.get(owner,0)>=owner_cap: continue
            selected.append({'id':item['id'],'owner_group':owner,'review_score':priority,'can_self_label':False})
            owner_counts[owner]=owner_counts.get(owner,0)+1
            if len(selected)>=limit: break
        return {'status':'REVIEW_BATCH_READY','selected':selected,'owner_cap':owner_cap,
                'unfilled':max(0,limit-len(selected)),'labels_must_be_independent':True}
