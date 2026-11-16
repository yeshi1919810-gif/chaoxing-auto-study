/**
 * auto_runner.js - 超星网课自动化通用执行器
 * 支持：已刷跳过、静音播放、弹窗题秒跳、心跳等待+变绿校验、进度持久化
 *
 * 注意：默认 SPEED = 1.0。超星播放器有风控会周期性把倍速重置回 1x，
 * 强推 2.0 既拿不到速度还可能触发风控，需要时用环境变量 CHAO_XING_SPEED=2 开启。
 */
// 优先用环境变量指定 puppeteer 路径（例如 MCP 内置的那份），否则用本地 npm i puppeteer 安装的
// 例：set PUPPETEER_PATH=C:/Users/me/AppData/Roaming/npm/node_modules/xxx/node_modules/puppeteer
const puppeteer = require(process.env.PUPPETEER_PATH || 'puppeteer');
const fs = require('fs');
const path = require('path');

const SPEED = Number(process.env.CHAO_XING_SPEED || 1.0);
const HEARTBEAT_WAIT = 8000;

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

/** 顶层"下一节"按钮 + 未完成任务点确认弹窗里的"下一节" */
async function clickNextPage(page) {
  const r = await page.evaluate(() => {
    const btn = document.querySelector('#prevNextFocusNext');
    if (btn) { btn.click(); return 'top_clicked'; }
    return 'no_btn';
  }).catch(() => 'err');
  await sleep(3000);
  const p = await page.evaluate(() => {
    const nc = document.querySelector('.nextChapter');
    if (nc && nc.offsetParent !== null) { nc.click(); return 'pop_next'; }
    const all = Array.from(document.querySelectorAll('a, span, div, button'));
    for (const el of all) {
      if (el.offsetParent === null) continue;
      const txt = (el.textContent || '').trim();
      if (txt === '下一节' && el.children.length === 0) { el.click(); return 'leaf_next'; }
    }
    return 'no_pop';
  }).catch(() => 'err');
  return { r, p };
}

/** 卡片任务点是否已变绿（心跳回传成功的唯一可信信号） */
async function isCardFinished(cardFrame) {
  return await cardFrame.evaluate(() => {
    const ct = document.querySelector('.ans-attach-ct');
    return ct ? ct.classList.contains('ans-job-finished') : false;
  }).catch(() => false);
}

