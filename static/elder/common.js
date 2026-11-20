/* 老人端公共 JS: token 管理 + API 封装 + 全局样式 + 提醒状态机
 * 所有页面都用 <script src="/static/elder/common.js"></script> 引入。
 */
const TOKEN_KEY = "elder_token";
const USER_KEY  = "elder_user";
const REMINDER_STATE_KEY = "elder_reminder_state";  // 吃药提醒持久化

/* ---------- token / 用户 ---------- */
function getToken()  { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function getUser()   { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; } }
function setUser(u)  { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function logout()    { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY);
                       localStorage.removeItem(REMINDER_STATE_KEY);
                       // 老人端只有一个页面, 退出后回首页(首页会自动显示登录框)
                       location.href = "/static/elder/index.html"; }

/* ---------- API 封装 ---------- */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const r = await fetch(path, { ...opts, headers });
  if (r.status === 401) { logout(); throw new Error("登录已过期，请重新登录"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.msg || `HTTP ${r.status}`);
  return body.data;
}

/* ---------- 登录守卫 ---------- */
function requireAuth() {
  // 老人端是单页应用, 没登录也留在 index.html(它自己会显示登录框)
  if (!getToken()) { location.href = "/static/elder/index.html"; return null; }
  return getUser();
}

/* ---------- 全局样式注入（老人友好：大字体、大按钮、高对比度） ---------- */
function injectElderCSS() {
  if (document.getElementById("__elder_css__")) return;
  const css = document.createElement("style");
  css.id = "__elder_css__";
  css.textContent = `
    :root { --bg:#0f1420; --card:#181f2e; --line:#2a3346; --txt:#f0f4fa; --sub:#a8b8d0;
            --pri:#3b82f6; --ok:#22c55e; --bad:#ef4444; --warn:#f59e0b; }
    * { box-sizing:border-box; }
    html, body { margin:0; padding:0; background:var(--bg); color:var(--txt);
                 font:18px/1.7 "Microsoft YaHei", system-ui, sans-serif; }
    .wrap { max-width: 960px; margin: 0 auto; padding: 24px 20px 80px; }
    h1 { font-size: 26px; margin: 0 0 4px; font-weight: 700; }
    h2 { font-size: 22px; margin: 16px 0 10px; font-weight: 700; }
    .sub { color: var(--sub); font-size: 15px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 22px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .spacer { flex: 1; }
    label { display: block; font-size: 16px; color: var(--sub); margin: 14px 0 6px; }
    input, select { width: 100%; padding: 14px 16px; background: #101725; color: var(--txt);
                    border: 2px solid var(--line); border-radius: 12px; font-size: 18px; }
    input:focus { border-color: var(--pri); outline: none; }
    button { padding: 14px 22px; border: 0; border-radius: 12px; background: var(--pri);
             color: #fff; font-size: 18px; cursor: pointer; font-weight: 600;
             min-height: 52px; transition: transform .08s, background .15s; }
    button:active { transform: scale(.97); }
    button.ghost { background: #22304a; color: var(--txt); }
    button.big   { padding: 20px 32px; font-size: 22px; min-height: 70px; }
    button.block { display: block; width: 100%; }
    button.danger { background: var(--bad); }
    /* SOS 超大红按钮 */
    .sos-btn {
      display: block; margin: 40px auto 30px;
      width: 280px; height: 280px; border-radius: 50%;
      background: linear-gradient(135deg, #ef4444, #991b1b);
      border: 7px solid #7f1d1d; box-shadow: 0 0 50px rgba(239,68,68,.5);
      color: #fff; font-size: 40px; font-weight: 900; letter-spacing: 6px;
      cursor: pointer; transition: transform .1s, box-shadow .2s;
      animation: sos-pulse 2s infinite;
    }
    .sos-btn:active { transform: scale(.95); }
    .sos-btn.cancel  { background: linear-gradient(135deg, #f59e0b, #78350f);
                       border-color: #78350f; box-shadow: 0 0 50px rgba(245,158,11,.5);
                       animation: none; font-size: 30px; letter-spacing: 3px; }
    @keyframes sos-pulse {
      0%,100% { box-shadow: 0 0 50px rgba(239,68,68,.5); }
      50%     { box-shadow: 0 0 80px rgba(239,68,68,.9), 0 0 100px rgba(239,68,68,.4); }
    }
    /* 消息 */
    .msg { margin-top: 14px; font-size: 17px; min-height: 24px; }
    .ok  { color: var(--ok); } .bad { color: var(--bad); } .warn { color: var(--warn); }
    /* 导航 */
    .nav { display: flex; gap: 6px; padding: 12px 16px; background: var(--card);
           border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 100; }
    .nav a { flex: 1; text-align: center; padding: 12px 8px; border-radius: 10px;
             color: var(--sub); text-decoration: none; font-size: 16px; font-weight: 600; }
    .nav a.active, .nav a:hover { background: #22304a; color: var(--txt); }
    .nav .me { margin-left: auto; background: transparent; color: var(--sub);
               font-size: 14px; padding: 12px 6px; cursor:pointer; }
    /* 首页大卡片 */
    .big-card { border-radius: 16px; padding: 22px; margin-bottom: 18px; border: 2px solid; }
    .big-card.danger { background: linear-gradient(135deg, #450a0a, #1f0a0a);
                       border-color: #ef4444; box-shadow: 0 0 30px rgba(239,68,68,.3); }
    .big-card.warn   { background: linear-gradient(135deg, #451a03, #1f1001);
                       border-color: var(--warn); box-shadow: 0 0 30px rgba(245,158,11,.3); }
    .big-card.info   { background: var(--card); border-color: var(--line); }
    .big-card .title { font-size: 18px; color: var(--sub); margin-bottom: 6px; }
    .big-card .main  { font-size: 28px; font-weight: 800; color: #fff; }
    .big-card .sub2  { font-size: 16px; color: var(--sub); margin-top: 6px; }
    .big-card .med-icon { font-size: 40px; }
    /* 提醒弹窗（普通样式, 不做全屏红色闪烁） */
    .popup { position: fixed; top: 0; left: 0; right: 0; bottom: 0;
             background: rgba(0,0,0,.85); z-index: 999;
             display: flex; align-items: center; justify-content: center; }
    .popup .box { background: linear-gradient(135deg, #1f2937, #181f2e); border: 4px solid var(--warn);
                  border-radius: 20px; padding: 36px 32px; text-align: center; max-width: 420px;
                  box-shadow: 0 0 80px rgba(245,158,11,.6); animation: pop-in .3s ease; }
    @keyframes pop-in { from { transform: scale(.7); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .popup h2 { color: var(--warn); font-size: 32px; margin: 0 0 8px; }
    .popup .med-name { font-size: 36px; font-weight: 900; color: #fff; margin: 14px 0; }
    .popup .dosage { color: var(--sub); font-size: 20px; }
    .popup .countdown { color: var(--warn); font-size: 16px; margin-top: 8px; }
    .popup .btn-row { margin-top: 24px; display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
    /* 标签 */
    .badge { display: inline-block; padding: 4px 14px; border-radius: 99px;
             font-size: 14px; font-weight: 700; margin-right: 8px; }
    .badge.fall  { background: #7f1d1d; color: #fecaca; }
    .badge.sos   { background: #78350f; color: #fed7aa; }
    .badge.static{ background: #1e3a8a; color: #bfdbfe; }
    .badge.handled   { background: #14532d; color: #bbf7d0; }
    .badge.unhandled { background: #7f1d1d; color: #fecaca; }
    /* 告警历史折叠 */
    .history-fold { margin-top: 20px; }
    .history-fold summary { cursor: pointer; color: var(--sub); font-size: 15px;
                            padding: 10px 0; user-select: none; }
    .history-fold summary:hover { color: var(--txt); }
    .alert-row { display: flex; align-items: center; gap: 12px;
                 padding: 12px 0; border-bottom: 1px solid var(--line); }
    .alert-row img { width: 70px; height: 70px; object-fit: cover; border-radius: 8px;
                     background: #0a0f1a; flex-shrink: 0; cursor:pointer; }
    /* 空状态 */
    .empty { text-align: center; color: var(--sub); padding: 40px 20px; font-size: 18px; }
    /* 响铃时弹窗微微发光（不抖动，老人看着安心） */
    .popup.beeping .box { box-shadow: 0 0 60px rgba(245,158,11,.8); }
    @keyframes box-shake { /* 已废弃：不再抖动 */ }
    /* 响应式 */
    @media (max-width: 600px) {
      .sos-btn { width: 220px; height: 220px; font-size: 32px; }
      h1 { font-size: 22px; }
      .big-card .main { font-size: 22px; }
    }
  `;
  document.head.appendChild(css);
}
window.addEventListener("DOMContentLoaded", injectElderCSS);

