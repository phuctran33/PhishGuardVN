"""Summarize persisted research predictions, compare paired folds, and propose candidates."""
from pathlib import Path
import sys,json,hashlib,importlib.util
from datetime import datetime, timezone
from importlib.metadata import version
import numpy as np
import pandas as pd
import joblib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import run_url_research as run

def read(path):
    return pd.read_csv(path,float_precision="round_trip")

def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join(["---"]*len(headers))+" |"]+
                    ["| "+" | ".join(str(x) for x in r)+" |" for r in rows])


def interpretation(summary, changes, cases, out):
    """Describe paired errors without attributing causality to an individual token."""
    ap=summary.set_index("experiment").ap_mean
    rows=[]
    for r in changes.itertuples():
        rows.append([r.experiment,r.baseline,r.corrected_fp,r.new_fp,r.corrected_fn,r.new_fn])
    error_table=table(["Pipeline","Baseline","FP sửa được","FP mới","FN sửa được","FN mới"],rows)
    selected=[]
    for name in ["hybrid_e2_w0p25","regex","bpe","canonical","l1_select","pretrained_url_transformer"]:
        for change in ["corrected","new_error"]:
            group=cases.loc[cases.experiment.eq(name)&cases.change.eq(change)].sort_values("id")
            if len(group):
                r=group.iloc[0]
                selected.append([name,r.id,int(r.fold),int(r.y_true),r.url,
                                 f"{r.baseline_score:.4f} -> {r.score:.4f}",change])
    case_table=table(["Pipeline","ID","Fold","y","URL defang","Score baseline -> mới","Thay đổi"],selected)
    fig_dir=ROOT/"reports/figures/url_research";fig_dir.mkdir(parents=True,exist_ok=True)
    import matplotlib.pyplot as plt
    ordered=summary.iloc[::-1]
    fig,ax=plt.subplots(figsize=(11,10))
    ax.barh(ordered.experiment,ordered.ap_mean,color=["#d59527" if x.startswith("tfidf") else "#16867f" for x in ordered.experiment])
    ax.set_xlabel("Mean outer Group CV average precision; descriptive, reused folds")
    ax.set_xlim(0,1);fig.tight_layout();fig.savefig(fig_dir/"comparison.png",dpi=150);plt.close(fig)
    return f"""
## Diễn giải đối chứng và FP/FN

Giữ cùng LR family: hybrid E2 weight0,25 đổi AP so với raw TF-IDF LR khoảng {ap["hybrid_e2_w0p25"]-ap["tfidf_logistic_regression"]:+.4f}; hybrid weight1/4 không mang lại cùng kết quả. Vì mỗi pipeline chọn C trong inner CV, đây là đóng góp nhánh/trọng số của quy trình, không là hiệu ứng nhân quả của một feature.

Regex-only đổi AP {ap["regex"]-ap["tfidf_logistic_regression"]:+.4f}; char+regex cũng không thắng raw char LR trong lượt này. Token nguyên đoạn mất những tương đồng nhỏ bên trong domain mà char n-gram giữ; đó là giả thuyết phù hợp kết quả, cần kiểm tra vocabulary/case chứ không coi là chứng minh.

BPE/WordPiece/Unigram có vocab khoảng 2K và file outer nhỏ hơn nhiều nhưng AP thấp hơn raw char LR. Đây là trade-off nén/biểu diễn ở cấu hình đã thử, không chứng minh mọi subword đều kém. So min_df, unknowns và domain segment trong fitting trước khi mở rộng grid.

Canonical/host-only làm giảm AP. Bỏ scheme/path/query có thể giảm format/source cues nhưng cũng bỏ thông tin thật. Canonical_lower so với canonical gần như không đổi trong dữ liệu này; không suy ra path/query case luôn vô ích. Đọc slices.csv cùng class counts, nhất là has_scheme chỉ có benign trong Train; đó là audit phân bố, không dùng format làm nhãn.

L1 giảm mạnh số feature nhưng AP giảm; artifact vẫn chứa vocabulary và selector nên ít cột không bảo đảm giảm bytes. Count/Binary/Log-TF khá gần TF-IDF về AP nhưng điểm Recall/FPR ở ranh giới mặc định khác nhau; không gọi các operating points là cùng FPR.

Neural dùng ngân sách epochs/LR nhỏ khác với LR tối ưu tới điều kiện solver. Kết quả thấp chỉ cho thấy các kiến trúc/cấu hình/ngân sách đã chạy chưa thay được baseline; không kết luận đã tối ưu hết họ mô hình. FastText-style có Recall 0 ở ngưỡng 0,5 trong đợt này, vì vậy không dùng nó làm candidate dù file có thể nhỏ.

{error_table}

Các số ở bảng là tổng OOF paired trên cùng IDs; corrected/new FP/FN phải xem cùng AP và operating point, không đếm riêng số lỗi sửa rồi bỏ qua lỗi mới.

## Case minh họa chọn cố định

{case_table}

Quan sát chỉ là thay đổi score/prediction trên cùng ID/fold. Với LR, giả thuyết liên quan biểu diễn/trọng số; với neural, cả classifier cũng đổi. next_check: đối chiếu token/feature trong fitting tương ứng, không truy cập website hoặc sửa nhãn. Bảng đầy đủ gồm observation/hypothesis/next_check trong cases.csv.

![So sánh nghiên cứu và baseline](figures/url_research/comparison.png)
"""

