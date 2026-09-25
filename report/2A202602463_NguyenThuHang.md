# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Thu Hằng           |
| MSSV               | 2A202602463                |
| Khóa/Lớp         | K4 — L3                    |
| Tên nhóm         | Clone                 |
| Vai trò chính    | Source owner — Ingestion & Raw Preservation |
| Repository         | https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Parse Crossref | `src/ingestion/crossref.py::parse_crossref_payload`, `strip_markup` | JSON `/works` | `list[PaperRecord]` | Hoàn thành |
| Fetch + retry + fallback | `fetch_source_records`, `_request_crossref` | `Settings` (query, filter, rows) | `data/raw/crossref_response.json`, `crossref_records.json` | Hoàn thành (live mode kiểm thử bằng mock) |
| Load raw | `load_raw_records` | `crossref_records.json` | `list[PaperRecord]` cho cleaning và repair | Hoàn thành |
| Môi trường CP0 | `.venv`, `.env.example` | `pyproject.toml` | Smoke test `Môi trường sẵn sàng` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Cung cấp nguồn cho repair | Lê Thanh Tùng — `repair_from_raw` | Repair đọc lại `crossref_records.json` qua `load_raw_records` |
| Thống nhất raw schema | Đậu Văn Thạch — `cleaning.py` | Cleaning nhận `PaperRecord` 11 trường, ngày dạng `YYYY-MM-DD` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Parse 24 item snapshot | `crossref.py`, `data/raw/crossref_records.json` | 24 record, giống hệt file gốc | `test_parse_snapshot_reproduces_committed_records`; `git diff data/raw` rỗng sau khi chạy |
| Retry 429/5xx rồi lưu raw | `_request_crossref` | 3 lần gọi (429 → 503 → 200) | `test_fetch_live_retries_on_429_then_saves_raw` |
| Fallback khi mất mạng | `fetch_source_records` | Vẫn trả 24 record từ snapshot | `test_fetch_live_falls_back_to_snapshot_when_offline` |
| Checkpoint CP0 | lệnh trong `docs/CHECKPOINTS.md` | `Tín hiệu hoàn thành: Đã tải 24 bài báo` | chạy lệnh CP0 |

Output cụ thể: `data/raw/crossref_records.json` (24 record, sha256 `87b6413046082aa8…`) là nguồn duy nhất mà bước repair dùng để khôi phục dữ liệu.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Lấy metadata bài báo từ Crossref một cách bền vững (API có thể trả 429 hoặc mất mạng) và bảo toàn nguyên bản dữ liệu gốc để mọi bước sau có thể tái lập.

### Cách triển khai

- **Parse:** duyệt `message.items`. DOI → `paper_id`. `title[0]` và `abstract` được bỏ thẻ `<jats:p>`, unescape HTML entity và gộp khoảng trắng. Tác giả lấy `given + family`, hoặc `name` với tác giả là tổ chức. Chuyên ngành lấy từ `subject`, nếu không có thì dùng `type`, cuối cùng là `Uncategorized`. Ngày xuất bản thử lần lượt `published → published-print → published-online → issued → created`, thiếu tháng/ngày thì gán 01. Link PDF lấy từ `link[content-type=pdf]`, không có thì dùng DOI URL.
- **Loại record không dùng được:** thiếu DOI, tiêu đề, abstract hoặc ngày xuất bản thì bỏ, vì agent không thể trả lời về bài đó.
- **Fetch:** mặc định dùng offline snapshot (khuyến nghị khi làm bài). Với `REFRESH_SOURCE=1` thì gọi `/works` với `query`, `filter=from-pub-date:<today-180>,has-abstract:true`, `rows=24`. Có tối đa 4 lần thử cho 429/500/502/503/504, ưu tiên header `Retry-After` (tối đa 30 s), nếu không có thì backoff 2/4/8 s. Thất bại thì fallback về snapshot; không có snapshot thì raise.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | Crossref `/works` JSON hoặc `data/raw/crossref_response.json` |
| Output | `crossref_response.json` (nguyên văn API), `crossref_records.json` (11 trường `PaperRecord`) |
| Module phụ thuộc | `core.config` (query/filter/paths), `core.utils` |
| Module sử dụng output | `ingestion.cleaning`, `observability.quality` (reconciliation), `pipelines.corruption_flow` (repair) |
| Điều kiện lỗi cần xử lý | 429/5xx, timeout/ConnectionError, HTTP 4xx khác (không retry), item thiếu trường |

### Cách xác minh

```bash
python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); r=fetch_source_records(s); print(f'Tín hiệu hoàn thành: Đã tải {len(r)} bài báo')"
python -m pytest tests/test_ingestion.py -q
```

