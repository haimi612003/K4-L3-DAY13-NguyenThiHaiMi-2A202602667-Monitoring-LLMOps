# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Thị Hải Mi
- **MSSV:** 2A202602667
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/haimi612003/K4-L3-DAY13-NguyenThiHaiMi-2A202602667-Monitoring-LLMOps
- **Commit SHA cuối:** SHA của commit cuối trên nhánh `main` (được nộp kèm URL repo trên LMS/Codelabs)
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602667`

## 2. Evidence index

| Evidence | Đường dẫn |
|---|---|
| Baseline (trước khi sửa) | [`evidence/00-baseline-log-validator.txt`](evidence/00-baseline-log-validator.txt), [`00-baseline-dashboard-validator.txt`](evidence/00-baseline-dashboard-validator.txt), [`00-baseline-pytest.txt`](evidence/00-baseline-pytest.txt), [`00-baseline-load-test.txt`](evidence/00-baseline-load-test.txt) |
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.png`](evidence/04-structured-log.png) |
| PII redaction | [`evidence/05-pii-redaction.png`](evidence/05-pii-redaction.png) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) |
| Prompt versions (đồng thời là trạng thái **trước** rollback) | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback (trạng thái **sau** rollback) | [`evidence/10b-after-rollback.png`](evidence/10b-after-rollback.png) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident (toàn bộ output điều tra) | [`evidence/12-14-incident-investigation.txt`](evidence/12-14-incident-investigation.txt) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) — spike lúc **10:40** là challenge; spike lúc 10:05 là practice `rag_slow` (mục 7, phần luyện tập) |
| Incident log | [`evidence/13-incident-log.png`](evidence/13-incident-log.png) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) — trace `2d2149eb…` ↔ `req-0032e323` (metadata `correlation_id`, xem bảng trong file `.txt`) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Baseline: `correlation_id="MISSING"`, thiếu `user_id_hash/session_id/feature/model` |
| `validate_dashboard.py` | 6/6 | 6/6 | Contract có sẵn; bổ sung dashboard runtime `scripts/dashboard.py` |
| `pytest` | 22 passed | 35 passed | Thêm 13 test: PII, correlation ID/context leak, thứ tự processor, child observations, dashboard aggregation |
| Số traces hợp lệ | 0 (chỉ có root observation, prompt `local-fallback`) | 45 trace đầy đủ + 1 trace lỗi (tính đến 10:06 ngày 30/09) | Mỗi trace: `lab-agent-run` → `retrieval` + `llm-generation` |
| Số PII leak | 0 trong file log (message preview đã được `summarize_text` scrub) | 0 | Scrubber giờ chạy trên **mọi** field của log trước khi ghi file, không chỉ payload |
| Latency P95 / TTFT P95 | 1578 ms / 55 ms | 159 ms / 55 ms | Workload 10 query mẫu; baseline chậm do fetch prompt 404 mỗi request + event loop bị block |
| Retrieval success rate | 100% | 100% (ngoài practice `tool_fail`) | Practice `tool_fail` làm retrieval success giảm, log `request_failed` có `tool_success=false` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** [`app/middleware.py`](../app/middleware.py) gọi `clear_contextvars()` ở đầu mỗi request, nhận header `x-request-id` nếu hợp lệ (`^[A-Za-z0-9._-]{1,64}$`, chống log injection) hoặc sinh `req-<8-hex>`, rồi `bind_contextvars(correlation_id=...)`. ID được trả lại qua header `x-request-id` cùng `x-response-time-ms`, nằm trong body response và được truyền vào `agent.run()` để ghi vào trace metadata.
- **Các metadata được ghi vào structured log:** [`app/main.py`](../app/main.py) bind `user_id_hash` (SHA-256 rút gọn, không log user_id gốc), `session_id`, `feature`, `model`, `env` trước log `request_received`, nên mọi log sau trong request đều có. `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** [`app/logging_config.py`](../app/logging_config.py) đăng ký `scrub_event` **sau** `format_exc_info` (để cả traceback cũng được scrub) và **trước** `JsonlFileProcessor`/`JSONRenderer`. `scrub_event` đệ quy qua mọi field (bỏ qua `ts`, `level`, `correlation_id`, `user_id_hash` vì do hệ thống sinh). [`app/pii.py`](../app/pii.py) có pattern email, thẻ thanh toán, CCCD 12 số, điện thoại VN (`0`/`+84`, có dấu cách/chấm/gạch) và hộ chiếu VN; pattern số dài chạy trước để điện thoại không cắt mất một phần số thẻ.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 100/100 với 0 PII leak trên 148 record; tests [`tests/test_pii.py`](../tests/test_pii.py) và [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py) kiểm tra từng loại PII, ghi log thật qua API rồi đọc file, kiểm tra hai request liên tiếp không rò context và `scrub_event` đứng trước file writer. Ví dụ log thực tế: `"message_preview": "What is the policy for PII and credit card [REDACTED_CREDIT_CARD]?"`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** `.env` dùng key của project `day13-k4-l3b-2A202602667`; mọi trace có metadata `correlation_id` trùng với dòng log trong `data/logs.jsonl` do tôi chạy `load_test.py`.
- **Cấu trúc root/retrieval/generation observations:** [`app/agent.py`](../app/agent.py) — root `lab-agent-run` (type `agent`, trace name `day13-agent-request`) có 2 con tạo bằng `start_as_current_observation` của SDK v4:
  - `retrieval` (type `retriever`): input là `query_preview` đã scrub, output `doc_count` + preview tài liệu; lỗi được ghi `level=ERROR` + `status_message`.
  - `llm-generation` (type `generation`): `model`, `prompt` (link tới prompt Langfuse), `usage_details` input/output, `cost_details` input/output/total, `completion_start_time` (= start + TTFT).
- **Cách nối trace với log:** `correlation_id` được đưa vào trace metadata bằng `propagate_attributes`; trên Langfuse lọc metadata `correlation_id = req-xxxxxxxx` để mở đúng trace của một dòng log.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** v1 — labels `baseline` (+ `production` sau rollback)
- **Version/label candidate:** v2 — label `candidate` (thêm yêu cầu trả lời tối đa 3 bullet)
- **Trace ID của mỗi version** (cùng input `"How should alerts be designed?"`):

  | Bước | correlation_id | Trace ID | Prompt | tokens_in |
  |---|---|---|---|---|
  | label `baseline` | `req-ba5e0002` | `11025e4339d09c1cba8bf19da95ebe6b` | v1 | 51 |
  | label `candidate` | `req-ca0d0001` | `efa031e35602241c669501ab2d6190fd` | v2 | 72 |
  | `production` sau khi promote → v2 | `req-9d0d0002` | `b516136ad0587a6c810256a26e16da0f` | v2 | 72 |
  | `production` sau khi rollback → v1 | `req-9d0d0003` | `93ccd07b0a98e3edd1cf457d61642e16` | v1 | 51 |

- **Cách promote và rollback `production`:** promote: chuyển label `production` sang v2 (`update_prompt(version=2, new_labels=["candidate","production"])`). Rollback: trên Langfuse UI mở version 1 → Prompt labels → chọn `production` → *Save and promote to production*; Langfuse tự gỡ `production` khỏi v2. App **không đổi code**, chỉ restart để xóa cache prompt 60 giây; trace sau rollback ghi `prompt_version=1` và `tokens_in` quay về 51.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [`scripts/dashboard.py`](../scripts/dashboard.py) (`python scripts/dashboard.py` → http://127.0.0.1:8050) đọc trực tiếp `data/logs.jsonl` và lấy title, time range 60 phút, refresh 30 giây, đơn vị, threshold từ [`config/dashboard.yaml`](../config/dashboard.yaml). Sáu panel: Latency (P50/P95/P99 + TTFT P95, đường threshold 3000 ms), Traffic (request/phút), Errors (error rate %, breakdown theo `error_type`, retrieval success %), Cost (USD/phút + tổng), Tokens (input/output), Quality (mean, threshold 0.75). Giá trị vượt threshold hiển thị màu đỏ. Logic tổng hợp có test [`tests/test_dashboard_runtime.py`](../tests/test_dashboard_runtime.py).
- **SLO và lý do chọn:** [`config/slo.yaml`](../config/slo.yaml) — `fast_successful_requests`: 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày. Baseline sau khi sửa P50 157 ms, P95 159 ms, request đầu sau khởi động ~850–1300 ms, nên 3000 ms là mức chờ tối đa chấp nhận được và còn dư nhiều cho biến động bình thường.
- **Cách tính error budget:** error budget = 100% − 99.5% = 0.5%. Với 10,000 request trong 28 ngày, tối đa 50 request được phép lỗi hoặc chậm hơn 3000 ms. Request lỗi không có `response_sent` nên tự động bị tính là bad event.
- **Ba alert và runbook tương ứng:** [`config/alert_rules.yaml`](../config/alert_rules.yaml), runbook trong [`docs/alerts.md`](../docs/alerts.md), tất cả gửi Slack `#k4-l3b-alerts`, owner `student-2A202602667`:
  1. `HighLatencyP95` (warning, 5m): P95 > 2000 ms — cảnh báo sớm dưới SLO 3000 ms vì practice `rag_slow` chỉ đẩy P95 lên ~2663 ms (chưa vi phạm SLO nhưng gấp ~15 lần baseline).
  2. `HighErrorRate` (critical, 5m): error rate > 2% hoặc retrieval success < 90%.
  3. `CostPerRequestSpike` (warning, 10m): chi phí trung bình/request > 0.005 USD (~2.4× baseline 0.0021 USD).

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (cohort K4, seed 1312, 5 query feature `monitoring`, `latency_threshold_ms` 2000). Chạy `python scripts/inject_incident.py` rồi `python scripts/load_test.py --challenge --concurrency 5`. Toàn bộ output: [`evidence/12-14-incident-investigation.txt`](evidence/12-14-incident-investigation.txt).
- **Khoảng thời gian điều tra:** 10:39:57–10:40:51 (UTC+7) ngày 30/09/2026 — từ lúc bật challenge đến lúc tắt và xác nhận hồi phục. Mốc so sánh: workload bình thường lúc 10:38:56.
- **Triệu chứng từ metrics:** panel Latency: P95 tăng từ **160 ms → 2671 ms** (×16.7), vượt `latency_threshold_ms` 2000 của challenge và ngưỡng alert `HighLatencyP95` (2000 ms). Trong khi đó **TTFT P95 giữ nguyên 54–55 ms**, error rate 0%, retrieval success 100%, cost/request 0.0020 → 0.0023 USD (không đáng kể) → chỉ có latency xấu đi và phần chậm nằm **trước** bước generation.
- **Log line và correlation ID liên quan:** cả 5 dòng `response_sent` của challenge có `latency_ms` 2663–2671, `ttft_ms` 51–54, `tool_success=true`. Dòng đại diện: `{"event": "response_sent", "correlation_id": "req-0032e323", "feature": "monitoring", "session_id": "k4-l3b-challenge-s02", "latency_ms": 2663, "ttft_ms": 51, "tool_success": true, "ts": "2026-09-30T03:40:00.024892Z"}`.
- **Trace ID và span gây ảnh hưởng:** trace `2d2149eb9fe4b135c6e0d692a570531b` (metadata `correlation_id=req-0032e323`): `lab-agent-run` 2.664 s = **`retrieval` 2.506 s (94%)** + `llm-generation` 0.156 s. So với trace bình thường `d101572bdb7e42fb53a702aa91866635` (`req-4eea3501`): retrieval ~0 s, generation 0.152 s. Generation, TTFT và `prompt_version=1` giống hệt baseline; 4 trace còn lại của challenge đều có retrieval 2.508–2.516 s.
- **Root cause:** bước retrieval (vector store/RAG) bị chậm thêm ~2.5 s mỗi lần gọi (sự cố `rag_slow` được challenge inject vào retrieval). Không phải do LLM (generation/TTFT không đổi), không phải do prompt (vẫn v1, không có thay đổi label trong khoảng này), không phải do tải (5 request, P50 cũng tăng như P95). Kiểm tra thêm khi sự cố còn bật: request `feature=qa` (`req-5c0be001`) cũng mất 2662 ms → retrieval chậm với **mọi** feature, `monitoring` bị ảnh hưởng vì là traffic của challenge.
- **Fix action:** khôi phục retrieval bằng `python scripts/inject_incident.py --disable` (tương đương rollback/khởi động lại vector store). Xác nhận bằng chính 5 query challenge: latency còn **156.6–164.7 ms**, về đúng baseline.
- **Preventive measure:** (1) alert `HighLatencyP95` > 2000 ms trong 5 phút (đã có trong [`config/alert_rules.yaml`](../config/alert_rules.yaml)) + runbook bước "TTFT không đổi → kiểm tra span retrieval"; (2) thêm SLI riêng cho span `retrieval` (ví dụ P95 > 500 ms) để cảnh báo đúng thành phần trước khi ảnh hưởng tổng latency; (3) đặt timeout ~1 s cho retrieval và fallback trả lời với context chung/cache thay vì để người dùng chờ; (4) chạy practice `rag_slow` trong CI/staging để kiểm tra alert và runbook còn hoạt động.

