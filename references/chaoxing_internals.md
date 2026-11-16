# 超星平台核心机制与底层技术参考

## 1. URL 架构与传参机制

### 章节学习页 URL 标准格式
```text
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId={chapterId}&courseId={courseId}&clazzid={clazzId}&cpi={cpi}&enc={enc}&mooc2=1&hidetype=0&fanyaVersion=0&openc={openc}
```

* `chapterId`：小节唯一知识点 ID（如 `1204651639`）。
* `courseId`：课程 ID（如 `265703563`）。
* `clazzid`：班级 ID（如 `151613187`）。
* `cpi`：超星用户的内部身份识别编码。
* `enc`：小节动态签名校验码。**注意：直接伪造或拼接他人 enc 会触发“enc校验失败”**，需从课程主页点击跳转或从 `toOld()` 获取。
* `openc`：课程实例授权开放密钥。

---

## 2. DOM 层次与 Iframe 结构

超星学生学习页采用了深层嵌套的 Iframe 架构：

```text
window (studentstudy)
 ├── #cells (右侧目录导航树)
 │    ├── #cur1204651639 (小节条目)
 │    │    └── em.icon_Completed (绿标：小节全任务已完成)
 │    │    └── em.orange / .prevTips (未完成小黄点及剩余任务数)
 └── iframe (#iframe / knowledge/cards)
      ├── .ans-attach-ct.videoContainer (单个任务容器)
      │    ├── class="... ans-job-finished" (表示本任务点已完成)
      │    └── iframe (.ans-insertvideo-online)
      │         └── iframe (/ananas/modules/video/index.html)
      │              ├── video (#video_html5_api)
      │              ├── button.vjs-big-play-button
      │              └── div.ans-videoquiz (视频中途弹出题窗口)
      └── iframe (/ananas/modules/pdf/index.html) (文档与课件)
```

---

## 3. 多媒体心跳与防作弊规则

1. **心跳日志上报机制**：
   * 视频播放过程中，播放器通过 `multimedia/log/a/{dtoken}` 接口定时上报播放进度。
   * 当视频播放达到 `video.ended` 或 `video.currentTime >= video.duration - 1` 时，会发送最终达标包。
   * **关键规则**：视频结束后必须在当前页维持 8 秒以上，确保心跳 API 200 响应入库后再跳转。
2. **倍速限制**：
   * 官方播放器支持 2.0x 倍速。直接修改 `video.playbackRate = 2.0` 在多数课程中安全生效且能通过服务端校验。
3. **单标签页限制（强约束）**：
   * 超星前端加载了 `detect.chaoxing.com/api/monitor_temp` 监控服务。
   * 同一账号严禁多开标签页并行刷课，否则会触发并发警报并锁定账号。所有章节必须在**同一标签页内顺序推进**。