/* ---------- 语音播报 ---------- */
let _voice = null;
function _getVoice() {
  if (_voice) return _voice;
  if (!("speechSynthesis" in window)) return null;
  // 等待语音列表加载
  const voices = speechSynthesis.getVoices();
  _voice = voices.find(v => /zh|chinese|mandarin/i.test(v.lang + v.name)) || voices[0] || null;
  return _voice;
}
// 有些浏览器 voices 异步加载
if ("speechSynthesis" in window) {
  speechSynthesis.onvoiceschanged = () => { _voice = null; _getVoice(); };
}

function speak(text, opts = {}) {
  if (!("speechSynthesis" in window)) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-CN";
    u.rate = opts.rate ?? 0.85;
    u.pitch = opts.pitch ?? 1;
    u.volume = opts.volume ?? 1;
    const v = _getVoice();
    if (v) u.voice = v;
    speechSynthesis.speak(u);
  } catch {}
}

/* ---------- 蜂鸣声（Web Audio API 生成） ---------- */
let _audioCtx = null;
function _getAudioCtx() {
  if (_audioCtx) return _audioCtx;
  try {
    _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return _audioCtx;
  } catch { return null; }
}

/* 响一声（0.3 秒），频率 freq Hz，返回一个可停止的对象 */
function beep(freq = 880, duration = 0.3) {
  const ctx = _getAudioCtx();
  if (!ctx) return { stop() {} };
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.value = 0.3;
  osc.connect(gain).connect(ctx.destination);
  osc.start();
  const stopAt = ctx.currentTime + duration;
  osc.stop(stopAt);
  return { stop() { try { osc.stop(); } catch {} } };
}

