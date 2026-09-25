# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Lê Thanh Tùng             |
| MSSV               | 2A202602499                |
| Khóa/Lớp         | K4 — L3                    |
| Tên nhóm         | Clone                 |
| Vai trò chính    | Nhóm trưởng — Corruption & integration owner |
| Repository         | https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Corruption suite | `src/ingestion/corruption.py::corrupt_clean_dataframe` | Clean dataframe | Corrupted dataframe, `data/results/corruption_log.json` | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py::main` | Settings, raw snapshot | Toàn bộ artifact pha 1 | Hoàn thành |
| Corruption/repair flow | `src/pipelines/corruption_flow.py::main`, `repair_from_raw` | Artifact pha 1, raw records | `corrupted_*`, `repaired_*`, `corruption_report.md` | Hoàn thành |
| LLM integration | `src/retrieval/llm.py`, `src/retrieval/agent.py`, `judge_backend` trong `metrics.py` | `.env` | Judge/agent chạy ổn định trên free tier | Hoàn thành |
| Test & CI | `tests/`, `script/run_tests.py`, `.github/workflows/ci.yml` | Toàn bộ `src/` | 31 test, coverage 97% | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Review contract clean schema (`CLEAN_COLUMNS`, `add_derived_columns`) | Đậu Văn Thạch — `cleaning.py` | Corruption tái sử dụng được hàm dựng `text_for_embedding` |
| Gắn quality report vào flow và report 3 trạng thái | Đinh Quốc Bảo — `quality.py`, `reporting.py` | Report có bảng "lỗi → detector" dùng đúng tên check của GX |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Tiêm 6 lỗi có seed, log DOI bị tác động | `corruption.py`, `corruption_log.json` | 24 → 22 dòng, 6 loại lỗi | `test_corruption_applies_six_logged_scenarios` |
| Gate chặn dữ liệu xấu ở pha 1 | `phase1.py` | FAIL thì `SystemExit`, không index | `test_phase1_rebuilds_stale_test_set_and_blocks_bad_data` |
| Auto-repair idempotent từ raw | `corruption_flow.py::repair_from_raw` | Fingerprint repair = baseline, 2 lần repair giống nhau | Mục 6 của `data/reports/corruption_report.md` |
| So sánh 3 trạng thái | `corruption_flow.py`, `*_metrics.json` | Bảng in ra console + report | `python script/run_corruption_flow.py` |

Output cụ thể: bảng console cuối `run_corruption_flow.py` cho thấy `retrieval_hit_rate` 1.0 → 0.8 → 1.0 và `mean_token_f1` 1.0 → 0.7519 → 1.0, gate PASS → FAIL → PASS.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần chứng minh bằng số liệu rằng dữ liệu bẩn làm agent trả lời sai mà không báo lỗi, rằng observability bắt được lỗi, và rằng repair đưa hệ thống về đúng trạng thái sạch một cách lặp lại được.

### Cách triển khai

- **Corruption có kiểm soát:** `random.Random(42)`. Trước tiên bỏ 20% bài mới nhất, sau đó xáo vị trí còn lại và chia **các lát rời nhau** cho blank summary (3), noise (3), truncate title (3) và stale date (30%, tức 6 dòng). Nhờ vậy mỗi thay đổi metric quy được về đúng một loại lỗi. Cuối cùng nhân bản 3 dòng rồi gọi `add_derived_columns` để lỗi đi vào `text_for_embedding`.
- **Cô lập trạng thái:** mỗi trạng thái có collection riêng (`papers-baseline/-corrupted/-repaired`), nên corrupted không ghi đè baseline.
- **Repair:** không vá bản bẩn mà dựng lại từ `data/raw/crossref_records.json` bằng chính `build_clean_dataframe`. Chạy 2 lần và so `dataframe_fingerprint` (sha256 trên các cột nội dung, bỏ `age_days` vì phụ thuộc ngày chạy). Bản repair phải PASS gate mới được index.
- **Tự động kích hoạt:** repair chạy khi gate hoặc freshness báo lỗi; danh sách cảnh báo được ghi vào trường `trigger` trong report.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `data/clean/papers_clean.json`, `data/eval/test_set.json`, `baseline_metrics.json`, `baseline_answers.json`, `data/raw/crossref_records.json` |
| Output | `papers_clean_{corrupted,repaired}.*`, `{corrupted,repaired}_{metrics,answers}.json`, `corruption_log.json`, `corruption_report.md` |
| Module phụ thuộc | `ingestion.cleaning`, `observability.quality`, `retrieval.index`, `evaluation.metrics` |
| Module sử dụng output | `observability.reporting`, demo CP6 |
| Điều kiện lỗi cần xử lý | Thiếu artifact pha 1 → `SystemExit` hướng dẫn chạy pha 1; repair không qua gate → dừng |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python script/run_tests.py
```

