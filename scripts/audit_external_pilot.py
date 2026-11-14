"""Rebuild K5.3 offline audit/host-only pilot, preserving all candidates and labels."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import pandas as pd
from phishguard_vn.external_pilot import build_ledger,format_diagnostic,reference_keys,sha256
from phishguard_vn.brand_features import explain_brand_matches,load_reference,build_e2_feature_table,E2_FEATURES,FEATURE_SCHEMA_VERSION
from phishguard_vn.features import build_feature_table


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=ROOT)
    args=ap.parse_args(); root=args.root.resolve()
    output=root/'reports/tables/external_pilot'; output.mkdir(parents=True,exist_ok=True)
    generated=root/'data/external/derived'; generated.mkdir(parents=True,exist_ok=True)
    source_paths=[root/'data/external'/n for n in ['phishing_candidates.csv','benign_candidates.csv']]
    candidates=pd.concat([pd.read_csv(p,dtype=str,keep_default_na=False,encoding='utf-8') for p in source_paths],ignore_index=True)
    inputs={p.relative_to(root).as_posix():sha256(p) for p in source_paths}
    # Exact historical bytes, separate namespace; do not relabel a 74-row file as 75.
    history_revision=subprocess.check_output(['git','rev-parse','2a0765c'],cwd=root,text=True).strip()
    historical=[]; archive=root/'data/external/history/2026-11-07';archive.mkdir(parents=True,exist_ok=True)
    history_files={}
    for filename in ['pilot_phishing_candidates.csv','pilot_benign_candidates.csv']:
        source='data/external/'+filename
        raw=subprocess.check_output(['git','show',f'{history_revision}:{source}'],cwd=root)
        path=archive/filename;path.write_bytes(raw)
        frame=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8');historical.append(frame)
        history_files[filename]={'original_git_path':source,'sha256':sha256(path),'rows':len(frame),
                                'status_counts':frame.review_status.value_counts().to_dict()}
    history=pd.concat(historical,ignore_index=True)
    legacy_keys=reference_keys(history.url)
    core_keys={k:set() for k in legacy_keys}
    overlap_sources=[]
    # These tables describe the same released URLs; do not concatenate for training.
    for filename in ['dataset_url.csv','vn_compphish.csv','abuse_type.csv']:
        path=root/'data'/filename
        frame=pd.read_csv(path,usecols=['url'],dtype=str,keep_default_na=False,encoding='utf-8')
        if filename=='dataset_url.csv':dataset_rows=len(frame)
        keys=reference_keys(frame.url)
        for k in core_keys:core_keys[k].update(keys[k])
        inputs[path.relative_to(root).as_posix()]=sha256(path)
        overlap_sources.append((filename,keys))
    review_path=root/'reports/annotations/k53_reviews.csv'
    reviews=pd.read_csv(review_path,dtype=str,keep_default_na=False,encoding='utf-8')
    inputs[review_path.relative_to(root).as_posix()]=sha256(review_path)
    ledger=build_ledger(candidates,core_keys,legacy_keys,reviews)
    document_path=root/'reports/annotations/k53_document_sources.csv'
    documents=pd.read_csv(document_path,dtype=str,keep_default_na=False,encoding='utf-8')
    inputs[document_path.relative_to(root).as_posix()]=sha256(document_path)
    document_reviews=ledger.loc[ledger.review_status.eq('verified') & ledger.review_method.eq('ai_document_review')]
    bound=document_reviews.merge(documents,on='source_reference',validate='many_to_one',how='left')
    if (not bound.evidence_document_sha256.eq(bound.document_sha256).all()
            or bound.evidence_kind.isna().any() or bound.evidence_kind.eq('not_accepted').any()):
        raise ValueError('AI verified review differs from assessed source document registry')
    source_checks=root/'reports/annotations/k53_source_checks.csv'
    if source_checks.is_file():
        checks=pd.read_csv(source_checks,dtype=str,keep_default_na=False,encoding='utf-8')
        if not checks.id.is_unique or set(checks.id)!=set(ledger.id): raise ValueError('Source-check IDs differ')
        matches=ledger[['id','candidate_signature']].merge(checks,on='id',validate='one_to_one',suffixes=('_actual','_checked'))
        if not matches.candidate_signature_actual.eq(matches.candidate_signature_checked).all(): raise ValueError('Stale source checks')
        ledger=ledger.merge(checks.drop(columns='candidate_signature'),on='id',validate='one_to_one')
        inputs[source_checks.relative_to(root).as_posix()]=sha256(source_checks)
    reference=load_reference()
    brands=[]
    for url in ledger.raw_url:
        _,events=explain_brand_matches(url,reference)
        brands.append(';'.join(sorted({e['brand_id'] for e in events if e['brand_id'] and e['rule'].startswith('brand_in_')})))
    ledger['brand_reference_cues']=brands
    brand_rows=[]
    brand_names={b.brand_id:b.canonical_name for b in reference.brands}
    for r in ledger[['id','label','brand_reference_cues']].itertuples(index=False):
        for brand in filter(None,r.brand_reference_cues.split(';')):
            brand_rows.append({'id':r.id,'label':r.label,'brand_id':brand,'canonical_name':brand_names[brand]})
    brand_counts=pd.DataFrame(brand_rows,columns=['id','label','brand_id','canonical_name']).groupby(
        ['brand_id','canonical_name','label']).size().rename('candidate_hosts').reset_index()
    brand_counts.to_csv(output/'brand_cue_counts.csv',index=False,encoding='utf-8',lineterminator='\n')
    host_features=build_e2_feature_table(ledger[['id','model_input_host']].rename(columns={'model_input_host':'url'}),reference)
    host_matrix=host_features.loc[host_features.is_valid,['id',*E2_FEATURES]]
    host_matrix.to_csv(generated/'k53_host_only_features.csv',index=False,encoding='utf-8',lineterminator='\n')
    host_features.loc[~host_features.is_valid,['id','error_reason']].to_csv(
        generated/'k53_host_only_feature_exclusions.csv',index=False,encoding='utf-8',lineterminator='\n')
    raw_features=build_feature_table(ledger[['id','raw_url']].rename(columns={'raw_url':'url'}))
    def lexical_format_purity(frame):
        joined=ledger[['id','label']].merge(frame[['id','slash_cnt','path_len']],on='id',validate='one_to_one')
        counts=joined.groupby(['slash_cnt','path_len','label']).size().unstack('label',fill_value=0)
        return int(counts.max(axis=1).sum())
    ledger.to_csv(output/'candidate_audit.csv',index=False,encoding='utf-8',lineterminator='\n')
    canonical=['id','snapshot_id','raw_url','label','source','source_family','source_reference','review_status',
               'review_evidence','normalized_url','hostname','registrable_domain','model_input_host','model_input_full',
               'parse_valid','parse_error','candidate_signature','reviewer','reviewed_at','label_scope',
               'full_url_verified','source_independence','eligible_host_only','eligible_full_url',
               'review_method','evidence_document_sha256','evidence_locator','evidence_limitations']
    ledger_path=generated/'k53_candidates.csv';ledger[canonical].to_csv(ledger_path,index=False,encoding='utf-8',lineterminator='\n')
    host=ledger[['id','snapshot_id','model_input_host','label','source','review_status','eligible_host_only']]
    host.to_csv(generated/'k53_host_only_pilot.csv',index=False,encoding='utf-8',lineterminator='\n')
    full=ledger[['id','model_input_full','label','source','review_status','observed_http_scheme','full_url_verified','eligible_full_url']]
    full.to_csv(generated/'k53_full_url_inventory.csv',index=False,encoding='utf-8',lineterminator='\n')
    grouped=ledger.groupby(['source','source_family','label','review_status'],dropna=False).agg(
        n=('id','size'),observed_scheme=('observed_http_scheme','sum'),has_path=('has_path','sum'),
        has_query=('has_query','sum'),has_fragment=('has_fragment','sum'),has_port=('has_port','sum'),has_userinfo=('has_userinfo','sum'),
        unicode=('has_unicode','sum'),punycode=('has_punycode','sum'),brand_cues=('brand_reference_cues',lambda s:s.ne('').sum())).reset_index()
    grouped.to_csv(output/'source_label_format.csv',index=False,encoding='utf-8',lineterminator='\n')
    overlaps=[]
    for source,keys in [*overlap_sources,('legacy_106',legacy_keys)]:
        for key in keys:
            overlaps.append({'reference':source,'key':key,'overlapping_current_rows':int((ledger[key].ne('') & ledger[key].isin(keys[key])).sum())})
    pd.DataFrame(overlaps).to_csv(output/'overlaps.csv',index=False,encoding='utf-8',lineterminator='\n')
    statuses=ledger.review_status.value_counts().to_dict()
    source_purity=ledger.groupby('source').label.nunique()
    family_purity=ledger.groupby('source_family').label.nunique()
    summary={'status':'PILOT_ONLY_NOT_OFFICIAL_GROUND_TRUTH','n_candidates':len(ledger),'labels':ledger.label.value_counts().to_dict(),
        'review_status':{s:int(statuses.get(s,0)) for s in ['verified','pending','rejected']},
        'verified_by_label':ledger.loc[ledger.review_status.eq('verified'),'label'].value_counts().to_dict(),
        'verified_review_methods':ledger.loc[ledger.review_status.eq('verified'),'review_method'].value_counts().to_dict(),
        'human_verified':int((ledger.review_status.eq('verified') & ledger.review_method.eq('human')).sum()),
        'internal_duplicates_after_first':{k:int(ledger[k].duplicated().sum()) for k in ['raw_url','normalized_url','model_input_host','registrable_domain']},
        'core_overlap_rows':{k:int(ledger['core_overlap_'+k].sum()) for k in core_keys},
        'legacy_overlap_rows':{k:int(ledger['legacy_overlap_'+k].sum()) for k in core_keys},
        'parser_invalid_rows':int((~ledger.parse_valid).sum()),'candidates_retained':len(ledger),'automatically_rejected_or_deleted':0,
        'stored_url_norm_mismatch_rows':int(ledger.stored_url_norm_mismatch.sum()),
        'host_only_feature_rows':len(host_matrix),'host_only_feature_exclusions':int((~host_features.is_valid).sum()),
        'source_groups':len(source_purity),'single_label_source_groups':int(source_purity.eq(1).sum()),
        'source_families':len(family_purity),'single_label_source_families':int(family_purity.eq(1).sum()),
        'ncsc_warning_or_republication_rows':int(ledger.source_origin_related_to_core.sum()),
        'brand_cue_rows_by_label':ledger.assign(cue=ledger.brand_reference_cues.ne('')).groupby('label').cue.sum().astype(int).to_dict(),
        'format_before':format_diagnostic(ledger,'raw_url'),'format_host_only':format_diagnostic(ledger,'model_input_host'),
        'frozen_lexical_format_diagnostic':{'raw_slash_path_candidate_label_purity_matches':lexical_format_purity(raw_features),
            'host_only_slash_path_candidate_label_purity_matches':lexical_format_purity(host_features),
            'host_only_slash_and_path_all_zero':bool(host_matrix[['slash_cnt','path_len']].eq(0).all().all()),
            'not_model_performance':True},
        'observed_full_http_urls':int(ledger.observed_http_scheme.sum()),'verified_full_urls':int(ledger.full_url_verified.sum()),
        'eligible_host_only':int(ledger.eligible_host_only.sum()),'eligible_full_url':int(ledger.eligible_full_url.sum()),
        'historical_priority':{'requested_size':75,'recovered_phishing_rows':int(history.label.eq('phishing').sum()),
            'recovered_benign_rows':int(history.label.eq('benign').sum()),'manifest_for_exactly_75_found':False,
            'status':'RESOLVED_IN_REPOSITORY_74_RECORDS_75_LINES; any different out-of-repository cohort unestablished',
            'source_counts':history.groupby(['label','source']).size().rename('n').reset_index().to_dict('records')},
        'limits':['Format-specific scheme/path fields are unified by construction; host spelling/source-label confounding remains.',
                  'NCSC warning republications are not independent feeds; URL/domain disjointness does not prove source/campaign independence.',
                  'Observed source links/host mentions do not auto-verify labels, current site state, or full-URL semantics.',
                  'Existing Core protocol fixes probability boundary .5/margin 0; no new threshold is chosen from Validation or external.']}
    write_json(output/'audit_summary.json',summary)
    source_counts=grouped.groupby(['source','label'],as_index=False).n.sum()
    source_rows='\n'.join(f'| {r.source} | {r.label} | {r.n} |' for r in source_counts.itertuples())
    seen=int(ledger.source_host_seen.astype(str).str.lower().eq('true').sum()) if 'source_host_seen' in ledger else 0
    before_status=candidates.review_status.value_counts().to_dict()
    phishing_history_lines=len((archive/'pilot_phishing_candidates.csv').read_text(encoding='utf-8').splitlines())
    report=f'''# K5.3 — External pilot audit và benchmark readiness

## A. Audit trước và sau

| Kiểm tra | Trước (CSV nguồn) | Sau audit / chuẩn hóa |
|---|---:|---:|
| Candidates | {len(candidates)} | {len(ledger)}, giữ toàn bộ ID/raw_url/label |
| Phishing / benign | {int(candidates.label.eq('phishing').sum())} / {int(candidates.label.eq('benign').sum())} | Không đổi nhãn |
| Verified / pending / rejected | {before_status.get('verified',0)} / {before_status.get('pending',0)} / {before_status.get('rejected',0)} | {summary['review_status']['verified']} / {summary['review_status']['pending']} / {summary['review_status']['rejected']} |
| Duplicate raw URL / host / registrable domain | Kiểm tra lại từ dữ liệu | {summary['internal_duplicates_after_first']['raw_url']} / {summary['internal_duplicates_after_first']['model_input_host']} / {summary['internal_duplicates_after_first']['registrable_domain']} |
| Overlap với toàn PhishVN theo URL / hostname / domain | Kiểm tra {dataset_rows:,} URL và bảng companion | {summary['core_overlap_rows']['normalized_url']} / {summary['core_overlap_rows']['hostname']} / {summary['core_overlap_rows']['registrable_domain']} |
| Overlap với cohort cũ theo host | Chưa tách cohort rõ | {summary['legacy_overlap_rows']['hostname']} rows; xem bảng overlap, không coi là hai holdout độc lập |
| URL parse không hợp lệ | Kiểm tra lại | {summary['parser_invalid_rows']}; không gán vector số giả |
| Metadata url_norm khác phép chuẩn hóa giữ case | Audit legacy hạ chữ thường toàn URL | {summary['stored_url_norm_mismatch_rows']} cảnh báo; giữ raw URL, không loại candidate |
| Format strata / pure strata | {summary['format_before']['format_strata']} / {summary['format_before']['pure_strata']} | {summary['format_host_only']['format_strata']} / {summary['format_host_only']['pure_strata']} |
| Nhãn ứng viên khớp majority của format strata | {summary['format_before']['apparent_majority_label_matches']}/{len(ledger)} | {summary['format_host_only']['apparent_majority_label_matches']}/{len(ledger)}; không phải metric model |
| Nhóm nguồn chỉ một nhãn | {summary['single_label_source_groups']}/{summary['source_groups']} | Vẫn {summary['single_label_source_groups']}/{summary['source_groups']} |

Trong raw, phishing không có HTTP scheme, benign có scheme và path. Cặp **slash_cnt/path_len của extractor E1 đã freeze** cũng phân tách {summary['frozen_lexical_format_diagnostic']['raw_slash_path_candidate_label_purity_matches']}/{len(ledger)} nhãn ứng viên. Như vậy bỏ is_https khỏi X chưa loại được artifact format. Đây là kiểm tra impurity trên chính candidate labels, không phải accuracy hay năng lực phát hiện phishing đã xác minh.

Sau phép biến đổi host-only không phụ thuộc nhãn, slash_cnt/path_len bằng 0 cho mọi input; chỉ còn một format stratum. Con số {summary['format_host_only']['apparent_majority_label_matches']}/{len(ledger)} là majority-class purity, không phải kết quả inference. Điều đã kiểm chứng là các dấu hiệu scheme/path này đã trở thành hằng trong biểu diễn mới; **chưa chứng minh loại hết source/campaign/lexical leakage hoặc đo khả năng tổng quát hóa**.

Audit legacy từng hạ chữ thường cả path/query: `ext_pilot_benign_0031` có raw path `/en-US/gioi-thieu.html/` nhưng url_norm lưu `/en-us/gioi-thieu.html/`. Không mặc định hai HTTP resources này tương đương. Canonical mới giữ case; CSV nguồn/nhãn giữ nguyên, cảnh báo metadata không biến thành loại mẫu. Notebook legacy cũng không còn loại candidate chỉ vì khác metadata normalization này.

## B. Nguồn, bằng chứng, nhãn và ngữ cảnh Việt Nam

| Nguồn trong CSV | Nhãn đề xuất | n |
|---|---|---:|
{source_rows}

Có {summary['source_families']} nhóm provenance sau khi gộp NCSC republications; vẫn chỉ một nhãn trong từng nhóm. {summary['ncsc_warning_or_republication_rows']} phishing là cảnh báo NCSC/republication, cùng cơ quan nguồn liên quan Core. Publisher URL mới không chứng minh feed/campaign độc lập. Không thực hiện leave-source-out hai lớp trên holdout chỉ có một nhãn, không lấy feed phishing + danh bạ benign rồi tuyên bố bias đã hết.

Mỗi candidate có source_reference, review_evidence, signature và kết quả kiểm tra tài liệu theo ID ở `candidate_audit.csv`. Kiểm tra HTTP/HTML tự động chỉ đọc reference chính thức allowlist; không theo hyperlink candidate. {seen}/{len(ledger)} hostname được tìm thấy nguyên chuỗi trong reference HTML sau xử lý dấu chấm vô hiệu hóa; HTML có thể chứa related links, ảnh/PDF/JS có thể không trích được. **Host mention không phải nhãn verified hoặc xác minh tình trạng hiện tại.** Chi tiết HTTP status, SHA256 tài liệu, thời điểm và giới hạn nằm ở `reports/annotations/k53_source_checks.csv`. Self-site reference không được coi là bằng chứng benign độc lập chỉ vì trang tự nhận chính thức.

### Review nội dung tài liệu, tách biệt human review

Sau bước availability/host mention, Codex đã đọc các đoạn cảnh báo và trường Website của hồ sơ hội viên VNBA, PDF corporate AEON (trang 6/10), giới hạn theo vị trí bài viết (không nhận related links/footer làm bằng chứng). `k53_reviews.csv` ghi quyết định cho đủ {len(ledger)} ID; `k53_document_sources.csv` ghi SHA256 của bytes tài liệu thực đọc (HTML/PDF), thời điểm truy xuất, ngày/kỳ bài và locator. Kết quả: **{summary['review_status']['verified']} verified theo tài liệu**, gồm {summary['verified_by_label'].get('phishing',0)} phishing và {summary['verified_by_label'].get('benign',0)} benign; {summary['review_status']['pending']} pending. **Human verified = {summary['human_verified']}**. Method là `ai_document_review`, reviewer là Codex, không ghi tên người dùng hoặc tự nhận đã được con người xác nhận.

Phạm vi verified chỉ là `hostname_historical`: hostname nguyên vẹn được nguồn cảnh báo chỉ rõ là giả mạo/lừa đảo, hoặc được hồ sơ tổ chức uy tín/tài liệu corporate của chủ sở hữu chỉ rõ là website của đơn vị. Nhãn phishing kế thừa là lớp cảnh báo giả mạo/lừa đảo rộng, không chứng minh mọi host đều đánh cắp credential; benign là danh tính tổ chức được ghi nhận, không bảo đảm không bị compromise hoặc mọi path đều an toàn. Không xác nhận trạng thái website hôm nay, không nâng lên full URL verified. Gate bắt buộc AI review có hash/locator/limitations và từ chối scope current/full URL.

Các trường hợp chưa đủ bằng chứng được giữ pending với lý do riêng: lỗi TLS nguồn Nghệ An (đã thử cả Python và curl dùng trust hệ điều hành), hostname có `www.` trong bài nhưng candidate đã bỏ tiền tố, reference danh bạ Chính phủ hiện trả homepage, và reference tự giới thiệu chưa có đối chiếu độc lập. Đặc biệt không mặc định `www.example` và `example` là cùng hostname/resource, không sửa raw URL hoặc nhãn để làm đủ số lượng. Các bằng chứng lịch sử không giải quyết source–label confounding; chỉ cho phép chuẩn bị recall pilot có phạm vi công bố rõ.

`brand_reference_cues` là tên key khớp trong reference hiện có, không xác minh chủ sở hữu, ý đồ hay việc tất cả brand là doanh nghiệp Việt Nam. Nguồn và warning nội dung Việt Nam hỗ trợ ngữ cảnh nhắm tới Việt Nam, nhưng không tạo mẫu ngẫu nhiên đại diện web Việt Nam. Hai lớp còn khác cơ chế tuyển chọn. collected_at vẫn thiếu, scraped_at chỉ ghi snapshot; không tự bịa ngày phát hiện hoặc trạng thái website hôm nay.

## C. Cohort ưu tiên được nhắc là “75 phishing”

Đã tìm lịch sử tất cả nhánh/commit liên quan external/pilot và phục hồi đúng bytes của `pilot_phishing_candidates.csv` tại commit `{history_revision}`: **{int(history.label.eq('phishing').sum())} rows**, {phishing_history_lines} dòng nếu tính cả header của file phishing. Không tìm thấy manifest chứng minh đúng 75 URL. Không thêm một URL giả hoặc tự gọi chúng verified. Bản phục hồi riêng có manifest mới ghi rõ nguồn Git, hash, số rows và danh sách ID ưu tiên; đây không phải manifest lịch sử được tìm thấy.

Cohort cũ gồm {int(history.label.eq('phishing').sum())} phishing từ tinnhiemmang + {int(history.label.eq('benign').sum())} benign, tất cả pending. {summary['legacy_overlap_rows']['hostname']} hostname hiện tại trùng cohort cũ (đều benign trong snapshot này). Không gộp {len(history)}+{len(ledger)} thành số mẫu đánh giá độc lập, không trộn cohort cũ vào Core, Train hay cohort mới. Đối chiếu trong repository đã kết thúc ở **74 records / 75 lines kể header**; không coi một URL thứ 75 chưa có chứng cứ là blocker kỹ thuật hoặc tự tạo thêm. Nếu có cohort khác ngoài Git, phải nhận manifest thật trước khi đánh giá cohort đó.

## D. Biểu diễn và benchmark

Raw 15-cột không bị sửa. Ledger canonical nằm tại `data/external/derived/k53_candidates.csv`; `raw_url` giữ đúng URL được cung cấp, `normalized_url` không thêm scheme/path thiếu. `model_input_host` dùng hostname chuẩn của parser, còn subdomain, bỏ scheme/userinfo/port/path/query/fragment cho **cả hai lớp**. Đây là phép biến đổi mất thông tin, không tự bảo đảm label-preserving; cần review label ở scope hostname_historical/current. Host-only feature matrix đúng E2 v1, id + 20 features, không có metadata/labels trong X và không fit model.

Full-URL inventory có {summary['observed_full_http_urls']} URL HTTP(S) quan sát được nhưng {summary['verified_full_urls']} full URL verified; thiếu scheme không được điền http/https để giả thành dữ liệu thật. Benchmark full URL chỉ dùng khi URL và nhãn full-URL được review đúng scope. Shared external domain chỉ là audit flag; không tự xóa hoặc đổi nhãn. Input hostname trùng cần curation rõ trước chấm host-only, để không đếm lặp cùng representation.

Benchmark hiện **PREPARED / BLOCKED**: {summary['eligible_host_only']} host-only / {summary['eligible_full_url']} full-URL eligible và không có Teacher artifact finalized được cung cấp. `benchmark_status.json` ghi metrics=null, n_evaluated=0; exit 2 là blocked, không phải recall=0. Không có external metric thật, không có kết quả official.

Code khi đủ điều kiện chỉ gọi inference đã có, không train. Teacher lock cần hash bundle/selection record, lựa chọn bằng Core Train Group CV trước external, cùng feature order/schema/reference. Model metadata hiện có còn E2 v0; không gán weights v0 thành v1. Protocol Core hiện chốt estimator.predict, probability boundary .5 / margin 0; không có threshold mới chọn từ Core Validation. Yêu cầu “threshold cố định từ Validation” không được thực hiện bằng cách tune lại hoặc ghi provenance giả: giữ protocol hiện hành và đòi Teacher lock thực tế.

Mặc định chỉ báo recall trên phishing verified và theo từng nguồn; precision/F1/accuracy/FPR để null. `--two-class` cần hai lớp verified/eligible, chỉ tạo exploratory results, không tự nhận official/generalization. Nguồn holdout một lớp không được chạy leave-source-out hai lớp. Inference lỗi không được âm thầm bỏ row hoặc dùng model prediction làm nhãn đúng.

## E. Tái lập, kiểm thử và phần còn lại

Xem `data/external/README.md` cho data dictionary/lệnh, `verification.json` cho tests/Run All/hashes thực tế; không tính trạng thái chuẩn bị là benchmark đã chạy thành công. Audit có thể tái tạo offline, source checks là bước mạng tùy chọn. Review thật lưu riêng tại `reports/annotations/k53_reviews.csv`, có ID/signature/reviewer/time/evidence; không tự ghi tên người dùng hoặc human verification.

Chưa đủ tin cậy để báo cáo kết quả external chính thức. Phần AI có thể hoàn thành đã tạo review có bằng chứng cho subset lịch sử, giữ pending các ID thiếu chứng cứ, và chốt đúng số bản ghi cohort cũ trong Git. Còn cần xác minh các nguồn/hostname pending và tuyển mẫu theo cùng cơ chế ở cả hai lớp để xử lý source–label confounding; không chỉ đổi tên nhóm nguồn hoặc tăng số URL. Phúc cần bàn giao Teacher đã khóa bằng Core-CV và bundle tương thích đúng version; sau đó mới chạy recall pilot trên subset đủ điều kiện và công bố giới hạn. Không hứa điểm tối đa hoặc đã loại leakage hoàn toàn.
'''
    report_path=root/'reports/k53_external_pilot_audit.md';report_path.write_text(report,encoding='utf-8',newline='\n')
    write_json(archive/'manifest.json',{'recovered_from_git_commit':history_revision,'deletion_commit':'d7f1cea0f305e7ee957c5dd869b4b778ea0cc9ad',
        'snapshot_id':'k53_legacy_106','files':history_files,'requested_75_manifest_found':False,
        'phishing_priority_ids':history.loc[history.label.eq('phishing'),'id'].tolist(),
        'note':'New recovery manifest, not a claim that a historical 75-URL manifest existed. All original statuses preserved.'})
    inputs['src/phishguard_vn/external_pilot.py']=sha256(root/'src/phishguard_vn/external_pilot.py')
    for name in ['audit_external_pilot.py','evaluate_external_pilot.py','check_external_source_evidence.py']:
        inputs['scripts/'+name]=sha256(root/'scripts'/name)
    for p in [root/'src/phishguard_vn/url_parser.py',root/'src/phishguard_vn/features.py',root/'src/phishguard_vn/brand_features.py',
              root/'src/phishguard_vn/resources/brand_reference_v1.csv']:
        inputs[p.relative_to(root).as_posix()]=sha256(p)
    # Any previous evaluation belongs to its old audit, not this fresh candidate view.
    for name in ['verified_predictions.csv','benchmark_status.json']:(output/name).unlink(missing_ok=True)
    outputs=[ledger_path,generated/'k53_full_url_inventory.csv',generated/'k53_host_only_pilot.csv',generated/'k53_host_only_features.csv',
             generated/'k53_host_only_feature_exclusions.csv',
             output/'candidate_audit.csv',output/'source_label_format.csv',output/'brand_cue_counts.csv',output/'overlaps.csv',output/'audit_summary.json',archive/'manifest.json']
    outputs.append(report_path)
    write_json(output/'manifest.json',{'audit_runtime_base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'publication_note':'Source/input hashes identify runtime content; published commit remains separate.',
        'inputs_sha256':inputs,'outputs_sha256':{p.relative_to(root).as_posix():sha256(p) for p in outputs},
        'current_ids_sha256':hashlib.sha256('\n'.join(sorted(ledger.id)).encode()).hexdigest(),
        'external_schema_version':'k53-pilot-v2-review-method','feature_schema_version':FEATURE_SCHEMA_VERSION,
        'feature_order':list(E2_FEATURES),'brand_reference_sha256':reference.sha256,
        'network_requests':False,'research_model_training':False,'original_labels_modified':False})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