// 播放并监控单个视频直到结束
async function playVideoInFrame(videoFrame, label) {
  console.log(`[${label}] === 开始播放视频 (${SPEED}x, 静音) ===`);

  // 初始化触发播放
  await videoFrame.evaluate((speed) => {
    if (window.videojs && window.videojs.getAllPlayers) {
      const players = window.videojs.getAllPlayers();
      if (players.length > 0) {
        players[0].muted(true);
        if (speed !== 1.0) players[0].playbackRate(speed);
        players[0].play();
      }
    }
    const v = document.querySelector('video');
    if (v) {
      v.muted = true;
      if (speed !== 1.0) v.playbackRate = speed;
      v.play().catch(() => {});
    }
    const btn = document.querySelector('.vjs-big-play-button, .vjs-play-control');
    if (btn) btn.click();
  }, SPEED).catch(() => {});

  let lastTime = -1;
  let stuckCount = 0;
  let finished = false;
  const startTime = Date.now();

  while (!finished) {
    await sleep(3000);

    const state = await videoFrame.evaluate((speed) => {
      // 1. 自动处理视频中途弹窗测试题
      const quiz = document.querySelector('.ans-videoquiz, #videoquiz, .videoquiz');
      let handledQuiz = false;
      if (quiz) {
        const opts = Array.from(quiz.querySelectorAll('input[type="radio"], input[type="checkbox"], .ans-videoquiz-opt, li'));
        if (opts.length > 0) opts[0].click();
        const submitBtn = quiz.querySelector('.ans-videoquiz-submit, button, .btn');
        if (submitBtn) submitBtn.click();
        handledQuiz = true;
      }

      // 关闭常规告警弹窗
      const alertBtn = document.querySelector('.popDiv .btn, .popwindow .btn, .alert-btn, .ans-videoquiz-close');
      if (alertBtn) alertBtn.click();

      // 2. 视频对象状态检测
      const v = document.querySelector('video');
      if (!v) return { hasVideo: false };

      v.muted = true;
      if (speed !== 1.0 && v.playbackRate !== speed) {
        try { v.playbackRate = speed; } catch (e) {}
      }
      if (v.paused && !v.ended) v.play().catch(() => {});

      return {
        hasVideo: true,
        currentTime: Math.round(v.currentTime),
        duration: Math.round(v.duration || 0),
        paused: v.paused,
        ended: v.ended,
        handledQuiz
      };
    }, SPEED).catch(e => ({ error: e.message }));

    if (!state || !state.hasVideo) continue;

    if (state.handledQuiz) {
      console.log(`[${label}] 已自动秒选并提交视频互动小测验！`);
    }

    const cur = state.currentTime;
    const dur = state.duration;
    const pct = dur > 0 ? Math.round((cur / dur) * 100) : 0;

    if (cur !== lastTime) {
      lastTime = cur;
      stuckCount = 0;
      console.log(`[${label}] 进度: ${cur}s / ${dur}s (${pct}%) @ ${SPEED}x`);
    } else {
      stuckCount++;
      // 超星在心跳上报 / 切前台时会把视频暂停数秒甚至一分钟，属正常现象，
      // 这里只负责唤回播放，不因短暂暂停判定卡死。
      if (stuckCount >= 4 && !state.ended) {
        console.log(`[${label}] 检测到播放暂停或卡顿，尝试重新唤醒播放...`);
        await videoFrame.evaluate((speed) => {
          const v = document.querySelector('video');
          if (v) {
            v.muted = true;
            if (speed !== 1.0) { try { v.playbackRate = speed; } catch (e) {} }
            v.play().catch(() => {});
          }
          const btn = document.querySelector('.vjs-play-control, .vjs-big-play-button');
          if (btn) btn.click();
        }, SPEED).catch(() => {});
      }
      if (stuckCount === 10 || stuckCount === 40) {
        console.log(`[${label}] WARN: 进度已停滞约 ${stuckCount * 3}s（${cur}s/${dur}s），继续等待恢复`);
      }
    }

    // 达标结束判断
    if (state.ended || (dur > 0 && cur >= dur - 1)) {
      console.log(`[${label}] 视频播放完毕 (${cur}s / ${dur}s)!`);
      finished = true;
    }

    // 单视频防死锁超时：按时长动态计算，避免长视频被误杀
    const limitMs = dur > 0
      ? Math.max(40 * 60 * 1000, (dur / SPEED) * 1000 + 15 * 60 * 1000)
      : 60 * 60 * 1000;
    if (Date.now() - startTime > limitMs) {
      console.log(`[${label}] 触发单视频最大时间保护，跳出。`);
      break;
    }
  }

  // 关键：等待多媒体日志上报服务端同步（固定 8s，调用方还会校验变绿）
  console.log(`[${label}] 等待 ${HEARTBEAT_WAIT / 1000} 秒回传多媒体心跳数据...`);
  await sleep(HEARTBEAT_WAIT);
}