- **Kết quả mong đợi:** 24 bài báo; test ingestion pass.
- **Kết quả thực tế:** `Tín hiệu hoàn thành: Đã tải 24 bài báo`; 7/7 test ingestion pass.
- **Artifact/log:** `data/raw/crossref_response.json`, `data/raw/crossref_records.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Ở chế độ offline, `fetch_source_records` ghi lại `crossref_records.json`, tức là có nguy cơ ghi đè bản raw đã commit.
- **Các phương án đã cân nhắc:** (a) Không ghi records ở chế độ offline. (b) Luôn ghi lại, nhưng đảm bảo parser tái tạo byte-for-byte bản gốc.
- **Phương án đã chọn:** (b).
- **Lý do:** Giữ một đường code duy nhất cho cả live và offline. Records luôn được suy ra từ response, nên chỉ có một nguồn sự thật (`crossref_response.json`). Nếu parser thay đổi hành vi, test sẽ phát hiện ngay.
- **Bằng chứng:** sau khi chạy pipeline, `git diff data/raw` không có thay đổi; test so sánh 24/24 record pass.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `UnicodeEncodeError: 'charmap' codec can't encode characters in position 6-7` khi chạy lệnh smoke test in chuỗi `Môi trường sẵn sàng` trên Windows.
- **Lệnh tái hiện:** `python -c "import chromadb, great_expectations, sentence_transformers; print('Môi trường sẵn sàng')"` trong console Windows mặc định (cp1252).
- **Nguyên nhân gốc:** stdout của Python dùng codepage cp1252 của console, không mã hóa được ký tự tiếng Việt. Các thư viện đã import thành công.
- **Cách xử lý:** đặt `PYTHONUTF8=1` (hoặc `PYTHONIOENCODING=utf-8`) trước khi chạy; ghi chú vào báo cáo nhóm.
- **Cách xác minh sau khi sửa:** lệnh in ra `Môi trường sẵn sàng`.
- **Điều học được:** tách "lỗi môi trường hiển thị" khỏi "lỗi thiếu thư viện" bằng cách đọc kỹ traceback: lỗi nằm ở `print`, không nằm ở `import`.

## 7. Hiểu biết về luồng end-to-end

1. Response Crossref được lưu nguyên văn, sau đó parse ra records, clean thành 24 dòng có `text_for_embedding`, qua quality gate, rồi được embed bằng MiniLM và nạp vào ChromaDB.
2. Mỗi câu hỏi có DOI đúng (`ground_truth_doc_ids`). Retrieval "hit" khi DOI đó nằm trong top-4; câu trả lời được so với `ground_truth` bằng token F1 và LLM judge.
3. Quality checks kiểm tra hình dạng dữ liệu (null, trùng, độ dài, định dạng, đối chiếu nguồn). Freshness kiểm tra độ cũ của toàn tập theo ngày chạy.
4. Giữ nguyên test set để chênh lệch chỉ phản ánh dữ liệu.
5. Repair thành công khi dữ liệu dựng lại từ raw trùng fingerprint baseline, gate PASS và 4 metric trở lại bằng baseline. Phần của tôi quyết định điều kiện đầu tiên: raw phải còn nguyên vẹn.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ------------- | -------: | --------: | -------: | -------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | 2 câu mất hit đều hỏi về bài mới nhất đã bị drop |
| `mean_token_f1` | 1.0000 | 0.7519 | 1.0000 | |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | |
| `mean_judge_score` | 5.0 | 4.2 | 5.0 | |
| Quality checks | PASS | FAIL | PASS | `source_reconciliation` coverage 0.7917 phát hiện 5 DOI bị mất |
| Freshness status | Fresh | Stale | Fresh | `latest_published` lùi từ 2026-07-22 về 2026-06-12 |

### Kết luận từ số liệu

1. Mất 5 bài mới nhất → reconciliation với raw chỉ còn 19/24 DOI (coverage 0.7917) → eval_001 và eval_002 mất hit; eval_002 trả tác giả của bài khác.
2. Repair đọc lại `crossref_records.json` → coverage 1.0 → hit rate 1.0.

Ảnh hưởng rõ nhất (theo góc nhìn nguồn dữ liệu) là `drop_latest_records`: đây là kịch bản "ingestion fail" và chỉ phát hiện được khi có bản raw để đối chiếu.

Khác kỳ vọng: freshness vẫn là "Fresh" ở baseline dù có 1 bài đã 181 ngày, vì SLA dùng ngưỡng tỉ lệ 25% chứ không phải "không bài nào quá hạn".

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Lưu raw nguyên văn trước mọi biến đổi; đó là "bảo hiểm" cho repair.
2. Retry phải phân biệt lỗi tạm thời (429/5xx) với lỗi vĩnh viễn (4xx khác), và phải có đường lui offline.
3. Mất dữ liệu ở đầu nguồn khiến agent trả lời sai mà không báo lỗi.

### Nếu có thêm thời gian

Ghi thêm manifest cho mỗi lần fetch (thời điểm, số item, `total-results`, sha256) để theo dõi volume theo thời gian. Khi đó phát hiện được cả trường hợp raw mới cũng thiếu bài, điều mà reconciliation hiện tại không thấy.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Thu Hằng
**Ngày xác nhận:** 2026-09-25
