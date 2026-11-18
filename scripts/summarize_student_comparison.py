"""Build plots and an honest technical report from saved results; never refit."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve,roc_curve,ConfusionMatrixDisplay
from phishguard_vn.student import sha256,metrics,student_text

TABLES=ROOT/"reports/tables/student_comparison"
FIGURES=ROOT/"reports/figures/student_comparison"


def kd_diagnostics(targets, teacher_data, prediction, selected, runs, folder):
    """Read-only KD audit: no model fitting or new evaluation cohort."""
    folder.mkdir(parents=True,exist_ok=True)
    train=targets.rename(columns={"target":"y_true"})
    threshold=json.loads((ROOT/"configs/teacher_lock.json").read_text(encoding="utf-8"))["threshold"]
    score_stats=[]
    for name,frame in (("Train (in-sample Teacher)",train),("Validation (development)",teacher_data)):
        for label in (0,1):
            group=frame.loc[frame.y_true.eq(label)]
            score_stats.append(dict(split=name,label=label,n=len(group),
                positive_prevalence=float(frame.y_true.mean()),
                teacher_score_mean=float(group.teacher_score.mean()),
                teacher_score_p10=float(group.teacher_score.quantile(.1)),
                teacher_score_p50=float(group.teacher_score.quantile(.5)),
                teacher_score_p90=float(group.teacher_score.quantile(.9)),
                teacher_label_agreement=float(np.mean((group.teacher_score>=threshold)==label)),
                mean_distance_from_hard_label=float(np.mean(np.abs(group.teacher_score-label)))))
    stats=pd.DataFrame(score_stats)
    stats.to_csv(folder/"teacher_targets_by_label.csv",index=False,encoding="utf-8",lineterminator="\n")
    hard_name=selected.split("__")[0]+"__hard_only"
    def chosen(name,prefix):
        result=prediction.loc[(prediction.candidate==name)&(prediction.seed==42),
                              ["id","y_true","score","prediction"]].copy()
        return result.rename(columns={"score":prefix+"_score","prediction":prefix+"_prediction"})
    paired=chosen(selected,"kd").merge(chosen(hard_name,"hard").drop(columns="y_true"),
                                      on="id",validate="one_to_one").merge(
        teacher_data[["id","teacher_prediction"]],on="id",validate="one_to_one")
    if len(paired)!=len(teacher_data):raise ValueError("Incomplete paired error audit")
    teacher_ok=paired.teacher_prediction.eq(paired.y_true)
    student_ok=paired.kd_prediction.eq(paired.y_true)
    transfers=[]
    for label in (0,1):
        for t in (False,True):
            for s in (False,True):
                transfers.append(dict(label=label,teacher_correct=t,student_correct=s,
                    n=int((paired.y_true.eq(label)&teacher_ok.eq(t)&student_ok.eq(s)).sum())))
    transfer=pd.DataFrame(transfers)
    transfer.to_csv(folder/"teacher_student_errors.csv",index=False,encoding="utf-8",lineterminator="\n")
    hard_ok=paired.hard_prediction.eq(paired.y_true)
    masks={"improved":~hard_ok&student_ok,"worsened":hard_ok&~student_ok,
           "unchanged":paired.hard_prediction.eq(paired.kd_prediction)}
    changes=pd.DataFrame([dict(label=label,change=name,n=int((mask&paired.y_true.eq(label)).sum()))
                          for label in (0,1) for name,mask in masks.items()])
    changes.to_csv(folder/"hard_kd_decision_changes.csv",index=False,encoding="utf-8",lineterminator="\n")
    changed=paired.loc[paired.hard_prediction.ne(paired.kd_prediction)].copy()
    changed["change"]=np.where(changed.kd_prediction.eq(changed.y_true),"improved","worsened")
    changed.to_csv(folder/"changed_ids.csv",index=False,encoding="utf-8",lineterminator="\n")
    optimizer=runs.loc[runs.family.eq("e2_mlp")&runs.operating_point.eq("validation_fpr_budget"),
                       ["candidate","seed","iterations","warning_count","warnings"]]
    optimizer.to_csv(folder/"mlp_optimization.csv",index=False,encoding="utf-8",lineterminator="\n")
    return stats,transfer,changes


def lightgbm_review():
    """Publish the requested study from saved predictions; no refitting."""
    folder=ROOT/"artifacts/student_lightgbm"
    if not (folder/"manifest.json").exists():return []
    from phishguard_vn.student_lightgbm import load_lightgbm_student
    from scipy.sparse import csr_matrix
    import lightgbm as lgb
    m=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    for p,digest in m["output_sha256"].items():
        if sha256(ROOT/p)!=digest:raise ValueError("LightGBM result changed: "+p)
    table=ROOT/"reports/tables/student_lightgbm"
    cv=pd.read_csv(table/"cv_summary.csv")
    cv_runs=pd.read_csv(table/"cv_metrics.csv")
    oof=pd.read_csv(table/"cv_predictions.csv.gz",float_precision="round_trip")
    validation=pd.read_csv(table/"validation_metrics.csv")
    decision=json.loads((table/"selection.json").read_text(encoding="utf-8"))
    boot=json.loads((table/"paired_bootstrap.json").read_text(encoding="utf-8"))
    teacher=[]
    for fold in (0,1,2):
        f=pd.read_csv(folder/f"cv_targets/outer{fold}_held_reference.csv.gz",float_precision="round_trip")
        row=metrics(f.target,f.teacher_score,.5)
        teacher.append(dict(fold=fold,**row))
    teacher_mean=float(np.mean([r["ap"] for r in teacher]))
    target_rows=[]
    for fold in (0,1,2):
        t=pd.read_csv(folder/f"cv_targets/outer{fold}_fitting_targets.csv.gz",float_precision="round_trip")
        for label,g in t.groupby("target"):
            target_rows.append(dict(outer_fold=fold,label=int(label),n=len(g),
                mean_teacher_score=float(g.teacher_score.mean()),
                mean_kd_target=float(((1-m["plan"]["alpha"])*g.target+m["plan"]["alpha"]*g.teacher_score).mean()),
                mean_teacher_distance_from_label=float(np.mean(np.abs(g.teacher_score-g.target)))))
    audit=ROOT/"reports/tables/student_kd_analysis"
    pd.DataFrame(target_rows).to_csv(audit/"cv_teacher_targets_by_label.csv",index=False,
                                   encoding="utf-8",lineterminator="\n")
    audit=ROOT/"reports/tables/student_kd_analysis"
    pd.DataFrame(teacher).to_csv(audit/"fold_teacher_metrics.csv",index=False,encoding="utf-8",lineterminator="\n")
    # Same desktop workload; report implementation backends, not Android speedups.
    from phishguard_vn.released_teacher import load_released_teacher
    from threadpoolctl import threadpool_limits
    import time
    raw=pd.read_csv(ROOT/"data/splits/url_val.csv",usecols=["id","url"],dtype=str)
    saved=pd.read_csv(table/"validation_predictions.csv.gz",usecols=["id","mode","seed"])
    sample=saved.loc[saved["mode"].eq("kd_mixed")&saved.seed.eq(42),["id"]].merge(
        raw,on="id",validate="one_to_one").iloc[:300]
    benchmarks=[("Teacher v2","Python released sklearn",load_released_teacher(ROOT))]
    benchmarks += [(mode,"Python portable JSON",load_lightgbm_student(ROOT,mode))
                   for mode in ("hard_only","kd_mixed")]
    times=[]
    with threadpool_limits(limits=1):
        for name,backend,predictor in benchmarks:
            durations=[]
            for i,url in enumerate(sample.url):
                start=time.perf_counter();predictor.predict_one(url)
                if i>=50:durations.append((time.perf_counter()-start)*1000)
            times.append(dict(model=name,backend=backend,warmup=50,requests=len(durations),
                p50_ms=float(np.median(durations)),p95_ms=float(np.quantile(durations,.95)),
                scope="desktop raw URL to result; same 250 inputs; threads=1",android_measured=False))
    latency=pd.DataFrame(times)
    latency.to_csv(audit/"lightgbm_desktop_latency.csv",index=False,encoding="utf-8",lineterminator="\n")
    # Static fixture expansion: no labels, no websites, no training.
    gold=json.loads((ROOT/"docs/mobile_parity_cases.json").read_text(encoding="utf-8"))["cases"]
    candidates=[{"name":c.get("name","example_"+str(i)),"url":c["url"]} for i,c in enumerate(
        json.loads((folder/"python_reference.json").read_text(encoding="utf-8"))["cases"])]
    candidates += [{"name":c["name"],"url":c["url"]} for c in gold]
    seen=set();fixtures=[]
    predictors={mode:load_lightgbm_student(ROOT,mode) for mode in ("hard_only","kd_mixed")}
    native={mode:lgb.Booster(model_file=str(folder/(mode+".model.txt"))) for mode in predictors}
    for case in candidates:
        url=case["url"]
        key=json.dumps(url,ensure_ascii=False)
        if key in seen:continue
        seen.add(key)
        try:
            e2=predictors["hard_only"].predict_batch([url])
            # Use exact sparse TF-IDF/E2 values for stage-by-stage Dart checks.
            from phishguard_vn.student_comparison import e2_matrix
            E=e2_matrix([url])[0]
            vector=predictors["hard_only"].vector(url,E)
            indices=sorted(vector)
            X=csr_matrix(([vector[i] for i in indices],([0]*len(indices),indices)),
                         shape=(1,len(predictors["hard_only"].terms)+20))
            predictions={}
            for mode,predictor in predictors.items():
                result=predictor.predict_one(url)
                native_score=float(native[mode].predict(X)[0])
                np.testing.assert_allclose(result["score"],native_score,atol=1e-12,rtol=0)
                predictions[mode]=result
            fixtures.append(dict(name=case["name"],url=url,status="classified",
                canonical_text=student_text(url),e2=E.tolist(),
                text_indices=[i for i in indices if i<len(predictors["hard_only"].terms)],
                text_values=[vector[i] for i in indices if i<len(predictors["hard_only"].terms)],
                expected=predictions))
        except (ValueError,TypeError) as exc:
            for predictor in predictors.values():
                try:predictor.predict_one(url)
                except (ValueError,TypeError):pass
                else:raise AssertionError("Invalid-input behavior differs between modes")
            fixtures.append(dict(name=case["name"],url=url,status="rejected",
                                 error_type=type(exc).__name__,error_reason=str(exc)))
    fixture_file=folder/"python_reference.json"
    fixture_file.write_text(json.dumps(dict(scope="static inputs, no accuracy/website labels",
        cases=fixtures),ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    # Add package hashes as a packaging-only supplement, preserving training provenance.
    m["bundle_files_sha256"]={p.name:sha256(p) for p in folder.iterdir()
        if p.is_file() and p.name!="manifest.json"}
    m["packaging_only"]=dict(script="scripts/summarize_student_comparison.py",
        script_sha256=sha256(Path(__file__)),training_rerun=False,
        valid_reference_cases=sum(c["status"]=="classified" for c in fixtures),
        rejected_reference_cases=sum(c["status"]=="rejected" for c in fixtures))
    (folder/"manifest.json").write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",
                                      encoding="utf-8",newline="\n")
    # Compact data package includes only one mode + common runtime data.
    common=sum((folder/p).stat().st_size for p in ["features.json","brand_reference_v1.csv","psl_icann_tldextract_5.4.0.txt"])
    sizes={mode:(folder/(mode+".json")).stat().st_size+common for mode in ("hard_only","kd_mixed")}
    pd.DataFrame([dict(mode=mode,package_bytes=size,original_goal_bytes=1048576,
                      within_original_goal=size<=1048576) for mode,size in sizes.items()]).to_csv(
        audit/"lightgbm_package_size.csv",index=False,encoding="utf-8",lineterminator="\n")
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for family in ("text_lr","hybrid_lightgbm"):
        for mode in ("hard_only","kd_mixed"):
            f=cv_runs.loc[cv_runs.family.eq(family)&cv_runs["mode"].eq(mode)&cv_runs.seed.eq(42)]
            axes[0].plot(f.fold,f.ap,marker="o",label=family+"/"+mode)
    axes[0].plot([0,1,2],[r["ap"] for r in teacher],"k--",label="Fold Teacher")
    axes[0].set(xlabel="Outer domain fold",ylabel="AP",title="Fixed architecture, 3 domain folds")
    axes[0].legend(fontsize=6);axes[0].set_xticks([0,1,2])
    for mode in ("hard_only","kd_mixed"):
        f=oof.loc[oof.family.eq("hybrid_lightgbm")&oof["mode"].eq(mode)&oof.seed.eq(42)]
        precision,recall,_=precision_recall_curve(f.y_true,f.score)
        axes[1].step(recall,precision,where="post",label="LightGBM "+mode)
    axes[1].set(xlabel="Recall",ylabel="Precision",title="Pooled Train OOF, seed 42")
    axes[1].legend(fontsize=8)
    fig.tight_layout();fig.savefig(FIGURES/"lightgbm_cv.png",dpi=180);plt.close(fig)
    lines=["", "## 7. LightGBM theo yêu cầu nhóm: 3-fold Teacher–Student", "",
        "Cấu hình: 400 trees, num_leaves=15, TF-IDF ký tự 8.192 + 20 E2. Chỉ thêm họ này, giữ LR làm baseline.",
        "Hai mode dùng cùng objective cross_entropy: hard-only q=y, KD q=0,5*y+0,5*Teacher score, T=1.",
        "Loss = -q*log(p)-(1-q)*log(1-p); LightGBM hỗ trợ trực tiếp fractional labels, không nhân đôi hàng.",
        "Teacher CV là các bản stacking theo fold đã lưu: cùng kiến trúc/hyperparameters, weights khác release, không học held fold.",
        "Đã kiểm fitting/held ID hashes, domain disjoint, fit ledger và tái hiện held predictions cũ; không fit lại Teacher.",
        "Targets còn in-sample trong phần fitting; không gọi là inner cross-fit KD. Student cuối dùng targets released Teacher v2.",
        "Vocabulary chỉ fit trong fitting partition của từng fold. Official splits và mapping 3 folds giữ nguyên.",
        "CV báo tại threshold 0,5 cố định. Threshold xuất model lấy từ pooled Train Student OOF với FPR budget 1%, không chọn trên outer-held/Validation.",
        "Dùng 3 seeds 42/43/44, export seed 42. Config deterministic, không subsample nên kết quả trùng seed; không coi đó là 9 independent tests.",
        "", "| Họ | Mode | Mean fold AP | Seed SD | Recall CV | FPR CV | F1 CV |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for _,r in cv.iterrows():
        lines.append(f"| {r.family} | {r['mode']} | {r.ap_mean:.4f} | {r.ap_seed_sd:.4f} | {100*r.recall_mean:.2f}% | {100*r.fpr_mean:.2f}% | {r.f1_mean:.4f} |")
    lines += ["",f"Teacher fold mean AP={teacher_mean:.4f}; không trộn với Teacher Validation AP=0,5549.",
        "Khác class prevalence và protocol nên không so trực tiếp CV AP ~0,92 với Validation AP ~0,65 để quy riêng thành overfit.",
        "", "![LightGBM CV](figures/student_comparison/lightgbm_cv.png)",
        "",f"Mode chọn từ CV: **{decision['selected_mode']}**. Chênh lệch mean-fold AP KD−hard rất nhỏ; pooled-OOF paired bootstrap ΔAP={boot['delta_mean_AP']:+.6f}, 95% CI [{boot['ci_low']:+.6f}, {boot['ci_high']:+.6f}].",
        "CI chứa 0: chưa có bằng chứng chắc chắn KD cải thiện ngoài mẫu. Mean-fold delta và pooled-OOF delta là hai đại lượng hơi khác nhau.",
        "", "Validation bổ sung sau khi freeze (không chọn lại cấu hình/ngưỡng từ bảng này):",
        "", "| Mode, seed 42 | AP | Recall | FPR | TP/FP/TN/FN | Threshold Train OOF |",
        "|---|---:|---:|---:|---|---:|"]
    for _,r in validation.loc[validation.seed.eq(42)].iterrows():
        lines.append(f"| {r['mode']} | {r.ap:.4f} | {100*r.recall:.2f}% | {100*r.fpr:.2f}% | {int(r.tp)}/{int(r.fp)}/{int(r.tn)}/{int(r.fn)} | {r.threshold:.6f} |")
    lines += ["", "LightGBM KD Validation AP=0,6549 cao hơn Teacher 0,5549; không che kết quả này. Tuy nhiên Student bắt 13/24, Teacher 15/24 tại ngưỡng tương ứng; Student có 10 FP so Teacher 14 FP.",
        "Hai mode LightGBM có cùng confusion counts trên Validation ở ngưỡng đã freeze, dù thứ hạng score/AP khác.",
        "Validation đã được xem trước trong đồ án; CV theo fold tách fitting hợp lệ nhưng reuse CV/adaptive research không phải final independent test.",
        "",f"Gói JSON + TF-IDF/IDF + reference + PSL: hard={sizes['hard_only']:,} bytes; KD={sizes['kd_mixed']:,} bytes. Vượt mục tiêu nghiên cứu 1 MiB; budget Android thật chưa được xác nhận.",
        "Không giảm số cây/lá hoặc đổi cấu hình để ép vừa budget. File .model.txt là bản native bổ sung; không cộng cả hai định dạng vào một runtime package.",
        f"Đã xuất {len(fixtures)} static Python fixtures: {m['packaging_only']['valid_reference_cases']} valid và {m['packaging_only']['rejected_reference_cases']} rejected; không có ground truth accuracy labels.",
        "Model JSON được kiểm với native LightGBM trên toàn Validation và static fixtures. Chưa có Dart adapter/Android parity hoặc số đo latency/RAM/APK cho Student này.",
        "Desktop end-to-end timings dưới đây dùng cùng 250 URLs sau 50 warm-ups, threads=1; Teacher dùng sklearn backend, Student dùng portable JSON. Đây là so sánh implementation, không suy ra Android speedup.",
        "", "| Model | Backend | p50 ms | p95 ms |", "|---|---|---:|---:|",
        *[f"| {r.model} | {r.backend} | {r.p50_ms:.3f} | {r.p95_ms:.3f} |" for _,r in latency.iterrows()],
        "Source targets/fit lineage, CV/Validation predictions, model, vocabulary/IDF, reference, PSL và SHA-256 được bàn giao trong repo.",
        "Teacher targets trên Train đã khá sát nhãn thật: release Teacher mean score benign ~0,0177, phishing ~0,9343. Trộn alpha=0,5 cho mean q ~0,0089 và ~0,9671.",
        "Vì vậy mục tiêu KD thay đổi khá ít so với hard labels ở nhiều mẫu. Đây là một giả thuyết giải thích lợi ích nhỏ, không phải nguyên nhân đã được chứng minh.",
        "Bảng cv_teacher_targets_by_label.csv tách từng Teacher/fitting context; không cộng các fitting sets chồng lặp thành dữ liệu độc lập.",
        "Trong Validation, LightGBM hard và KD có cùng nhãn cho toàn bộ 1.585 IDs tại các threshold đã freeze; khác biệt AP là khác thứ hạng score, không phải tăng số URL phát hiện tại operating point này.",
        "Student sửa 12 lỗi Teacher nhưng tạo thêm 10 lỗi trên những mẫu Teacher đúng; có 11 lỗi cả hai cùng sai. Co-error không chứng minh Teacher gây lỗi Student.",
        "", "## 8. Quyết định engine và việc còn lại", "",
        "**Giữ Teacher stacking v2 làm engine cho tích hợp Android theo quyết định nhóm/Phúc; không thay weights hoặc threshold.**",
        "LightGBM là candidate nghiên cứu bổ sung; không tự promote chỉ vì AP Validation cao hơn. Teacher fold-CV cao hơn, KD chưa có lợi ích chắc chắn, và chi phí triển khai Student chưa được đo trên thiết bị.",
        "Quyết định Teacher không phủ nhận kết quả LightGBM Validation tốt hơn hoặc tuyên bố Student vô ích. Có thể review lại trong nghiên cứu sau với đánh giá độc lập và budget thiết bị rõ ràng.",
        "Hy ưu tiên nối Teacher vào UI/offline và đo thiết bị. Student bundle/contract sẵn để thử riêng nếu nhóm cần; Khiêm kiểm hash/invalid inputs/regression/parity.",
        "Official Test/external chưa được đánh giá trong nghiên cứu Student. Không có tuyên bố production-ready.",
        ""]
    return lines


def main():
    FIGURES.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/"artifacts/student_comparison/manifest.json").read_text(encoding="utf-8"))
    for p,digest in manifest["output_sha256"].items():
        if sha256(ROOT/p)!=digest:raise ValueError("Stale saved result: "+p)
    summary=pd.read_csv(TABLES/"summary.csv")
    runs=pd.read_csv(TABLES/"runs.csv")
    prediction=pd.read_csv(TABLES/"validation_predictions.csv.gz",float_precision="round_trip")
    delta=pd.read_csv(TABLES/"kd_effect.csv")
    bootstrap=pd.read_csv(TABLES/"paired_bootstrap.csv")
    selected=manifest["selected_candidate"]
    chosen=summary.set_index("candidate").loc[selected]
    exported=runs.loc[(runs.candidate==selected)&(runs.seed==42)&
                      (runs.operating_point=="validation_fpr_budget")].iloc[0]
    teacher=json.loads((ROOT/"reports/tables/student_week7/teacher_validation.json").read_text(encoding="utf-8"))
    old=pd.read_csv(ROOT/"reports/tables/student_week7/hard_only_validation.csv",float_precision="round_trip")
    teacher_data=prediction.loc[(prediction.candidate=="text_lr__hard_only")&(prediction.seed==42),
                               ["id","y_true"]].merge(old[["id","teacher_score","teacher_prediction"]],on="id",validate="one_to_one")
    baseline=summary.set_index("candidate").loc["text_lr__hard_only"]
    e2lr=summary.set_index("candidate").loc["e2_lr__hard_only"]

    audit=ROOT/"reports/tables/student_kd_analysis"
    lgb_pred_path=ROOT/"reports/tables/student_lightgbm/validation_predictions.csv.gz"
    if lgb_pred_path.exists():
        lgb_pred=pd.read_csv(lgb_pred_path,float_precision="round_trip")
        lgb_pred["candidate"]="hybrid_lightgbm__"+lgb_pred["mode"]
        diagnostic_predictions=lgb_pred
        diagnostic_selected="hybrid_lightgbm__kd_mixed"
    else:
        diagnostic_predictions,diagnostic_selected=prediction,selected
    targets=pd.read_csv(ROOT/"artifacts/student_week7/teacher_targets.csv.gz",float_precision="round_trip")
    stats,transfer,changes=kd_diagnostics(targets,teacher_data,diagnostic_predictions,
                                        diagnostic_selected,runs,audit)
    future=[["Tỷ lệ học Teacher","Hiện chỉ alpha=0 (hard baseline) và 0,5; chưa thử alpha khác hoặc alpha=1.","Chưa thử; không tune tiếp trên Validation đã xem."],["Dạng target/loss","Hard Teacher labels, logit matching, temperature-scaled KD, class-dependent KD.","Chưa thử; không gọi hard_only hiện tại là học hard labels của Teacher."],["Độ tin cậy Teacher","Calibration, phân tích hoặc giảm trọng số các Teacher targets mâu thuẫn nhãn.","Chưa thử; raw score hiện tại chưa calibrated, chưa chứng minh đây là nguyên nhân làm KD yếu."],["Tạo targets","Teacher targets cross-fit theo domain trong Train.","Chưa thử; cần thiết kế nghiên cứu riêng, không yêu cầu khôi phục protocol KD cũ và không đổi release Teacher."],["Kiến trúc/đầu vào","Char-CNN, MLP đọc text/raw bytes, distillation đầu ra trung gian.","Chưa thử các hướng này; hybrid TF-IDF+E2 đã thử với LightGBM, không còn là hướng chưa khảo sát."],["Optimization/imbalance","MLP train dài hơn/cấu hình khác, class weighting hoặc sampling có kiểm soát.","Chưa thử; fixed-budget 200 epochs không đồng nghĩa đã hội tụ. Không trộn thay đổi này với hiệu ứng KD."],["Dữ liệu/đánh giá","Nhãn được kiểm chứng thêm, cohort độc lập nhiều positives hơn và domain/source shift.","Chưa có; không dùng Official Test để lựa chọn hoặc cứu candidate."],["Triển khai/nén","Benchmark Android Teacher/Student; quantization hoặc pruning có đo lường.","Chưa làm trong nghiên cứu này; quantization/pruning không phải bằng chứng về KD."]]
    pd.DataFrame(future,columns=["direction","not_run","status"]).to_csv(
        audit/"untested_directions.csv",index=False,encoding="utf-8",lineterminator="\n")

    # Mean +/- SD refers to training randomness, not a confidence interval.
    fig,ax=plt.subplots(figsize=(10,6))
    display=summary.iloc[::-1]
    ax.barh(display.candidate,display.ap_mean,xerr=display.ap_sd,
            color=["#147d75" if c==selected else "#829ab1" for c in display.candidate],capsize=3)
    ax.axvline(teacher["ap"],color="#a92f2f",linestyle="--",label="Frozen Teacher v2 (one release)")
    ax.set(xlabel="Validation AP: mean +/- seed SD",title="Student comparison: three training seeds")
    ax.legend();fig.tight_layout();fig.savefig(FIGURES/"ap_comparison.png",dpi=180);plt.close(fig)

    # One fixed seed per family/mode, no ensemble and no best-seed cherry-picking.
    show=summary.groupby("family",sort=False).head(1).candidate.tolist()
    fig,ax=plt.subplots(figsize=(8,6))
    for candidate in show:
        f=prediction.loc[(prediction.candidate==candidate)&(prediction.seed==42)]
        precision,recall,_=precision_recall_curve(f.y_true,f.score)
        ax.step(recall,precision,where="post",label=candidate)
    precision,recall,_=precision_recall_curve(teacher_data.y_true,teacher_data.teacher_score)
    ax.step(recall,precision,where="post",color="black",linestyle="--",label="Frozen Teacher v2")
    ax.axhline(24/1585,color="grey",linestyle=":",label="Positive prevalence")
    ax.set(xlabel="Recall",ylabel="Precision",title="Validation PR curves (export seed 42)")
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(FIGURES/"pr_curves.png",dpi=180);plt.close(fig)

    fig,ax=plt.subplots(figsize=(8,5))
    for candidate in sorted(set([selected,"text_lr__hard_only","e2_lr__hard_only"])):
        f=prediction.loc[(prediction.candidate==candidate)&(prediction.seed==42)]
        fpr,tpr,_=roc_curve(f.y_true,f.score)
        ax.plot(fpr,tpr,label=candidate)
    fpr,tpr,_=roc_curve(teacher_data.y_true,teacher_data.teacher_score)
    ax.plot(fpr,tpr,"k--",label="Frozen Teacher v2")
    ax.axvline(.01,color="grey",linestyle=":")
    ax.set(xlim=(0,.05),ylim=(0,1),xlabel="FPR",ylabel="Recall",title="Low-FPR operating region, Validation")
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(FIGURES/"recall_fpr.png",dpi=180);plt.close(fig)

    fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,name in zip(axes,["text_lr__hard_only",selected,"Teacher v2"]):
        f=(teacher_data.rename(columns={"teacher_prediction":"prediction"}) if name=="Teacher v2"
           else prediction.loc[(prediction.candidate==name)&(prediction.seed==42)])
        ConfusionMatrixDisplay.from_predictions(f.y_true,f.prediction,labels=[0,1],
            display_labels=["benign","phishing"],colorbar=False,ax=ax,cmap="Blues")
        ax.set_title(name,fontsize=10)
    fig.tight_layout();fig.savefig(FIGURES/"confusion.png",dpi=180);plt.close(fig)

    fig,ax=plt.subplots(figsize=(9,6))
    for _,r in summary.iterrows():
        ax.scatter(r.package_bytes/1024,r.ap_mean,s=65,
                   color="#147d75" if r.candidate==selected else "#829ab1")
        ax.annotate(r.candidate,(r.package_bytes/1024,r.ap_mean),fontsize=7,xytext=(4,4),textcoords="offset points")
    ax.axvline(1024,color="grey",linestyle="--",label="Research package budget")
    ax.set(xlabel="Model JSON + required data assets (KiB)",ylabel="Mean Validation AP",title="Quality / size trade-off")
    ax.legend();fig.tight_layout();fig.savefig(FIGURES/"quality_size.png",dpi=180);plt.close(fig)

    lines=["# Teacher–Student tuần 7 — baseline, so sánh, LightGBM và quyết định","",
      "**Đây là nghiên cứu phát triển trên Validation, chưa phải final evaluation hoặc Android release.**",
      "Kế hoạch cấu hình được commit trước fitting; không sửa Teacher, E2, reference, targets hay baseline cũ.",
      "Căn cứ: [protocol](../docs/week7_student_comparison_protocol.md).",
      "", "## 1. Phạm vi đã chạy","",
      "- 5 họ × 2 cách học × 3 seed = **30 fits**, không grid hoặc chọn seed đẹp.",
      "- Train 13.078; Validation 1.585, chỉ **24 phishing**. Cùng IDs/targets giữa mọi mô hình.",
      "- Bản cũ text LR được chạy lại làm đối chứng. E2 LR tách tác dụng đổi input khỏi đổi thuật toán.",
      "- MLP 32–16, HistGB 150 vòng/7 lá và Extra Trees 64 cây/sâu 8 là các cấu hình nhỏ đã chốt.",
      "- Hard-only và KD đều dùng weighted BCE; alpha=0,5. Không tune alpha sau khi thấy số liệu.",
      "- Artifacts là seed 42 đã định trước; không dùng seed có AP tốt nhất.",
      "- Mean/SD phản ánh biến động training seed; không phải uncertainty từ ba dataset độc lập.",
      "", "## 2. Bảng kết quả","",
      "| Candidate | AP mean ± SD | Recall mean | FPR mean | F1 mean | Data package KiB | Desktop p95 ms |",
      "|---|---:|---:|---:|---:|---:|---:|"]
    for _,r in summary.iterrows():
        lines.append(f"| {r.candidate} | {r.ap_mean:.4f} ± {r.ap_sd:.4f} | {100*r.recall_mean:.2f}% | {100*r.fpr_mean:.2f}% | {r.f1_mean:.4f} | {r.package_bytes/1024:.1f} | {r.p95_ms:.3f} |")
    lines += ["",f"Teacher v2 trên cùng Validation: AP **{teacher['ap']:.4f}**, Recall {100*teacher['recall']:.2f}%, FPR {100*teacher['fpr']:.2f}%, TP/FP/TN/FN={teacher['tp']}/{teacher['fp']}/{teacher['tn']}/{teacher['fn']}.",
      "Teacher giữ ngưỡng phát hành; Student dùng ngưỡng riêng chọn trên Validation. PR/Recall–FPR curves cho phép xem các operating points.",
      "", "![AP](figures/student_comparison/ap_comparison.png)",
      "", "## 3. Candidate tốt nhất trong khảo sát Validation ban đầu","",
      f"Chọn **{selected}** theo tiêu chí đã chốt: đạt budget, mean AP cao nhất; tie-break Recall rồi kích thước.",
      f"- AP mean **{chosen.ap_mean:.4f}**, SD **{chosen.ap_sd:.4f}**; so với text LR hard-only {baseline.ap_mean:.4f} và E2 LR hard-only {e2lr.ap_mean:.4f}.",
      f"- Artifact **{int(chosen.model_bytes):,} bytes**; cộng PSL/reference cần thiết thành **{int(chosen.package_bytes):,} bytes**; budget nghiên cứu là 1.048.576 bytes.",
      f"- Export seed 42: TP={int(exported.tp)}, FP={int(exported.fp)}, TN={int(exported.tn)}, FN={int(exported.fn)}, threshold={exported.threshold:.17g}.",
      f"- Desktop p50/p95: {chosen.p50_ms:.3f}/{chosen.p95_ms:.3f} ms, scope raw URL→score; không suy ra số đo Android.",
      "- Đây là lựa chọn tốt nhất trong menu/cấu hình/budget đã thử. Không gọi là optimum toàn cục hoặc Student đã sẵn sàng triển khai.",
      "", "Tác dụng của KD trong từng họ (cùng input/kiến trúc):","",
      "| Họ | AP hard | AP KD | KD − hard |","|---|---:|---:|---:|"]
    for _,r in delta.iterrows():
        lines.append(f"| {r.family} | {r.hard_AP:.4f} | {r.kd_AP:.4f} | {r.kd_minus_hard_AP:+.4f} |")
    lines += ["", "Không quy mọi cải thiện so với text LR thành lợi ích KD: đổi sang E2 và đổi kiến trúc cũng là thay đổi.",
              "KD có thể không giúp một họ; bản hard-only tốt hơn vẫn được giữ và báo cáo.",
              "Trong lượt này, HistGB hard-only đã đạt AP 0,4322; thêm KD chỉ tăng 0,0048. Phần lớn mức tăng so với text LR không đến từ riêng KD.",
              "HistGB 150 vòng/7 lá học tương tác phi tuyến giữa các đặc trưng E2, thay cho một tầng linear trên ký tự. Đây là cấu hình Student mới, không lấy lại nhánh Teacher đã fit.",
              "E2 LR KD cũng có Recall/FPR/F1 giống HistGB KD ở ngưỡng đã chọn, nhưng AP thấp hơn và package nhỏ hơn; nếu ưu tiên chi phí hơn AP, đây là đối án đáng xem.",
              "MLP KD seed 42 có AP 0,4619, cao hơn HistGB, nhưng mean qua 3 seed chỉ 0,4062 và SD 0,0631; không lấy riêng seed đẹp để chọn.",
              "SD bằng 0 của LR/HistGB trong cấu hình này chủ yếu do thuật toán xác định, không phải bằng chứng model ổn định trước dataset/source shift.",
              "", "![PR](figures/student_comparison/pr_curves.png)",
              "", "![Confusion](figures/student_comparison/confusion.png)",
              "", "## 4. Uncertainty và chi phí","",
              "Paired bootstrap theo registrable domain Validation, 1.000 lần. Delta là mean AP qua seed, models đã fit; CI không điều chỉnh quá trình chọn winner:"]
    for _,r in bootstrap.iterrows():
        lines.append(f"- {r.candidate} − {r.comparator}: ΔAP={r.delta_mean_AP:+.4f}, 95% CI [{r.ci_low:+.4f}, {r.ci_high:+.4f}], valid={int(r.valid)}, undefined={int(r.undefined)}.")
    lines += ["", "Các CI trên đều chứa 0: chưa có bằng chứng chắc chắn rằng cải thiện AP tổng quát là dương. Lựa chọn candidate là theo tiêu chí development đã chốt, không phải khẳng định thắng có ý nghĩa thống kê.", "", "![Size](figures/student_comparison/quality_size.png)",
              "", "![Low FPR](figures/student_comparison/recall_fpr.png)",
              "", "Cỡ package tính model JSON và dữ liệu PSL/reference bắt buộc, chưa gồm source/runtime/APK overhead.",
              "E2 cần parser/feature extractor/reference; vector input 20 số không có nghĩa chi phí đầu-cuối bằng 0.",
              "Latency là Python JSON reference trên desktop, có tách E2 extraction và inference trong latency.csv.",
              "MLP chạy cố định 200 epochs; ConvergenceWarning được lưu trong runs.csv, không bị che và không được gọi là đã hội tụ.",
              "", "## 5. Giới hạn và Go/No-Go","",
              "- Validation đã được xem và nay dùng chọn model/ngưỡng; mở rộng theo yêu cầu sau baseline là adaptive development.",
              "- Chỉ 24 phishing, ba seeds, một cấu hình/họ. CI có điều kiện không xóa selection bias.",
              "- Targets Teacher in-sample trên Train; không phải cross-fitted/OOF KD.",
              "- Source × label còn confounded; domain split không chứng minh tổng quát tốt ngoài dataset.",
              "- Chưa thử CNN/Transformer; không có kết luận chúng kém hơn menu hiện tại.",
              "- Không đọc/chấm Official Test/external mới. Teacher không retrain; baseline Student cũ không ghi đè.",
              "- JSON/sklearn parity trên 1.585 Validation samples mỗi exported model không phải Android parity.",
              "- Chưa có số đo thiết bị/RAM/battery/APK; chưa chuyển engine mặc định.",
              "", "**Khảo sát ban đầu:** HistGB KD là candidate đứng đầu menu này; kết quả giữ làm đối chiếu lịch sử.",
              "**Engine hiện tại:** giữ Teacher stacking v2. Nhóm yêu cầu kiểm chứng thêm LightGBM bên dưới; Student không tự chuyển thành mặc định.",
              "", "## 6. Tái chạy và bàn giao","",
              "Notebook 07_student.ipynb (đã gộp baseline và các thử nghiệm) có bảng/hình/output đã chạy.",
              "scripts/compare_students.py chạy thí nghiệm; scripts/summarize_student_comparison.py chỉ đọc kết quả để tạo report/hình.",
              "scripts/predict_student_comparison.py --examples dùng model đã xuất, không cần Teacher ở inference.",
              "artifacts/student_comparison/manifest.json lưu selected_candidate, hash/version, parity và source revision.",
              "Toàn bộ kết quả gồm các bản yếu đều nằm trong reports/tables/student_comparison/.",
              ""]
    lines += lightgbm_review()
    lines += ["", "## Rà soát KD và hướng chưa thử", "",
        "Phạm vi này đủ để giải thích quyết định của đồ án, chưa đủ để kết luận KD vô ích trong mọi kiến trúc/dữ liệu.",
        "Đã kiểm: paired hard/KD, input control, thuật toán, 3 seeds, AP/Recall/FPR/F1, PR/confusion, size/desktop latency, domain bootstrap và target lineage.",
        "Chỉ alpha=0 và 0,5 với T=1; hard_only là nhãn thật, không phải hard labels của Teacher. Chưa đánh giá toàn bộ lựa chọn targets/loss.",
        "Teacher raw scores chưa calibrated; score hoặc agreement cao không tự chứng minh xác suất đúng.",
        "Train và Validation khác class prevalence; không quy chênh lệch AP giữa hai cohort thành riêng overfit hoặc domain shift.",
        "Các bảng teacher_targets_by_label.csv, teacher_student_errors.csv và hard_kd_decision_changes.csv chỉ mô tả quan sát, không chứng minh Teacher gây ra lỗi Student.",
        "Mỗi mode có threshold riêng; các thay đổi decision còn chịu ảnh hưởng operating point, không chỉ loss KD.",
        "MLP chạm budget 200 epochs; chưa có bằng chứng đã hội tụ, nên chưa loại trừ giới hạn optimization.",
        "", "| Hướng | Chưa thử gì | Giới hạn/kế hoạch |", "|---|---|---|"]
    lines += ["| "+" | ".join(row)+" |" for row in future]
    lines += ["", "Không chạy thêm các hướng trên trong đợt này. Đây là hướng còn mở, không phải các phương pháp đã bị chứng minh kém.",
        "Teacher stacking v2 được giữ làm engine cho tích hợp Android; không có tuyên bố production-ready hoặc đã hoàn thành benchmark thiết bị.",
        ""]
    lines.insert(2,"> Notebook thống nhất: 07_student.ipynb. Phần 1–6 là khảo sát Validation ban đầu; phần LightGBM dùng Group CV riêng. Không trộn hai protocol.")
    (ROOT/"reports/week7_student_comparison.md").write_text("\n".join(lines),encoding="utf-8",newline="\n")
    print("Generated unified KD/LightGBM report, diagnostics, fixtures and figures.")


if __name__=="__main__":
    main()