// 主入口函数
async function runCourse(config) {
  const { sections, baseUrl, port = 9222, progressFile = 'study_progress.json' } = config;
  let browser;

  try {
    console.log(`连接浏览器调试端口 ${port}...`);
    browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${port}`, defaultViewport: null });
    const pages = await browser.pages();
    const studyPage = pages.find(p => p.url().includes('studentstudy')) || pages[0];

    let progress = {};
    if (fs.existsSync(progressFile)) {
      try { progress = JSON.parse(fs.readFileSync(progressFile, 'utf8')); } catch (_) {}
    }

    console.log(`=== 开始自动化刷课，共 ${sections.length} 个小节 ===`);

    for (let i = 0; i < sections.length; i++) {
      const sec = sections[i];
      console.log(`\n----------------------------------------------------`);
      console.log(`[${i + 1}/${sections.length}] 检查: ${sec.name}`);

      // 1. 检查右侧目录是否已有绿标已完成
      const isCatalogCompleted = await studyPage.evaluate((targetId) => {
        const item = document.getElementById('cur' + targetId);
        return item ? !!item.querySelector('.icon_Completed') : false;
      }, sec.id).catch(() => false);

      if (isCatalogCompleted) {
        console.log(`[${sec.name}] 目录显示已完成 (icon_Completed)，直接跳过！`);
        progress[sec.id] = { name: sec.name, status: 'SKIPPED_ALREADY_FINISHED' };
        fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2));
        continue;
      }

      // 2. 跳转到该章节
      const secUrl = `${baseUrl}&chapterId=${sec.id}`;
      await studyPage.goto(secUrl, { waitUntil: 'domcontentloaded', timeout: 35000 });
      await sleep(3500);

      const cardFrame = studyPage.frames().find(f => f.url().includes('knowledge/cards'));
      if (!cardFrame) {
        console.log(`未找到卡片 iframe，跳过本节。`);
        continue;
      }

      // 3. 检查卡片容器内的任务点
      //    【关键】类型判断必须用内层 iframe 的 src（modules/video|work|document），
      //    外层 knowledge/cards 的 src 永远是 cards，用它判断只会得到 other。
      const cardsData = await cardFrame.evaluate(() => {
        const list = Array.from(document.querySelectorAll('.ans-attach-ct'));
        return list.map((ct, idx) => {
          const inner = ct.querySelector('iframe');
          const isrc = inner ? (inner.src || '') : '';
          let type = 'other';
          if (isrc.includes('modules/video')) type = 'video';
          else if (isrc.includes('modules/work')) type = 'quiz';
          else if (isrc.includes('modules/document') || isrc.includes('docid')) type = 'doc';
          else if ((ct.className || '').includes('videoContainer')) type = 'video';
          return {
            idx, type,
            finished: ct.classList.contains('ans-job-finished'),
            src: isrc.slice(0, 100)
          };
        });
      }).catch(() => []);

      const videoCards = cardsData.filter(c => c.type === 'video');
      const pendingVideos = videoCards.filter(c => !c.finished);
      const quizCards = cardsData.filter(c => c.type === 'quiz');
      const summary = cardsData.map(c => `${c.type}${c.finished ? '✓' : '✗'}`).join(', ') || '无任务点';
      console.log(`[${sec.name}] 任务点: ${summary} | 待完成视频: ${pendingVideos.length}`);

      if (quizCards.length > 0) {
        console.log(`[${sec.name}] 含 ${quizCards.length} 个测验（纯刷课模式不答），本小节目录仍会显示待完成。`);
      }

      // 4. 逐个未完成视频：播放 → 等心跳 → 校验变绿
      const allVideoFrames = studyPage.frames().filter(f => f.url().includes('modules/video'));
      for (let k = 0; k < videoCards.length; k++) {
        const card = videoCards[k];
        if (card.finished) {
          console.log(`[${sec.name}] 视频 ${k + 1} 已标记 ans-job-finished，跳过（不重复刷）`);
          continue;
        }
        const vf = allVideoFrames[k] || allVideoFrames[0];
        if (!vf) {
          console.log(`[${sec.name}] 视频 ${k + 1} 的 iframe 未加载，跳过`);
          continue;
        }
        await playVideoInFrame(vf, `${sec.name} [视频 ${k + 1}]`);

        // 心跳上报后校验任务点是否变绿；没绿说明心跳未回传，不能急着切章
        let green = await isCardFinished(cardFrame);
        for (let r = 1; r <= 4 && !green; r++) {
          console.log(`[${sec.name}] 任务点未变绿，额外等待 8s 重试（${r}/4）...`);
          await sleep(8000);
          green = await isCardFinished(cardFrame);
        }
        if (green) {
          console.log(`[${sec.name}] 视频 ${k + 1} 任务点已变绿 ✓`);
        } else {
          console.log(`[${sec.name}] WARN: 视频 ${k + 1} 多次等待仍未变绿，可能心跳未回传，建议人工确认`);
        }
      }

      // 5. 自动通关课件文档 / PDF（滚动到底触发阅读上报）
      const docCards = cardsData.filter(c => c.type === 'doc' && !c.finished);
      for (let dj = 0; dj < docCards.length; dj++) {
        const docFrame = studyPage.frames().filter(f => f.url().includes('modules/document') || f.url().includes('docid'))[dj];
        if (docFrame) {
          await docFrame.evaluate(() => {
            const b = document.body;
            if (b) b.scrollTop = b.scrollHeight;
            try { document.documentElement.scrollTop = document.documentElement.scrollHeight; } catch (e) {}
          }).catch(() => {});
          await sleep(3000);
        }
      }
      await cardFrame.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight);
      }).catch(() => {});
      await sleep(1500);

      progress[sec.id] = { name: sec.name, status: 'DONE', time: new Date().toISOString() };
      fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2));
      console.log(`[${sec.name}] 处理完成，进入下一小节。`);
    }

    console.log('\n====================================================');
    console.log('全部章节任务处理完成！');
    console.log('====================================================');

  } catch (err) {
    console.error('执行出错:', err);
  } finally {
    if (browser) browser.disconnect();
  }
}

module.exports = { runCourse, playVideoInFrame };
