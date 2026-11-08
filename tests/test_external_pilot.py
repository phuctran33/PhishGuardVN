"""Synthetic audit/evaluation fixtures; no external ground truth or real model metrics."""
import json

import numpy as np
import pandas as pd
import pytest

from phishguard_vn.external_pilot import (REVIEW_FIELDS,build_ledger,evaluate_verified,format_diagnostic,
                                         load_locked_teacher,sha256,url_views)


def candidates(urls=None, labels=None):
    urls=urls or ['alpha-example.com','https://beta-example.org/','gamma-example.net']
    labels=labels or ['phishing','benign','phishing']
    return pd.DataFrame({'id':[f'c{i}' for i in range(len(urls))],'url':urls,'label':labels,
                         'source':[f'source{i%2}' for i in range(len(urls))],
                         'evidence_ref':['https://authority.example/reference']*len(urls),
                         'review_status':['pending']*len(urls),'review_note':['unverified fixture']*len(urls)})


def verified(c, core=None, scope='hostname_historical', full=False):
    first=build_ledger(c,core or {})
    records=[]
    for r in first.to_dict('records'):
        records.append({'id':r['id'],'candidate_signature':r['candidate_signature'],'review_status':'verified',
            'reviewer':'synthetic reviewer fixture','reviewed_at':'2026-01-01T00:00:00Z',
            'review_evidence':'synthetic fixture evidence, not real labels','label_scope':scope,
            'full_url_verified':str(full).lower(),'source_independence':'unresolved','review_method':'human',
            'evidence_document_sha256':'','evidence_locator':'','evidence_limitations':''})
    return build_ledger(c,core or {},reviews=pd.DataFrame(records,columns=REVIEW_FIELDS))


@pytest.mark.parametrize('raw,host', [('example.com','example.com'),('HTTPS://EXAMPLE.COM/Path?A=B','example.com'),
    ('https://BÜCHER.de/Path','xn--bcher-kva.de'),('http://user:pass@example.com:8080/x','example.com'),
    ('http://[2001:db8::1]/x','[2001:db8::1]')])
def test_label_blind_hostname_representation_and_raw_preservation(raw,host):
    c=candidates([raw,raw],['benign','phishing'])
    ledger=build_ledger(c,{})
    assert ledger.raw_url.tolist()==[raw,raw]
    assert ledger.model_input_host.tolist()==[host,host]
    from phishguard_vn.features import extract_features
    assert extract_features(ledger.model_input_host.iloc[0])==extract_features(ledger.model_input_host.iloc[1])
    assert ledger.normalized_url.nunique()==1
    assert ledger.review_status.eq('pending').all()  # Conflicting proposals are flagged, not relabeled.
    assert ledger.conflicting_labels_model_input_host.all()


def test_no_invented_scheme_path_and_no_casefolding_path():
    bare=url_views('Example.com/Path?Q=A')
    full=url_views('https://EXAMPLE.com/Path?Q=A')
    assert bare['normalized_url']=='example.com/Path?Q=A' and bare['model_input_full']==''
    assert full['normalized_url']=='https://example.com/Path?Q=A'
    assert full['model_input_full'].endswith('/Path?Q=A')
    assert not bare['observed_http_scheme'] and full['observed_http_scheme']
    assert url_views('https://example.com/path?q=a')['normalized_url']!=full['normalized_url']
    assert url_views('example.com')['path']==''


def test_legacy_casefolded_path_is_a_metadata_warning_not_row_or_label_deletion():
    c=candidates(['https://vexere.com/en-US/gioi-thieu.html/'],['benign'])
    c['url_norm']='vexere.com/en-us/gioi-thieu.html/'
    ledger=build_ledger(c,{})
    assert len(ledger)==1 and ledger.stored_url_norm_mismatch.item()
    assert ledger.normalized_url.item()=='https://vexere.com/en-US/gioi-thieu.html/'
    assert ledger.review_status.item()=='pending' and ledger.label.item()=='benign'


@pytest.mark.parametrize('url', ['', 'https://example.com:99999/a','https://[broken/','not_a_resolved_domain'])
def test_bad_parse_never_becomes_fake_model_input(url):
    view=url_views(url)
    assert not view['parse_valid'] and view['model_input_host']==view['model_input_full']==''


def test_shared_registrable_domain_is_not_automatic_deletion_or_rejection():
    c=candidates(['a.shared-example.com','b.shared-example.com'],['benign','phishing'])
    ledger=verified(c)
    assert len(ledger)==2 and ledger.id.tolist()==c.id.tolist()
    assert ledger.shared_registrable_domain.all() and ledger.conflicting_labels_registrable_domain.all()
    assert ledger.review_status.eq('verified').all() and ledger.eligible_host_only.all()


def test_core_overlap_blocks_evaluation_but_retains_reviewed_candidate():
    ledger=verified(candidates(),core={'registrable_domain':{'alpha-example.com'}})
    assert len(ledger)==3 and ledger.review_status.eq('verified').all()
    assert not ledger.loc[ledger.id.eq('c0'),'eligible_host_only'].item()