- **Kết quả mong đợi:** exit 0; corrupted thấp hơn baseline; repaired bằng baseline; coverage ≥ 80%.
- **Kết quả thực tế:** exit 0 cả hai; 1.0 / 0.8 / 1.0 (hit rate); 31 passed, coverage 97.13%.
- **Artifact/log:** `data/reports/corruption_report.md`, `data/results/*.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Đề yêu cầu vừa chặn dữ liệu xấu trước vector store, vừa đo được agent suy giảm trên dữ liệu xấu.
- **Các phương án đã cân nhắc:** (a) Index dữ liệu bẩn vào collection chính rồi sửa sau. (b) Gate chặn cứng, không bao giờ index dữ liệu bẩn, nên không đo được suy giảm. (c) Gate chặn cứng ở pha 1 (serving), còn ở pha 2 index dữ liệu bẩn vào collection cô lập chỉ để đo.
- **Phương án đã chọn:** (c).
- **Lý do:** collection serving không bao giờ nhận dữ liệu bẩn, nhưng vẫn có bằng chứng định lượng cho silent failure. Đổi lại phải thêm một collection, chi phí rất nhỏ.
- **Bằng chứng:** `papers-baseline` vẫn 24 vector sạch; `papers-corrupted` cho hit rate 0.8.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Pha 1 exit 0 nhưng `judge_backend = heuristic_fallback`; `agent_demo_answers.json` ghi `GoogleModelNotFoundError: ... 'gemini-2.5-flash' (NOT_FOUND) ... no longer available to new users`. Sau khi đổi model thì gặp `429 RESOURCE_EXHAUSTED ... limit: 20, model: gemini-3.8-flash`.
- **Lệnh tái hiện:** `python script/run_phase1.py` với `LLM_MODEL=gemini-2.5-flash`.
- **Nguyên nhân gốc:** `_judge_answer` bắt mọi exception và âm thầm dùng heuristic; model mặc định đã ngừng cấp; free tier của `gemini-3.8-flash` chỉ có 5 RPM / 20 RPD, trong khi một lần chạy cần khoảng 40 lời gọi.
- **Cách xử lý:** thêm `judge_backend` vào metrics và ghi tên exception vào `reasoning`; thêm `InMemoryRateLimiter` dùng chung (`LLM_REQUESTS_PER_MINUTE`) cùng `max_retries=6`; đổi sang `gemini-3.5-flash-lite`; chuẩn hóa content dạng list của Gemini 3 trong `run_agent_question`.
- **Cách xác minh sau khi sửa:** `grep judge_backend data/results/*_metrics.json` cho ra `"llm"` ở cả 3 file; agent demo có câu trả lời thật.
- **Điều học được:** fallback mà không để lại dấu vết trong artifact thì chính nó là một silent failure.

## 7. Hiểu biết về luồng end-to-end

1. Crossref (hoặc snapshot) → `crossref_response.json` → parse → `crossref_records.json` → clean (`text_for_embedding`) → quality gate → MiniLM embedding → ChromaDB `papers-baseline`.
2. Mỗi câu hỏi có `ground_truth_doc_ids`: hit = DOI đúng nằm trong top-4; token F1 so câu trả lời với `ground_truth`; LLM judge chấm 1–5 và đúng/sai.
3. Quality checks kiểm tra tính hợp lệ của từng dòng/bảng (null, unique, độ dài, regex, đối chiếu nguồn). Freshness đo tỉ lệ dữ liệu cũ của cả tập, và là tín hiệu SLA thay đổi theo thời gian dù dữ liệu không đổi.
4. Cùng test set thì chênh lệch metric chỉ đến từ dữ liệu. Đổi test set thì không so sánh được.
5. Repair thành công khi: gate PASS, freshness PASS, fingerprint trùng baseline, 2 lần repair giống nhau, và 4 metric bằng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ------------- | -------: | --------: | -------: | -------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Chỉ drop latest làm mất hit; các lỗi khác vẫn tìm đúng tài liệu nhưng nội dung sai |
| `mean_token_f1` | 1.0000 | 0.7519 | 1.0000 | Metric nhạy nhất với lỗi nội dung |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | Judge chấm sai đúng 2 câu F1 = 0 |
| `mean_judge_score` | 5.0 | 4.2 | 5.0 | |
| Quality checks | PASS | FAIL (5) | PASS | |
| Freshness status | Fresh | Stale | Fresh | |

### Kết luận từ số liệu

1. Stale date (6 dòng) → freshness 31.8% > 25% → eval_007 trả `2025-06-03`, F1 = 0.
2. Repair từ raw → 13/13 check PASS → 4 metric về đúng baseline.

Corruption ảnh hưởng rõ nhất là `drop_latest_records`: nó làm mất hit và khiến agent trả tác giả của bài khác, trong khi row count vẫn nằm trong 5–5000.

Kết quả khác kỳ vọng: `truncate_title` không làm giảm metric nào. Kiểm tra `corruption_log.json` cho thấy 3 DOI bị cắt tiêu đề không nằm trong test set, nên đây là giới hạn độ phủ của benchmark, không phải lỗi vô hại.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline phải idempotent và có nguồn raw bất biến; repair là "dựng lại", không phải "vá".
2. Observability cần một detector cho mỗi failure mode, và bản thân các fallback cũng cần được quan sát.
3. Dữ liệu sai làm agent sai một cách tự tin; chỉ số chất lượng dữ liệu phải được kiểm tra trước chỉ số model.

### Nếu có thêm thời gian

Mở rộng test set lên mỗi bài 1 câu (24+) để mọi corruption đều trúng ít nhất một câu, rồi đo lại tác động riêng của `truncate_title` và `blank_summary`.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lê Thanh Tùng
**Ngày xác nhận:** [YYYY-MM-DD]
