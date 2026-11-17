# -*- coding: utf-8 -*-
"""把「阅读」小节里的多个 PDF 卡片逐个滚动到底，触发阅读进度上报。"""
import json, subprocess, sys, time

BASE = "C:/Users/实哥/WorkBuddy/2026-11-16-13-02-04"

def run(js, frame, timeout="20"):
    r = subprocess.run([sys.executable, "cdp_frame_eval.py", js, frame, timeout],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8")
    try:
        d = json.loads(r.stdout)
        return json.loads(d["result"]["result"]["value"])
    except Exception:
        return {"_raw": r.stdout[:200], "_err": r.stderr[:200]}

def scroll_to_end(idx, max_steps=160, delay=0.5):
    frame = "screen/v2/file|%d" % idx
    last = None
    for i in range(max_steps):
        st = run("pdf_scroll.js", frame)
        if "_err" in st:
            return {"idx": idx, "err": st}
        last = st
        if st.get("done"):
            return {"idx": idx, "steps": i + 1, **st}
        time.sleep(delay)
    return {"idx": idx, "steps": max_steps, "last": last, "timeout": True}

def cards():
    st = run("scan_cards.js", "knowledge/cards")
    return st.get("cards", [])

if __name__ == "__main__":
    targets = [int(x) for x in sys.argv[1:]] or [0]
    for idx in targets:
        print("=== PDF frame", idx, "===")
        print(json.dumps(scroll_to_end(idx), ensure_ascii=False))
        time.sleep(2)
        for c in cards():
            print("  card", c["idx"], "finished=", c["finished"])
