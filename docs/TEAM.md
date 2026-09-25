# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `Clone`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** [`tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline`](https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline)

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Lê Thanh Tùng | 2A202602499 | [email] | Trưởng nhóm / Corruption & Integration (`corruption.py`, `phase1.py`, `corruption_flow.py`, `llm.py`, `tests/`, CI) | [`report/2A202602499_LeThanhTung.md`](../report/2A202602499_LeThanhTung.md) |
| 2 | Nguyễn Thu Hằng | 2A202602463 | [email] | Source owner (`crossref.py`, raw data, fallback snapshot) | [`report/2A202602463_NguyenThuHang.md`](../report/2A202602463_NguyenThuHang.md) |
| 3 | Đậu Văn Thạch | 2A202602592 | [email] | Data model & Evaluation set (`cleaning.py`, `testset.py`) | [`report/2A202602592_DauVanThach.md`](../report/2A202602592_DauVanThach.md) |
| 4 | Đinh Quốc Bảo | 2A202602933 | [email] | Observability (`quality.py` GX 1.x + Freshness SLA, `reporting.py`) | [`report/2A202602933_DinhQuocBao.md`](../report/2A202602933_DinhQuocBao.md) |

### Phân công theo Checkpoint

| Checkpoint | Owner chính | Hỗ trợ | Deliverable |
|---|---|---|---|
| CP0 — Môi trường & Raw ingestion | Nguyễn Thu Hằng | Lê Thanh Tùng | `.venv`, `.env`, `data/raw/*.json` |
| CP1 — Cleaning & Quality Gate GX 1.x | Đậu Văn Thạch, Đinh Quốc Bảo | — | `papers_clean.*`, `baseline_quality_report.json` |
| CP2 — Test set & ChromaDB index | Đậu Văn Thạch | Lê Thanh Tùng | `test_set.json`, collection `papers-baseline` |
| CP3 — Baseline end-to-end | Lê Thanh Tùng | Đinh Quốc Bảo | `baseline_metrics.json`, `phase1_report.md` |
| CP4 — Corruption & đo suy giảm | Lê Thanh Tùng | Đinh Quốc Bảo | `corruption_log.json`, `corrupted_metrics.json` |
| CP5 — Repair & báo cáo 3 trạng thái | Lê Thanh Tùng | Nguyễn Thu Hằng, Đậu Văn Thạch | `repaired_metrics.json`, `corruption_report.md` |
| CP6 — Live demo & nộp bài | Cả nhóm | — | Demo, commit `main`, nộp link LMS |

---

## # Cá nhân

### ## LeThanhTung-2A202602499
- **Vai trò:** Trưởng nhóm, Corruption & Pipeline Integration.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/corruption.py`: 6 kịch bản lỗi có seed 42 (drop 20% bài mới nhất, blank summary, inject noise, truncate title, stale date −365 ngày, duplicate rows) và log từng DOI bị tác động vào `corruption_log.json`.
  - `src/pipelines/phase1.py`: ingest → clean → quality gate (FAIL thì dừng, không index) → index → test set cố định → evaluate → agent demo → report.
  - `src/pipelines/corruption_flow.py`: corrupt → gate cảnh báo → index collection riêng để đo silent failure → tự động repair từ raw (chạy 2 lần, so fingerprint) → gate lại → evaluate → báo cáo 3 trạng thái.
  - Tích hợp LLM: rate limiter dùng chung (`LLM_REQUESTS_PER_MINUTE`), trường `judge_backend` để phát hiện judge rơi về heuristic, chuẩn hóa content block của Gemini 3.
  - Bộ test Pytest (31 test, coverage 97%), `script/run_tests.py`, GitHub Actions.
- **Điều học được / Đóng góp chính:**
  - Chính bước đánh giá cũng có thể silent-fail: judge Gemini lỗi 404/429 mà pipeline vẫn exit 0. Vì vậy mọi fallback đều phải để lại dấu vết trong artifact.

### ## NguyenThuHang-2A202602463
- **Vai trò:** Source owner — Ingestion & Raw Preservation.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/crossref.py`: `parse_crossref_payload` (bỏ thẻ `<jats:p>`, fallback ngày `published → published-print → published-online → issued → created`, tác giả `given family`/`name`, `subject → type → Uncategorized`, link PDF), bỏ record thiếu DOI/title/abstract/ngày.
  - `fetch_source_records`: chế độ offline snapshot mặc định; `REFRESH_SOURCE=1` gọi Crossref với retry 4 lần cho 429/5xx (tôn trọng `Retry-After`, backoff 2/4/8 s), lỗi thì fallback snapshot.
  - `load_raw_records` chịu được trường thiếu; xác minh parser tái tạo `crossref_records.json` giống hệt 24/24 record.
- **Điều học được / Đóng góp chính:**
  - Raw snapshot là "nguồn sự thật" cho repair: nếu parser không tái lập được đúng file raw thì mọi so sánh phía sau đều mất ý nghĩa.

### ## DauVanThach-2A202602592
- **Vai trò:** Data model & Evaluation-set owner.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/cleaning.py`: chuẩn hóa text, DOI lowercase làm `paper_id`, loại dòng thiếu title/summary/ngày, dedup giữ bản `updated` mới nhất, `age_days` theo ngày UTC, `text_for_embedding` 5 phần; tách `add_derived_columns` để corruption tái sử dụng.
  - `src/evaluation/testset.py`: 10 câu hỏi cố định, chọn bài cách đều theo thời gian, xoay vòng 4 dạng `summary/authors/date/categories`, câu hỏi khớp pattern của `qa._extract_answer`, bỏ tiêu đề chứa dấu `'`.
- **Điều học được / Đóng góp chính:**
  - Test set phải sinh từ dữ liệu sạch và giữ cố định cho cả 3 trạng thái; sinh lại từ dữ liệu bẩn sẽ che mất sự suy giảm.

### ## DinhQuocBao-2A202602933
- **Vai trò:** Observability owner — Quality Gate & Reporting.
- **Công việc chi tiết đã hoàn thành:**
  - `src/observability/quality.py`: GX 1.x ephemeral context (`get_context(mode="ephemeral")`, `data_sources.add_pandas`, batch definition whole dataframe), 11 expectation (row count, not-null × 5, unique `paper_id`, độ dài summary ≥ 30 và title ≥ 8, regex chống nhiễu, định dạng ngày) và check `source_reconciliation` đối chiếu với raw.
  - Freshness SLA: `is_fresh=False` khi > 25% bài có `age_days > 180`, kèm phân bố tuổi và nội dung cảnh báo.
  - `src/observability/reporting.py`: `phase1_report.md` và `corruption_report.md` (bảng 3 trạng thái, ma trận check, bảng "lỗi → detector", root cause theo từng câu hỏi).
- **Điều học được / Đóng góp chính:**
  - Mỗi loại corruption cần một detector riêng; row-count 5–5000 không bắt được việc mất 20% bài mới, phải đối chiếu với nguồn.
