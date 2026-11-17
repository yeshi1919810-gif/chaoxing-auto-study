---
name: chaoxing-auto-study
description: >-
  自动化进行超星尔雅/学习通高校网课刷课的标准化工作流。涵盖 Windows 系统防熄屏挂机设置、
  独立调试端口浏览器接管、多层 iframe 穿透、静音播放（倍速可选，默认 1.0）、视频弹窗测验自动跳过、课件文档快速通关、
  已完成任务点自动跳过（不重复刷）、播完变绿校验以及章节测验题库核对与提交全流程。
  当用户需要进行超星网课自动化挂机、批量完成视频与课件任务点时使用。
---

# 超星学习通全自动刷网课 Skill 指南

本 Skill 沉淀了超星平台（泛雅 / 尔雅 / 学习通）网课自动化的完整落地流程与规避风控的最佳实践。

> **先读这段**：本文档中标记 ⚠️ 的地方都是真机实测踩过的坑，脚本已按"实测修正"实现，
> 不要凭直觉改回看似更简洁的写法。

## 推荐执行方式（按优先级）

| 方式 | 适用场景 | 入口 |
| :--- | :--- | :--- |
| **单进程全自动循环（首选）** | 挂机刷完整门课，无需人工衔接 | `scripts/auto_loop_cdp.py` |
| Node 批量遍历 | 需要按目录清单逐节跑、要进度持久化 | `scripts/auto_runner.js` |

```bash
# 全自动循环：默认 1.0 倍速，遇到测验跳过，播完自动推进直到课程末尾
python scripts/auto_loop_cdp.py --port 9222 --log run.log

# 需要 2 倍速时显式开启（超星会周期性重置回 1x，别指望稳定 2x）
python scripts/auto_loop_cdp.py --speed 2
```

---

## 核心流程与执行步骤

```mermaid
flowchart TD
    A["1. 环境准备与防熄屏"] --> B["2. 启动带调试端口的浏览器 (CDP 9222)"]
    B --> C["3. 用户登录并锁定目标课程"]
    C --> D["4. 全量扫描章节目录与已完成状态"]
    D --> E["5. 逐节自动化推进"]
    E --> F{"任务点类型判断"}
    F -->|"已标记完成"| G["跳过该节点 (不重复刷)"]
    F -->|"课件 / PDF"| H["滚动阅读 + 心跳触发秒通"]
    F -->|"视频"| I["静音播放（默认1.0x）+ 弹窗题秒解 + 8s 心跳 + 变绿校验"]
    F -->|"单元测验"| J["根据策略跳过或题库匹配答题"]
    G --> K["进入下一小节"]
    H --> K
    I --> K
    J --> K
    K --> L{"全部章节完成?"}
    L -->|"否"| E
    L -->|"是"| M["6. 生成通关验收报告与截图"]
```

---

## 第一步：Windows 系统防熄屏锁定（挂机前必备）

长周期挂机最容易因为电脑黑屏、休眠导致网络断开或浏览器挂起。

* **执行命令**：
  运行 [keep_awake.ps1](./scripts/keep_awake.ps1) 或在 PowerShell 中执行：
  ```powershell
  powercfg /change monitor-timeout-ac 0
  powercfg /change standby-timeout-ac 0
  powercfg /change monitor-timeout-dc 0
  powercfg /change standby-timeout-dc 0
  ```
* **验证状态**：
  确认 `VIDEOIDLE` 与 `STANDBYIDLE` 均为 `0x00000000`（永不熄屏、永不待机）。

---

## 第二步：启动自动化调试浏览器（CDP 端口 9222）

日常双击打开的 Chrome / Edge 受系统沙盒保护，外部程序无法直接注入。必须通过特定参数拉起：

1. **规避 Chromium 调试限制**：
   * 现代 Chrome (120+) 禁止在默认 `User Data` 目录启用 `--remote-debugging-port`，且加密 Cookies 绑定路径。
   * **最佳实践**：使用独立的调试配置目录，如 `--user-data-dir="D:\chrome_debug_profile"`。
