# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4 — L3                    |
| Tên nhóm         | Clone                 |
| Repository         | https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline |
| Ngày hoàn thành | 2026-09-25                 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Lê Thanh Tùng (nhóm trưởng) | 2A202602499 | Corruption & integration owner | `src/ingestion/corruption.py`, `src/pipelines/*.py`, `src/retrieval/llm.py`, `tests/`, CI |
| 2 | Nguyễn Thu Hằng | 2A202602463 | Source owner | `src/ingestion/crossref.py`, `data/raw/` |
| 3 | Đậu Văn Thạch | 2A202602592 | Data model & evaluation-set owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py` |
| 4 | Đinh Quốc Bảo | 2A202602933 | Observability owner | `src/observability/quality.py`, `src/observability/reporting.py` |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thiện toàn bộ các khối `TODO(student)`: ingestion Crossref (retry/backoff 429/5xx + fallback snapshot), cleaning (bỏ thẻ JATS, chuẩn hóa DOI, `age_days`, `text_for_embedding` 5 phần, khử trùng lặp), Quality Gate Great Expectations 1.23 (ephemeral context, 11 expectation + source reconciliation), Freshness SLA, test set 10 câu / 4 dạng, bộ tiêm 6 lỗi có seed, repair idempotent và 2 báo cáo Markdown.

Baseline (24 bài, offline snapshot) đạt `retrieval_hit_rate = 1.0`, `mean_token_f1 = 1.0`, `judge_accuracy = 1.0` với LLM judge thật (Gemini `gemini-3.5-flash-lite`). Khi tiêm lỗi, agent **không báo lỗi gì** nhưng hit rate giảm còn 0.80, token F1 còn 0.7519, judge accuracy còn 0.80 — đúng hiện tượng silent failure. Ảnh hưởng rõ nhất là `drop_latest_records` (câu hỏi về bài bị mất vẫn được trả lời tự tin bằng tác giả của bài khác, F1 = 0) và `stale_date` (trả sai ngày, F1 = 0). Quality gate phát hiện **cả 6/6** lỗi bằng đúng detector dự kiến. Repair dựng lại từ `data/raw/crossref_records.json` đạt 24 dòng, fingerprint trùng baseline, 2 lần repair cho kết quả giống hệt nhau (idempotent), và khôi phục 100% cả 4 chỉ số.

Giới hạn chính: snapshot là dữ liệu tổng hợp có các cặp bài gần trùng ("X" và "Advanced Perspectives on X"), và bộ trả lời QA là rule-based nên baseline đạt tuyệt đối 1.0.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (REFRESH_SOURCE=1) hoặc snapshot data/raw/crossref_response.json
    -> parse_crossref_payload -> data/raw/crossref_records.json
    -> build_clean_dataframe -> data/clean/papers_clean.{csv,json}
    -> Quality gate GX 1.x + source reconciliation + Freshness SLA -> data/quality/
       (gate FAIL => phase 1 dừng, không index dữ liệu xấu)
    -> MiniLM embedding + ChromaDB "papers-baseline" -> data/chroma, data/embeddings/
    -> evaluate (test set cố định) -> data/results/baseline_*.json, data/reports/phase1_report.md
    -> corrupt (6 kịch bản, seed 42) -> gate phát cảnh báo
    -> index "papers-corrupted" riêng + evaluate  (đo silent failure)
    -> gate tripped => auto-repair từ raw (x2, so fingerprint)
    -> gate lại (PASS) -> index "papers-repaired" + evaluate
    -> data/reports/corruption_report.md (Baseline vs Corrupted vs Repaired)
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref `/works` hoặc snapshot | Retry 4 lần (429/5xx, tôn trọng `Retry-After`), parse DOI/title/abstract/author/subject/date, bỏ record thiếu trường bắt buộc | `data/raw/crossref_response.json`, `crossref_records.json` | Nguyễn Thu Hằng |
| Cleaning          | `list[PaperRecord]`, `run_date` | Strip markup, DOI lowercase, loại dòng thiếu title/summary/ngày, dedup giữ bản `updated` mới nhất, `age_days`, `text_for_embedding` | `data/clean/papers_clean.{csv,json}` | Đậu Văn Thạch |
| Embedding/index   | Clean dataframe | `all-MiniLM-L6-v2` (normalize), Chroma cosine, 1 collection/trạng thái | `data/chroma/`, `data/embeddings/*.json` | Lê Thanh Tùng |
| Evaluation        | Clean dataframe, index | 10 câu cố định, hit rate, token F1, LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Đậu Văn Thạch |
| Observability     | Dataframe bất kỳ | GX 1.x ephemeral + reconciliation với raw + Freshness SLA | `data/quality/*.json` | Đinh Quốc Bảo |
| Corruption/repair | Clean dataframe / raw records | 6 lỗi có seed; repair = rebuild từ raw | `corruption_log.json`, `papers_clean_{corrupted,repaired}.*` | Lê Thanh Tùng |
| Orchestration     | Settings        | Thứ tự chạy, gate chặn, auto-repair | Reports + metrics | Lê Thanh Tùng |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `gemini`            |
| `LLM_MODEL`                | `gemini-3.5-flash-lite` |
| `LLM_REQUESTS_PER_MINUTE`  | `10` (throttle client-side cho free tier) |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (offline snapshot) |
| Retrieval `top_k`           | 4                   |
| Freshness threshold          | `age_days > 180`, cảnh báo khi tỉ lệ stale > 25% |
| Random seed                  | 42 (corruption)     |

Không có API key trong repo; `.env` nằm trong `.gitignore`. Không có key vẫn chạy được: judge tự rơi về heuristic và `judge_backend` ghi rõ điều đó; hoặc đặt `LLM_PROVIDER=mock`.

### Lệnh cài đặt và chạy

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # hoặc: source .venv/bin/activate
python -m pip install -e ".[dev]"
python script/run_phase1.py
python script/run_corruption_flow.py
python script/run_tests.py          # 31 test, coverage >= 80%
```

Trên Windows nên đặt `PYTHONUTF8=1` nếu console không in được tiếng Việt.

### Kết quả tái hiện

| Lệnh             | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| ----------------- | ---------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công (exit 0) | 2026-09-25 08:54 UTC | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow   | Thành công (exit 0) | 2026-09-25 08:56 UTC | `data/reports/corruption_report.md`, `data/results/{corrupted,repaired}_metrics.json` |
| Test suite        | 31 passed, coverage 97.13% | 2026-09-25 | `python script/run_tests.py` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API `https://api.crossref.org/works` (lần chạy nộp bài dùng offline snapshot) |
| Query/filter                | `query=agentic retrieval augmented generation large language model`, `filter=from-pub-date:<today-180d>,has-abstract:true`, `rows=24` |
| Thời điểm lấy dữ liệu | Snapshot có sẵn trong repo; sha256 response `d968be684bff7d7f…` |
| Số record nhận được    | 24 item → 24 `PaperRecord` |
| Cơ chế retry/backoff      | 4 lần; 429/500/502/503/504 được retry; ưu tiên header `Retry-After` (tối đa 30 s), nếu không có thì backoff 2/4/8 s; thất bại → fallback snapshot, không có snapshot → raise |

Parser tái tạo `crossref_records.json` giống hệt file gốc 24/24 record (có test `test_parse_snapshot_reproduces_committed_records`).

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id`      | str (DOI, lowercase) | Có | Định danh ổn định | Thiếu DOI → bỏ record |
| `title`         | str | Có | Tiêu đề | Thiếu → bỏ; strip markup |
| `summary`       | str | Có | Abstract đã bỏ `<jats:*>` | Thiếu/rỗng → bỏ |
| `authors`       | list[str] | Không | `given family` hoặc `name` | Rỗng → `[]` |
| `categories`    | list[str] | Không | `subject` | Fallback `type` → `Uncategorized` |
| `published`     | str `YYYY-MM-DD` | Có | Ngày xuất bản | Thứ tự `published → published-print → published-online → issued → created`; thiếu tháng/ngày → 01; không parse được → bỏ |
| `updated`       | str `YYYY-MM-DD` | Không | Dùng để chọn bản khi trùng | Fallback `published` |
| `age_days`      | int | Có (derived) | `run_date − published` (ngày UTC) | — |
| `authors_joined`, `categories_joined`, `summary_chars` | str/int | derived | Metadata cho Chroma/QA | — |
| `text_for_embedding` | str | derived | 5 dòng Title/Authors/Published/Categories/Summary | — |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension | Số record bị tác động | Cách xác minh |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Bỏ thẻ JATS/HTML, unescape, gộp khoảng trắng | Validity | 24 (mọi abstract có `<jats:p>`) | `test_parse_handles_markup_missing_fields_and_fallbacks` |
| Loại record thiếu DOI/title/abstract/ngày | Completeness | 0 trên snapshot | `dropped_by_cleaning = 0` trong phase1 report |
| Dedup theo `paper_id`, giữ `updated` mới nhất | Uniqueness | 0 trên snapshot | `test_clean_dedup_normalize_and_filter` |
| Chuẩn hóa ngày `YYYY-MM-DD` + `age_days` | Validity/Timeliness | 24 | GX `expect_column_values_to_match_regex(published)` |

`text_for_embedding` ghép 5 phần theo đúng thứ tự trong Guide để truy vấn theo tiêu đề, tác giả, ngày hay chuyên ngành đều có tín hiệu trong vector. `paper_id` là DOI lowercase vì DOI không phân biệt hoa thường. `age_days` tính theo ngày UTC tại thời điểm chạy.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10                            |
| Các `question_type`                    | summary (3), authors (3), date (2), categories (2) |
| Ground-truth document ID                 | DOI của bài được chọn ở vị trí cách đều nhau trong danh sách sắp theo ngày mới → cũ |
| Embedding model                          | `all-MiniLM-L6-v2`            |
| Vector store/collection                  | ChromaDB persistent, cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired` |
| Retrieval `top_k`                       | 4                             |
| LLM provider/model                       | Gemini `gemini-3.5-flash-lite` (judge + agent demo), `judge_backend = llm` cho cả 3 trạng thái |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sha256 `3541bfb96efb6757…`) |

Test set được sinh một lần từ dữ liệu sạch và phase 1 chỉ dựng lại khi `REFRESH_TEST_SET=1` hoặc khi file tham chiếu DOI không còn tồn tại. Như vậy mọi thay đổi về chỉ số giữa baseline, corrupted và repaired đều đến từ dữ liệu, không đến từ đề thi. Nếu sinh test set từ dữ liệu bẩn thì ground truth cũng bẩn theo, và sự suy giảm sẽ bị che mất.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | 24 record |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/`   | Có | 3 collection; manifest lưu đường dẫn tương đối |
| Evaluation set           | `data/eval/`                         | Có | 10 câu |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | kèm `baseline_answers.json` |
| Quality/freshness        | `data/quality/`                      | Có | baseline/corrupted/repaired + freshness |
| Baseline report          | `data/reports/phase1_report.md`      | Có | có thêm agent demo |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` | 1.0000 | 10/10 câu có DOI đúng trong top-4 (tra cứu chính xác theo tiêu đề đặt tài liệu đúng lên đầu) |
| `mean_token_f1`      | 1.0000 | Bộ trả lời rule-based trích đúng trường metadata nên khớp tuyệt đối với ground truth |
| `judge_accuracy`     | 1.0000 | Gemini chấm 10/10 đúng |
| `mean_judge_score`   | 5 | Toàn bộ điểm 5/5 |
| Ragas                | N/A | Không bật (`RUN_RAGAS=1` để chạy); free tier Gemini không đủ quota |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Volume | 5–5000 | PASS (24) | `baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 5 | Completeness | `paper_id`, `title`, `summary`, `published`, `text_for_embedding` | PASS | như trên |
| `ExpectColumnValuesToBeUnique(paper_id)` | Uniqueness | 0 trùng | PASS | như trên |
| `ExpectColumnValueLengthsToBeBetween(summary)` | Completeness | ≥ 30 ký tự | PASS | như trên |
| `ExpectColumnValueLengthsToBeBetween(title)` | Validity | ≥ 8 ký tự | PASS | như trên |
| `ExpectColumnValuesToNotMatchRegex(summary)` | Validity (nhiễu/mojibake) | không khớp `[#@!%&*~^$<>?]{2,}\|�\|Ã` | PASS | như trên |
| `ExpectColumnValuesToMatchRegex(published)` | Validity | `^\d{4}-\d{2}-\d{2}$` | PASS | như trên |
| `source_reconciliation` (custom) | Completeness so với nguồn | coverage ≥ 0.95 so với raw | PASS (1.0) | như trên |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | Clean dataset (`age_days`) trước khi index |
| Timestamp mới nhất       | `latest_published = 2026-07-22` (65 ngày) |
| Ngưỡng freshness         | `age_days > 180` là stale; SLA vi phạm khi stale ratio > 25% |
| Trạng thái baseline      | Fresh |
| Lý do                     | 1/24 bài (2026-03-28, 181 ngày) stale → 4.17% ≤ 25% |

Freshness là tín hiệu cảnh báo tách khỏi quality gate. Snapshot cố định sẽ tự già đi: từ khoảng 2026-11-29 trở đi, 7/24 bài vượt 180 ngày và baseline sẽ bị cảnh báo `is_fresh=False`, trong khi gate vẫn PASS. Việc cần làm lúc đó là refresh nguồn, không phải sửa dữ liệu.

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| `drop_latest_records` | Bỏ 20% bài mới nhất | 5 | `source_reconciliation` FAIL (coverage 0.7917) | eval_001/002 mất hit; eval_002 trả tác giả của bài khác (F1 0) | Rebuild từ raw |
| `blank_summary` | `summary = ""` | 3 | Độ dài summary < 30 | eval_008 (categories) không bị ảnh hưởng | Rebuild từ raw |
| `inject_noise` | Chèn token rác trước mỗi 3 từ | 3 | Regex nhiễu FAIL | eval_005/009 F1 còn 0.8889 | Rebuild từ raw |
| `truncate_title` | Cắt tiêu đề còn 6 ký tự | 3 | Độ dài title < 8 | Không trúng bài nào trong test set | Rebuild từ raw |
| `stale_date` | Lùi `published` 365 ngày | 6 | Freshness SLA FAIL (7/22 = 31.8%) | eval_007 trả `2025-06-03` (F1 0) | Rebuild từ raw |
| `duplicate_rows` | Nhân bản 3 dòng | 3 | Unique `paper_id` FAIL | Không đổi đáp án, làm loãng top-k | Rebuild từ raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: log đủ 6 loại, mỗi loại có `description`, `params`, `affected_count`, danh sách `affected_paper_ids` (truncate có thêm ví dụ trước/sau), cùng seed và số dòng vào/ra (24 → 22).

Repair không vá bản bị hỏng. Hàm `repair_from_raw` dựng lại dataset từ `data/raw/crossref_records.json` bằng chính hàm cleaning của baseline, nên kết quả chỉ phụ thuộc vào nguồn thô đã được bảo toàn (sha256 `87b6413046082aa8…`). Bằng chứng: fingerprint nội dung (bỏ qua `age_days`) của bản repair trùng baseline, hai lần repair liên tiếp giống hệt nhau, và bản repair phải PASS gate trước khi được index vào `papers-repaired`. Repair được **tự động kích hoạt** khi gate hoặc freshness báo lỗi, và lý do kích hoạt được ghi vào report.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | 2 câu hỏi về bài bị drop |
| `mean_token_f1`        | 1.0000 | 0.7519 | 1.0000 | −0.2481 | 100% | Giảm do drop, stale date, noise |
| `judge_accuracy`       | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | Gemini đánh sai 2 câu |
| `mean_judge_score`     | 5.0 | 4.2 | 5.0 | −0.8 | 100% | |
| Quality checks pass/fail | PASS (0 fail) | FAIL (5 fail) | PASS (0 fail) | +5 check fail | 100% | unique, title len, summary len, regex, reconciliation |
| Freshness status         | Fresh (4.2%) | Stale (31.8%) | Fresh (4.2%) | +27.7 điểm % | 100% | |

Kết luận nhân quả:

1. `drop_latest_records` → `source_reconciliation` FAIL (thiếu 5/24 DOI) → câu eval_002 (hỏi tác giả của bài mới nhất bị mất) vẫn được agent trả lời tự tin là "Anh Tran, Quoc Pham" (tác giả của bài khác), hit = FAIL, F1 = 0. Tương tự, `stale_date` → freshness 31.8% > 25% → eval_007 trả ngày `2025-06-03` thay vì `2026-06-03`. Đây là silent failure: không có exception, chỉ có câu trả lời sai.
2. Repair từ raw → cả 13 check trở lại PASS, freshness 4.2% → cả 4 chỉ số agent quay về đúng giá trị baseline (100% recovery), với cùng test set.

Hai kịch bản không làm giảm chỉ số: `truncate_title` (không trúng bài nào trong test set) và `blank_summary` (chỉ trúng một câu hỏi về categories). Chúng vẫn bị gate bắt. Điều này cho thấy gate có giá trị ngay cả khi benchmark không đủ rộng để nhìn thấy lỗi.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Lần chạy đầu với `.env` mặc định, phase 1 báo `judge_accuracy = 1.0` nhưng `judge_backend = heuristic_fallback`. Mọi lời gọi LLM đều lỗi mà pipeline vẫn exit 0: chính bước đánh giá cũng bị silent failure.
- **Nguyên nhân:** (1) `gemini-2.5-flash` trả `404 NOT_FOUND` ("no longer available to new users"); (2) sau khi đổi sang `gemini-3.8-flash`, free tier chỉ cho 5 request/phút và 20 request/ngày, nên các câu sau nhận `429 RESOURCE_EXHAUSTED`. Judge nuốt exception và dùng heuristic.
- **Cách xử lý:** Thêm `judge_backend` (`llm` / `heuristic_fallback` / `mixed (k/n heuristic)`) vào metrics và ghi loại lỗi vào `reasoning`. Thêm rate limiter dùng chung (`LLM_REQUESTS_PER_MINUTE`) và `max_retries=6` cho Gemini. Đổi sang `gemini-3.5-flash-lite` (quota riêng, đủ cho ~40 lời gọi/lần chạy). Chuẩn hóa `content` dạng list-of-blocks của Gemini 3 trong `run_agent_question`.
- **Cách xác minh:** `grep judge_backend data/results/*_metrics.json` → cả 3 file là `"llm"`; `data/results/agent_demo_answers.json` có câu trả lời thật, không có lỗi.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| QA rule-based trích metadata của top-1 | Baseline F1 = 1.0 là "trần", không đo được chất lượng sinh câu trả lời | Dùng LLM sinh câu trả lời từ context; so F1/judge giữa rule-based và LLM |
| Test set 10 câu, 10/24 bài | `truncate_title` không trúng câu nào → không thấy tác động lên metric | Tăng lên 1 câu/bài (24+) và thêm câu hỏi không có tiêu đề để ép semantic search |
| Snapshot có cặp bài gần trùng | Semantic search đơn thuần xếp nhầm bài "Advanced Perspectives on X" | Hybrid BM25 + dense, hoặc rerank; đo hit@1 thay vì hit@4 |
| Reconciliation dựa vào raw | Nếu raw cũng mất bài mới thì drop không bị phát hiện | Theo dõi xu hướng volume/`latest_published` theo lịch sử các lần chạy |
| Freshness phụ thuộc ngày chạy | Snapshot cố định sẽ tự thành stale (~2026-11-29) | Refresh định kỳ bằng `REFRESH_SOURCE=1`, cảnh báo theo `latest_age_days` |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
