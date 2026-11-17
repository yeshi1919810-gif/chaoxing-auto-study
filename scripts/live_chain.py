# -*- coding: utf-8 -*-
"""直播回放接力监控：第 1 场到阈值 -> 打开第 2 节直播 -> 监控第 2 场到阈值

只负责"盯着播 + 接力"，不负责启动浏览器。
用法:
  python live_chain.py --live1 5000268572614308 --chapter2 1272997990 \
      --course 265744998 --clazz 151099250 --enc <enc>

注意: 学习页只允许存在 1 个 studentstudy 标签（多开会被判多终端登录）。
"""
import argparse, json, sys, time, urllib.request

try:
    import websocket
except ImportError:
    print("need: pip install websocket-client")
    sys.exit(1)

ARGS = None


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def tabs():
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{ARGS.port}/json"))


def find(pred):
    for t in tabs():
        if t.get("type") == "page" and pred(t.get("url", "")):
            return t
    return None


class Tab:
    def __init__(self, t):
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15)
        self.i = 0

    def send(self, method, params=None, timeout=15):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                return None
            if m.get("id") == mid:
                return m
        return None

    def ev(self, expr, timeout=15):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": True}, timeout)
        if not r:
            return None
        return r.get("result", {}).get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


STATE = """
(function(){var v=document.querySelector('video');
if(!v) return JSON.stringify({none:true});
return JSON.stringify({t:Math.floor(v.currentTime),d:Math.floor(v.duration||0),
paused:!!v.paused,ended:!!v.ended});})()
"""

COORD = """
(function(){
  try{
    var top=document.querySelector('#iframe');
    if(!top||!top.contentDocument) return JSON.stringify({err:'no_top_frame'});
    var r0=top.getBoundingClientRect(), cd=top.contentDocument;
    var lv=cd.querySelector('iframe[src*="modules/live"]');
    if(!lv) return JSON.stringify({err:'no_live_iframe'});
    var r1=lv.getBoundingClientRect();
    var card=lv.contentDocument.querySelector('.liveHref');
    if(!card) return JSON.stringify({err:'no_card'});
    var r2=card.getBoundingClientRect();
    return JSON.stringify({x:Math.round(r0.left+r1.left+r2.left+r2.width/2),
                           y:Math.round(r0.top+r1.top+r2.top+r2.height/2)});
  }catch(e){return JSON.stringify({err:e.message});}
})()
"""


def wait_live(live_id, threshold, label=""):
    """监控某个直播回放到 threshold 比例（0~1）"""
    log(f"{label}watch {live_id} until {int(threshold*100)}%")
    tab, last = None, None
    while True:
        if tab is None:
            t = find(lambda u: live_id in u and "zhibo.chaoxing.com" in u)
            if not t:
                log("live tab not found, retry 10s")
                time.sleep(10)
                continue
            tab = Tab(t)
        raw = tab.ev(STATE)
        try:
            d = json.loads(raw) if raw else {}
        except Exception:
            d = {}
        if d.get("none"):
            log("no video element, retry")
            tab.close(); tab = None; time.sleep(8); continue
        t_, dur = d.get("t") or 0, d.get("d") or 0
        pct = (t_ * 100.0 / dur) if dur else 0
        if (t_, dur) != last:
            log(f"{label}{t_}/{dur}s ({pct:.1f}%) paused={d.get('paused')}")
            last = (t_, dur)
        if d.get("paused") and not d.get("ended"):
            tab.ev("(function(){var v=document.querySelector('video');"
                   "if(v){v.muted=true;v.play();return 'play';}return 'no';})()")
        if d.get("ended") or pct >= threshold * 100:
            log(f"{label}reach {pct:.1f}% -> done")
            tab.close()
            return True
        time.sleep(30)


def open_next_live(chapter2):
    """把学习页导航到下一节并真实点击直播卡片，返回新直播 liveId"""
    log("navigate study page to next chapter")
    t = find(lambda u: "studentstudy" in u)
    if not t:
        log("study tab missing")
        return None
    tab = Tab(t)
    url = (f"https://mooc1.chaoxing.com/mooc-ans/mycourse/studentstudy?chapterId={chapter2}"
           f"&courseId={ARGS.course}&clazzid={ARGS.clazz}&enc={ARGS.enc}")
    tab.send("Page.navigate", {"url": url})
    time.sleep(10)
    tab.send("Page.bringToFront")
    time.sleep(2)
    c_raw = tab.ev(COORD)
    log(f"coord: {c_raw}")
    try:
        c = json.loads(c_raw)
    except Exception:
        c = {}
    if "x" not in c:
        log("locate live card failed")
        tab.close()
        return None
    x, y = c["x"], c["y"]
    tab.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    tab.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                          "button": "left", "clickCount": 1})
    tab.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                          "button": "left", "clickCount": 1})
    tab.close()
    time.sleep(10)

    for _ in range(20):
        t2 = find(lambda u: "zhibo.chaoxing.com" in u and ARGS.live1 not in u)
        if t2:
            new_id = t2["url"].split("zhibo.chaoxing.com/")[1].split("?")[0]
            log(f"lecture 2 opened: {new_id}")
            nt = Tab(t2)
            nt.send("Page.bringToFront")
            time.sleep(2)
            nt.ev("(function(){var v=document.querySelector('video');"
                  "if(v){v.muted=true;var p=v.play();if(p&&p.catch)p.catch(function(){});return 'ok';}return 'no';})()")
            nt.close()
            return new_id
        time.sleep(5)
    return None


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--live1", required=True, help="第 1 场直播 liveId")
    ap.add_argument("--chapter2", required=True, help="第 2 场直播所在章节 chapterId")
    ap.add_argument("--course", required=True)
    ap.add_argument("--clazz", required=True)
    ap.add_argument("--enc", required=True, help="studentstudy 的 enc 参数")
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="切下一场的阈值（默认 0.95；任务点完成判据是 90%%）")
    ARGS = ap.parse_args()

    log("=== live chain start ===")
    wait_live(ARGS.live1, ARGS.threshold, "[1] ")
    new_id = open_next_live(ARGS.chapter2)
    if not new_id:
        log("FAILED to open lecture 2")
        return
    wait_live(new_id, ARGS.threshold, "[2] ")
    log("=== ALL LECTURES DONE ===")


if __name__ == "__main__":
    main()
