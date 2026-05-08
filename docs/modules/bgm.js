// BGM 環境音 drone — 從 app.py:1346-1477 搬
// 用 WebAudio 5 個 oscillator + LFO + 帶通噪音合成
// 必須等使用者第一次互動才能 start AudioContext (auto-prime)

export function mountBGM(container) {
  container.innerHTML = `
    <div class="bgm" id="bgm">
      <span>BGM</span>
      <button id="bgm-toggle">◉ ON</button>
      <input id="bgm-vol" type="range" min="0" max="100" value="100" />
    </div>
  `;
  const toggleBtn = container.querySelector('#bgm-toggle');
  const vol = container.querySelector('#bgm-vol');

  let ctx = null, master = null, started = false, on = true;

  function buildDrone() {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);

    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 220;
    filter.Q.value = 0.6;
    filter.connect(master);

    function osc(type, freq, gain) {
      const o = ctx.createOscillator(); o.type = type; o.frequency.value = freq;
      const g = ctx.createGain(); g.gain.value = gain;
      o.connect(g); g.connect(filter);
      o.start();
      return o;
    }
    osc('sine', 55, 1.0);
    osc('sine', 73.4, 0.7);
    osc('sawtooth', 27.5, 0.25);
    osc('sine', 110, 0.35);
    osc('sine', 56.2, 0.4);

    const lfo = ctx.createOscillator();
    lfo.type = 'sine'; lfo.frequency.value = 0.13;
    const lfoG = ctx.createGain(); lfoG.gain.value = 0.025;
    lfo.connect(lfoG); lfoG.connect(master.gain);
    lfo.start();

    const sw = ctx.createOscillator();
    sw.type = 'sine'; sw.frequency.value = 0.05;
    const swg = ctx.createGain(); swg.gain.value = 60;
    sw.connect(swg); swg.connect(filter.frequency);
    sw.start();

    const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * 0.05;
    const noise = ctx.createBufferSource();
    noise.buffer = buf; noise.loop = true;
    const noiseG = ctx.createGain(); noiseG.gain.value = 0.06;
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 800; bp.Q.value = 1.5;
    noise.connect(bp); bp.connect(noiseG); noiseG.connect(master);
    noise.start();
  }

  function setOn(v) {
    if (!started) return;
    const tgt = v ? (parseInt(vol.value) / 100) * 0.12 : 0;
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + (v ? 1.8 : 0.6));
    on = v;
    toggleBtn.textContent = v ? '◉ ON' : '○ OFF';
    toggleBtn.style.background = v ? '#1a3a1a' : '#0a0a0a';
    toggleBtn.style.color = v ? '#fff' : '#4caf50';
  }

  function autoPrime(e) {
    // 點到 BGM 按鈕本身不算 — 那條路自己走
    if (e.target && e.target.closest && e.target.closest('#bgm-toggle')) return;
    if (!started) { buildDrone(); started = true; setOn(true); }
    document.removeEventListener('pointerdown', autoPrime, true);
    document.removeEventListener('keydown', autoPrime, true);
  }
  document.addEventListener('pointerdown', autoPrime, true);
  document.addEventListener('keydown', autoPrime, true);

  toggleBtn.addEventListener('click', () => {
    document.removeEventListener('pointerdown', autoPrime, true);
    document.removeEventListener('keydown', autoPrime, true);
    if (!started) { buildDrone(); started = true; setOn(false); return; }
    setOn(!on);
  });
  vol.addEventListener('input', () => {
    if (started && on) {
      const tgt = (parseInt(vol.value) / 100) * 0.12;
      master.gain.cancelScheduledValues(ctx.currentTime);
      master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + 0.2);
    }
  });
}
