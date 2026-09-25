# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Đậu Văn Thạch             |
| MSSV               | 2A202602592                |
| Khóa/Lớp         | K4 — L3                    |
| Tên nhóm         | Clone                 |
| Vai trò chính    | Data model & evaluation-set owner |
| Repository         | https://github.com/tungdaisy7it/K4-L3-DAY10-Clone-DataPipeline |
| Ngày hoàn thành | 2026-09-25                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Cleaning & data model | `src/ingestion/cleaning.py::build_clean_dataframe` | `list[PaperRecord]`, `run_date` | `data/clean/papers_clean.{csv,json}` (24 × 16) | Hoàn thành |
| Helper dùng chung | `add_derived_columns`, `compose_text_for_embedding`, `CLEAN_COLUMNS` | Dataframe | Cột derived, dùng lại ở corruption | Hoàn thành |
| Evaluation set | `src/evaluation/testset.py::build_test_set` | Clean dataframe | `data/eval/test_set.json` (10 câu) | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Cung cấp `add_derived_columns` cho corruption | Lê Thanh Tùng — `corruption.py` | Lỗi tiêm vào đi được vào `text_for_embedding` |
| Kiểm tra dữ liệu repair | Lê Thanh Tùng — `repair_from_raw` | Repair dùng lại `build_clean_dataframe`, fingerprint trùng baseline |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Clean 24 record | `cleaning.py` | 24 dòng, `paper_id` unique, sort mới → cũ | Lệnh CP1: `Clean thành công 24 dòng` |
| `text_for_embedding` 5 phần | `compose_text_for_embedding` | Title/Authors/Published/Categories/Summary | `test_clean_snapshot_shape` |
| Dedup + lọc dòng xấu | `build_clean_dataframe` | Giữ bản `updated` mới nhất; bỏ dòng thiếu summary/ngày sai | `test_clean_dedup_normalize_and_filter` |
| Test set 10 câu / 4 dạng | `testset.py` | summary 3, authors 3, date 2, categories 2 | Lệnh CP2: `Sinh được 10 câu hỏi test` |
| Validation benchmark | `testset.py`, `tests/test_quality_and_testset.py` | Báo lỗi schema thiếu; bỏ ground truth rỗng; kết quả tất định | `test_build_test_set_*` |

Output cụ thể: `data/eval/test_set.json` (sha256 `3541bfb96efb6757…`) được dùng chung cho cả 3 trạng thái baseline, corrupted và repaired.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Biến records thô thành một bảng có schema ổn định để embed, và tạo một "đề thi" cố định có đáp án để đo chất lượng RAG.

### Cách triển khai

- **Cleaning:** strip markup và whitespace cho mọi trường text; `authors`/`categories` được khử rỗng và khử trùng mà vẫn giữ thứ tự. DOI được lowercase làm `paper_id` (DOI không phân biệt hoa thường). Ngày được parse bằng `pd.to_datetime(utc=True, errors="coerce")`, dòng nào ngày không hợp lệ thì bỏ. `age_days = (ngày run − ngày published).days` theo ngày UTC. Khi trùng `paper_id`, sort theo `updated` giảm dần rồi `drop_duplicates(keep="first")` để giữ bản mới nhất. Cuối cùng sort theo `published` giảm dần, rồi `paper_id`, để output có thứ tự xác định.
- **Test set:** lấy danh sách bài đã sort mới → cũ và chọn 10 vị trí cách đều (`round(i × (n−1)/9)`), nên đề phủ cả bài mới lẫn cũ. Dạng câu hỏi xoay vòng summary → authors → date → categories. Câu hỏi đặt tiêu đề trong dấu nháy đơn để `qa.answer_question` tra cứu chính xác được. Ground truth là `first_sentence(summary)`, `authors_joined`, `published` hoặc `categories_joined`.
- **Data contract của test set:** kiểm tra đủ sáu cột bắt buộc trước khi sinh đề; loại paper thiếu ID/title hoặc title có dấu nháy đơn; nếu vị trí cách đều không có ground truth phù hợp thì chọn paper hợp lệ gần nhất chưa dùng. Nhờ vậy 10 câu hỏi không trùng document, không có đáp án rỗng và vẫn tái lập được giữa các lần chạy.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `list[PaperRecord]` từ `load_raw_records`; `run_date` |
| Output | Dataframe 16 cột `CLEAN_COLUMNS`; `test_set.json` gồm `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids` |
| Module phụ thuộc | `ingestion.crossref` (`PaperRecord`, `strip_markup`), `core.utils` |
| Module sử dụng output | `retrieval.index`, `observability.quality`, `ingestion.corruption`, `evaluation.metrics` |
| Điều kiện lỗi cần xử lý | Input rỗng (trả dataframe rỗng đủ cột), ngày không parse được, trùng DOI khác hoa thường, dưới 4 bài (raise), tiêu đề chứa `'` (bỏ khỏi test set) |

### Cách xác minh

```bash
python -c "from datetime import datetime, timezone; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s=load_settings(); df=build_clean_dataframe(load_raw_records(s.paths.raw_records_json), datetime.now(timezone.utc)); print(f'Tín hiệu hoàn thành: Clean thành công {len(df)} dòng')"
python -c "from core.config import load_settings; from evaluation.testset import build_test_set; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); ts=build_test_set(df, s.paths.eval_testset); print(f'Tín hiệu hoàn thành: Sinh được {len(ts)} câu hỏi test')"
```