/* 连续蜂鸣 N 次，间隔 gap 秒 */
function beepSequence(count = 3, gap = 0.4) {
  const timers = [];
  for (let i = 0; i < count; i++) {
    const t = setTimeout(() => beep(880, 0.3), i * gap * 1000);
    timers.push(t);
  }
  return { stop() { timers.forEach(t => clearTimeout(t)); } };
}

/* 停止所有蜂鸣声（不再提供"全屏强制蜂鸣"效果） */
let _alarmInterval = null;
function alarmOff() {
  if (_alarmInterval) { clearInterval(_alarmInterval); _alarmInterval = null; }
}

/* ---------- 吃药提醒状态机（localStorage 持久化） ---------- */
/* 状态结构: { [planId]: { lastTrigger: timestamp, count: number, pausedUntil: timestamp|null } } */

function loadReminderState() {
  try { return JSON.parse(localStorage.getItem(REMINDER_STATE_KEY) || "{}"); }
  catch { return {}; }
}
function saveReminderState(state) {
  localStorage.setItem(REMINDER_STATE_KEY, JSON.stringify(state));
}

/* 已确认吃药的 plan 集合（存在 localStorage, 防止后端失败时前端死循环提醒） */
function loadConfirmedToday() {
  try { return JSON.parse(localStorage.getItem("elder_confirmed_today") || "{}"); }
  catch { return {}; }
}
function saveConfirmedToday(map) {
  localStorage.setItem("elder_confirmed_today", JSON.stringify(map));
}

/* 本地日期 YYYY-MM-DD。
 * ⚠ 不能用 toISOString(): 它返回 UTC 日期, 北京时间早上 8 点才翻篇,
 *   会导致早上 8 点状态被整份清空、提醒从第 1 次重来。
 */
