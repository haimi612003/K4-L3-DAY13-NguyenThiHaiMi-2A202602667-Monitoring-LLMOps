# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (99.5% request thành công và `latency_ms <= 3000`) trong [`config/slo.yaml`](../config/slo.yaml); panel **Latency** của dashboard. Ngưỡng alert 2000 ms thấp hơn SLO để cảnh báo sớm (baseline P95 ~170 ms; practice `rag_slow` cho P95 ~2663 ms — chưa vi phạm SLO nhưng đã bất thường).
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 2000 ms` liên tục trong 5 phút.
- Ảnh hưởng tới người dùng: ít nhất 5% người dùng chờ hơn 2 giây mới nhận được câu trả lời; nếu tiếp tục xấu đi quá 3 giây thì mỗi request chậm tiêu vào error budget 0.5%.
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard (`python scripts/dashboard.py`), xem panel Latency: P95/P99 tăng từ lúc nào; TTFT P95 có tăng theo không (TTFT không đổi → chậm nằm trước bước generation).
  2. Lọc log chậm và lấy `correlation_id`:
     `grep '"response_sent"' data/logs.jsonl | python -c "import sys,json;[print(e['ts'],e['correlation_id'],e['latency_ms']) for e in map(json.loads,sys.stdin) if e['latency_ms']>2000]"`
  3. Trên Langfuse, lọc trace theo metadata `correlation_id`, so sánh duration của span `retrieval` và `llm-generation` trong waterfall.
- Mitigation tạm thời: nếu `retrieval` chậm → tắt/khôi phục vector store hoặc cấu hình retrieval vừa đổi (practice: `python scripts/inject_incident.py --scenario rag_slow --disable`); nếu `llm-generation` chậm sau khi đổi prompt → rollback label `production` về version trước; giảm tải nếu do traffic tăng đột biến.
- Owner: `student-2A202602667`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` và guardrails `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`; panel **Errors** (error rate + retrieval success).
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received) * 100 > 2%` **hoặc** retrieval success `< 90%`, kéo dài 5 phút.
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời; error budget bị đốt rất nhanh (2% lỗi = đốt budget nhanh gấp 4 lần mức cho phép).
- Ba bước kiểm tra đầu tiên:
  1. Panel Errors: xem error rate, dòng `error breakdown` (loại lỗi nào) và retrieval success có giảm cùng lúc không.
  2. Lọc log lỗi: `grep '"request_failed"' data/logs.jsonl` → đọc `error_type`, `tool_name`, `payload.detail` và lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`: observation nào có level `ERROR` và `status_message` gì (ví dụ `retrieval` → `RuntimeError: Vector store timeout`).
- Mitigation tạm thời: khôi phục dependency lỗi (practice: `python scripts/inject_incident.py --scenario tool_fail --disable`); nếu lỗi bắt đầu ngay sau deploy/đổi prompt thì rollback; cân nhắc trả câu trả lời fallback thay vì 500 khi retrieval lỗi.
- Owner: `student-2A202602667`

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5`; panel **Cost** và **Tokens**.
- Điều kiện và thời gian duy trì: chi phí trung bình mỗi request `sum(cost_usd) / count(response_sent) > 0.005 USD` (≈ 2.4 lần baseline ~0.002 USD) liên tục 10 phút.
- Ảnh hưởng tới người dùng: câu trả lời dài bất thường (khó đọc, chậm hơn) và ngân sách ngày có thể bị vượt trước khi hết ngày.
- Ba bước kiểm tra đầu tiên:
  1. Panel Cost và Tokens: cost tăng do `tokens_in` (prompt/context dài hơn) hay `tokens_out` (câu trả lời dài hơn)?
  2. Lọc log `response_sent` có `cost_usd` cao nhất, lấy `correlation_id`, kiểm tra `feature` nào bị ảnh hưởng.
  3. Mở trace cùng `correlation_id`: xem `usage`/`cost` của `llm-generation` và `prompt_version` — có trùng thời điểm promote prompt mới không.
- Mitigation tạm thời: rollback label `production` nếu prompt mới làm tăng token; đặt `max_tokens` cho generation; tắt nguyên nhân gây phình output (practice: `python scripts/inject_incident.py --scenario cost_spike --disable`).
- Owner: `student-2A202602667`
