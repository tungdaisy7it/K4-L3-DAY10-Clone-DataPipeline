# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Đinh Quốc Bảo             |
| MSSV               | 2A202602933                |
| Khóa/Lớp         | K4 — L3                    |
| Tên nhóm         | Clone                 |
| Vai trò chính    | Observability owner — Quality Gate, Freshness SLA & Reporting |
| Repository         | https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Quality gate GX 1.x | `src/observability/quality.py::run_data_quality_checks`, `_run_gx`, `_build_suite` | Dataframe bất kỳ | `data/quality/{baseline,corrupted,repaired}_quality_report.json` | Hoàn thành |
| Source reconciliation | `_source_reconciliation` | Dataframe + raw records | Coverage và danh sách DOI bị thiếu | Hoàn thành |
| Freshness SLA | `build_freshness_report`, `_freshness` | Dataframe (`age_days`) | `freshness_report.json` + bản corrupted/repaired | Hoàn thành |
| Báo cáo Markdown | `src/observability/reporting.py` | Metrics, quality, freshness, answers, log | `phase1_report.md`, `corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Thống nhất tên check cho bảng "lỗi → detector" | Lê Thanh Tùng — `corruption.py` | 6/6 lỗi map đúng detector, cột "Detected?" tự tính từ report |
| Xác minh số trong report khớp artifact | Cả nhóm | Report sinh tự động từ `*_metrics.json` và `*_answers.json`, không nhập tay |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Gate PASS trên dữ liệu sạch | `baseline_quality_report.json` | 12/12 check PASS | Lệnh CP1: `Quality check status = True` |
| Gate FAIL trên dữ liệu bẩn | `corrupted_quality_report.json` | 5 check FAIL | `test_quality_gate_detects_every_corruption` |
| Freshness SLA | `freshness_report.json`, `corrupted_freshness_report.json` | 4.17% (Fresh) → 31.82% (Stale) | Mục 1 của `corruption_report.md` |
| Báo cáo 3 trạng thái | `corruption_report.md` | 7 mục: so sánh, ma trận check, detector, theo dạng câu hỏi, root cause, repair, phân tích | `python script/run_corruption_flow.py` |

Output cụ thể: bảng "Injected corruptions and detection" trong `corruption_report.md` cho thấy 6/6 loại lỗi bị bắt (YES) bởi đúng detector dự kiến.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Chặn dữ liệu xấu trước vector store và biến silent failure thành cảnh báo có tên, có số liệu.

### Cách triển khai

- **GX 1.x đúng chuẩn:** `gx.get_context(mode="ephemeral")` → `context.data_sources.add_pandas("papers_source")` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `get_batch(batch_parameters={"dataframe": df})` → `batch.validate(suite)`. Không dùng cú pháp cũ `context.sources.pandas_default`.
- **Suite (11 expectation):** `ExpectTableRowCountToBeBetween(5, 5000)`; `ExpectColumnValuesToNotBeNull` cho `paper_id`, `title`, `summary`, `published`, `text_for_embedding`; `ExpectColumnValuesToBeUnique(paper_id)`; `ExpectColumnValueLengthsToBeBetween` cho summary ≥ 30 và title ≥ 8; `ExpectColumnValuesToNotMatchRegex(summary, [#@!%&*~^$<>?]{2,}|�|Ã)`; `ExpectColumnValuesToMatchRegex(published, ^\d{4}-\d{2}-\d{2}$)`.
- **Source reconciliation (custom):** clean lại raw records để lấy tập DOI kỳ vọng, rồi đo coverage của dataset; dưới 0.95 thì FAIL.
- **Freshness SLA:** stale khi `age_days > 180`; `is_fresh=False` khi tỉ lệ stale > 25%. Kèm `latest_published`, `median_age_days`, phân bố tuổi 5 bucket và thông điệp cảnh báo.
- **Reporting:** mọi con số được sinh từ artifact. Recovery = (repaired − corrupted) / (baseline − corrupted). Cột "Detected?" đọc trực tiếp kết quả check của trạng thái corrupted.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | Dataframe theo `CLEAN_COLUMNS`, `Settings`, `report_name` |
| Output | Dict `{success, gx_success, failed_checks, expectations[], source_reconciliation, freshness, statistics}` + file JSON |
| Module phụ thuộc | `great_expectations` 1.23, `ingestion.cleaning`/`crossref` (reconciliation) |
| Module sử dụng output | `pipelines.phase1` (chặn index), `pipelines.corruption_flow` (kích hoạt repair), `reporting` |
| Điều kiện lỗi cần xử lý | Không có raw → reconciliation `skipped`; dataframe rỗng → freshness `is_fresh=False`; giá trị GX không serialize được → `default=str` |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Tín hiệu hoàn thành: Quality check status = {res[\"success\"]}')"
python -m pytest tests/test_quality_and_testset.py -q
```

- **Kết quả mong đợi:** `True` trên dữ liệu sạch; test phát hiện lỗi pass.
- **Kết quả thực tế:** `Tín hiệu hoàn thành: Quality check status = True`; 6/6 test pass.
- **Artifact/log:** `data/quality/*.json`, `data/reports/*.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Freshness có nên là một phần của `success` (chặn gate) không?
- **Các phương án đã cân nhắc:** (a) Đưa freshness vào GX (`ExpectColumnValuesToBeBetween(age_days, max=180, mostly=0.75)`) để nó chặn gate. (b) Để freshness là tín hiệu SLA riêng: cảnh báo, và kích hoạt repair ở pha 2, nhưng không chặn pha 1.
- **Phương án đã chọn:** (b).
- **Lý do:** Freshness phụ thuộc ngày chạy, không phụ thuộc dữ liệu. Snapshot cố định sẽ tự vượt 25% từ khoảng 2026-11-29 (7/24 bài > 180 ngày). Nếu chặn gate thì pha 1 sẽ tự hỏng dù dữ liệu không đổi. Dữ liệu cũ cần refresh nguồn, không phải chặn index.
- **Bằng chứng:** baseline `is_fresh=True` (1/24 = 4.17%); corrupted `is_fresh=False` (7/22 = 31.82%) vẫn kích hoạt repair.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Với bộ 4 expectation tối thiểu, thiết kế ban đầu không bắt được 3/6 lỗi. `drop_latest_records` vẫn còn 22 dòng (trong 5–5000); summary bị xóa là `""` chứ không phải null, nên `NotBeNull` vẫn PASS; token rác không vi phạm độ dài.
- **Lệnh hoặc bước tái hiện:** chạy `run_data_quality_checks` trên output của `corrupt_clean_dataframe` và đối chiếu `failed_checks` với `corruption_log.json`.
- **Nguyên nhân gốc:** mỗi failure mode cần một detector tương ứng; row count kiểm tra biên tuyệt đối, không kiểm tra độ đầy đủ so với nguồn.
- **Cách xử lý:** giữ `ExpectColumnValueLengthsToBeBetween(summary ≥ 30)` để bắt cả chuỗi rỗng; thêm regex chống nhiễu, độ dài title ≥ 8, và check `source_reconciliation` đối chiếu DOI với raw.
- **Cách xác minh sau khi sửa:** mục 3 của `corruption_report.md` có "Detected? = YES" cho cả 6 loại; `test_quality_gate_detects_every_corruption` pass.
- **Điều học được:** xuất phát từ danh sách failure mode để thiết kế expectation, không phải từ danh sách expectation có sẵn.

## 7. Hiểu biết về luồng end-to-end

1. Raw → clean → **gate của tôi** → nếu PASS thì MiniLM + ChromaDB; nếu FAIL thì pha 1 dừng, không index.
2. Hit = DOI ground truth nằm trong top-4; token F1 và LLM judge đo câu trả lời.
3. Quality checks trả lời câu hỏi "dữ liệu có hợp lệ và đầy đủ không"; freshness trả lời "dữ liệu còn đủ mới không". Cái thứ hai thay đổi theo thời gian dù dữ liệu không đổi.
4. Cùng test set thì mọi chênh lệch đều quy về dữ liệu.
5. Repair thành công khi 13/13 tín hiệu (11 GX + reconciliation + freshness) trở lại PASS và 4 metric bằng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ------------- | -------: | --------: | -------: | -------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | |
| `mean_token_f1` | 1.0000 | 0.7519 | 1.0000 | |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | |
| `mean_judge_score` | 5.0 | 4.2 | 5.0 | |
| Quality checks | PASS (0 fail) | FAIL (5 fail) | PASS (0 fail) | unique, title len, summary len, noise regex, reconciliation |
| Freshness status | Fresh (4.17%) | Stale (31.82%) | Fresh (4.17%) | |

### Kết luận từ số liệu

1. Duplicate rows → `expect_column_values_to_be_unique(paper_id)` FAIL. Metric agent không đổi (eval_006 vẫn F1 1.0): gate bắt được lỗi mà benchmark không thấy.
2. Repair → 0 check FAIL và freshness 4.17% → metric trở về baseline.

Kịch bản đáng chú ý nhất với observability là `drop_latest_records`: số dòng vẫn "bình thường", chỉ reconciliation với nguồn mới phát hiện được (coverage 0.7917).

Khác kỳ vọng: gate tìm thấy 6 vấn đề nhưng agent chỉ giảm 20% hit rate. Điều đó cho thấy độ phủ của test set nhỏ hơn độ phủ của gate. LLM judge cũng chấm 5/5 cho câu trả lời có token rác, nên không thể dùng judge thay cho data quality check.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. GX 1.x ephemeral context đủ nhẹ để chạy trong pipeline mà không cần project GX trên đĩa.
2. Tách tín hiệu "hợp lệ" (gate) khỏi tín hiệu "tươi" (SLA) vì chúng có nguyên nhân và cách xử lý khác nhau.
3. Report phải sinh từ artifact; mọi con số trong report đều truy được về file JSON.

### Nếu có thêm thời gian

Làm dashboard HTML (bonus B1) vẽ phân bố `age_days` và lịch sử `stale_ratio`/coverage qua các lần chạy, cảnh báo drift khi `latest_age_days` tăng liên tục.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đinh Quốc Bảo
**Ngày xác nhận:** [YYYY-MM-DD]