function localDateStr(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/* 提醒间隔（秒）, 下标 = 第几次提醒:
 *   [0] 第1次 -> 到点立刻
 *   [1] 第2次 -> 距第1次提醒 5 分钟
 *   [2] 第3次 -> 距第2次提醒 5 分钟
 * ⚠ 间隔是"距上一次提醒"的时长, 不是"距计划时刻"的绝对偏移。
 *   否则计划时间一过, 后面几次会全部判定为已到期, 15 秒内连放完。
 */
const REMINDER_GAPS = [0, 5 * 60, 5 * 60];

/* 检查某个计划到点没，如果到了且最近没提醒过，触发提醒
 * 返回 "shouldTrigger" 或 null
 */
function shouldTriggerReminder(plan) {
  if (!plan.take_time) return null;
  const state = loadReminderState();
  const todayStr = localDateStr();
  const key = plan.id;
  let s = state[key] || { count: 0, lastTrigger: 0, day: todayStr };

  // 换天(按本地日期)才重置; 同一天内绝不重置
  if (s.day !== todayStr) {
    s = { count: 0, lastTrigger: 0, day: todayStr, confirmed: false };
  }

  // 已确认吃药 -> 今天永远不再弹
  if (s.confirmed) return null;

  const now = Date.now();
  const planTimeStr = String(plan.take_time).slice(0, 5); // "08:00"
  const [ph, pm] = planTimeStr.split(":").map(Number);
  const planDate = new Date();
  planDate.setHours(ph, pm, 0, 0);
  const planTs = planDate.getTime();

  // 还没到点
  if (now < planTs) return null;

  // 超过当天 23:59 就不再提醒（等明天）
  const endOfDay = new Date(); endOfDay.setHours(23, 59, 59, 999);
  if (now > endOfDay.getTime()) return null;

  // 3 次用完了就停
  if (s.count >= REMINDER_GAPS.length) return null;

  // 触发基准: 第1次 = 计划时刻; 后面几次 = 上一次实际提醒的时间
  const baseTs = s.count === 0 ? planTs : (s.lastTrigger || planTs);
  const triggerTs = baseTs + (REMINDER_GAPS[s.count] || 0) * 1000;

  // 还没到这次的触发时间
  if (now < triggerTs) return null;

  // 暂停中（"稍后提醒"功能备用）
  if (s.pausedUntil && now < s.pausedUntil) return null;

  return { plan, state: s, stateKey: key };
}

function markReminderTriggered(stateKey) {
  const state = loadReminderState();
  if (!state[stateKey]) state[stateKey] = { count: 0, lastTrigger: 0 };
  state[stateKey].count = (state[stateKey].count || 0) + 1;
  state[stateKey].lastTrigger = Date.now();
  state[stateKey].day = localDateStr();
  state[stateKey].pausedUntil = 0;
  saveReminderState(state);
}

/* 确认已吃药: 打上 permanent 标记, 今天不再弹 */
function markReminderConfirmed(stateKey) {
  const state = loadReminderState();
  if (!state[stateKey]) state[stateKey] = { count: 0, lastTrigger: 0 };
  state[stateKey].confirmed = true;
  state[stateKey].day = localDateStr();
  saveReminderState(state);
}

function pauseReminder(stateKey, minutes = 5) {
  const state = loadReminderState();
  if (!state[stateKey]) state[stateKey] = { count: 0, lastTrigger: 0 };
  state[stateKey].pausedUntil = Date.now() + minutes * 60 * 1000;
  saveReminderState(state);
}

/* ⚠ 不要提供"删除状态"的函数: 删掉状态会让 count 归零, 下一轮立刻从头重弹。
 *   需要停止提醒请用 markReminderConfirmed()。
 */

/* ---------- 弹窗 ---------- */
/*
 * showMedicineReminder(plan, reminderInfo, onTaken, onLater, onSkip)
 *   plan  = { id, medicine_name, dosage, take_time }
 *   reminderInfo = { count: 第几提醒 (0~4), maxCount: 5 }
 *   onTaken()    = 用户点"已吃药"
 *   onLater()    = 用户点"稍后 5 分钟"
 *   onSkip()     = 用户点"今天不吃"
 *   onClose()    = 弹窗被强制关闭（刷新等）
 */
function showMedicineReminder(plan, reminderInfo, callbacks) {
  const { count } = reminderInfo;
  const total = REMINDER_GAPS.length;
  const isLast = count >= total - 1;

  // 防御: 已确认吃药就不再弹（无论如何都不能"关掉还弹"）
  if (loadReminderState()[plan.id]?.confirmed) return null;
  // 不再有全屏红色闪烁特效 —— 只靠语音+蜂鸣

  // 如果已存在弹窗就更新，不重复创建
  let popup = document.querySelector(".popup.medicine-reminder");
  const firstTime = !popup;

  if (firstTime) {
    popup = document.createElement("div");
    popup.className = "popup medicine-reminder";
    popup.innerHTML = `
      <div class="box">
        <div class="title-bar"></div>
        <h2 id="popTitle">⏰ 该吃药啦！</h2>
        <div class="dosage" id="popTime">现在是 ${String(plan.take_time).slice(0,5)}</div>
        <div class="med-name" id="popName">${plan.medicine_name}</div>
        <div class="dosage" id="popDosage">剂量：${plan.dosage || '—'}</div>
        <div class="countdown" id="popCount"></div>
        <div class="btn-row">
          <button class="big block" id="popTaken">✓ 已吃药</button>
        </div>
      </div>
    `;
    document.body.appendChild(popup);

    popup.querySelector("#popTaken").onclick = () => {
      cleanup(true); callbacks.onTaken && callbacks.onTaken();
    };
  }

  // 更新弹窗状态
  const box = popup.querySelector(".box");
  const title = popup.querySelector("#popTitle");
  const popCount = popup.querySelector("#popCount");

  popup.classList.toggle("beeping", true);

  if (isLast) {
    title.textContent = "⏰ 最后一次提醒";
    title.style.color = "";
  } else {
    title.textContent = "⏰ 该吃药啦！";
    title.style.color = "";
  }

  if (count > 0) {
    popCount.textContent = `（这是第 ${count + 1} 次提醒）`;
  } else {
    popCount.textContent = "";
  }

  // 触发音效和语音。⚠ 每次触发只播一遍, 不再用 setInterval 每 3 秒重复
  //   (重复播报就是之前"关掉还一直出现"的来源; 下一次提醒由 5 分钟间隔控制)
  function cleanup(removePopup = false) {
    alarmOff();
    try { beep().stop(); } catch {}
    if (removePopup && popup.parentNode) popup.parentNode.removeChild(popup);
  }
  cleanup();
  const maxBeeps = isLast ? 5 : 3;

  beepSequence(maxBeeps, 0.35);
  speak(isLast
    ? `紧急！请立即吃${plan.medicine_name}！剂量${plan.dosage || ''}！`
    : `嘀嘀嘀，该吃药啦！请吃${plan.medicine_name}，剂量${plan.dosage || ''}`);

  popup._cleanup = () => cleanup(true);

  return {
    close: () => cleanup(true),
    getElement: () => popup,
  };
}

/* ---------- 启动吃药提醒引擎 ----------
 * 调用一次即可，会自动轮询 plans 列表。
 * plans 会被刷新（传入函数）。
 * registerMedicineReminder({ getPlans: async () => [...], onReminder: callback })
 */
let _reminderTimer = null;
function registerMedicineReminder(opts) {
  const { getPlans, onReminder } = opts;
  if (_reminderTimer) clearInterval(_reminderTimer);

  async function tick() {
    if (!getToken()) return;
    let plans = [];
    try { plans = (await getPlans()) || []; } catch { return; }

    const todayStr = localDateStr();

    for (const plan of plans) {
      if (plan.cycle === "two_day") {
        const today = new Date();
        if (today.getDate() % 2 === 1) continue;  // 隔天跳过一次
      }

      // 今天已经确认过的就不再提醒（后端 + 本地双保险, 防止网络失败死循环）
      let confirmedToday = false;
      try {
        const records = (await api("/api/medicine/record")) || [];
        // 后端字段: remind_date(YYYY-MM-DD) + take_result("taken"/"untaken")
        confirmedToday = records.some(r =>
          r.plan_id === plan.id &&
          String(r.remind_date || "").slice(0, 10) === todayStr &&
          r.take_result === "taken"
        );
      } catch {}
      if (!confirmedToday) {
        const localMap = loadConfirmedToday();
        // 只看今天的记录, 跨天自动过期
        if (localMap._date === todayStr && localMap[plan.id]) confirmedToday = true;
      }
      if (confirmedToday) continue;

      const check = shouldTriggerReminder(plan);
      if (check) {
        const state = loadReminderState();
        const count = (state[check.stateKey]?.count || 0);

        showMedicineReminder(plan, { count, total: REMINDER_GAPS.length }, {
          async onTaken() {
            // 1. 先落两个本地标记（网络断了也能挡住下一轮提醒）
            const todayStr = localDateStr();
            const localMap = loadConfirmedToday();
            localMap._date = todayStr;
            localMap[plan.id] = true;
            saveConfirmedToday(localMap);
            // ⚠ 关键: 之前这里调 resetReminder() 把状态删了, 下一轮 count 归零又重弹
            markReminderConfirmed(check.stateKey);

            // 2. 再上报后端（字段必须是 take_result: "taken"）
            try {
              await api("/api/medicine/record", {
                method: "POST",
                body: JSON.stringify({ plan_id: plan.id, take_result: "taken" }),
              });
              speak("好的，已记录您吃过了");
            } catch {
              speak("好的");  // 后端挂了也报平安
            }
          },
        });

        markReminderTriggered(check.stateKey);
        onReminder && onReminder(plan, count);
        break;  // 一次只处理一个，避免弹窗叠
      }
    }
  }

  // 立即跑一次，然后每 15 秒轮询
  tick();
  _reminderTimer = setInterval(tick, 15000);

  // 页面关闭时清理
  window.addEventListener("beforeunload", () => {
    if (_reminderTimer) clearInterval(_reminderTimer);
    alarmOff();
  });
}

/* ---------- 工具 ---------- */
const $ = id => document.getElementById(id);
function msg(t, cls = "", el = document.getElementById("msg")) {
  if (!el) { el = document.createElement("div"); el.id = "msg"; document.querySelector(".wrap")?.prepend(el); }
  el.className = cls; el.textContent = t;
}
