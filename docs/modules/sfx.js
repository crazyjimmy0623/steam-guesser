// 音效 — 從 app.py:2080-2099 搬,並擴充 hover / press UI 音效
// 共用單一 AudioContext,避免 hover 連發爆量建 context

let sharedCtx = null;

function getCtx() {
  if (sharedCtx) return sharedCtx;
  try {
    sharedCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (sharedCtx.state === 'suspended') {
      sharedCtx.resume().catch(() => {});
    }
  } catch (e) {
    return null;
  }
  return sharedCtx;
}

// ---------- 揭曉音效:100/50/0 三種 ----------
export function playSFX(score) {
  const ctx = getCtx();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    const freq = ({ 100: 880, 50: 523, 0: 196 })[score] ?? 440;

    const o = ctx.createOscillator();
    o.type = score === 0 ? 'square' : 'sine';
    o.frequency.setValueAtTime(freq, now);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.25, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    o.connect(g); g.connect(ctx.destination);
    o.start(now);
    o.stop(now + 0.55);

    if (score === 100) {
      const o2 = ctx.createOscillator();
      o2.type = 'sine';
      o2.frequency.setValueAtTime(1320, now + 0.15);
      const g2 = ctx.createGain();
      g2.gain.setValueAtTime(0, now + 0.15);
      g2.gain.linearRampToValueAtTime(0.2, now + 0.17);
      g2.gain.exponentialRampToValueAtTime(0.0001, now + 0.7);
      o2.connect(g2); g2.connect(ctx.destination);
      o2.start(now + 0.15);
      o2.stop(now + 0.75);
    }
  } catch (e) { /* 靜默 */ }
}

// ---------- hover 音效:cyberpunk「數位 scan」 — 高通 noise 微爆 ----------
export function playHoverSFX() {
  const ctx = getCtx();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;

    // 30ms 白噪音 burst → high-pass 濾掉低頻,只剩高頻數位「ㄕ」聲
    const dur = 0.035;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      data[i] = (Math.random() * 2 - 1);
    }
    const noise = ctx.createBufferSource();
    noise.buffer = buf;

    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 3000;
    hp.Q.value = 2;

    const g = ctx.createGain();
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.035, now + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, now + dur);

    noise.connect(hp); hp.connect(g); g.connect(ctx.destination);
    noise.start(now);
  } catch (e) { /* 靜默 */ }
}

// ---------- 倒數時鐘 tick — 高頻短促 click,模擬機械秒針 ----------
export function playClockSFX() {
  const ctx = getCtx();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    // 高頻噪音 burst,bandpass 在 2.5kHz,給乾淨的「ㄉㄚ」秒針聲
    const dur = 0.025;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      // 衰減包絡讓 noise 像 click 而非 hiss
      data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
    }
    const noise = ctx.createBufferSource();
    noise.buffer = buf;

    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 2400;
    bp.Q.value = 4;

    const g = ctx.createGain();
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.07, now + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, now + dur);

    noise.connect(bp); bp.connect(g); g.connect(ctx.destination);
    noise.start(now);
  } catch (e) { /* 靜默 */ }
}

// ---------- 倒數心跳 tick — 短促低頻 thump,intensity 控制音量 ----------
export function playTickSFX(intensity = 1) {
  const ctx = getCtx();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(85, now);
    o.frequency.exponentialRampToValueAtTime(45, now + 0.09);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.12 * intensity, now + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);
    o.connect(g); g.connect(ctx.destination);
    o.start(now);
    o.stop(now + 0.13);

    // 後一聲補低頻(製造心跳「咚-咚」感)
    if (intensity >= 1.4) {
      const o2 = ctx.createOscillator();
      o2.type = 'sine';
      o2.frequency.setValueAtTime(70, now + 0.13);
      const g2 = ctx.createGain();
      g2.gain.setValueAtTime(0, now + 0.13);
      g2.gain.linearRampToValueAtTime(0.08 * intensity, now + 0.135);
      g2.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
      o2.connect(g2); g2.connect(ctx.destination);
      o2.start(now + 0.13);
      o2.stop(now + 0.24);
    }
  } catch (e) { /* 靜默 */ }
}

// ---------- press 音效:被蒙住的低沉 thomp — 重 low-pass 砍掉所有高頻 + sub-bass 強化體感 ----------
export function playPressSFX() {
  const ctx = getCtx();
  if (!ctx) return;
  try {
    const now = ctx.currentTime;

    // 主體:detuned saw 對,從 150Hz 滑到 45Hz(整個都在低頻區)
    const o1 = ctx.createOscillator();
    o1.type = 'sawtooth';
    o1.frequency.setValueAtTime(150, now);
    o1.frequency.exponentialRampToValueAtTime(45, now + 0.2);

    const o2 = ctx.createOscillator();
    o2.type = 'sawtooth';
    o2.frequency.setValueAtTime(154, now);   // detune,有寬度
    o2.frequency.exponentialRampToValueAtTime(46, now + 0.2);

    // 重 low-pass:起點就壓在 700Hz,掃到 180Hz,Q=2 不共振 → 像隔著棉被聽
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.setValueAtTime(700, now);
    lp.frequency.exponentialRampToValueAtTime(180, now + 0.22);
    lp.Q.value = 2;

    // 軟起音:12ms attack(不要尖銳點擊),0.25s decay
    const bodyG = ctx.createGain();
    bodyG.gain.setValueAtTime(0, now);
    bodyG.gain.linearRampToValueAtTime(0.12, now + 0.012);
    bodyG.gain.exponentialRampToValueAtTime(0.0001, now + 0.25);

    o1.connect(lp); o2.connect(lp);
    lp.connect(bodyG); bodyG.connect(ctx.destination);
    o1.start(now); o1.stop(now + 0.28);
    o2.start(now); o2.stop(now + 0.28);

    // sub-bass:60→40Hz sine,給胸腔的「沉」
    const sub = ctx.createOscillator();
    sub.type = 'sine';
    sub.frequency.setValueAtTime(60, now);
    sub.frequency.exponentialRampToValueAtTime(40, now + 0.2);
    const subG = ctx.createGain();
    subG.gain.setValueAtTime(0, now);
    subG.gain.linearRampToValueAtTime(0.09, now + 0.008);
    subG.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    sub.connect(subG); subG.connect(ctx.destination);
    sub.start(now); sub.stop(now + 0.25);
  } catch (e) { /* 靜默 */ }
}