### Luyện tập trước CP3 (practice scenario, không phải challenge chính thức)

Chạy `python scripts/inject_incident.py --scenario rag_slow` rồi `python scripts/load_test.py --concurrency 5`, khoảng 10:05:17–10:05:22 (UTC+7) ngày 30/09/2026:

- **Metrics:** `/metrics` và panel Latency: P95 tăng từ 159 ms lên 2663 ms, P50 vẫn 157 ms (vì cửa sổ gồm cả request bình thường), còn **TTFT P95 không đổi 55 ms** → phần chậm nằm trước bước generation.
- **Log:** `response_sent` `correlation_id=req-3089a22d`, `latency_ms=2663`, `ttft_ms=55`, `feature=qa`.
- **Trace:** `3894f561feed2471d5cb95dd0d431654` (cùng `correlation_id`): `retrieval` 2.503 s, `llm-generation` 0.159 s.
- **Kết luận:** retrieval (vector store) chậm là nguyên nhân; fix bằng cách tắt scenario (`--disable`) → latency trở về ~170 ms. Preventive: alert `HighLatencyP95` 2000 ms + timeout cho retrieval.

Practice `tool_fail`: log `request_failed` `req-e0000001` (`error_type=RuntimeError`, `tool_success=false`) ↔ trace `16d030d543620f25de5231025fd310c6`, observation `retrieval` có `level=ERROR`, `status_message="RuntimeError: Vector store timeout"`.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** chạy `agent.run` trong threadpool (`run_in_threadpool`) thay vì gọi trực tiếp trong endpoint `async`. Agent dùng `time.sleep`/IO đồng bộ nên trước đây chặn event loop: với concurrency 5, client chờ tới ~4.8 s dù agent chỉ mất 0.5–2.3 s — metric `latency_ms` (đo trong agent) **không** nhìn thấy thời gian xếp hàng này. Sau khi sửa, cùng workload chỉ ~160 ms. Contextvars (correlation ID, OTel span) vẫn được copy sang thread nên log và trace không bị đứt.
- **Một lỗi/blocker đã gặp:** (1) Mọi trace dùng prompt v1 đều không xuất hiện trên Langfuse, trong khi trace v2 thì có. (2) Port 8000 bị container Docker của bài Day 12 chiếm (`localhost` trỏ vào container, `127.0.0.1` vào app Day 13). (3) API `GET /api/public/traces` trả 410 cho organization mới.
- **Cách tìm nguyên nhân và xử lý:** (1) Bật `LANGFUSE_DEBUG` thấy SDK có xử lý đủ 3 span, nhưng span được gửi theo batch nền; tôi restart API ngay sau khi gửi request nên process bị tắt trước khi batch được export. Thêm `get_langfuse_client().flush()` trong shutdown của `lifespan` → trace v1 xuất hiện đầy đủ. (2) Dùng `lsof -iTCP:8000` tìm ra container, dừng container Day 12. (3) Chuyển sang `GET /api/public/v2/observations` và gom theo `traceId` để kiểm tra trace.
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời *có vấn đề gì và từ khi nào* (P95 tăng, TTFT không đổi); logs trả lời *request nào bị ảnh hưởng* (lọc `latency_ms` cao, lấy `correlation_id`); trace trả lời *bước nào gây ra* (so sánh duration/level của `retrieval` và `llm-generation`). `correlation_id` là khóa nối log với trace; thiếu nó thì chỉ đoán được.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là một phần của "code" nhưng thay đổi được mà không deploy, nên mỗi trace phải ghi `prompt_name/label/version` để biết request dùng prompt nào. Ví dụ ở đây v2 làm `tokens_in` tăng 51 → 72 (+41%) — nếu cost/latency xấu đi thì rollback chỉ là chuyển label `production`, không cần sửa code. SLO + error budget cho biết khi nào được phép thử prompt mới và khi nào phải dừng.
- **Điều quan trọng nhất đã học:** validator 100/100 không có nghĩa hệ thống quan sát được đúng — phải kiểm tra trực tiếp trên Langfuse mới phát hiện trace bị mất khi shutdown, và phải chạy thử incident mới thấy ngưỡng alert 3000 ms không bắt được `rag_slow`.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Quality score vẫn là heuristic (FakeLLM trả câu trả lời cố định). Dashboard là dashboard local đọc file JSONL, alert chưa được gửi tự động lên Slack.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
