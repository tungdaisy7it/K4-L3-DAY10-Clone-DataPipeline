"""Small local demo dashboard for the Day 10 data observability lab.

Run from the repository root:
    python demo/app.py

The dashboard is intentionally dependency-free: it reads the JSON artifacts
written by the existing pipeline and can start either pipeline entrypoint.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
JOB_LOCK = threading.Lock()
JOB: dict[str, Any] = {"status": "idle", "flow": None, "started_at": None, "finished_at": None, "log": ""}


ARTIFACTS = {
    "baseline_metrics": DATA / "results/baseline_metrics.json",
    "corrupted_metrics": DATA / "results/corrupted_metrics.json",
    "repaired_metrics": DATA / "results/repaired_metrics.json",
    "baseline_quality": DATA / "quality/baseline_quality_report.json",
    "corrupted_quality": DATA / "quality/corrupted_quality_report.json",
    "repaired_quality": DATA / "quality/repaired_quality_report.json",
    "baseline_freshness": DATA / "quality/freshness_report.json",
    "corrupted_freshness": DATA / "quality/corrupted_freshness_report.json",
    "repaired_freshness": DATA / "quality/repaired_freshness_report.json",
    "corruption_log": DATA / "results/corruption_log.json",
    "baseline_report": DATA / "reports/phase1_report.md",
    "comparison_report": DATA / "reports/corruption_report.md",
    "papers": DATA / "clean/papers_clean.json",
}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def compact_metrics(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metrics:
        return None
    keys = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score", "samples")
    return {key: metrics.get(key) for key in keys if key in metrics}


def status_payload() -> dict[str, Any]:
    states = {}
    for state in ("baseline", "corrupted", "repaired"):
        states[state] = {
            "metrics": compact_metrics(read_json(ARTIFACTS[f"{state}_metrics"])),
            "quality": read_json(ARTIFACTS[f"{state}_quality"]),
            "freshness": read_json(ARTIFACTS[f"{state}_freshness"]),
        }
    log = read_json(ARTIFACTS["corruption_log"], {}) or {}
    with JOB_LOCK:
        job = dict(JOB)
    return {
        "states": states,
        "corruptions": log.get("corruptions", []),
        "papers": len(read_json(ARTIFACTS["papers"], []) or []),
        "artifacts": {name: path.exists() for name, path in ARTIFACTS.items()},
        "job": job,
    }


def run_flow(flow: str) -> None:
    script = "run_phase1.py" if flow == "baseline" else "run_corruption_flow.py"
    command = [sys.executable, str(ROOT / "script" / script)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    started = datetime.now(timezone.utc).isoformat()
    with JOB_LOCK:
        JOB.update({"status": "running", "flow": flow, "started_at": started, "finished_at": None, "log": ""})
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1800)
        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        status = "success" if result.returncode == 0 else "error"
        with JOB_LOCK:
            JOB.update({"status": status, "finished_at": datetime.now(timezone.utc).isoformat(), "log": output[-12000:]})
    except Exception as exc:  # pragma: no cover - defensive UI boundary
        with JOB_LOCK:
            JOB.update({"status": "error", "finished_at": datetime.now(timezone.utc).isoformat(), "log": repr(exc)})


def start_flow(flow: str) -> tuple[int, dict[str, str]]:
    if flow not in {"baseline", "corruption"}:
        return 400, {"error": "flow must be baseline or corruption"}
    with JOB_LOCK:
        if JOB["status"] == "running":
            return 409, {"error": "A pipeline is already running"}
    threading.Thread(target=run_flow, args=(flow,), daemon=True).start()
    return 202, {"status": "started", "flow": flow}


HTML = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Data Observability Demo</title>
  <style>
    :root{--bg:#f4f7fb;--ink:#172033;--muted:#64748b;--card:#fff;--line:#dfe6f0;--blue:#2563eb;--green:#15803d;--red:#b91c1c;--amber:#b45309}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif}
    .wrap{max-width:1180px;margin:auto;padding:28px 20px 60px}.hero{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;margin-bottom:22px}
    h1{margin:0;font-size:32px;letter-spacing:-.03em}.subtitle{color:var(--muted);margin:6px 0 0}.badge{padding:7px 12px;border-radius:999px;background:#e0ecff;color:#1d4ed8;font-weight:700;white-space:nowrap}
    .actions{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}.btn{border:0;border-radius:10px;padding:10px 15px;font-weight:700;cursor:pointer;background:var(--blue);color:#fff}.btn.secondary{background:#e8eef8;color:#1e3a8a}.btn:disabled{opacity:.5;cursor:wait}
    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:0 5px 18px #183b6b0b}.card h2{font-size:16px;margin:0 0 12px}.number{font-size:29px;font-weight:800}.muted{color:var(--muted)}
    .wide{grid-column:span 2}.full{grid-column:1/-1}.state-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.state{border:1px solid var(--line);border-radius:12px;padding:14px}.state h3{margin:0 0 10px}.pass{color:var(--green);font-weight:800}.fail{color:var(--red);font-weight:800}.warn{color:var(--amber);font-weight:800}
    table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:700}.metric{text-transform:none}.scenario{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)}
    pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#101827;color:#dbeafe;border-radius:10px;padding:13px;font-size:12px}.empty{color:var(--muted);padding:12px 0}.small{font-size:12px}.footer{color:var(--muted);margin-top:22px;text-align:center}
    @media(max-width:800px){.grid,.state-grid{grid-template-columns:1fr 1fr}.wide{grid-column:span 2}.hero{display:block}.badge{display:inline-block;margin-top:12px}} @media(max-width:520px){.grid,.state-grid{grid-template-columns:1fr}.wide{grid-column:span 1}}
  </style>
</head>
<body><main class="wrap">
  <div class="hero"><div><h1>Data Observability Lab</h1><p class="subtitle">Crossref → Cleaning → Quality Gate → RAG → Corruption → Repair</p></div><span id="jobBadge" class="badge">Đang tải...</span></div>
  <div class="actions"><button class="btn" onclick="runFlow('baseline')">▶ Chạy Baseline</button><button class="btn" onclick="runFlow('corruption')">⚠ Chạy Corruption & Repair</button><button class="btn secondary" onclick="loadData()">↻ Làm mới</button></div>
  <section class="grid">
    <div class="card"><h2>Clean records</h2><div id="papers" class="number">—</div><div class="muted">sau bước cleaning</div></div>
    <div class="card"><h2>Quality Gate</h2><div id="quality" class="number">—</div><div class="muted">Great Expectations 1.x</div></div>
    <div class="card"><h2>Freshness SLA</h2><div id="freshness" class="number">—</div><div class="muted">tỷ lệ dữ liệu stale</div></div>
    <div class="card"><h2>Corruption cases</h2><div id="corruptions" class="number">—</div><div class="muted">lỗi được tiêm có kiểm soát</div></div>
    <div class="card full"><h2>Ba trạng thái dữ liệu</h2><div id="states" class="state-grid"></div></div>
    <div class="card wide"><h2>Metric comparison</h2><div id="metrics"></div></div>
    <div class="card wide"><h2>6 corruption scenarios</h2><div id="scenarios"></div></div>
    <div class="card full"><h2>Pipeline log</h2><pre id="log" class="empty">Chưa chạy pipeline trong phiên này.</pre></div>
  </section><div class="footer">Demo local • Không gửi dữ liệu ra ngoài • Artifact thật từ thư mục data/</div>
</main>
<script>
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';
const stateLabel={baseline:'Baseline sạch',corrupted:'Corrupted lỗi',repaired:'Repaired phục hồi'};
async function loadData(){const d=await fetch('/api/status').then(r=>r.json()); render(d);}
function render(d){
  const states=d.states||{}; document.querySelector('#papers').textContent=d.papers||'—'; document.querySelector('#corruptions').textContent=d.corruptions.length||'—';
  const b=states.baseline||{}; document.querySelector('#quality').innerHTML=b.quality? (b.quality.success?'<span class="pass">PASS</span>':'<span class="fail">FAIL</span>'):'—';
  document.querySelector('#freshness').textContent=b.freshness?pct(b.freshness.stale_ratio):'—';
  document.querySelector('#states').innerHTML=['baseline','corrupted','repaired'].map(k=>{const s=states[k]||{},q=s.quality,f=s.freshness;return `<div class="state"><h3>${stateLabel[k]}</h3><div>Gate: ${q?(q.success?'<span class="pass">PASS</span>':'<span class="fail">FAIL</span>'):'<span class="muted">chưa có</span>'}</div><div>Freshness: ${f?(f.is_fresh?'<span class="pass">OK</span>':'<span class="warn">ALERT</span>'):'—'}</div><div>Rows: ${esc(q?.row_count)}</div><div class="small muted">Failed checks: ${esc(q?.statistics?.failed_checks)}</div></div>`}).join('');
  const keys=['retrieval_hit_rate','mean_token_f1','judge_accuracy','mean_judge_score']; document.querySelector('#metrics').innerHTML=`<table><thead><tr><th>Metric</th><th>Baseline</th><th>Corrupted</th><th>Repaired</th></tr></thead><tbody>${keys.map(k=>`<tr><td class="metric">${esc(k)}</td>${['baseline','corrupted','repaired'].map(s=>`<td>${pct(states[s]?.metrics?.[k])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  document.querySelector('#scenarios').innerHTML=d.corruptions.length?d.corruptions.map(x=>`<div class="scenario"><span><b>${esc(x.type)}</b><br><span class="small muted">${esc(x.description)}</span></span><b>${esc(x.affected_count)} rows</b></div>`).join(''):'<div class="empty">Chạy Corruption & Repair để hiện 6 kịch bản.</div>';
  const job=d.job||{}; document.querySelector('#jobBadge').textContent=job.status==='running'?`Đang chạy: ${job.flow}`:job.status==='success'?'Pipeline hoàn tất':job.status==='error'?'Pipeline lỗi':'Sẵn sàng'; document.querySelector('#log').textContent=job.log||'Chưa chạy pipeline trong phiên này.';
}
async function runFlow(flow){const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({flow})});const x=await r.json();if(!r.ok)alert(x.error||'Không thể chạy');else poll();}
function poll(){loadData();setTimeout(async()=>{const d=await fetch('/api/status').then(r=>r.json());render(d);if(d.job?.status==='running')poll();},1500)} loadData();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/status":
            self.send_json(status_payload())
        elif parsed.path == "/api/report":
            name = parse_qs(parsed.query).get("name", [""])[0]
            path = ARTIFACTS.get(name)
            if not path or path.suffix != ".md":
                self.send_json({"error": "unknown report"}, 404)
            else:
                self.send_json({"name": name, "exists": path.exists(), "text": path.read_text(encoding="utf-8") if path.exists() else ""})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self.send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            flow = json.loads(self.rfile.read(length)).get("flow")
        except (json.JSONDecodeError, AttributeError):
            flow = None
        status, payload = start_flow(flow)
        self.send_json(payload, status)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[demo] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local data observability demo dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
