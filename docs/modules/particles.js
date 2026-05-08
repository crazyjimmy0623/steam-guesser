// 滑鼠粒子背景 — 從 app.py:1481-1586 搬
// 注入 <canvas> 進 body,網格粒子受滑鼠排斥位移,以彈簧回歸
// 拿掉原本的 window.parent.document indirection (沒 iframe 了)

export function mountParticles() {
  if (document.body.dataset.particlesArmed === '1') return;
  document.body.dataset.particlesArmed = '1';

  const canvas = document.createElement('canvas');
  canvas.id = 'bg-particles';
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  let mouseX = -9999, mouseY = -9999;

  const SPACING = 22;
  const REPEL_RADIUS = 110;
  const MAX_OFFSET = 5;
  const SPRING = 0.18;
  const BASE_R = 0.55;
  const BASE_ALPHA = 0.09;
  const GLOW_ALPHA = 0.6;

  let particles = [];

  function rebuildGrid() {
    particles = [];
    const cols = Math.ceil(canvas.width / SPACING) + 2;
    const rows = Math.ceil(canvas.height / SPACING) + 2;
    for (let i = 0; i < cols; i++) {
      for (let j = 0; j < rows; j++) {
        const offsetX = (j % 2 === 0) ? 0 : SPACING / 2;
        const hx = i * SPACING - SPACING + offsetX;
        const hy = j * SPACING - SPACING;
        particles.push({ homeX: hx, homeY: hy, x: hx, y: hy });
      }
    }
  }

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    rebuildGrid();
  }
  resize();
  window.addEventListener('resize', resize);

  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  }, true);
  document.addEventListener('mouseleave', () => { mouseX = -9999; mouseY = -9999; });

  function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const p of particles) {
      const dx = p.homeX - mouseX;
      const dy = p.homeY - mouseY;
      const dist = Math.sqrt(dx * dx + dy * dy);

      let targetX = p.homeX, targetY = p.homeY;
      let influence = 0;
      if (dist < REPEL_RADIUS && dist > 0) {
        influence = Math.pow(1 - dist / REPEL_RADIUS, 2);
        const offset = influence * MAX_OFFSET;
        targetX = p.homeX + (dx / dist) * offset;
        targetY = p.homeY + (dy / dist) * offset;
      }

      p.x += (targetX - p.x) * SPRING;
      p.y += (targetY - p.y) * SPRING;

      const alpha = BASE_ALPHA + influence * (GLOW_ALPHA - BASE_ALPHA);
      const r = BASE_R + influence * 1.2;

      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(170, 230, 180,' + alpha + ')';
      if (influence > 0.05) {
        ctx.shadowColor = 'rgba(76,175,80,0.7)';
        ctx.shadowBlur = r * 3;
      } else {
        ctx.shadowBlur = 0;
      }
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
