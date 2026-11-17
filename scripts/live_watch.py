# -*- coding: utf-8 -*-
"""直播回放监控：保持静音播放、自动恢复暂停、打印进度，播完退出。"""
import json, urllib.request, time, sys
import websocket

BASE = "http://127.0.0.1:9222"
KEY = "zhibo.chaoxing.com"

EVAL = r"""
(function(){
  var v = document.querySelector('video');
  if (!v) return JSON.stringify({err:'no_video'});
  if (v.muted !== true) v.muted = true;
  if (v.paused && !v.ended) { try { v.play(); } catch(e){} }
  return JSON.stringify({t: Math.floor(v.currentTime), d: Math.floor(v.duration||0),
                         paused: !!v.paused, ended: !!v.ended, rate: v.playbackRate,
                         vis: document.visibilityState});
})()
"""

def tab():
    for t in json.load(urllib.request.urlopen(BASE + "/json")):
        if t.get("type") == "page" and KEY in t.get("url", ""):
            return t
    return None

def main():
    ws = None
    last_log = 0
    while True:
        try:
            if ws is None:
                t = tab()
                if not t:
                    print("[wait] zhibo tab not found", flush=True)
                    time.sleep(5); continue
                ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": EVAL, "returnByValue": True}}))
            data = None
            deadline = time.time() + 8
            while time.time() < deadline:
                m = json.loads(ws.recv())
                if m.get("id") == 1:
                    data = m; break
            if not data:
                time.sleep(3); continue
            raw = data["result"]["result"].get("value")
            st = json.loads(raw) if raw else {}
            if st.get("err"):
                print("[warn]", st["err"], flush=True)
            else:
                now = time.time()
                if now - last_log >= 30:
                    pct = round(st["t"] * 100.0 / st["d"], 1) if st.get("d") else 0
                    print(f"[{time.strftime('%H:%M:%S')}] live {st['t']}/{st['d']}s ({pct}%) "
                          f"paused={st['paused']} vis={st['vis']}", flush=True)
                    last_log = now
                if st.get("ended") or (st.get("d") and st["t"] >= st["d"] - 3):
                    print("[done] replay finished", flush=True)
                    break
            time.sleep(3)
        except Exception as e:
            print("[err]", e, flush=True)
            try:
                ws.close()
            except Exception:
                pass
            ws = None
            time.sleep(5)

if __name__ == "__main__":
    main()
