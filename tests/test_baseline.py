"""Protect handoff alignment, metric definitions and fold-local fitting."""
import copy
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

from phishguard_vn.evaluation import summarize_predictions
from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.modeling import run_baseline, predict_url


@pytest.fixture
def inputs():
    feature_rows, targets, folds = [], [], []
    for group in range(6):
        for label in range(2):
            row_id=f"train-{group}-{label}"
            values={c:float(group+label+1) for c in CANDIDATE_FEATURES}
            values.update(id=row_id,url_len=float(10+group*2+label))
            feature_rows.append(values)
            targets.append(dict(id=row_id,label="phishing" if label else "benign",tier="gold",
                                split="train",registrable_domain=f"site-{group}.example"))
            folds.append(dict(id=row_id,fold_id=group%3))
    for split,offset in [("val",1000),("test",10000)]:
        for label in range(2):
            row_id=f"{split}-{label}"
            values={c:float(label+1) for c in CANDIDATE_FEATURES}
            values.update(id=row_id,url_len=float(offset+label))
            feature_rows.append(values)
            targets.append(dict(id=row_id,label="phishing" if label else "benign",tier="silver",
                                split=split,registrable_domain=f"{split}-{label}.example"))
    config={"experiment":{"seed":42},"evaluation":{"n_splits":3,"use_test":False,
            "decision_threshold":0.5},"model":{"compare_balanced":False}}
    return pd.DataFrame(feature_rows),pd.DataFrame(targets),pd.DataFrame(folds),config


def test_average_precision_and_confusion_definitions():
    metrics=summarize_predictions([0,1,1,0],[1,1,0,0],[0.6,0.8,0.3,0.2])
    assert [metrics[k] for k in ['tn','fp','fn','tp']]==[1,1,1,1]
    assert metrics['pr_auc']==pytest.approx(5/6)
    assert metrics['f1_phishing']==pytest.approx(0.5)
    assert metrics['pr_auc_definition']=='average_precision'


def test_no_positive_support_is_explicitly_undefined():
    metrics=summarize_predictions([0,0],[0,0],[0.1,0.2])
    assert metrics['recall_phishing'] is None and metrics['pr_auc'] is None


@pytest.mark.parametrize('scores',[[np.nan,0.5],[0.1,1.2]])
def test_invalid_scores_are_rejected(scores):
    with pytest.raises(ValueError,match='Scores'):
        summarize_predictions([0,1],[0,1],scores)


def test_scaler_never_fits_holdout_validation_or_test(inputs,monkeypatch):
    X,y,folds,config=inputs
    seen=[];original=StandardScaler.fit
    def tracking(self,values,*args,**kwargs):
        seen.append(set(values['url_len']))
        return original(self,values,*args,**kwargs)
    monkeypatch.setattr(StandardScaler,'fit',tracking)
    result=run_baseline(X,y,folds,config)
    training=X.merge(folds,on='id')
    expected=[set(training.loc[training.fold_id.ne(f),'url_len']) for f in range(3)]
    expected.append(set(training.url_len))
    assert seen==expected
    assert len(result['cv_predictions'])==12*2
    assert not result['scope']['test_evaluated']
    assert set(result['validation_predictions'].id)=={'val-0','val-1'}


def test_validation_labels_do_not_select_configuration(inputs):
    X,y,folds,config=inputs;config=copy.deepcopy(config)
    config['model']['compare_balanced']=True
    first=run_baseline(X,y,folds,config)
    changed=y.copy();mask=changed.split.ne('train')
    changed.loc[mask,'label']=changed.loc[mask,'label'].map({'phishing':'benign','benign':'phishing'})
    second=run_baseline(X.sample(frac=1,random_state=1),changed,folds,config)
    assert first['selected_model']==second['selected_model']
    pd.testing.assert_frame_equal(first['cv_predictions'],second['cv_predictions'])


def test_val_test_ids_cannot_enter_folds(inputs):
    X,y,folds,config=inputs
    extra=pd.concat([folds,pd.DataFrame([{'id':'test-0','fold_id':0}])],ignore_index=True)
    with pytest.raises(ValueError,match='eligible train IDs'):
        run_baseline(X,y,extra,config)


def test_domain_cannot_be_split_between_folds(inputs):
    X,y,folds,config=inputs;bad=folds.copy()
    bad.loc[bad.id.eq('train-0-1'),'fold_id']=1
    with pytest.raises(ValueError,match='same domain'):
        run_baseline(X,y,bad,config)


