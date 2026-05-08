// 從圖片抽主色,推到 CSS variable
// 用 canvas 縮成 64x64 取每個像素平均(RGB),再做幾個處理:
//   1. 把太暗(brightness < 0.18)跟太接近灰的像素過濾掉,避免黑色背景拉低主色
//   2. 提升飽和度,讓低彩度的圖也有「accent」感
//   3. 保證亮度不會太暗(夜間風格要是亮色)
// 因為 Steam CDN 的圖預設沒有 CORS,我們透過 image.crossOrigin='anonymous' 試;
// 失敗就 fallback 不變色

export async function extractAccentColor(imageUrl) {
  return new Promise((resolve) => {
    if (!imageUrl) return resolve(null);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.referrerPolicy = 'no-referrer';
    let done = false;
    const finish = (val) => { if (!done) { done = true; resolve(val); } };
    img.onload = () => {
      try {
        const W = 64, H = 32;
        const c = document.createElement('canvas');
        c.width = W; c.height = H;
        const ctx = c.getContext('2d');
        ctx.drawImage(img, 0, 0, W, H);
        const data = ctx.getImageData(0, 0, W, H).data;
        let r = 0, g = 0, b = 0, n = 0;
        for (let i = 0; i < data.length; i += 4) {
          const pr = data[i], pg = data[i+1], pb = data[i+2];
          const lum = 0.2126*pr + 0.7152*pg + 0.0722*pb;
          if (lum < 36) continue;                 // 太暗 (黑底)
          // 過濾近灰(R/G/B 差太小)
          const max = Math.max(pr, pg, pb), min = Math.min(pr, pg, pb);
          if ((max - min) < 25) continue;
          r += pr; g += pg; b += pb; n++;
        }
        if (n === 0) return finish(null);
        r /= n; g /= n; b /= n;
        // 提升飽和(把離平均更遠的色道再往外推)
        const avg = (r + g + b) / 3;
        const boost = 1.45;
        r = Math.min(255, Math.max(0, avg + (r - avg) * boost));
        g = Math.min(255, Math.max(0, avg + (g - avg) * boost));
        b = Math.min(255, Math.max(0, avg + (b - avg) * boost));
        // 保證亮度 ≥ 130(深色主題下要看得到 glow)
        const lum2 = 0.2126*r + 0.7152*g + 0.0722*b;
        if (lum2 < 130) {
          const lift = 130 / Math.max(1, lum2);
          r = Math.min(255, r * lift);
          g = Math.min(255, g * lift);
          b = Math.min(255, b * lift);
        }
        finish(`rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`);
      } catch (e) {
        // canvas tainted 或其他錯誤
        finish(null);
      }
    };
    img.onerror = () => finish(null);
    img.src = imageUrl;
    // 4 秒超時
    setTimeout(() => finish(null), 4000);
  });
}

export function applyAccent(rgb) {
  if (!rgb) {
    document.documentElement.style.removeProperty('--game-accent');
    document.documentElement.style.removeProperty('--game-accent-glow');
    return;
  }
  document.documentElement.style.setProperty('--game-accent', rgb);
  // 對應的 glow 是 rgba 0.55
  const m = rgb.match(/\d+/g);
  if (m) {
    document.documentElement.style.setProperty('--game-accent-glow', `rgba(${m[0]}, ${m[1]}, ${m[2]}, 0.55)`);
  }
}
