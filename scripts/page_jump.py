# -*- coding: utf-8 -*-
"""强制跳章：绕过"当前章节还有任务点未完成"的拦截

章节测验不答（纯刷课模式）时，"下一节"按钮及其弹窗里的"下一节"都点不动，
唯一可靠的做法是直接把地址栏的 chapterId 换掉（enc 可跨章节复用）。

用法:
  # 直接跳到指定章节
  python page_jump.py --to 247520692
  # 按目录顺序从当前章节跳到下一章
  python page_jump.py --catalog order.json --next
  # 顺序表是扁平 chapterId 数组，如 ["247520668", "247520679", ...]
"""
import argparse, json, re, sys, time, urllib.request

try:
    import websocket
except ImportError:
    print("need: pip install websocket-client")
    sys.exit(1)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def find_tab(port, match):
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
    for t in tabs:
        if t.get("type") == "page" and match in t.get("url", ""):
            return t
    return None


class Tab:
    def __init__(self, t):
        self.ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=15)
        self.i = 0

    def ev(self, expr, timeout=15):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                 "params": {"expression": expr, "returnByValue": True,
                                            "awaitPromise": True}}))
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                return None
            if r.get("id") == mid:
                return r.get("result", {}).get("result", {}).get("value")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--tab-match", default="studentstudy")
    ap.add_argument("--to", help="目标 chapterId")
    ap.add_argument("--catalog", help="目录顺序 JSON（扁平 chapterId 数组或 {order:[...]})")
    ap.add_argument("--next", action="store_true", help="按目录取当前章节的下一章")
    args = ap.parse_args()

    tab = find_tab(args.port, args.tab_match)
    if not tab:
        log("TAB_NOT_FOUND")
        return
    t = Tab(tab)
    url = t.ev("location.href") or ""
    m = re.search(r"chapterId=(\d+)", url)
    if not m:
        log(f"not a chapter page: {url[:80]}")
        return
    cur = m.group(1)

    target = args.to
    if not target and args.next:
        raw = json.load(open(args.catalog, encoding="utf-8"))
        order = [str(x) for x in (raw if isinstance(raw, list) else raw.get("order", []))]
        if cur not in order:
            log(f"current {cur} not in catalog")
            return
        i = order.index(cur)
        if i + 1 >= len(order):
            log("already at last chapter")
            return
        target = order[i + 1]
    if not target:
        log("need --to or --next")
        return

    new = re.sub(r"chapterId=\d+", "chapterId=" + target, url)
    log(f"jump {cur} -> {target}")
    t.ev("location.href=" + json.dumps(new))
    time.sleep(8)
    log("now: " + str(t.ev("location.href"))[:110])


if __name__ == "__main__":
    main()