def test_metadata_and_missing_train_rows_cannot_silently_enter_X(inputs):
    X,y,folds,config=inputs
    with pytest.raises(ValueError,match='metadata'):
        run_baseline(X.assign(source='leak'),y,folds,config)
    with pytest.raises(ValueError,match='exactly the resolved'):
        run_baseline(X.loc[X.id.ne('train-0-0')],y,folds,config)


def test_artifact_reload_predicts_identically_and_rejects_bad_url(inputs,tmp_path):
    X,y,folds,config=inputs;result=run_baseline(X,y,folds,config)
    path=tmp_path/'model.joblib';joblib.dump(result['pipeline'],path)
    first=predict_url('https://example.com/a',result['pipeline'],result['feature_names'])
    second=predict_url('https://example.com/a',joblib.load(path),result['feature_names'])
    assert first==second and 0<=first['score']<=1
    with pytest.raises(ValueError,match='invalid_port'):
        predict_url('https://example.com:99999/a',result['pipeline'],result['feature_names'])


def test_test_scoring_option_is_rejected(inputs):
    X,y,folds,config=inputs;config=copy.deepcopy(config);config['evaluation']['use_test']=True
    with pytest.raises(ValueError,match='test evaluation'):
        run_baseline(X,y,folds,config)


@pytest.mark.parametrize("section,key,value", [
    ("model", "selection_metric", "accuracy"),
    ("model", "scaling", "none"),
    ("model", "baseline", "svm"),
    ("model", "C", 0.1),
    ("evaluation", "strategy", "random_split"),
])
def test_unsupported_experiment_settings_fail_explicitly(inputs,section,key,value):
    X,y,folds,config=inputs;config=copy.deepcopy(config)
    config.setdefault(section,{})[key]=value
    with pytest.raises(ValueError,match="Unsupported"):
        run_baseline(X,y,folds,config)


def _report_fixture(root):
    config_path=root/'configs/baseline.toml'
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[experiment]\nseed=42\n',encoding='utf-8')
    interim=root/'data/interim';interim.mkdir(parents=True)
    for name in ['core_gold_silver.csv','03_matrix_X_features.csv',
                 '03_registrable_domains.csv','02_group_folds_train.csv']:
        (interim/name).write_text('id\nfixture\n',encoding='utf-8')
    return config_path


def test_rerun_keeps_manual_error_annotations(inputs,tmp_path):
    from phishguard_vn.reporting import save_results
    X,y,folds,config=inputs
    result=run_baseline(X,y,folds,config)
    config_path=_report_fixture(tmp_path)
    save_results(result,config,tmp_path,config_path)
    path=tmp_path/'reports/tables/04_error_examples.csv'
    notes=pd.read_csv(path,keep_default_na=False)
    assert len(notes)>0
    chosen=notes.iloc[0]
    notes.loc[0,'observation']='manually checked this example'
    notes.to_csv(path,index=False)
    save_results(result,config,tmp_path,config_path)
    after=pd.read_csv(path,keep_default_na=False)
    row=after.loc[after.id.eq(chosen.id)&after.model.eq(chosen.model)&after.error_type.eq(chosen.error_type)]
    assert row.iloc[0].observation=='manually checked this example'


def test_report_describes_actual_run_and_publishes_environment(inputs,tmp_path):
    from phishguard_vn.reporting import save_results
    X,y,folds,config=inputs
    result=run_baseline(X,y,folds,config)
    config_path=_report_fixture(tmp_path)
    save_results(result,config,tmp_path,config_path)
    text=(tmp_path/'reports/week4_baseline.md').read_text(encoding='utf-8')
    assert '24 phishing samples' not in text
    assert 'Two unresolved URLs' not in text
    assert 'Balanced LR prioritizes' not in text
    assert (tmp_path/'reports/tables/04_run_metadata.json').is_file()


def test_error_sample_covers_folds_and_is_order_invariant():
    from phishguard_vn.reporting import select_error_examples
    rows = []
    for fold in range(3):
        for error_type, true, predicted in [("fp", 0, 1), ("fn", 1, 0)]:
            for index in range(4):
                rows.append(dict(id=f"{fold}-{error_type}-{index}", model="selected", fold_id=fold,
                                 true_label=true, predicted_label=predicted, score=0.6 if predicted else 0.4))
    frame = pd.DataFrame(rows)
    selected = select_error_examples(frame, "selected")
    shuffled = select_error_examples(frame.sample(frac=1, random_state=17), "selected")
    pd.testing.assert_frame_equal(selected, shuffled)
    assert len(selected) == 10
    for _, group in selected.groupby("error_type"):
        assert group.fold_id.tolist() == [0, 1, 2, 0, 1]
        assert not group.id.duplicated().any()
    # If one fold has no errors, consume the available folds without inventing rows.
    sparse = select_error_examples(frame.loc[frame.fold_id.ne(1)], "selected")
    assert set(sparse.fold_id) == {0, 2} and len(sparse) == 10
    correct = frame.assign(predicted_label=frame.true_label)
    assert select_error_examples(correct, "selected").empty


