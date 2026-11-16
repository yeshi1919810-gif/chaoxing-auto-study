# -*- coding: utf-8 -*-
"""
auto_loop_cdp.py - 超星刷课单进程全自动循环（实测可用版）

设计要点（均为线上实测踩坑后的修正，勿随意回退）：
  1. 类型判断必须用【内层】iframe 的 src（modules/video|work|document），
     外层 knowledge/cards 的 src 永远是 cards，用它判断只会得到 other。
  2. 已标记 .ans-job-finished 的卡片一律跳过，绝不重复刷。
  3. 视频播完必须等心跳（默认 8s）并【校验任务点变绿】，未变绿要加长等待，
     直接切章会导致进度丢失。
  4. "当前章节还有任务点未完成"确认弹窗要点里面的"下一节"，否则永远卡住。
  5. 播放倍数默认 1.0：超星播放器有风控会周期性重置倍速，强推 2x 意义不大，
     且可能触发风控；需要时用 --speed 2 显式开启。
  6. 视频"暂停"是常态（心跳上报/切前台都会暂停），每轮都唤回播放即可，
     但不要因为短暂暂停就判定卡死。

用法：
  python auto_loop_cdp.py                 # 默认 9222 端口、1.0 倍速
  python auto_loop_cdp.py --speed 2       # 显式 2 倍速
  python auto_loop_cdp.py --port 9333 --log run.log
"""
import argparse
import json
import time
import urllib.request

try:
    import websocket
except ImportError:
    raise SystemExit("缺少依赖：pip install websocket-client")


