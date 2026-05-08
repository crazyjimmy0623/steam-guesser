// 計時挑戰 timer — 從 app.py:1610-1667 搬,接到 state machine
// 用單一 setInterval 250ms tick,更新 widget DOM 與 class,
// 時間到時 callback 呼叫 setPhase('ended')

export function startTimer({ container, getStartTime, getScore, getPhase, getTimeLimit, getLabel, getScoreLabel, onExpire, onTick }) {
  // 把 widget 結構 mount 進 container
  container.innerHTML = `
    <div class="timer" id="tw">
      <span class="lbl">${getLabel()}</span>
      <span class="clock" id="clk">--:--</span>
      <span class="score-side">${getScoreLabel()} <b id="scr">0</b></span>
    </div>
  `;
  const tw = container.querySelector('#tw');
  const clk = container.querySelector('#clk');
  const scr = container.querySelector('#scr');

  let stopped = false;
  let expired = false;
  let lastTickedSec = -1;
  const startMs = () => getStartTime() * 1000;
  const limitMs = () => getTimeLimit() * 1000;

  function tick() {
    if (stopped) return;
    const remain = Math.max(0, limitMs() - (Date.now() - startMs()));
    const s = Math.ceil(remain / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    clk.textContent = mm + ':' + ss;
    tw.classList.toggle('urgent', remain > 0 && remain <= 60000);
    tw.classList.toggle('danger', remain > 0 && remain <= 15000);
    scr.textContent = String(getScore());

    // 心跳 callback:剩 ≤15s 時整數秒踏上一次,只在跨越秒數時觸發
    if (remain > 0 && remain <= 15000 && s !== lastTickedSec && onTick) {
      lastTickedSec = s;
      onTick(s);
    }

    if (remain <= 0 && !expired && getPhase() !== 'ended') {
      expired = true;
      onExpire();
    }
  }
  tick();
  const intervalId = setInterval(tick, 250);

  return function stop() {
    stopped = true;
    clearInterval(intervalId);
  };
}

// 讓外部可以重新整理 widget 上的標籤(語言切換時)
export function refreshTimerLabels(container, label, scoreLabel) {
  const lbl = container.querySelector('.timer .lbl');
  const ss = container.querySelector('.timer .score-side');
  if (lbl) lbl.textContent = label;
  if (ss) {
    const b = ss.querySelector('b');
    const score = b ? b.textContent : '0';
    ss.innerHTML = `${scoreLabel} <b>${score}</b>`;
  }
}