def test_git_provenance_distinguishes_sources_from_generated_outputs(tmp_path):
    import subprocess
    from phishguard_vn.reporting import _git_provenance
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True)
    git("init")
    source = tmp_path / "runtime.py"
    source.write_text("value = 1\n", encoding="utf-8")
    git("add", "runtime.py")
    git("-c", "user.name=Baseline Test", "-c", "user.email=baseline-test@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
    head = git("rev-parse", "HEAD").stdout.strip()
    clean = _git_provenance(tmp_path, [source])
    assert clean["git_revision"] == head and clean["source_state"] == "matches_head"
    (tmp_path / "generated.csv").write_text("output\n", encoding="utf-8")
    outputs_only = _git_provenance(tmp_path, [source])
    assert outputs_only["source_state"] == "matches_head"
    assert "generated.csv" in outputs_only["git_worktree_status"]
    source.write_text("value = 2\n", encoding="utf-8")
    dirty = _git_provenance(tmp_path, [source])
    assert dirty["git_revision"] == head and dirty["source_state"] == "modified_from_head"
    assert "runtime.py" in dirty["git_source_worktree_status"]


def test_provenance_is_captured_before_generated_writes(inputs,tmp_path,monkeypatch):
    import json
    import phishguard_vn.reporting as reporting
    X,y,folds,config=inputs
    result=run_baseline(X,y,folds,config)
    config_path=_report_fixture(tmp_path)
    original=reporting._git_provenance
    captured=[]
    def capture(root,sources):
        captured.append(not (root/'reports/tables/04_cv_metrics.csv').exists())
        return original(root,sources)
    monkeypatch.setattr(reporting,'_git_provenance',capture)
    reporting.save_results(result,config,tmp_path,config_path)
    assert captured == [True]
    metadata=json.loads((tmp_path/'reports/tables/04_run_metadata.json').read_text(encoding='utf-8'))
    assert len(metadata['source_manifest_sha256']) == 64
    assert metadata['source_sha256_lf']['configs/baseline.toml'] == reporting._source_hash(config_path)


def test_error_diagnostics_reproduce_counts_and_reject_changed_inputs(inputs,tmp_path):
    import importlib.util
    import json
    from pathlib import Path
    from phishguard_vn.reporting import save_results
    path=Path(__file__).resolve().parents[1]/'scripts/analyze_baseline_errors.py'
    spec=importlib.util.spec_from_file_location('error_diagnostics',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    X,y,folds,config=inputs
    result=run_baseline(X,y,folds,config)
    config_path=_report_fixture(tmp_path)
    interim=tmp_path/'data/interim'
    X.to_csv(interim/'03_matrix_X_features.csv',index=False)
    y.assign(source='fixture').to_csv(interim/'core_gold_silver.csv',index=False)
    folds.to_csv(interim/'02_group_folds_train.csv',index=False)
    save_results(result,config,tmp_path,config_path)
    diagnostics=module.build_diagnostics(tmp_path)
    selected=result['selected_model']
    metrics=result['cv_metrics'].loc[result['cv_metrics'].model.eq(selected)]
    assert diagnostics['cv']['pooled']['fp'] == int(metrics.fp.sum())
    assert diagnostics['cv']['pooled']['fn'] == int(metrics.fn.sum())
    assert diagnostics['validation']['pooled']['rows'] == 2
    assert diagnostics['error_sample_collisions']
    # Reject predictions with a test ID even if shape and labels look valid.
    prediction_path=interim/'04_validation_predictions.csv'
    predictions=pd.read_csv(prediction_path)
    predictions.loc[predictions.model.eq(selected),'id']=['test-0','test-1']
    predictions.to_csv(prediction_path,index=False)
    with pytest.raises(ValueError,match='Unexpected prediction IDs'):
        module.build_diagnostics(tmp_path)
    with (interim/'03_matrix_X_features.csv').open('a') as handle:handle.write('\n')
    with pytest.raises(ValueError,match='Handoff changed'):
        module.build_diagnostics(tmp_path)
