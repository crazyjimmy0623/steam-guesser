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
