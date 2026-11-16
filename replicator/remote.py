"""Web remote control: start/stop captures, watch the log and manage archives from a phone or
another computer's browser. Stdlib only.

    python -m replicator remote            # this PC only:  http://127.0.0.1:8765/?token=...
    python -m replicator remote --lan      # reachable from your phone on the same Wi-Fi

Everything runs on the PC that hosts it - "Play offline" opens the browser on that PC. Access needs
the secret token printed at startup (kept in a cookie after the first visit).
"""
from __future__ import annotations

import collections
import json
import secrets
import socket
import threading
import traceback
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .store import Archive, default_root, list_archives
from .util import human_size

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Replicator Remote</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#2a2f3a;--fg:#e8eaf0;--mut:#8b93a7;--acc:#4f8cff;--bad:#ff5d5d;--ok:#3ecf8e}
@media(prefers-color-scheme:light){:root{--bg:#f4f5f8;--card:#fff;--line:#dde1ea;--fg:#171a21;--mut:#5d6579}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;padding:16px;max-width:760px;margin:auto}
h1{font-size:20px;margin:4px 0 14px}h2{font-size:14px;margin:0 0 10px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
input,button{font:inherit;border-radius:8px;border:1px solid var(--line);padding:9px 10px;background:var(--bg);color:var(--fg)}
input[type=text],input[type=url]{width:100%}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center}
.row label{display:flex;flex-direction:column;font-size:12px;color:var(--mut);gap:3px}.row input[type=number]{width:84px}
button{cursor:pointer}button.p{background:var(--acc);border-color:var(--acc);color:#fff}button.d{color:var(--bad)}
button:disabled{opacity:.45}pre{margin:0;max-height:260px;overflow:auto;font:12px/1.35 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.a{border-top:1px solid var(--line);padding:10px 0}.a:first-of-type{border-top:0}.a b{word-break:break-all}.m{color:var(--mut);font-size:12px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--mut);margin-right:6px}.dot.on{background:var(--ok)}
</style></head><body>
<h1>Replicator Remote <span class="m" id="st"></span></h1>
<div class="card"><h2>Capture a site</h2>
<input type="url" id="url" placeholder="https://example.com" autocapitalize="off">
<div class="row">
<label>Depth<input type="number" id="depth" value="1" min="0" max="5"></label>
<label>Max pages<input type="number" id="pages" value="25" min="1" max="500"></label>
<label>WebGL wait (s)<input type="number" id="wait" value="8" min="0" max="300"></label>
<label>Tabs<input type="number" id="workers" value="8" min="1" max="16"></label>
</div>
<div class="row"><label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="click" checked>Click every button / menu</label></div>
<div class="row"><button class="p" id="go">Capture</button><button id="stop" disabled>Stop</button></div></div>
<div class="card"><h2>Log</h2><pre id="log">-</pre></div>
<div class="card"><h2>Archives</h2><div id="arcs"></div></div>
<script>
const $=id=>document.getElementById(id);let seq=0;
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.status==401){document.body.innerHTML='<p>Not authorised - open the link with ?token=... from the PC console.</p>';throw 0}return r.json()}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function tick(){try{const s=await api('/api/state?since='+seq);
  $('st').textContent=s.capturing?'- capturing...':'';$('go').disabled=s.capturing;$('stop').disabled=!s.capturing;
  if(s.log.length){const el=$('log');const bottom=el.scrollTop+el.clientHeight>=el.scrollHeight-30;
    if(seq===0)el.textContent='';el.textContent+=s.log.join('\n')+'\n';if(bottom)el.scrollTop=el.scrollHeight}
  seq=s.seq;$('arcs').innerHTML=s.archives.map(a=>`<div class="a"><span class="dot ${a.serving?'on':''}"></span><b>${esc(a.name)}</b>
   <div class="m">${esc(a.url)} - ${a.files} files, ${a.size} - ${esc(a.date)}</div><div class="row">
   <button data-a="play" data-n="${esc(a.name)}">Play on PC</button>${a.serving?`<button data-a="stopserver" data-n="${esc(a.name)}">Stop server</button>`:''}
   <button data-a="zip" data-n="${esc(a.name)}">Export .zip</button><button class="d" data-a="delete" data-n="${esc(a.name)}">Delete</button></div></div>`).join('')||'<span class="m">Nothing captured yet.</span>'
}catch(e){}}
$('go').onclick=async()=>{const u=$('url').value.trim();if(!u)return;seq=0;await api('/api/capture',{url:u,depth:+$('depth').value,max_pages:+$('pages').value,
  wait:+$('wait').value,workers:+$('workers').value,click_all:$('click').checked});tick()};
$('stop').onclick=()=>api('/api/stop',{});
$('arcs').onclick=async e=>{const b=e.target.closest('button');if(!b)return;const n=b.dataset.n,a=b.dataset.a;
  if(a=='delete'&&!confirm('Delete '+n+'? (goes to the Recycle Bin)'))return;await api('/api/'+a,{name:n});tick()};
tick();setInterval(tick,1500);
</script></body></html>"""


class RemoteState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.log_lines: collections.deque[tuple[int, str]] = collections.deque(maxlen=600)
        self.seq = 0
        self.stop_event: threading.Event | None = None
        self.thread: threading.Thread | None = None
        self.servers: dict = {}

    def log(self, msg: str) -> None:
        with self.lock:
            for line in str(msg).splitlines() or [""]:
                self.seq += 1
                self.log_lines.append((self.seq, line))

    @property
    def capturing(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start_capture(self, d: dict) -> str:
        from .capture import CaptureOptions, capture_blocking
        if self.capturing:
            return "A capture is already running."
        url = str(d.get("url", "")).strip()
        if not url:
            return "Missing URL."
        try:
            opts = CaptureOptions(
                url=url, name=str(d.get("name", "")), depth=max(0, min(5, int(d.get("depth", 1)))),
                max_pages=max(1, min(500, int(d.get("max_pages", 25)))),
                wait_seconds=max(0.0, min(300.0, float(d.get("wait", 8)))), headless=True,
                workers=max(1, min(16, int(d.get("workers", 8)))), click_all=bool(d.get("click_all", True)))
        except (TypeError, ValueError) as e:
            return f"Invalid setting: {e}"
        self.stop_event = threading.Event()
        self.log(f"Capturing {url} ...")

        def run() -> None:
            try:
                capture_blocking(opts, self.log, self.stop_event)
            except Exception as e:  # noqa: BLE001
                self.log(f"CAPTURE FAILED: {e}")
                self.log(traceback.format_exc().rstrip())

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return ""

    def archive(self, name: str) -> Archive | None:
        return next((a for a in list_archives() if a.name == name), None)  # only real archive names

    def snapshot(self, since: int) -> dict:
        with self.lock:
            lines = [t for s, t in self.log_lines if s > since]
            seq = self.seq
        arcs = []
        for a in list_archives():
            try:
                m, s = a.meta(), a.stats()
            except Exception:  # corrupt or locked db
                m, s = {"start_url": "(unreadable)"}, {"files": 0, "bytes": 0}
            arcs.append({"name": a.name, "url": m.get("start_url", "(incomplete)"), "files": s["files"],
                         "size": human_size(s["bytes"]), "date": m.get("created_at", ""),
                         "serving": a.name in self.servers})
        return {"capturing": self.capturing, "log": lines, "seq": seq, "archives": arcs}

    def play(self, name: str) -> str:
        from .server import ReplayServer
        a = self.archive(name)
        if not a:
            return "Unknown archive."
        srv = self.servers.get(name)
        if srv is None:
            srv = ReplayServer(a, log=self.log)
            srv.start()
            self.servers[name] = srv
        webbrowser.open(srv.launch_url)
        self.log(f"Opened {srv.launch_url} on the PC")
        return ""

    def stop_server(self, name: str) -> None:
        srv = self.servers.pop(name, None)
        if srv:
            srv.stop()

    def delete(self, name: str) -> str:
        a = self.archive(name)
        if not a:
            return "Unknown archive."
        self.stop_server(name)
        self.log(f"Deleted '{name}' ({a.delete()})")
        return ""

    def export_zip(self, name: str) -> str:
        a = self.archive(name)
        if not a:
            return "Unknown archive."
        out = default_root().parent / f"{name}.zip"

        def run() -> None:
            try:
                self.log(f"Wrote {a.export_package(out, self.log)}")
            except Exception as e:  # noqa: BLE001
                self.log(f"EXPORT FAILED: {e}")

        threading.Thread(target=run, daemon=True).start()
        return ""


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def make_handler(state: RemoteState, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ReplicatorRemote"

        def log_message(self, *a) -> None:  # keep the console quiet
            pass

        def _authed(self) -> bool:
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            got = c["rt"].value if "rt" in c else ""
            return secrets.compare_digest(got.encode(), token.encode())

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self) -> None:
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            if "token" in q:  # first visit from the printed link: store the token in a cookie
                ok = secrets.compare_digest(q["token"][0].encode(), token.encode())
                if ok:
                    self._send(302, b"", "text/plain", {
                        "Location": "/", "Set-Cookie": f"rt={token}; Path=/; HttpOnly; SameSite=Strict"})
                else:
                    self._send(401, b"Wrong token", "text/plain")
                return
            if not self._authed():
                self._json({"error": "unauthorised"}, 401) if u.path.startswith("/api/") else \
                    self._send(401, b"Open the link with ?token=... printed on the PC.", "text/plain")
                return
            if u.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif u.path == "/api/state":
                self._json(state.snapshot(int(q.get("since", ["0"])[0] or 0)))
            else:
                self._send(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            if not self._authed():
                self._json({"error": "unauthorised"}, 401)
                return
            if "application/json" not in self.headers.get("Content-Type", ""):  # blocks cross-site form posts
                self._json({"error": "bad content type"}, 415)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                d = json.loads(self.rfile.read(min(n, 100_000)) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._json({"error": "bad json"}, 400)
                return
            route, name = self.path, str(d.get("name", ""))
            err = ""
            try:
                if route == "/api/capture":
                    err = state.start_capture(d)
                elif route == "/api/stop":
                    if state.stop_event:
                        state.stop_event.set()
                        state.log("Stopping after the current page...")
                elif route == "/api/play":
                    err = state.play(name)
                elif route == "/api/stopserver":
                    state.stop_server(name)
                elif route == "/api/delete":
                    err = state.delete(name)
                elif route == "/api/zip":
                    err = state.export_zip(name)
                else:
                    self._json({"error": "unknown"}, 404)
                    return
            except Exception as e:  # noqa: BLE001
                err = str(e)
            self._json({"ok": not err, "error": err}, 200 if not err else 400)

    return Handler


def run_remote(host: str = "127.0.0.1", port: int = 8765, lan: bool = False, open_browser: bool = True) -> None:
    token = secrets.token_urlsafe(18)
    state = RemoteState()
    bind = "0.0.0.0" if lan else host
    httpd = ThreadingHTTPServer((bind, port), make_handler(state, token))
    local = f"http://127.0.0.1:{port}/?token={token}"
    print(f"Remote control on this PC:  {local}")
    if lan:
        print(f"From your phone (same Wi-Fi): http://{lan_ip()}:{port}/?token={token}")
        print("Anyone on the network WITH this link can control the app - keep it private. Ctrl+C to stop.")
    else:
        print("Only this PC can reach it. Use --lan to open it to your phone. Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(local)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if state.stop_event:
            state.stop_event.set()
        for srv in list(state.servers.values()):
            srv.stop()
        httpd.server_close()