def main():
    out,local=run.OUT,run.LOCAL
    recorded=json.loads((out/"execution_manifest.json").read_text())
    for name,digest in recorded["input_sha256"].items():
        assert run.sha(ROOT/name)==digest, "Executed research source/data changed; do not relabel old outputs"
    previous_verification=json.loads((out/"verification.json").read_text()) if (out/"verification.json").exists() else {}
    plan=json.loads((ROOT/"configs/url_research_plan.json").read_text())
    train=run.load_train()
    specs={s["id"]:s for s in plan["experiments"]}
    names={**{s["id"]:s["baseline"] for s in plan["experiments"]},
           "tfidf_linear_svm":"tfidf_linear_svm","tfidf_logistic_regression":"tfidf_logistic_regression",
           "catboost":"catboost"}
    predictions={};fold_tables=[]
    statuses=read(out/"experiment_status.csv")
    for spec in plan["experiments"]:
        name=spec["id"];path=out/(name+"_oof.csv.gz")
        if not path.exists():continue
        frame=read(path)
        assert len(frame)==13078 and frame.id.is_unique and set(frame.id)==set(train.id)
        predictions[name]=frame
        fold_tables.append(read(out/(name+"_folds.csv")))
    old=read(ROOT/"reports/tables/week6/oof_predictions.csv.gz")
    old_resources=read(ROOT/"reports/tables/week6/resources.csv").set_index("model")
    for name in ["catboost","tfidf_linear_svm","tfidf_logistic_regression"]:
        frame=old.loc[old.model.eq(name)].rename(columns={"fold_id":"fold","true_label":"y_true",
                                                       "predicted_label":"prediction"}).copy()
        frame["experiment"]=name;predictions[name]=frame
        rows=[]
        for fold,g in frame.groupby("fold"):
            rows.append({"experiment":name,"group":"cached_baseline","fold":fold,
                         **run.metrics(g.y_true,g.prediction,g.score),
                         "model_bytes":old_resources.loc[name,"pipeline_bytes"],
                         "latency_p50_ms":np.nan,"latency_scope":"cached baseline timing has different scope; not compared"})
        fold_tables.append(pd.DataFrame(rows))
    folds=pd.concat(fold_tables,ignore_index=True)
    expected=train.set_index("id")
    max_error=0.
    for name,frame in predictions.items():
        assert not frame.duplicated("id").any()
        assert np.array_equal(frame.fold.to_numpy(),expected.loc[frame.id,"fold_id"].to_numpy())
        assert np.array_equal(frame.y_true.to_numpy(),expected.loc[frame.id,"target"].to_numpy())
        for fold,g in frame.groupby("fold"):
            row=folds.loc[folds.experiment.eq(name)&folds.fold.eq(fold)].iloc[0]
            for k,v in run.metrics(g.y_true,g.prediction,g.score).items():
                max_error=max(max_error,abs(float(v)-float(row[k])))
    assert max_error<1e-12
    metrics=["ap","precision","recall","f1","fpr","model_bytes","latency_p50_ms","features_before","features_after"]
    summary=folds.groupby("experiment")[[m for m in metrics if m in folds]].agg(["mean","std"])
    summary.columns=[f"{m}_{s}" for m,s in summary.columns]
    summary=summary.reset_index().sort_values(["ap_mean","f1_mean","fpr_mean","experiment"],
                                               ascending=[False,False,True,True]).reset_index(drop=True)
    deltas=[];cases=[];group_rows=[];error_changes=[]
    for name,frame in predictions.items():
        if name not in specs:continue
        baseline=specs[name]["baseline"]
        if baseline not in predictions:continue
        paired=frame.merge(predictions[baseline][["id","y_true","fold","prediction","score"]],
            on=["id","y_true","fold"],suffixes=("","_baseline"),validate="one_to_one").merge(
            train[["id","url","source",*run.E2_FEATURES]],on="id",validate="one_to_one")
        for fold in [0,1,2]:
            a=folds.loc[folds.experiment.eq(name)&folds.fold.eq(fold)].iloc[0]
            b=folds.loc[folds.experiment.eq(baseline)&folds.fold.eq(fold)].iloc[0]
            deltas.append({"experiment":name,"baseline":baseline,"fold":fold,
                **{f"delta_{m}":float(a[m]-b[m]) for m in ["ap","precision","recall","f1","fpr","fp","fn","tp","tn"]}})
        base_bad=paired.prediction_baseline.ne(paired.y_true)
        new_bad=paired.prediction.ne(paired.y_true)
        improved=base_bad&~new_bad;regressed=~base_bad&new_bad
        paired["change"]=np.where(improved,"corrected",np.where(regressed,"new_error","unchanged"))
        masks={"all":np.ones(len(paired),dtype=bool),"has_scheme":paired.url.str.contains("://",regex=False),
               "has_query":paired.url.str.contains("?",regex=False),
               "idn_or_unicode":paired.url.str.contains("xn--",regex=False)|paired.url.str.contains(r"[^\x00-\x7f]",regex=True),
               "brand_signal":paired[list(run.E2_FEATURES)[12:]].ne(0).any(axis=1),
               "short_url_le20":paired.url.str.len().le(20)}
        for group,mask in masks.items():
            g=paired.loc[mask]
            group_rows.append({"experiment":name,"baseline":baseline,"slice":group,"n":len(g),
                "positive":int(g.y_true.eq(1).sum()),"negative":int(g.y_true.eq(0).sum()),
                "corrected_fn":int((improved&mask&paired.y_true.eq(1)).sum()),
                "corrected_fp":int((improved&mask&paired.y_true.eq(0)).sum()),
                "new_fn":int((regressed&mask&paired.y_true.eq(1)).sum()),
                "new_fp":int((regressed&mask&paired.y_true.eq(0)).sum())})
        error_changes.append(group_rows[-len(masks)])
        chosen=paired.loc[improved|regressed].sort_values("id").groupby(["fold","change"]).head(2)
        for row in chosen.itertuples():
            same_classifier=specs[name]["group"]!="neural"
            cases.append({"experiment":name,"baseline":baseline,"id":row.id,"fold":row.fold,
                "parameters":row.parameters,"y_true":row.y_true,"score":row.score,
                "prediction":row.prediction,"baseline_score":row.score_baseline,
                "baseline_prediction":row.prediction_baseline,"change":row.change,
                "url":row.url.replace(".","[.]"),
                "observation":f"{row.change}; same ID/fold, baseline prediction {row.prediction_baseline} -> {row.prediction}.",
                "hypothesis":("Representation/weighting may change this boundary; LR is held as the classifier family, but C is selected separately."
                              if same_classifier else "The whole representation and neural classifier differ; this is not isolated preprocessing evidence."),
                "next_check":"Inspect fitted vocabulary/selector or encoding and the corresponding fitting partition; do not visit the URL or change labels."})
    for name,frame in {"comparison":summary,"fold_metrics":folds,"paired_deltas":pd.DataFrame(deltas),
                       "error_changes":pd.DataFrame(error_changes),"slices":pd.DataFrame(group_rows),
                       "cases":pd.DataFrame(cases)}.items():
        frame.to_csv(out/(name+".csv"),index=False,encoding="utf-8",lineterminator="\n")
    # Candidate proposals are descriptive on the reused folds, not a final Teacher decision.
    primary=str(summary.iloc[0].experiment)
    alternatives=summary.loc[(summary.ap_mean>=float(summary.iloc[0].ap_mean)-.01)&summary.experiment.ne(primary)&summary.experiment.isin(specs)]
    compact=str(alternatives.sort_values(["model_bytes_mean","experiment"]).iloc[0].experiment) if len(alternatives) else None
    if compact is not None and primary in specs and float(summary.loc[summary.experiment.eq(compact),"model_bytes_mean"].iloc[0])>=float(summary.iloc[0].model_bytes_mean):
        compact=None
    ledger=read(out/"fit_ledger.csv").to_dict("records")
    # Keep completed full-Train proposals on repeated summarization, without spending fits again.
    selection_path=out/"candidate_proposal.json"
    previous=json.loads(selection_path.read_text()) if selection_path.exists() else {}
    candidate_records=[]
    for role,name in [("main",primary),("compact",compact)]:
        if name is None:continue
        model_path=local/(role+"_candidate.joblib")
        record=next((r for r in previous.get("candidates",[]) if r["role"]==role and r["experiment"]==name),None)
        if record and model_path.exists() and run.sha(model_path)==record["sha256"]:
            candidate_records.append(record);continue
        spec=specs.get(name)
        if spec is None:
            spec={"id":"baseline_tfidf_svm" if name=="tfidf_linear_svm" else "baseline_tfidf_lr",
                  "group":"baseline","representation":"char","grid":{"C":[.5,2]}}
        if name=="catboost":
            raise RuntimeError("Tabular cached baseline needs an explicit full-Train builder before proposing it.")
        model,best=run.select_fit(spec,train,"full_train",local/"pretrained",ledger)
        joblib.dump(model,model_path)
        reloaded=joblib.load(model_path)
        X=run.input_frame(train.iloc[:8])
        np.testing.assert_allclose(run.scores_for(model,X),run.scores_for(reloaded,X),rtol=0,atol=1e-7)
        candidate_records.append({"role":role,"experiment":name,"spec":spec,"full_train_parameters":best[2],
            "full_train_inner_ap":best[0],"model_path":model_path.relative_to(ROOT).as_posix(),
            "sha256":run.sha(model_path),"resources":run.measure(reloaded,spec,train.url.iloc[:16].tolist()),
            "outer_ap_mean_of_family_not_specific_full_train_config":float(summary.loc[summary.experiment.eq(name),"ap_mean"].iloc[0]),
            "reload_checked":True})
    if len(candidate_records)==2 and candidate_records[1]["resources"]["model_bytes"]>=candidate_records[0]["resources"]["model_bytes"]:
        compact=None;candidate_records=candidate_records[:1]
    proposal={"status":"candidate_proposed","teacher_finalized":False,"candidates":candidate_records,
        "selection_scope":"descriptive on repeatedly observed outer folds; full-Train configs selected only by inner Group CV",
        "reference_sha256":run.load_reference().sha256,
        "source_sha256":{n:run.sha(ROOT/n) for n in ["src/phishguard_vn/research_preprocessing.py",
                                                   "src/phishguard_vn/research_neural.py"]}}
    selection_path.write_text(json.dumps(proposal,indent=2)+"\n",encoding="utf-8")
    ledger=read(out/"fit_ledger.csv")
    success=int(ledger.status.eq("success").sum());failed=int(ledger.status.eq("failed").sum())
    config_status=[]
    for spec in plan["experiments"]:
        for config in [0,1]:
            rows=ledger.loc[ledger.experiment.eq(spec["id"])&ledger.config_id.eq(config)&ledger.stage.eq("inner")&ledger.context.astype(str).ne("full_train")]
            state="success" if len(rows)==6 and rows.status.eq("success").all() else ("failed_or_partial" if len(rows) else "not_run")
            config_status.append({"experiment":spec["id"],"config_id":config,"status":state,"inner_fits":len(rows)})
    pd.DataFrame(config_status).to_csv(out/"config_status.csv",index=False)
    pretrained=json.loads((local/"pretrained/provenance.json").read_text()) if (local/"pretrained/provenance.json").exists() else {}
    verification={"checked_utc":datetime.now(timezone.utc).isoformat(),"research_families_completed":len(predictions)-3,
       "research_families_planned":21,"configuration_status":pd.DataFrame(config_status).status.value_counts().to_dict(),
       "fit_success":success,"fit_failed":failed,"fit_total":len(ledger),"plan_fit_ceiling":325,
       "max_metric_recompute_error":max_error,"all_oof_ids_folds_labels_checked":True,
       "versions":{n:version(n) for n in ["numpy","pandas","scikit-learn","tokenizers","torch","transformers"]},
       "pretrained":pretrained,"teacher_finalized":False,"not_evaluated":["Validation","Official Test","external"]}
    assert len(ledger)<=325,"Budget exceeded; investigate and document rather than hide retries"
    for key in ["tests","independent_audit","setup_notes"]:
        if key in previous_verification:
            verification[key]=previous_verification[key]
    (out/"verification.json").write_text(json.dumps(verification,indent=2)+"\n",encoding="utf-8")
    budget_rows=[]
    for spec in plan["experiments"]:
        state=statuses.loc[statuses.experiment.eq(spec["id"])]
        budget_rows.append([spec["id"],spec["group"],state.iloc[0]["status"] if len(state) else "not_run",
                            spec["baseline"],json.dumps(spec["grid"]),12,3])
    top=table(["Pipeline","AP mean","SD","Recall","FPR","F1","Model KiB (outer / cached full)"],[
      [r.experiment,f"{r.ap_mean:.4f}",f"{r.ap_std:.4f}",f"{r.recall_mean:.2%}",f"{r.fpr_mean:.2%}",f"{r.f1_mean:.4f}",f"{r.model_bytes_mean/1024:.1f}"] for r in summary.itertuples()])
    budget_table=table(["Experiment","Group","Status","Baseline","Grid","Inner fits","Outer refits"],budget_rows)
    delta_table=table(["Experiment","Baseline","Mean delta AP","Mean delta FP","Mean delta FN"],[
       [name,specs[name]["baseline"],f"{group.delta_ap.mean():+.4f}",
        f"{group.delta_fp.mean():+.2f}",f"{group.delta_fn.mean():+.2f}"] for name,group in pd.DataFrame(deltas).groupby("experiment")])
    candidate_table=table(["Role","Pipeline","Full-Train params","Bytes","p50 ms / 16 URLs"],[[r["role"],r["experiment"],json.dumps(r["full_train_parameters"]),r["resources"]["model_bytes"],f'{r["resources"]["latency_p50_ms"]:.3f}'] for r in candidate_records])
    report=f"""# Nghiên cứu URL preprocessing để đề xuất candidate

Trạng thái: **candidate_proposed, teacher_finalized=false**. Làm tiếp trên phuc-week6-teacher-v1 theo yêu cầu mới. Benchmark 13 model tại PR #24 được giữ nguyên; số liệu mới nằm riêng trong reports/tables/url_research.

## Kế hoạch và protocol

Không tìm thấy grid 496/224 đủ chi tiết trong workspace/repo/issue đã đọc. Đây là kế hoạch mới đăng ký trước kết quả trong configs/url_research_plan.json (commit 1d10cdc), không nhận là tái lập 496. Có 21 nhóm, 42 cấu hình: 252 inner fits + 63 outer refits, cộng tối đa 10 full-Train fits. Kế hoạch không nhân mọi preprocessing với mọi classifier.

Cùng 13.078 Train IDs, 3 domain outer folds; 2 inner StratifiedGroupKFold trong fitting. Vocabulary, DF/IDF, scaler, selector và tokenizer học trong từng fit. Không dùng Validation/Official Test/external, ID/nhãn/source làm đầu vào. Neural dùng fixed epoch budget, không early-stop bằng holdout và không nhận đã hội tụ chỉ vì hoàn tất epochs. Seed 42, CPU 2 threads. Mean/SD ba folds không phải CI; các folds đã được quan sát nhiều lần, so sánh không là kiểm chứng độc lập sau lựa chọn.

{budget_table}

Thực tế: {success} fit thành công, {failed} fit thất bại, tổng {len(ledger)}. Config status: {verification["configuration_status"]}. Baseline CatBoost/E2, TF-IDF LR và TF-IDF SVM tái sử dụng OOF đã xác nhận, không fit lại để đổi baseline char 3–5.

## Triển khai và biểu diễn

A: char TF-IDF LR ghép E1, brand, E2; đối chứng trọng số numeric 0,25/1/4. Numeric vẫn trích từ URL gốc, giữ công thức và thứ tự freeze; StandardScaler học trong fitting, không chuẩn hóa lại feature definitions.
B: regex giữ tiền tố component scheme/host/path/query/fragment và delimiter tokens. Char+regex là hai nhánh độc lập. Scheme absent là tín hiệu định dạng có thể liên quan nguồn, không phải chứng cứ phishing.
C: L1 LogisticRegression selector C=1 trong pipeline, classifier LR chọn C 0,5/2; số cột trước/sau trong fold_metrics.csv. Selector không tự rút gọn vocabulary gốc khi serialize nên ít cột không bảo đảm file nhỏ hơn.
D: BPE/WordPiece/Unigram vocab tối đa 2.048, pretokenize delimiter rồi ByteLevel. Tokenizer vocabulary tạo token IDs/tokens, vectorizer vocabulary tạo cột sparse và IDF: hai mapping khác nhau, đều fit riêng trong fitting. [UNK] rõ ràng; tokenizer nghiên cứu không thay vào pretrained embeddings.
E: raw; canonical bỏ scheme/userinfo/fragment, lower+IDNA host, bỏ port mặc định, giữ path/query case và percent escapes; canonical_lower còn lower path/query (mất thông tin); host_only bỏ cả port/path/query. URL parser lỗi giữ raw để không loại ID. Không sửa raw CSV.
F: Count/Binary/Log-TF so với TF-IDF trên cùng char 3–5, min_df=2, max_features=50.000, L2 norm; chỉ thay weighting/IDF tương ứng.
Char-CNN: vocab ký tự fitting-only, PAD=0/UNK=1, dài 256, embed32, Conv kernels3/5/7×32, global max pooling.
FastText-style: vocab từ fitting-only + hashed char subwords 3–5 trong từng token, word/subword embeddings học supervised rồi mean pooling. Không phải TF-IDF và không tuyên bố là package FastText chính thức.
FT-Transformer: 20 số E2, scaler fitting-only, feature-specific affine tokens 32 chiều, CLS, 1 attention block/2 heads. Không dùng BPE cho cột số.
URL Transformer: google/bert_uncased_L-2_H-128_A-2, revision {plan["pretrained"]["revision"]}, Apache 2.0; đúng WordPiece vocab của encoder, uncased, max64 tokens, end-to-end fine-tune 2 epochs, LR2e-4/5e-4. Truncation/case có thể mất thông tin. Nguồn [model card](https://huggingface.co/google/bert_uncased_L-2_H-128_A-2); hashes checkpoint trong verification.json.

## Kết quả từ OOF đã lưu

{top}

AP là average_precision_score. Dự đoán dùng 0,5 probability; baseline SVM dùng margin 0. Tính lại từ CSV float_precision=round_trip, max error {max_error}. Mỗi pipeline đủ đúng IDs/folds, không trùng ID. Hướng chưa hoàn thành phải đọc experiment_status.csv/config_status.csv, không xem là đã chạy.

## Delta theo baseline của từng giả thuyết

{delta_table}

paired_deltas.csv có từng fold cho AP/Precision/Recall/F1/FPR. error_changes.csv và slices.csv tách corrected/new FP/FN, có sample/class counts cho scheme, query, IDN/Unicode, brand, URL ngắn. Nhóm nhỏ chỉ mô tả. So sánh các nhóm A–F giữ classifier family LR nhưng C được chọn riêng; neural khác cả biểu diễn và classifier, không quy hết delta cho preprocessing. Char TF-IDF LR/SVM cached là đối chứng classifier giữ biểu diễn.

cases.csv chọn tối đa hai ID theo thứ tự cố định mỗi fold×corrected/new_error, chứa score/config/nhãn và URL defang, observation/hypothesis/next_check. Không truy cập URL, tự sửa nhãn hoặc tune rule theo case. Feature-based error notes không dùng để giải thích nhân quả một model text.

## Candidate và tài nguyên

Đề xuất chính: **{primary}**. Phương án gọn trong khoảng 0,01 AP và file nhỏ hơn: **{compact or "không có theo tiêu chí đã đăng ký"}**.
Cấu hình full Train được chọn bằng inner Group CV trong grid đăng ký; mean outer AP là điểm mô tả family procedure, không phải đánh giá độc lập của riêng cấu hình full-Train. Candidate artifacts local dưới data/interim/url_research, metadata/hash ở candidate_proposal.json. Không sửa Teacher lock, artifact MLP cũ hoặc API/Web/Android/KD.

Tất cả latency mới đo CPU offline URL→score, có extraction numeric khi nhánh cần; batch16, warmup2, repeat5. Baseline lịch sử đo scope khác nên không ghép vào cùng bảng latency. Kích thước, số cột và thời gian từng fold ở fold_metrics.csv; số full Train ở candidate_proposal.json. Chưa benchmark điện thoại.

## Tái lập và kiểm chứng

Cài CPU PyTorch theo pyproject và pip install -e \".[teacher,test,research]\". Chạy scripts/prepare_url_research.py tải checkpoint pinned, scripts/run_url_research.py (hoặc --classical-only rồi --resume), sau đó scripts/summarize_url_research.py. Cần handoff core/E2/domains/folds như benchmark. Không chạy notebook 06 để tái lập nghiên cứu này.

Code: src/phishguard_vn/research_preprocessing.py; research_neural.py; scripts/run_url_research.py. Fit ledger ghi config/partition IDs hash, time, lỗi, warnings và loss lịch sử neural. partitions.csv.gz cho phép audit group leakage. Không suy ra OOF tự chứng minh lịch sử fit; cần đối chiếu ledger và code.

Candidate reload được đối chiếu với model gốc. Kiểm thử fixture mới ở tests/test_url_research.py, kết quả test thực tế được bổ sung vào verification.json. Không gọi hoàn thành nghiên cứu nếu status còn nhóm chưa chạy/blocker. Teacher chỉ được đóng gói sau khi nhóm chốt candidate và contract.
"""
    report+=interpretation(summary,pd.DataFrame(error_changes),pd.DataFrame(cases),out)
    report+='\nKết quả đã commit là một lần chạy hoàn chỉnh. Lệnh --resume chỉ dùng lại family đã hoàn tất khi source/data hash khớp, không phải chạy lại training. Để tái lập từ đầu mà không ghi đè bảng nghiên cứu đã lưu, có thể chạy đoạn Python sau từ root repo:\n\n~~~python\nimport sys, shutil\nfrom pathlib import Path\nsys.path.insert(0, "scripts")\nimport run_url_research as run\nrun.OUT = run.ROOT / "data/interim/url_research_reproduction/tables"\nrun.LOCAL = run.ROOT / "data/interim/url_research_reproduction/models"\nshutil.copytree(run.ROOT / "data/interim/url_research/pretrained",\n                run.LOCAL / "pretrained", dirs_exist_ok=True)\nsys.argv = ["run_url_research.py"]\nrun.main()\nimport summarize_url_research as summary\nsummary.main()\n~~~\n\nĐoạn này dành thư mục riêng cho kết quả và candidate mới; summary dùng cùng module run và các paths vừa đặt. Báo cáo chính sẽ được tái tạo từ lượt chạy mới. Cần prepare checkpoint và tạo handoff trước như hướng dẫn bên trên.\n'

    if "tests" in verification:
        r=verification["tests"]["research"];f=verification["tests"]["full"]
        report+=f"""
## Kiểm thử và bàn giao thực tế

Research fixtures: **{r["passed"]} passed, {r["skipped"]} skipped**; full suite **{f["passed"]} passed, {f["skipped"]} skipped**. Skip cũ là bộ tham số brand regression rỗng. Hai cảnh báo API L1 của sklearn 1.9 đã ghi trong verification, không phải cảnh báo hội tụ. Đã thử candidate load/CLI không dataset trên 5 URL/role.

Torch CPU 2.8 ban đầu lỗi hash; không bỏ qua kiểm tra. Torch CPU 2.6 chính thức đã chạy đủ bốn hướng neural, không còn blocker runtime trong scope đã đăng ký. Core versions được ghi trong fit ledger; không nhận config/seed bảo đảm byte-identical trên mọi platform/library.

Candidate Binary LR giảm bytes full Train khoảng 18,9% nhưng Recall mặc định thấp hơn và latency tương tự. Baseline SVM đã có Validation AP thấp khoảng 0,4011 ở benchmark cũ; không xóa hoặc bỏ qua giới hạn này. Nghiên cứu mới không dùng Validation để chọn/tune và chưa chứng minh hiệu quả ngoài thực tế. Nhóm còn cần quyết định contract/candidate trước khi đóng gói Teacher, kiểm thử tích hợp và external.
"""

    (ROOT/"reports/url_preprocessing_research.md").write_text(report,encoding="utf-8",newline="\n")
    print(summary[["experiment","ap_mean","recall_mean","fpr_mean"]].to_string(index=False))
    print("Candidate proposals",primary,compact)

if __name__=="__main__":
    with run.threadpool_limits(limits=2):
        main()