2. **解决交互桌面 Session 隔离问题**：
   * 通过 Windows 任务计划程序 (`schtasks`) 在前台用户会话中启动，确保前台最大化显示窗口供用户扫码。
   * 参考启动脚本：[launch_browser.cmd](./scripts/launch_browser.cmd)。
   ```cmd
   "D:\Chrome\Application\chrome.exe" ^
     --remote-debugging-port=9222 ^
     --remote-allow-origins=* ^
     --user-data-dir="D:\chrome_debug_profile" ^
     --start-maximized ^
     --disable-background-timer-throttling ^
     --disable-backgrounding-occluded-windows ^
     --disable-renderer-backgrounding ^
     --disable-features=CalculateNativeWinOcclusion ^
     --autoplay-policy=no-user-gesture-required ^
     "https://i.chaoxing.com"
   ```
   > **⚠️ 末尾 5 个 `--disable-*` / `--autoplay-*` 参数不能省**：窗口一旦最小化或**被其他窗口完全遮住**，
   > Chrome 的遮挡检测（`CalculateNativeWinOcclusion`）会把页面判定为 `hidden`，定时器与渲染被节流，
   > 播放速度会从 1.0x 掉到 **约 0.3x**（实测：231 秒墙钟只推进 69 秒视频，期间出现 90 秒级长暂停）。
3. **连接验证**：
   * 访问 `http://127.0.0.1:9222/json/version` 确认端口连通。
   * 用 `document.visibilityState` 检查是否被节流：返回 `visible` 才正常，`hidden` 说明窗口被遮挡/最小化。
   * 若窗口已被最小化，可用 CDP 恢复：`Browser.getWindowForTarget` 取 windowId →
     `Browser.setWindowBounds` 设 `windowState: "normal"`（仅恢复窗口还不够，标签页还需 `Page.bringToFront`）。

---

## 第三步：课程定位与参数提取

用户登录后，进入课程详情页（`mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu`），从 URL 中提取 5 大核心参数：
* `courseid`：课程 ID
* `clazzid`：班级 ID
* `cpi`：用户唯一标识
* `enc`：动态加密密钥
* `openc`：开放密钥

*学习页基础 URL 范式*：
```text
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId={chapterId}&courseId={courseId}&clazzid={clazzId}&cpi={cpi}&enc={enc}&mooc2=1&hidetype=0&fanyaVersion=0&openc={openc}
```

---

## 第四步：已刷检测与任务点遍历（不重复刷）

### 1. 目录级跳过判断
在右侧目录 `#cells` 中定位每个章节节点 `#cur{chapterId}`：
* 若包含 `.icon_Completed`：说明该小节**全部任务点已通关**，直接跳过。

### 2. 卡片级跳过判断
对于未完全绿标的小节，进入页面穿透 `knowledge/cards` Iframe：
* 检查每个任务容器 `.ans-attach-ct`：
  * 若具有类名 `.ans-job-finished`：说明此任务点**已完成**，直接跳过。
  * 仅对**未包含** `.ans-job-finished` 的视频或文档进行处理。

---

## 第五步：自动化刷课核心逻辑（视频与文档）

* 单进程全自动循环：[auto_loop_cdp.py](./scripts/auto_loop_cdp.py)
* Node 批量遍历：[auto_runner.js](./scripts/auto_runner.js)

### 0. ⚠️ 类型判断必须用【内层】iframe 的 src

```javascript
const outer = document.querySelector('#iframe');        // knowledge/cards 层
const doc = outer.contentDocument;
const inner = doc.querySelector('iframe');              // 内层：modules/video|work|document
const src = inner ? inner.src : '';
// 正确：用 inner.src 判断 video / work / document
// 错误：用 outer.src 判断，它永远是 "knowledge/cards"，只会得到 other，循环会一直空转
```
> 这是最容易写错、也最难从日志看出来的一处：表现为"脚本在跑但永远不识别任何任务点"。