def test_missing_source_does_not_delete_pending_but_cannot_be_verified():
    c=candidates();c.loc[0,'evidence_ref']=''
    assert len(build_ledger(c,{}))==3
    with pytest.raises(ValueError,match='usable source reference'):verified(c)


def test_scheme_artifact_diagnostic_is_not_a_detection_metric():
    ledger=build_ledger(candidates(['alpha-example.com','https://beta-example.org/'],['phishing','benign']),{})
    before=format_diagnostic(ledger,'raw_url');after=format_diagnostic(ledger,'model_input_host')
    assert before['apparent_majority_label_matches']==2 and after['apparent_majority_label_matches']==1
    assert after['format_strata']==1 and 'ground-truth' in after['definition']


@pytest.mark.parametrize('defect',['signature','reviewer','reviewed_at','review_evidence','status'])
def test_review_binding_rejects_stale_or_incomplete_annotations(defect):
    c=candidates();first=build_ledger(c,{})
    review={'id':'c0','candidate_signature':first.loc[0,'candidate_signature'],'review_status':'verified',
            'reviewer':'fixture','reviewed_at':'2026-01-01Z','review_evidence':'fixture evidence',
            'label_scope':'hostname_historical','full_url_verified':'false','source_independence':'unresolved',
            'review_method':'human','evidence_document_sha256':'','evidence_locator':'','evidence_limitations':''}
    review['reviewed_at']='2026-01-01T00:00:00Z'
    if defect=='signature':review['candidate_signature']='stale'
    if defect in ['reviewer','reviewed_at','review_evidence']:review[defect]=''
    if defect=='status':review['review_status']='accepted_without_review'
    with pytest.raises(ValueError):build_ledger(c,{},reviews=pd.DataFrame([review],columns=REVIEW_FIELDS))


def test_pending_rows_are_never_scored_and_no_zero_recall_is_fabricated():
    def forbidden(_):raise AssertionError('No inference on pending ground truth')
    result,pred=evaluate_verified(build_ledger(candidates(),{}),forbidden)
    assert result['metrics'] is None and result['n_evaluated']==0 and pred.empty


@pytest.mark.parametrize('defect',['method','hash','locator','limitations','current_scope','full_url'])
def test_ai_document_reviews_cannot_claim_human_or_live_full_url_verification(defect):
    c=candidates()
    first=verified(c)
    review=first.loc[[0],REVIEW_FIELDS].copy()
    review['review_method']='ai_document_review'
    review['evidence_document_sha256']='a'*64
    review['evidence_locator']='synthetic article warning list, exact hostname'
    review['evidence_limitations']='Synthetic fixture; not human or live-site verification'
    if defect=='method':review['review_method']='unspecified'
    if defect=='hash':review['evidence_document_sha256']='missing'
    if defect=='locator':review['evidence_locator']=''
    if defect=='limitations':review['evidence_limitations']=''
    if defect=='current_scope':review['label_scope']='hostname_current'
    if defect=='full_url':review['full_url_verified']=True
    with pytest.raises(ValueError):build_ledger(c,{},reviews=review)


def test_ai_historical_document_review_is_transparent_and_pending_is_not_scored():
    c=candidates()
    review=verified(c).loc[[0],REVIEW_FIELDS].copy()
    review['reviewer']='AI fixture'
    review['review_method']='ai_document_review'
    review['evidence_document_sha256']='a'*64
    review['evidence_locator']='synthetic source section'
    review['evidence_limitations']='Historical identity only, not human or current verification'
    ledger=build_ledger(c,{},reviews=review)
    result,pred=evaluate_verified(ledger,lambda _:dict(label='phishing',score=.9,score_kind='probability'))
    assert result['review_methods']=={'ai_document_review':1}
    assert pred.id.tolist()==['c0'] and ledger.review_status.eq('pending').sum()==2
    assert not ledger.full_url_verified.any() and not ledger.eligible_full_url.any()


def fixture_predictor(url):
    positive=url.startswith('alpha')
    return {'label':'phishing' if positive else 'benign','score':.9 if positive else .1,'score_kind':'probability'}


def test_phishing_only_recall_and_per_source_omit_two_class_metrics():
    result,pred=evaluate_verified(verified(candidates()),fixture_predictor)
    assert len(pred)==2 and result['metrics']['recall_phishing']==.5
    assert result['metrics']['positive_support']==2 and result['metrics']['negative_support']==0
    assert all(result['metrics'][m] is None for m in ['precision','f1','accuracy','fpr'])
    assert all(s['fpr'] is None for s in result['by_source']) and result['official'] is False


def test_two_class_requires_both_verified_labels():
    result,_=evaluate_verified(verified(candidates()),fixture_predictor,two_class=True)
    assert result['metrics']['accuracy']==pytest.approx(2/3) and result['metrics']['fpr']==0
    assert result['official'] is False
    with pytest.raises(ValueError,match='both verified'):
        evaluate_verified(verified(candidates(labels=['phishing']*3)),fixture_predictor,two_class=True)