# ---------------------------------------------------------------- CDP 连接层
class CDP:
    def __init__(self, port=9222, tab_match="studentstudy"):
        self.base = f"http://127.0.0.1:{port}"
        self.tab_match = tab_match
        self.ws = None
        self._id = 0
        self.connect()

    def find_tab(self):
        tabs = json.load(urllib.request.urlopen(self.base + "/json", timeout=5))
        for t in tabs:
            if t.get("type") == "page" and self.tab_match in t.get("url", ""):
                return t
        # 退化：任意 http 页面
        for t in tabs:
            if t.get("type") == "page" and t.get("url", "").startswith("http"):
                return t
        return None

    def connect(self):
        tab = self.find_tab()
        if not tab:
            raise RuntimeError("TAB_NOT_FOUND: 没有找到学习页标签，请确认浏览器已打开 studentstudy 页面")
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=12)

    def ev(self, expr, timeout=12):
        """在主世界执行 JS 并取回返回值（JSON 字符串）。"""
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({
            "id": mid, "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True,
                       "awaitPromise": False, "timeout": timeout * 1000},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                return None
            if data.get("id") == mid:
                return data.get("result", {}).get("result", {}).get("value")
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# ------------------------------------------------------------------ JS 片段
# 扫描当前小节：类型、进度、卡片完成态；顺手处理弹窗题 + 唤回播放
SCAN = r"""
(function(){
  const out = {};
  const m = location.href.match(/chapterId=(\d+)/);
  out.chapterId = m ? m[1] : null;
  const mf = document.querySelector('#iframe');
  if (!mf || !mf.contentDocument) { out.type = 'no_frame'; return JSON.stringify(out); }
  const doc = mf.contentDocument;              // knowledge/cards 层
  const inner = doc.querySelector('iframe');   // 内层：modules/video|work|document
  const isrc = inner ? (inner.src || '') : '';
  out.isrc = isrc.slice(0, 100);
  const cards = doc.querySelectorAll('.ans-attach-ct');
  out.cardCount = cards.length;
  const card = cards[0];
  out.cardFinished = card ? card.classList.contains('ans-job-finished') : null;

  if (isrc.indexOf('modules/video') >= 0) {
    out.type = 'video';
    const vd = inner.contentDocument;
    if (!vd) { out.videoState = 'no_vframe'; return JSON.stringify(out); }
    const v = vd.querySelector('video');
    if (!v) { out.videoState = 'no_video_el'; return JSON.stringify(out); }
    out.ended  = !!v.ended;
    out.paused = !!v.paused;
    out.t   = Math.floor(v.currentTime);
    out.dur = Math.floor(v.duration || 0);

    // 视频内弹窗互动题：勾首个选项 + 提交
    const quiz = vd.querySelector('.ans-videoquiz, #videoquiz, .videoquiz');
    out.quiz = !!quiz;
    if (quiz) {
      const opt = quiz.querySelector('input[type="radio"], input[type="checkbox"], .ans-videoquiz-opt, li');
      if (opt) opt.click();
      const sb = quiz.querySelector('.ans-videoquiz-submit, button, .btn');
      if (sb) sb.click();
      out.quizActed = true;
    }
    // 保静音 + 暂停自动唤回（不强制改倍速）
    if (v.muted !== true) v.muted = true;
    if (v.paused && !v.ended && v.currentTime < (v.duration || 1e9) - 2) {
      try { v.play(); } catch (e) {}
    }
  } else if (isrc.indexOf('modules/work') >= 0) {
    out.type = 'quiz';
  } else if (isrc.indexOf('modules/document') >= 0 || isrc.indexOf('docid') >= 0) {
    out.type = 'doc';
    const dd = inner.contentDocument;
    if (dd) {
      const b = dd.body;
      if (b) b.scrollTop = b.scrollHeight;
      try { dd.documentElement.scrollTop = dd.documentElement.scrollHeight; } catch (e) {}
      out.scrolled = true;
    }
  } else {
    out.type = 'other';
  }
  return JSON.stringify(out);
})()
"""

# 顶层"下一节"按钮
CLICK_NEXT = r"""
(function(){
  const btn = document.querySelector('#prevNextFocusNext');
  if (btn) { btn.click(); return 'top_clicked'; }
  return 'no_btn';
})()
"""

# 未完成任务点确认弹窗里的"下一节"（叶子节点，避免嵌套误匹配）
POP_NEXT = r"""
(function(){
  const nc = document.querySelector('.nextChapter');
  if (nc && nc.offsetParent !== null) { nc.click(); return 'pop_next'; }
  const all = Array.from(document.querySelectorAll('a, span, div, button'));
  for (const el of all) {
    if (el.offsetParent === null) continue;
    const txt = (el.textContent || '').trim();
    if (txt === '下一节' && el.children.length === 0) { el.click(); return 'leaf_next'; }
  }
  return 'no_pop';
})()
"""


# -------------------------------------------------------------------- 主循环
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--speed", type=float, default=1.0,
                    help="播放倍速，默认 1.0；2.0 会被超星风控周期性重置")
    ap.add_argument("--tab-match", default="studentstudy")
    ap.add_argument("--log", default=None, help="日志文件路径（可选）")
    ap.add_argument("--heartbeat-wait", type=int, default=8)
    args = ap.parse_args()

    logf = open(args.log, "a", encoding="utf-8") if args.log else None

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    log(f"auto loop start (port={args.port}, speed={args.speed})")

    cdp = None
    ended_ts = None
    last_kid = None
    quiz_seen_ts = None
    idle_count = 0
    green_retry = 0
    last_t, stuck = -1, 0
    speed_logged = False

    while True:
        try:
            if cdp is None:
                cdp = CDP(args.port, args.tab_match)
            raw = cdp.ev(SCAN)
            d = json.loads(raw) if raw else {}
        except Exception as e:
            log(f"conn err: {e}, reconnect in 5s")
            try:
                cdp.close()
            except Exception:
                pass
            cdp = None
            time.sleep(5)
            continue

        typ = d.get("type")
        kid = d.get("chapterId")

        if typ in (None, "no_frame"):
            idle_count += 1
            if idle_count % 10 == 0:
                log("page loading or frame missing, waiting...")
            time.sleep(3)
            continue
        idle_count = 0

        if typ == "video":
            # 1) 已完成卡片：跳过，绝不重复刷
            if d.get("cardFinished"):
                log(f"chapter {kid}: video ALREADY FINISHED, skipping")
                r = cdp.ev(CLICK_NEXT)
                time.sleep(3)
                p = cdp.ev(POP_NEXT)
                log(f"skip finished: next={r} pop={p}")
                last_kid = ended_ts = None
                time.sleep(6)
                continue

            if not d.get("ended"):
                ended_ts = None
            if d.get("quizActed"):
                log("quiz popup answered!")

            t, dur = d.get("t"), d.get("dur")
            st = "ended" if d.get("ended") else ("paused" if d.get("paused") else "playing")
            if kid != last_kid:
                log(f"new chapter {kid}: video {dur}s")
                last_kid, last_t, stuck = kid, -1, 0

            # 可选倍速（默认关闭，风控会重置）
            if args.speed != 1.0:
                if not speed_logged:
                    log(f"speed={args.speed} requested; 注意播放器可能重置为 1x")
                    speed_logged = True
                cdp.ev(f"(function(){{const v=document.querySelector('video');"
                       f"if(v){{try{{v.playbackRate={args.speed};}}catch(e){{}}}}}})()")

            # 卡死提示（只告警，不切章）
            if t == last_t and not d.get("ended"):
                stuck += 1
                if stuck in (10, 40, 80):
                    log(f"WARN: 进度 {t}/{dur}s 已停滞约 {stuck*3}s，等待恢复")
            else:
                last_t, stuck = t, 0
            log(f"video {t}/{dur}s {st}")

            # 2) 播完：等心跳 -> 校验变绿 -> 推进
            if d.get("ended"):
                if ended_ts is None:
                    ended_ts = time.time()
                    log(f"video ended, waiting {args.heartbeat_wait}s heartbeat...")
                elif time.time() - ended_ts >= args.heartbeat_wait:
                    cur = {}
                    try:
                        cur = json.loads(cdp.ev(SCAN) or "{}")
                    except Exception:
                        cur = {}
                    if cur.get("cardFinished") or green_retry >= 4:
                        if green_retry >= 4 and not cur.get("cardFinished"):
                            log("WARN: still not green after retries, advancing anyway")
                        else:
                            log("task point GREEN -> advancing")
                        cdp.ev(CLICK_NEXT)
                        time.sleep(3)
                        cdp.ev(POP_NEXT)
                        log("advanced to next section")
                        ended_ts = green_retry = 0
                        last_kid = None
                        time.sleep(6)
                    else:
                        green_retry += 1
                        log(f"not green yet, extra wait ({green_retry}/4)")
                        ended_ts = time.time()
            time.sleep(3)

        elif typ == "quiz":
            if kid != last_kid:
                log(f"chapter {kid}: QUIZ found, skipping (no answer)")
                last_kid = kid
            if quiz_seen_ts is None:
                quiz_seen_ts = time.time()
            elif time.time() - quiz_seen_ts >= 4:
                r = cdp.ev(CLICK_NEXT)
                time.sleep(3)
                p = cdp.ev(POP_NEXT)
                log(f"skip quiz: next={r} pop={p}")
                quiz_seen_ts = None
                time.sleep(6)
            time.sleep(3)

        elif typ == "doc":
            log(f"chapter {kid}: document, scrolled")
            time.sleep(4)
            r = cdp.ev(CLICK_NEXT)
            time.sleep(3)
            p = cdp.ev(POP_NEXT)
            log(f"doc advance: next={r} pop={p}")
            last_kid = None
            time.sleep(6)

        else:
            if kid != last_kid:
                log(f"chapter {kid}: type={typ} src={d.get('isrc','')}")
                last_kid = kid
            time.sleep(5)


if __name__ == "__main__":
    main()