### 1. 视频多层 Iframe 穿透与控制
* **Iframe 路径**：
  `studentstudy` -> `iframe(knowledge/cards)` -> `iframe(ans-insertvideo-online)` -> `iframe(/ananas/modules/video/index.html)`
* **播放控制（video.js / HTML5）**：
  ```javascript
  const v = document.querySelector('video');
  if (v) {
    v.muted = true;             // 必须静音，防止浏览器阻止自动播放
    v.playbackRate = 1.0;       // 默认 1.0；2.0 会被风控重置，见下方说明
    v.play();
  }
  const btn = document.querySelector('.vjs-big-play-button');
  if (btn) btn.click();
  ```
* **⚠️ 倍速不要死磕**：实测超星播放器会"周期性把 `playbackRate` 重置回 1x"，
  且自带倍速菜单被风控隐藏。强推 2.0 的收益不稳定，还可能踩风控。
  默认按 1.0 真实时长播放；用户明确要求时才用 `--speed 2`，并接受被重置。
* **暂停是常态**：心跳上报、切前台、缓冲都会触发 `paused`，短则 3~6 秒，长可达 60~70 秒。
  每轮巡检唤回 `play()` 即可，**不要因为短暂暂停就判定卡死或切章**。

### 2. 视频弹窗互动测验秒解
视频播到特定时间点常会弹出选择题中断播放。每 3 秒检测一次：
```javascript
const quiz = document.querySelector('.ans-videoquiz, #videoquiz, .videoquiz');
if (quiz) {
  // 自动勾选首个选项
  const opt = quiz.querySelector('input[type="radio"], input[type="checkbox"], .ans-videoquiz-opt, li');
  if (opt) opt.click();
  // 自动点击提交关闭
  const submitBtn = quiz.querySelector('.ans-videoquiz-submit, button, .btn');
  if (submitBtn) submitBtn.click();
}
```

### 3. 多媒体心跳同步（防掉进度）
* 当视频达到终点（`v.ended || cur >= dur - 1`）：
* **必须等待 8 秒**，让超星的 `/multimedia/log/a/...` 心跳数据完全上报至服务器后再切换下一节。
* **⚠️ 8 秒不够就校验，别盲等**：8 秒后重新读 `.ans-attach-ct` 是否带 `.ans-job-finished`：
  * 已变绿 → 切下一节；
  * 未变绿 → 说明心跳未回传，再等 8 秒重试，最多 4 轮；仍不绿则记录 WARN（可能是网络或视频未真正播完）。
* **⚠️ 计时器状态机别每轮重置**：`ended_ts` 只在"进入结束态"时赋值一次，
  循环里若无脑 `ended_ts = null` 会导致"永远等不满 8 秒"，表现为视频播完后僵死不动。

### 4. 课件与 PDF 通关
* 定位文档类 Iframe（`modules/document` 或含 `docid`），执行
  `body.scrollTop = body.scrollHeight` 且同时设置 `documentElement.scrollTop`，停留 3 秒触发阅读进度上报。
* 只滚外层 cards iframe 是无效的——阅读进度在文档内层 iframe 里统计。

### 5. ⚠️ 未完成任务点确认弹窗
点"下一节"时，若本节还有未完成任务（典型就是**跳过的测验**），会弹出
**"当前章节还有任务点未完成，是否去完成？"**。此时按钮在弹窗里：

```javascript
// 优先专用类名
const nc = document.querySelector('.nextChapter');
if (nc && nc.offsetParent !== null) nc.click();
// 兜底：全局找可见的、无子元素的"下一节"文本节点（避免匹配到外层容器）
```
> 不处理这个弹窗，就会一直卡在当前小节，日志看起来一切正常但章节号不变——
> 判别方法：连续多轮 `chapterId` 完全相同且都在 quiz 分支。

---

## 第六步：章节测验与作业策略

1. **纯刷课模式**：识别到测验卡片（含有 `work/dowork` 或 `TiMu`）时跳过不提交。
   * 注意：跳过后目录里该小节**仍显示"N 个待完成任务点"**，这是预期现象，不是刷课失败。