- **Kết quả mong đợi:** 24 dòng; 10 câu hỏi.
- **Kết quả thực tế:** `Clean thành công 24 dòng`; `Sinh được 10 câu hỏi test`.
- **Artifact/log:** `data/clean/papers_clean.csv`, `data/eval/test_set.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chọn bài nào để hỏi trong test set.
- **Các phương án đã cân nhắc:** (a) Chọn ngẫu nhiên có seed. (b) 10 bài mới nhất. (c) 10 vị trí cách đều theo thời gian.
- **Phương án đã chọn:** (c).
- **Lý do:** Tất định mà không cần seed, và phủ đều trục thời gian. Nếu chọn 10 bài mới nhất thì kịch bản drop latest làm hỏng gần hết đề; chọn ngẫu nhiên thì khó giải thích khi trình bày.
- **Bằng chứng:** đề chứa cả bài mới nhất (2026-07-22, eval_001) lẫn bài cũ nhất (2026-03-28, eval_010). Ở trạng thái corrupted, 2/10 câu mất hit do drop, các câu còn lại cho thấy tác động của từng loại lỗi khác.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Test retrieval thất bại: `AssertionError: assert ... '10.1145/3637528.3671824' == '10.1145/3637528.3671812'` khi tìm theo tiêu đề bài "Continuous Benchmark Evaluation for Enterprise Retrieval Pipelines".
- **Lệnh tái hiện:** `python -m pytest tests/test_retrieval_and_metrics.py -x`.
- **Nguyên nhân gốc:** snapshot có các cặp bài gần trùng ("X" và "Advanced Perspectives on X", cùng chủ đề và chuyên ngành). Semantic search thuần có thể xếp bài "anh em" lên trên bài đúng.
- **Cách xử lý:** giữ tiêu đề trong nháy đơn ở mọi câu hỏi để QA tra cứu chính xác theo tiêu đề và đưa bài đúng lên đầu; test retrieval chỉ yêu cầu bài đúng nằm trong top-3.
- **Cách xác minh sau khi sửa:** baseline hit rate = 1.0 và F1 = 1.0; test pass.
- **Điều học được:** thiết kế câu hỏi quyết định việc benchmark đo cái gì. Với dữ liệu có bản gần trùng, hit@4 che mất lỗi xếp hạng mà hit@1 sẽ lộ ra.

## 7. Hiểu biết về luồng end-to-end

1. Raw records được clean (phần của tôi), tạo ra `text_for_embedding`; sau đó MiniLM embed và ChromaDB lưu kèm metadata (`authors_joined`, `published`, …) để QA trích câu trả lời.
2. `ground_truth_doc_ids` dùng để tính hit (DOI đúng trong top-k); `ground_truth` dùng cho token F1 và LLM judge.
3. Quality checks xét từng dòng/bảng; freshness xét phân bố `age_days` (cột do tôi tính) so với SLA 180 ngày / 25%.
4. Test set sinh từ dữ liệu sạch và giữ nguyên; nếu sinh lại từ dữ liệu bẩn thì ground truth cũng bẩn theo và không còn thấy suy giảm.
5. Repair gọi lại đúng `build_clean_dataframe` trên raw; fingerprint trùng baseline chứng minh cleaning là tất định.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ------------- | -------: | --------: | -------: | -------------------- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | |
| `mean_token_f1` | 1.0000 | 0.7519 | 1.0000 | Dạng `date` giảm mạnh nhất (0.5), `categories` không đổi (1.0) |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | |
| `mean_judge_score` | 5.0 | 4.2 | 5.0 | |
| Quality checks | PASS | FAIL | PASS | |
| Freshness status | Fresh | Stale | Fresh | |

### Kết luận từ số liệu

1. Inject noise → regex chống nhiễu FAIL → eval_005 và eval_009 (summary) chỉ còn F1 0.8889 vì token rác lẫn vào câu trả lời.
2. Repair bằng cleaning tất định → fingerprint trùng → F1 theo từng dạng câu hỏi về lại 1.0.

Ảnh hưởng rõ nhất theo dạng câu hỏi là `date` (F1 1.0 → 0.5), vì stale date làm sai hoàn toàn token duy nhất của đáp án.

Khác kỳ vọng: `blank_summary` trúng bài của eval_008 nhưng không làm giảm điểm, vì câu đó hỏi categories, trường không bị xóa. Ngoài ra, LLM judge vẫn chấm 5/5 cho câu trả lời có token rác (eval_005/009) và cho eval_001, dù câu trả lời lấy từ bài gần trùng (F1 0.74). Judge khá dễ dãi, nên token F1 nhạy hơn với lỗi nội dung.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Cleaning phải tất định (sort, dedup có quy tắc) thì repair mới kiểm chứng được bằng fingerprint.
2. `age_days` là cầu nối giữa cleaning và freshness monitoring.
3. Benchmark chỉ nhìn thấy những lỗi trúng vào tài liệu nó hỏi tới.

Kiểm thử bổ sung cho phần sở hữu của tôi bao gồm schema thiếu cột, ground truth rỗng, tính tất định của test set, và fallback `updated → published` trong cleaning.

### Nếu có thêm thời gian

Sinh mỗi bài 1 câu hỏi và thêm câu hỏi không kèm tiêu đề để ép semantic search, rồi báo cáo thêm hit@1 để đo được lỗi xếp hạng giữa các bài gần trùng.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đậu Văn Thạch
**Ngày xác nhận:** 2026-09-25
