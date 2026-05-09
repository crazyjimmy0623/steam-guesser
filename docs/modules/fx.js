// FX 特效:perfect 全螢幕綠色快閃 + 中心粒子爆炸 / miss 整頁微震 / verdict CRT 加強

// ---------- perfect 全螢幕 flash + 粒子爆炸 ----------
export function triggerPerfectFx(originX, originY) {
  // 全螢幕快閃綠色 overlay
  const flash = document.createElement('div');
  flash.className = 'perfect-flash';
  document.body.appendChild(flash);
  setTimeout(() => flash.remove(), 700);

  // 從 verdict 中心放射 30 個粒子(用 canvas)
  const cx = originX ?? window.innerWidth / 2;
  const cy = originY ?? window.innerHeight / 2;

  const canvas = document.createElement('canvas');
  canvas.className = 'fx-burst';
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  const N = 32;
  const parts = [];
  for (let i = 0; i < N; i++) {
    const angle = (Math.PI * 2 * i) / N + (Math.random() - 0.5) * 0.3;
    const speed = 280 + Math.random() * 220;       // px/sec
    parts.push({
      x: cx, y: cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      r: 2 + Math.random() * 3,
      life: 0.7 + Math.random() * 0.4,
      age: 0,
      hue: 100 + Math.random() * 40,               // 綠到黃綠
    });
  }

  const start = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - (frame.last || start)) / 1000);
    frame.last = now;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = 0;
    for (const p of parts) {
      p.age += dt;
      if (p.age >= p.life) continue;
      alive++;
      // 重力 + 阻尼
      p.vy += 380 * dt;
      p.vx *= Math.pow(0.6, dt);
      p.vy *= Math.pow(0.85, dt);
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      const a = 1 - p.age / p.life;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r * a, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 80%, 60%, ${a})`;
      ctx.shadowColor = `hsla(${p.hue}, 90%, 70%, ${a * 0.8})`;
      ctx.shadowBlur = 12 * a;
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    if (alive > 0) requestAnimationFrame(frame);
    else canvas.remove();
  }
  requestAnimationFrame(frame);
}

// ---------- miss 整頁微震 ----------
export function triggerMissShake() {
  document.body.classList.remove('miss-shake');
  // 強制 reflow 讓 class 移除生效,下一格才能再加上去重新觸發動畫
  void document.body.offsetWidth;
  document.body.classList.add('miss-shake');
  setTimeout(() => document.body.classList.remove('miss-shake'), 350);
}

// ---------- 時間到全螢幕特效 — 紅色 TIME UP 大字 + 紅色 vignette + 警報音 ----------
// onComplete:大概 1.5s 後 callback 進結算 phase
export function triggerTimeUpFx(label = 'TIME UP', onComplete = null) {
  // 全螢幕紅色覆蓋層
  const overlay = document.createElement('div');
  overlay.className = 'timeup-overlay';
  overlay.innerHTML = `
    <div class="timeup-content">
      <div class="timeup-glitch" data-text="${label}">${label}</div>
      <div class="timeup-tag">SESSION TERMINATED</div>
    </div>
  `;
  document.body.appendChild(overlay);

  // 警報聲(獨立 AudioContext,避免被 BGM 共用 ctx 影響;不用 sfx.js 因為它有共用)
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    // 雙音 alarm:200Hz / 280Hz 交替,gain 從 0.18 降到 0.07 + 用 sine 波(原本 square 太刺)
    const tones = [200, 280, 200, 280];
    tones.forEach((freq, i) => {
      const o = ctx.createOscillator();
      o.type = 'sine';
      o.frequency.setValueAtTime(freq, now + i * 0.18);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, now + i * 0.18);
      g.gain.linearRampToValueAtTime(0.07, now + i * 0.18 + 0.015);
      g.gain.setValueAtTime(0.07, now + i * 0.18 + 0.13);
      g.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.16);
      o.connect(g); g.connect(ctx.destination);
      o.start(now + i * 0.18);
      o.stop(now + i * 0.18 + 0.18);
    });
    // 1.5 秒後關 audio context
    setTimeout(() => { try { ctx.close(); } catch (_) {} }, 1500);
  } catch (e) { /* audio 不通就靜默 */ }

  // 1.5 秒後移除 overlay + 呼叫 callback
  setTimeout(() => {
    overlay.classList.add('out');
    setTimeout(() => {
      overlay.remove();
      if (onComplete) onComplete();
    }, 400);
  }, 1500);
}

// ---------- 浮動 toast (排行榜上榜通知等通用) ----------
export function showToast({ icon = '↑', title = '', subtitle = '', tier = 'default', durationMs = 2500 }) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${tier}`;
  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-body">
      <span class="toast-title">${title}</span>
      ${subtitle ? `<span class="toast-sub">${subtitle}</span>` : ''}
    </span>
  `;
  document.body.appendChild(toast);
  // 強制 reflow 後加 .show 觸發進場 transition
  void toast.offsetWidth;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 600);
  }, durationMs);
}

// ---------- verdict 揭曉時 CRT 加強 ----------
export function boostCrt() {
  const crt = document.querySelector('.crt');
  if (!crt) return;
  crt.classList.remove('crt-boost');
  void crt.offsetWidth;
  crt.classList.add('crt-boost');
  setTimeout(() => crt.classList.remove('crt-boost'), 500);
}