2. **答题模式**：
   * 结合用户提供的题库文档（如 DOCX/ZIP/PDF）。
   * 题目使用模糊文字匹配（去掉标点与序号）。
   * 选项优先读取 `aria-label` 规避超星前台选项乱序混淆。
   * 提交前执行选项二次核对并截图留存。

---

## 核心排错速查表

| 症状 | 根本原因 | 解决方案 |
| :--- | :--- | :--- |
| **`enc校验失败`** | 直接拼接 URL 导致加密 token 不一致 | 从课程主页点击章节，或通过 `toOld()` 接口生成的合法 URL 跳转 |
| **浏览器端口连不上** | 默认目录限制或进程残留 | 使用独立 `--user-data-dir` 并通过 `schtasks` 在前台启动 |
| **脚本在跑但识别不到任务点（type=other）** | 用了外层 `knowledge/cards` 的 src 判断类型 | 改用内层 iframe 的 src（`modules/video|work|document`） |
| **视频卡在某秒不动** | 触发了视频内嵌互动测验 | 检测 `.ans-videoquiz`，自动点击选项并提交跳过 |
| **视频播完任务点没绿** | 切章太快，心跳未回传 | 8 秒后**校验** `.ans-job-finished`，未绿则每 8 秒重试，最多 4 轮 |
| **视频播完循环僵住不推进** | `ended_ts` 每轮被重置，永远等不满心跳窗口 | 结束态只赋值一次，用独立状态机 |
| **连续多轮 chapterId 不变** | 未处理"还有任务点未完成"确认弹窗 | 点弹窗内 `.nextChapter` 或可见的"下一节"叶子节点 |
| **倍速总被改回 1x** | 播放器风控周期性重置 `playbackRate` | 默认 1.0 播放，不强推 2x |
| **ElementHandle.click 假死** | 跨域/跨层 iframe 坐标计算死锁 | 使用 `evaluate(() => el.click())` 或直接调用 `video.play()` |
| **鼠标移开/切窗口后视频暂停** | 心跳上报与失焦导致 `paused` | 每 3 秒巡检唤回 `play()`；长暂停（≤70s）属正常，勿切章 |
| **最小化 / 被遮挡后播放变极慢（约 0.3x）** | Chrome 遮挡检测把页面判为 `hidden`，定时器与渲染被节流 | 启动时加 `--disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion`；或保持窗口可见（分屏） |
| **想确认是否被节流** | 无直观信号 | 读 `document.visibilityState`：`visible` 正常，`hidden` 说明窗口被遮挡/最小化 |
| **标签被强制跳到 `detect.chaoxing.com/api/monitor_temp`，提示"多终端登录"** | 同一账号同时开了**两个** `studentstudy` 章节页（哪怕只是打开来核对进度） | 只保留 1 个章节页；把跳走的标签导航回原章节即可续播，不要重新登录 |
| **脚本一启动就 `UnboundLocalError: SPEED`** | 函数内后面对 `SPEED` 有回落赋值，Python 视为局部变量 | 在函数首行加 `global SPEED` |
| **倍速"回落 1x"完全不生效** | 扫描表达式在模块导入时 `.replace("SPEED", ...)` 把倍速**固化**进 JS 字符串 | 不要在 import 期替换，改成每轮 `scan_expr()` 现拼表达式 |
| **长任务跑一会儿就没了 / 日志只有一行启动标记** | 用 `nohup ... &` 或父进程 `Popen` 起的子进程，会话结束被连带杀掉 | 改用工具托管的后台任务（`run_in_background`）直接跑脚本本体 |
| **用 python `urllib` 请求学习通接口后账号告警** | UA / 指纹与浏览器不一致，被判成另一台终端 | 一切读写都走 CDP 在真实页面里执行，不要绕过浏览器调用接口 |
| **`type=other` 且 isrc 是 `modules/pdf`，点"下一节"原地打转** | 章节里除了视频还有一个"本章PPT"阅读卡片，被当成未知类型 | 识别 `modules/pdf`，对 `pan-yz` 跨域帧逐帧滚到底，变绿后再推进 |
| **章节测验没答，点"下一节"毫无反应** | 学习通拦截：本章还有任务点未完成，弹窗按钮点不动 | 按目录顺序直接 `location.href` 改成下一章 `chapterId` 强制跳章 |