def test_full_url_cannot_invent_missing_scheme_or_transport_host_labels():
    ledger=verified(candidates(),scope='full_url',full=True)
    assert ledger.eligible_full_url.sum()==1  # Only the actually observed HTTPS input.
    result,_=evaluate_verified(verified(candidates()),fixture_predictor,representation='full_url')
    assert result['n_evaluated']==0 and result['metrics'] is None


def test_forged_eligibility_and_inference_failure_are_not_silently_dropped():
    ledger=build_ledger(candidates(),{});ledger['review_status']='verified';ledger['eligible_host_only']=True
    with pytest.raises(ValueError,match='review identity'):evaluate_verified(ledger,fixture_predictor)
    ledger=verified(candidates())
    with pytest.raises(ValueError,match='Invalid inference'):
        evaluate_verified(ledger,lambda _:dict(label='phishing',score=np.nan,score_kind='probability'))
    ledger.loc[0,'model_input_host']='changed.example.com'
    with pytest.raises(ValueError,match='changed model input'):evaluate_verified(ledger,fixture_predictor)


@pytest.mark.parametrize('change',[{'teacher_finalized':False},{'external_used_for_selection':True},
    {'selected_by':'validation'},{'feature_set':'e2-brand-v0'},{'threshold':.9},
    {'operating_point_scope':'external_selected'}])
def test_teacher_lock_rejects_unfinalized_external_tuned_or_wrong_schema(tmp_path,change):
    lock={'teacher_finalized':True,'selected_by':'core_train_group_cv','external_used_for_selection':False,
          'feature_set':'e2-brand-v1','decision_rule':'estimator.predict','score_kind':'probability',
          'operating_point_scope':'fixed_core_protocol','threshold':.5}
    lock.update(change)
    with pytest.raises(ValueError):load_locked_teacher(tmp_path,lock)


def test_v0_selection_record_is_rejected_before_deserializing_a_v1_teacher(tmp_path):
    artifact=tmp_path/'not-a-pickle.joblib';artifact.write_bytes(b'not a pickle, must not be loaded')
    selection=tmp_path/'selection.json';selection.write_text(json.dumps({'primary_metric':'mean_outer_average_precision',
        'test_evaluated':False,'protocol':'fixture','feature_schema_version':'e2-brand-v0','teacher_candidates':['E2__mlp']}),encoding='utf-8')
    lock={'teacher_finalized':True,'selected_by':'core_train_group_cv','external_used_for_selection':False,
          'feature_set':'e2-brand-v1','decision_rule':'estimator.predict','score_kind':'probability','model_name':'mlp',
          'operating_point_scope':'fixed_core_protocol','threshold':.5,
          'bundle':{'path':artifact.name,'sha256':sha256(artifact)},'selection_record':{'path':selection.name,'sha256':sha256(selection)}}
    with pytest.raises(ValueError,match='different E2 version'):load_locked_teacher(tmp_path,lock)


@pytest.mark.parametrize('class_order',[[0,1],[1,2]])
def test_locked_teacher_calls_existing_inference_without_training(tmp_path,monkeypatch,class_order):
    from phishguard_vn.features import CANDIDATE_FEATURES
    import joblib
    class SyntheticEstimator:
        classes_=np.array(class_order)
        def predict(self,X):return np.ones(len(X),dtype=int)
        def predict_proba(self,X):return np.tile([.2,.8],(len(X),1))
    bundle={'feature_set':'lexical_12','feature_names':list(CANDIDATE_FEATURES),'protocol':'synthetic_fixture',
            'models':{'logistic_regression':SyntheticEstimator()},'selected_model':'logistic_regression',
            'score_kinds':{'logistic_regression':'probability'}}
    artifact=tmp_path/'fixture.joblib';artifact.write_bytes(b'fixture intercepted by monkeypatch, never a real Teacher')
    selection=tmp_path/'selection.json';selection.write_text(json.dumps({'primary_metric':'mean_outer_average_precision',
        'test_evaluated':False,'protocol':'synthetic_fixture','teacher_candidates':['E1__logistic_regression']}),encoding='utf-8')
    lock={'teacher_finalized':True,'selected_by':'core_train_group_cv','external_used_for_selection':False,
          'feature_set':'lexical_12','decision_rule':'estimator.predict','score_kind':'probability','model_name':'logistic_regression',
          'operating_point_scope':'fixed_core_protocol','threshold':.5,
          'bundle':{'path':artifact.name,'sha256':sha256(artifact)},'selection_record':{'path':selection.name,'sha256':sha256(selection)}}
    monkeypatch.setattr(joblib,'load',lambda path:bundle)
    if class_order!=[0,1]:
        with pytest.raises(ValueError,match='class order'):load_locked_teacher(tmp_path,lock)
        return
    predict=load_locked_teacher(tmp_path,lock)
    result=predict('https://example.com/a')
    assert result['label']=='phishing' and result['score']==.8 and result['decision_rule']=='estimator.predict'