---

## 阅读（PDF）与直播回放任务点

### 1. 阅读 / PDF 任务点（`ananas/modules/pdf/index.html`）
* **关键**：外层 `modules/pdf` 的 `document` 滚动**完全无效**，任务点只在真正的阅览器里累计——
  实际帧是跨域的 `https://pan-yz.chaoxing.com/screen/v2/file_<hash>`。
* 必须用 CDP `Page.createIsolatedWorld` 在该跨域帧内执行滚动：
  ```javascript
  var se = document.scrollingElement;
  var step = Math.floor(se.clientHeight * 0.8);
  se.scrollTop = Math.min(se.scrollHeight - se.clientHeight, se.scrollTop + step);
  window.dispatchEvent(new Event('scroll'));
  ```
  每步间隔 0.5~1.2s，滚到底后 `~3s` 内该卡片会变成 `ans-job-finished`。
* **一个小节多张同类卡片时**：frame 顺序与卡片顺序一致，用「第 N 个匹配 frame」逐个滚完即可。
  参考实现：[pdf_scroll.js](./scripts/pdf_scroll.js) / [pdf_finish.py](./scripts/pdf_finish.py)。

### 2. 直播回放任务点（`ananas/modules/live/index.html`）
* 卡片是 `javascript:void(0)` + jQuery 绑定，`element.click()` **常常无效**（`window.open` 被浏览器拦截）。
  → 改用 CDP 真实鼠标事件：
  ```python
  Input.dispatchMouseEvent(type='mousePressed'/'mouseReleased', x=..., y=..., button='left')
  ```
  坐标 = 顶层 `#iframe` rect + `cards` 内 live iframe rect + `.liveHref` rect 逐级相加。
* 点击后会打开新标签 `https://zhibo.chaoxing.com/<liveId>?...`，里面是 `video`（`blob:` 源）。
* 完成条件是**观看时长达总时长 90%**，无法快进，且提示「不要最小化/切到其他网页」。
  参考监控脚本：[live_watch.py](./scripts/live_watch.py)（静音 + 暂停自动恢复 + 进度日志）。

### 3. 循环遇到未知类型不要僵死
`type=other` 连续停留超过 90s 应记录告警并强制推进，否则整条循环会像本次一样静默卡住数小时。

---

## 多终端判定：单章节页铁律（踩过坑，务必遵守）

为核对"某个章节到底绿没绿"，在**第二个标签**里打开同一账号的另一个 `studentstudy` 章节页，
会立刻触发风控页：

```
https://detect.chaoxing.com/api/monitor_temp?mes=您的账号于HH:MM在一台谷歌内核浏览器设备登入章节页面。
多终端登录可能会被判定异常学习。如非本人操作，请尽快修改密码
```

后果：**正在播放的那个章节页会被强制跳走**，视频停住、进度不再累计（已累计的时长不会丢）。

处理与规矩：
1. **同一时刻只允许存在 1 个 `mooc1.chaoxing.com/.../studentstudy` 标签页。**
2. 需要核对别的章节 → 等整门课刷完再核对，或直接导航当前标签（会打断播放，别在跑课时做）。
3. 已被跳走时：把该标签**导航回原章节 URL** 即可，登录态还在，不用重新扫码；循环脚本会自己重连并续播。
4. 顺手把多余的 `zhibo.chaoxing.com`、`detect` 标签关掉，用 `curl http://127.0.0.1:9222/json/close/<id>`。
5. 不要用 python 直接 `urllib` 请求 `mooc1` 接口去"只读查询"状态——UA/指纹不同，一样算另一终端。

---

## 倍速的四个隐藏坑

### 1. `global` 缺失会直接崩
```python
SPEED = float(os.environ.get("SPEED", "2.0"))

def main():
    global SPEED            # ← 少了这行，下面一赋值 SPEED 就变局部变量
    log(f"start SPEED={SPEED}")   # UnboundLocalError
    ...
    SPEED = 1.0             # 回落
```

### 2. 别在 import 期把倍速拼进 JS
```python
SCAN = """... v.playbackRate = SPEED ...""".replace("SPEED", str(SPEED))   # ❌ 固化，运行期改不动
```
正确做法是保留占位符，每轮现拼：
```python
def scan_expr():
    return SCAN.replace("SPEED", str(SPEED))
```
这样"连续被重置 → 回落 1.0"才真正落到页面上。

### 3. 倍速上限是播放器决定的，`video.js` 只到 2x

超星的视频播放器是 **video.js**，播控条上有 `.vjs-playback-rate` 菜单，选项写死：
`0.75x / 1x / 1.25x / 1.5x / 2x`——**没有 3x、4x**。

坑在于**即时读回会骗人**：
```js
v.playbackRate = 3;   // 同一 tick 读 v.playbackRate → 返回 3，看着"成功了"
// 下一帧 video.js 的 ratechange 监听把它拽回去，实际落在 1 或 2
```
正确判定方式必须**等 3 秒再读一次**：
```python
cdp.ev("...v.playbackRate=3; return 'ok'")
time.sleep(3)
print(cdp.ev("...return v.playbackRate"))   # 这一枪才是真实值
```

实测三种设法的结果：

| 设法 | 结果 |
| :--- | :--- |
| `v.playbackRate = 3` / `= 4` | ❌ 即时读回 3/4，3 秒后回落 1，且 1↔2 抖动，等效约 1.5x |
| `player.playbackRate(2)`（video.js API） | ❌ 返回 1，被 clamp（`playbackRates()` 为空、`options_.playbackRates` 才是 `[0.75,1,1.25,1.5,2]`） |
| **`SPEED=2.0` 让扫描表达式每轮强设 2** | ✅ 稳定 2x，每 3 秒推进 6 秒，可连续跑几小时 |

结论：**别碰 3x/4x，2.0 就是天花板**。另外注意个别章节会整体禁倍速（菜单点了没反应、rate 恒为 1），
这种章节等它 1x 播完即可，下一章 `speed_tried` 会重新试探回 2x，不要中途改代码。

---

## 章节测验：别重试，第一次就跳

`modules/work` 类型的章节是**章节测验**，不答题时"下一节"和弹窗按钮全部无效。
早期写法是判两次才 `force_next`，每次白等 10 秒以上。正确做法是**第一次跳不出去就改 URL**：

```python
if str(cur.get("chapterId")) == str(kid):
    log("quiz blocks chapter -> force jump")
    force_next(cdp, kid)      # 不再 stuck>=2 重试
```

配合"落地轮询"，跳章也比死等快：
```python
cdp.ev("location.href=" + json.dumps(new))
deadline = time.time() + 16
while time.time() < deadline:
    time.sleep(1.2)
    cur2 = cdp.ev(r"(function(){var m=location.href.match(/chapterId=(\d+)/);return m?m[1]:'';})()")
    if cur2 and str(cur2) != str(cur):   # 切到就走，通常在 8-11s
        return True
```
`sleep(9)` 死等改成轮询后，每次跳章省 4-5 秒；两者合计每次挡章少耗约 15 秒。

### 末章必须写退出条件（否则永远空转）

跳到最后一节后，如果这节还挂着没答的测验，`force_next` 会返回 `False`（"already at last chapter"），
而调用方只关心"跳没跳"，于是下一轮又重新判定 quiz → 又调 `force_next` → 又失败……

实测在末节这样空转了 **2 小时 41 分**（每 11 秒一轮，约 870 次无效请求），日志刷满却什么都没干。
正确写法是把失败当终止信号：

```python
if stuck >= 1:
    log("quiz blocks chapter -> force jump")
    if not force_next(cdp, kid) and CATALOG and str(kid) == CATALOG[-1]:
        log("COURSE DONE: 末章已到，只剩未答的测验 -> 退出")
        return           # 直接结束主循环，别在最后一节打转
    stuck = 0
```

判据：**末节 + 有测验 + 视频已绿** 就是这门课在「不答测验」前提下的终态，该退出而不是重试。

---


## 长任务保活

| 启动方式 | 结果 |
| :--- | :--- |
| `nohup python loop.py &` | ❌ 会话结束即被杀，日志只剩一行启动标记 |
| 父脚本 `subprocess.Popen(...)` | ❌ 父进程退出时子进程被连带清理 |
| 工具托管后台任务（`run_in_background`） | ✅ 实测连续跑 2 小时无中断 |

推论：**不要在自动化脚本里再套一层"启动器"**。接力逻辑可以写成"等条件满足 → 打印下一步该做什么"，
真正的长跑进程由外部托管直接拉起。

---

## 多课程串行接力

一门课的最后任务是直播回放（几十分钟且不能快进）时，可以写个链式监控，避免人工守着切课：

* [live_chain.py](./scripts/live_chain.py)：监控第 1 场到阈值（默认 95%）→ 导航学习页到第 2 节 →
  真实鼠标点击 `.liveHref` → 继续监控第 2 场 → 打印 `ALL LECTURES DONE`。
  ```bash
  python live_chain.py --live1 5000268572614308 --chapter2 1272997990 \
      --course 265744998 --clazz 151099250 --enc <enc>
  ```
* 直播回放**播到 100% 自然结束**最稳；阈值只用来决定"何时切下一场"，别拿阈值当完成判据。
* 切换下一门前，先确认目标课程页 `enc` 仍然有效（直接导航试一次），失效就回课程主页重点一次章节重新取。

---

## 章节内多卡片：PDF 与测验拦截

一个章节**不止一张卡片**。实测管理学 3.1 = 视频 + 2 个"本章PPT"(PDF) + 1 个章节测验，
只处理视频会导致循环在原地反复点"下一节"而永不前进。

### 1. 识别与处理顺序
按内层 iframe 的 src 分流：`modules/video` → `modules/pdf` → `modules/document` → `modules/work`。
`modules/pdf` **不能**归到 `other`，否则就是死循环。

### 2. PDF 在跨域帧里，必须逐帧滚
一个章节可能有**多个** PDF 卡片，对应**多个** `pan-yz.chaoxing.com/screen/v2/file_*` 帧：
```python
fr = [f for f in cdp.frames() if "screen/v2/file" in (f.get("url") or "")]
for i in range(len(fr)):
    while True:
        st = cdp.ev_frame("screen/v2/file", PDF_SCROLL, i)   # createIsolatedWorld + evaluate
        if json.loads(st).get("done"): break
        time.sleep(0.5)
```
实测 37 步 + 56 步滚完（两个 16k / 24k 像素长的文档），约 50s 后卡片变绿。

### 3. 测验拦截：只能强制跳章
章节测验不答（纯刷课模式）时，"下一节"按钮点了没反应，
弹窗「当前章节还有任务点未完成」里的"下一节"**在 JS 里也点不动**（点击后 URL 不变）。

可靠做法是绕过按钮，直接按目录顺序改地址：
```python
new = re.sub(r"chapterId=\d+", "chapterId=" + next_id, location_href)
cdp.ev("location.href=" + json.dumps(new))
```
`next_id` 来自刷课前抓好的目录顺序表（`chapterId` 扁平数组），`enc` 沿用当前 URL 里的即可，
实测同一门课跨章节复用 `enc` 有效。

**判定时机**：点完"下一节"等 5s 重新扫描，若 `chapterId` 没变就计数，连续 2 次没变即强制跳章。
现成脚本：[page_jump.py](./scripts/page_jump.py)（`--to <id>` 或 `--catalog order.json --next`）。
