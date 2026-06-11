// dashboard-fx.js -- background-effect engine OWNED BY THE DASHBOARD (untracked).
// Lifted out of Odysseus theme.js so the dashboard can add a SPEED control without
// modifying any tracked Odysseus file -> theme.js stays pristine, no git-pull conflicts.
// Self-contained (hexToRgb inlined; THEMES still imported read-only by the dashboard).

function hexToRgb(hex){ if(!hex) return null; hex=String(hex).replace('#','').trim(); if(hex.length===3) hex=hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2]; if(hex.length<6) return null; return { r:parseInt(hex.slice(0,2),16), g:parseInt(hex.slice(2,4),16), b:parseInt(hex.slice(4,6),16) }; }

const _BG_CLASSES = ['bg-pattern-dots',
  'bg-pattern-synapse', 'bg-pattern-rain', 'bg-pattern-constellations',
  'bg-pattern-perlin-flow',
  'bg-pattern-petals', 'bg-pattern-sparkles', 'bg-pattern-embers'];
const _CANVAS_PATTERNS = { synapse: _initSynapse, rain: _initRain, constellations: _initConstellations,
  'perlin-flow': _initPerlinFlow,
  petals: _initPetals, sparkles: _initSparkles, embers: _initEmbers };

export function applyBgEffectColor(color) {
  document.documentElement.style.setProperty('--bg-effect-color', color || '');
}

export function applyBgEffectIntensity(v) {
  // v is 0..1. Default 1 (full intensity) when missing.
  const n = (v === undefined || v === null || isNaN(v)) ? 1 : Math.max(0, Math.min(1, Number(v)));
  document.documentElement.style.setProperty('--bg-effect-intensity', String(n));
}

export function applyBgEffectSize(v) {
  // v is a multiplier 0.3..2.5. Default 1 when missing.
  const n = (v === undefined || v === null || isNaN(v)) ? 1 : Math.max(0.2, Math.min(3, Number(v)));
  document.documentElement.style.setProperty('--bg-effect-size', String(n));
}

export function applyBgEffectSpeed(v) {
  // v is a multiplier 0.2..3. Default 1 when missing. Scales the animation rate of canvas-based effects.
  const n = (v === undefined || v === null || isNaN(v)) ? 1 : Math.max(0.1, Math.min(3, Number(v)));
  document.documentElement.style.setProperty('--bg-effect-speed', String(n));
}

/** Toggle the global "frosted glass" look — applies a translucent + blurred
 *  treatment to every panel, sidebar, modal, dropdown, and popover via CSS
 *  rules scoped to `body.theme-frosted`. */
export function applyFrostedGlass(on) {
  document.body.classList.toggle('theme-frosted', !!on);
}

// Read current size multiplier for JS effects (canvas-based).
function _getEffectSize() {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bg-effect-size'));
  return isNaN(v) ? 1 : v;
}

// Read current speed multiplier for JS effects (canvas-based).
function _getEffectSpeed() {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bg-effect-speed'));
  return isNaN(v) ? 1 : v;
}

// Patterns where the intensity/size sliders have no visible effect.
const _STATIC_PATTERNS = new Set(['none', 'dots']);

export function applyBgPattern(pattern) {
  const p = pattern || 'none';
  document.body.classList.remove(..._BG_CLASSES);
  // Clean up any canvas backgrounds
  document.querySelectorAll('#synapse-canvas, #rain-canvas, #constellations-canvas, #perlin-flow-canvas, #petals-canvas, #sparkles-canvas, #embers-canvas').forEach(c => c.remove());
  if (p !== 'none') document.body.classList.add('bg-pattern-' + p);
  if (_CANVAS_PATTERNS[p]) _CANVAS_PATTERNS[p]();
  // Hide sliders that do nothing on static patterns.
  const hide = _STATIC_PATTERNS.has(p);
  const ig = document.getElementById('theme-bg-intensity-group');
  const sg = document.getElementById('theme-bg-size-group');
  if (ig) ig.style.display = hide ? 'none' : '';
  if (sg) sg.style.display = hide ? 'none' : '';
}

// ── Synapse background effect ──
// Uses the CSS grid pattern as base, overlays fast-moving small light pulses on grid lines
function _initSynapse() {
  if (document.getElementById('synapse-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'synapse-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const GRID = 24; // matches CSS grid size
  const MAX_PULSES = 20;
  const SPEED_MIN = 2;
  const SPEED_MAX = 22;
  const TRAIL_LEN = 12; // pixels of trailing glow

  let W, H, cols, rows, pulses = [];

  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cols = Math.ceil(W / GRID); rows = Math.ceil(H / GRID);
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);

  function getColor() {
    const s = getComputedStyle(document.documentElement);
    return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2';
  }

  function spawnPulse() {
    const speed = SPEED_MIN + Math.random() * (SPEED_MAX - SPEED_MIN);
    if (Math.random() > 0.5) {
      // Horizontal — pick a grid row
      const row = Math.floor(Math.random() * (rows + 1));
      pulses.push({ x: -TRAIL_LEN, y: row * GRID, dx: speed, dy: 0 });
    } else {
      // Vertical — pick a grid column
      const col = Math.floor(Math.random() * (cols + 1));
      pulses.push({ x: col * GRID, y: -TRAIL_LEN, dx: 0, dy: speed });
    }
  }

  function draw() {
    if (!document.body.classList.contains('bg-pattern-synapse')) {
      window.removeEventListener('resize', _onResize);
      canvas.remove();
      return;
    }
    requestAnimationFrame(draw);
    ctx.clearRect(0, 0, W, H);
    const c = getColor();

    const spd = _getEffectSpeed();
    // Spawn
    if (pulses.length < MAX_PULSES && Math.random() < 0.12) spawnPulse();

    // Draw pulses as small bright dots with a short trail
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.x += p.dx * spd; p.y += p.dy * spd;

      // Off screen — remove
      if (p.x > W + TRAIL_LEN || p.y > H + TRAIL_LEN) { pulses.splice(i, 1); continue; }

      // Trail (line gradient fading behind the dot)
      const tx = p.x - (p.dx > 0 ? TRAIL_LEN : 0);
      const ty = p.y - (p.dy > 0 ? TRAIL_LEN : 0);
      const grad = ctx.createLinearGradient(tx, ty, p.x, p.y);
      grad.addColorStop(0, 'transparent');
      grad.addColorStop(1, c);
      ctx.strokeStyle = grad;
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(tx, ty);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();

      // Bright dot at head
      ctx.globalAlpha = 0.55;
      ctx.fillStyle = c;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }
  draw();
}

// ── Rain — thin vertical streaks falling ──
function _initRain() {
  if (document.getElementById('rain-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'rain-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H;
  const drops = [];
  const MAX_DROPS = 130;

  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);

  function getColor() {
    const s = getComputedStyle(document.documentElement);
    return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2';
  }

  function spawn() {
    const len = 20 + Math.random() * 40;
    const speed = 4 + Math.random() * 8;
    drops.push({ x: Math.random() * W, y: -len, len, speed, alpha: 0.32 + Math.random() * 0.28 });
  }

  function draw() {
    if (!document.body.classList.contains('bg-pattern-rain')) {
      window.removeEventListener('resize', _onResize);
      canvas.remove();
      return;
    }
    requestAnimationFrame(draw);
    ctx.clearRect(0, 0, W, H);
    const c = getColor();
    // Intensity also controls rain speed + spawn rate (feels slower/lighter when dim)
    const intenCss = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bg-effect-intensity'));
    const inten = isNaN(intenCss) ? 1 : intenCss;
    const speedMult = 0.35 + inten * 0.65;
    const spd = _getEffectSpeed();
    const sizeMult = _getEffectSize();

    if (drops.length < MAX_DROPS * inten && Math.random() < 0.6 * inten) spawn();

    for (let i = drops.length - 1; i >= 0; i--) {
      const d = drops[i];
      d.y += d.speed * speedMult * spd;
      if (d.y > H + d.len * sizeMult) { drops.splice(i, 1); continue; }

      const effLen = d.len * sizeMult;
      const grad = ctx.createLinearGradient(d.x, d.y - effLen, d.x, d.y);
      grad.addColorStop(0, 'transparent');
      grad.addColorStop(1, c);
      ctx.strokeStyle = grad;
      ctx.globalAlpha = d.alpha;
      ctx.lineWidth = 1.3 * Math.min(2, Math.max(0.6, sizeMult));
      ctx.beginPath();
      ctx.moveTo(d.x, d.y - effLen);
      ctx.lineTo(d.x, d.y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  draw();
}

// ── Constellations — static dots that slowly form/dissolve connecting lines ──
function _initConstellations() {
  if (document.getElementById('constellations-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'constellations-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H;
  const STAR_COUNT = 50;
  const CONNECT_DIST = 120;
  let stars = [];

  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (stars.length === 0) initStars();
  }

  function initStars() {
    stars = [];
    for (let i = 0; i < STAR_COUNT; i++) {
      stars.push({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.15,
        vy: (Math.random() - 0.5) * 0.15,
        r: 0.8 + Math.random() * 0.8,
        phase: Math.random() * Math.PI * 2,
      });
    }
  }

  resize();
  const _onResize = () => { resize(); initStars(); };
  window.addEventListener('resize', _onResize);

  function getColor() {
    const s = getComputedStyle(document.documentElement);
    return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2';
  }

  let t = 0;
  function draw() {
    if (!document.body.classList.contains('bg-pattern-constellations')) {
      window.removeEventListener('resize', _onResize);
      canvas.remove();
      return;
    }
    requestAnimationFrame(draw);
    const spd = _getEffectSpeed();
    t += 0.01 * spd;
    ctx.clearRect(0, 0, W, H);
    const c = getColor();

    // Move stars gently
    for (const s of stars) {
      s.x += s.vx * spd; s.y += s.vy * spd;
      if (s.x < 0) s.x = W; if (s.x > W) s.x = 0;
      if (s.y < 0) s.y = H; if (s.y > H) s.y = 0;
    }

    // Draw connections
    ctx.strokeStyle = c;
    ctx.lineWidth = 0.5;
    for (let i = 0; i < stars.length; i++) {
      for (let j = i + 1; j < stars.length; j++) {
        const dx = stars[i].x - stars[j].x;
        const dy = stars[i].y - stars[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONNECT_DIST) {
          ctx.globalAlpha = (1 - dist / CONNECT_DIST) * 0.15;
          ctx.beginPath();
          ctx.moveTo(stars[i].x, stars[i].y);
          ctx.lineTo(stars[j].x, stars[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw stars with subtle twinkle
    ctx.fillStyle = c;
    for (const s of stars) {
      const twinkle = 0.5 + 0.5 * Math.sin(t * 2 + s.phase);
      ctx.globalAlpha = 0.15 + twinkle * 0.25;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  draw();
}

// ── Noise helper for Perlin effects ──
function _bgNoise2d(x, y) { const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453; return n - Math.floor(n); }
function _bgSmoothNoise(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
  const a = _bgNoise2d(ix, iy), b = _bgNoise2d(ix + 1, iy), cc = _bgNoise2d(ix, iy + 1), d = _bgNoise2d(ix + 1, iy + 1);
  const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
  return a + (b - a) * ux + (cc - a) * uy + (a - b - cc + d) * ux * uy;
}

// ── Perlin Flow — colored particle streams ──
function _initPerlinFlow() {
  if (document.getElementById('perlin-flow-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'perlin-flow-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H, t = 0;
  const particles = [];
  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (particles.length === 0) for (let i = 0; i < 200; i++) particles.push({ x: Math.random() * W, y: Math.random() * H, life: Math.random() });
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);
  function getColor() { const s = getComputedStyle(document.documentElement); return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2'; }
  function getBg() { return getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#282c34'; }
  let _cachedBg = '', _fadeStyle = '';
  function getFade() {
    const bg = getBg();
    if (bg !== _cachedBg) {
      _cachedBg = bg;
      // Parse hex to rgb for rgba fade
      const { r, g, b } = hexToRgb(bg) || { r: 0, g: 0, b: 0 };
      _fadeStyle = `rgba(${r},${g},${b},0.02)`;
    }
    return _fadeStyle;
  }
  function draw() {
    if (!document.body.classList.contains('bg-pattern-perlin-flow')) { window.removeEventListener('resize', _onResize); canvas.remove(); return; }
    requestAnimationFrame(draw);
    ctx.fillStyle = getFade();
    ctx.fillRect(0, 0, W, H);
    const c = getColor();
    const spd = _getEffectSpeed();
    particles.forEach(p => {
      const n = _bgSmoothNoise(p.x * 0.004 + t * 0.0008, p.y * 0.004 + 100);
      const angle = n * Math.PI * 6;
      const speed = 1 + _bgSmoothNoise(p.x * 0.003, p.y * 0.003 + 50) * 1.5;
      p.x += Math.cos(angle) * speed * spd; p.y += Math.sin(angle) * speed * spd; p.life -= 0.001;
      if (p.life <= 0 || p.x < 0 || p.x > W || p.y < 0 || p.y > H) { p.x = Math.random() * W; p.y = Math.random() * H; p.life = 1; }
      ctx.beginPath(); ctx.arc(p.x, p.y, 1, 0, Math.PI * 2);
      ctx.fillStyle = c; ctx.globalAlpha = p.life * 0.15; ctx.fill();
    });
    ctx.globalAlpha = 1;
    t += spd;
  }
  draw();
}

// ── Petals — gentle falling flower petals ──
function _initPetals() {
  if (document.getElementById('petals-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'petals-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H;
  const petals = [];
  function makePetal() {
    return {
      x: Math.random() * W, y: -10 - Math.random() * 40,
      size: 3 + Math.random() * 5, rot: Math.random() * Math.PI * 2,
      vr: (Math.random() - 0.5) * 0.03, vy: 0.3 + Math.random() * 0.6,
      drift: Math.random() * Math.PI * 2, driftSpeed: 0.008 + Math.random() * 0.012,
      wobble: 0.3 + Math.random() * 0.8
    };
  }
  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (petals.length === 0) for (let i = 0; i < 30; i++) { const p = makePetal(); p.y = Math.random() * H; petals.push(p); }
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);
  function getColor() { const s = getComputedStyle(document.documentElement); return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2'; }
  function draw() {
    if (!document.body.classList.contains('bg-pattern-petals')) { window.removeEventListener('resize', _onResize); canvas.remove(); return; }
    requestAnimationFrame(draw);
    ctx.clearRect(0, 0, W, H);
    const c = getColor();
    const sz = _getEffectSize();
    const spd = _getEffectSpeed();
    petals.forEach(p => {
      p.y += p.vy * spd; p.rot += p.vr * spd; p.drift += p.driftSpeed * spd;
      p.x += Math.sin(p.drift) * p.wobble * spd;
      if (p.y > H + 15) Object.assign(p, makePetal());
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
      ctx.globalAlpha = 0.2;
      // petal shape — two overlapping ellipses
      ctx.fillStyle = c;
      ctx.beginPath(); ctx.ellipse(-p.size * 0.2 * sz, 0, p.size * 0.6 * sz, p.size * 0.3 * sz, 0.3, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 0.15;
      ctx.beginPath(); ctx.ellipse(p.size * 0.2 * sz, 0, p.size * 0.6 * sz, p.size * 0.3 * sz, -0.3, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    });
    ctx.globalAlpha = 1;
  }
  draw();
}

// ── Sparkles — twinkling star-shaped sparkles ──
function _initSparkles() {
  if (document.getElementById('sparkles-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'sparkles-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H;
  const sparkles = [];
  function makeSpark() {
    return { x: Math.random() * W, y: Math.random() * H, size: 2 + Math.random() * 5, phase: Math.random() * Math.PI * 2, speed: 0.015 + Math.random() * 0.03, life: 0.5 + Math.random() * 0.5 };
  }
  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (sparkles.length === 0) for (let i = 0; i < 35; i++) sparkles.push(makeSpark());
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);
  function getColor() { const s = getComputedStyle(document.documentElement); return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#9cdef2'; }
  function drawStar(x, y, r, c, alpha) {
    ctx.save(); ctx.translate(x, y); ctx.fillStyle = c; ctx.globalAlpha = alpha;
    // 4-point star
    ctx.beginPath();
    ctx.moveTo(0, -r); ctx.quadraticCurveTo(r * 0.15, -r * 0.15, r, 0);
    ctx.quadraticCurveTo(r * 0.15, r * 0.15, 0, r);
    ctx.quadraticCurveTo(-r * 0.15, r * 0.15, -r, 0);
    ctx.quadraticCurveTo(-r * 0.15, -r * 0.15, 0, -r);
    ctx.fill();
    ctx.restore();
  }
  function draw() {
    if (!document.body.classList.contains('bg-pattern-sparkles')) { window.removeEventListener('resize', _onResize); canvas.remove(); return; }
    requestAnimationFrame(draw);
    ctx.clearRect(0, 0, W, H);
    const c = getColor();
    const sizeMult = _getEffectSize();
    const spd = _getEffectSpeed();
    sparkles.forEach(s => {
      s.phase += s.speed * spd;
      const twinkle = Math.sin(s.phase);
      const alpha = Math.max(0, twinkle) * 0.25 * s.life;
      const scale = 0.5 + Math.max(0, twinkle) * 0.5;
      if (alpha > 0.01) drawStar(s.x, s.y, s.size * scale * sizeMult, c, alpha);
      // respawn when cycle completes
      if (s.phase > Math.PI * 6) Object.assign(s, makeSpark());
    });
    ctx.globalAlpha = 1;
  }
  draw();
}

// ── Embers — warm particles rising with glow and occasional spark bursts ──
function _initEmbers() {
  if (document.getElementById('embers-canvas')) return;
  const canvas = document.createElement('canvas');
  canvas.id = 'embers-canvas';
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
  // Decorative background effect — hide from assistive tech so screen readers
  // don't announce an empty canvas and axe's "region" rule doesn't flag it.
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W, H;
  const embers = [];
  function makeEmber() {
    return {
      x: Math.random() * W,
      y: H + Math.random() * 40,
      vx: (Math.random() - 0.5) * 0.3,
      vy: -0.3 - Math.random() * 0.8,
      r: 0.3 + Math.random() * 0.6,
      life: 0,
      maxLife: 220 + Math.random() * 220,
      wobble: Math.random() * Math.PI * 2,
      spark: false,
    };
  }
  function resize() {
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (embers.length === 0) {
      for (let i = 0; i < 60; i++) { const e = makeEmber(); e.y = Math.random() * H; e.life = Math.random() * e.maxLife; embers.push(e); }
    }
  }
  resize();
  const _onResize = () => resize();
  window.addEventListener('resize', _onResize);
  function getColor() {
    const s = getComputedStyle(document.documentElement);
    return s.getPropertyValue('--bg-effect-color').trim() || s.getPropertyValue('--fg').trim() || '#c9a95a';
  }
  function rgba(hex, a) {
    const { r, g, b } = hexToRgb(hex) || { r: 0, g: 0, b: 0 };
    return `rgba(${r},${g},${b},${a})`;
  }
  function draw() {
    if (!document.body.classList.contains('bg-pattern-embers')) {
      window.removeEventListener('resize', _onResize);
      canvas.remove();
      return;
    }
    requestAnimationFrame(draw);
    // Fade previous frame (destination-out keeps canvas transparent where no embers)
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = 'rgba(0,0,0,0.18)';
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'lighter';
    const color = getColor();
    const spd = _getEffectSpeed();
    for (let i = embers.length - 1; i >= 0; i--) {
      const e = embers[i];
      e.wobble += 0.03 * spd;
      e.x += (e.vx + Math.sin(e.wobble) * 0.5) * spd;
      e.y += e.vy * spd;
      e.life++;
      if (e.life > e.maxLife || e.y < -20) {
        embers.splice(i, 1);
        if (embers.length < 70) embers.push(makeEmber());
        continue;
      }
      if (!e.spark && Math.random() < 0.003) e.spark = true;
      const lifeRatio = e.life / e.maxLife;
      const fade = Math.min(1, Math.min(lifeRatio * 4, (1 - lifeRatio) * 3));
      const sz = _getEffectSize();
      const r = e.r * (e.spark ? 2.4 : 1) * sz;
      const a = (e.spark ? 0.9 : 0.55) * fade;
      const g = ctx.createRadialGradient(e.x, e.y, 0, e.x, e.y, r * 4);
      g.addColorStop(0, rgba(color, a));
      g.addColorStop(0.4, rgba(color, a * 0.3));
      g.addColorStop(1, rgba(color, 0));
      ctx.fillStyle = g;
      ctx.fillRect(e.x - r * 4, e.y - r * 4, r * 8, r * 8);
      ctx.fillStyle = rgba('#ffffff', a * 0.6);
      ctx.beginPath();
      ctx.arc(e.x, e.y, r * 0.5, 0, Math.PI * 2);
      ctx.fill();
      e.spark = false;
    }
    if (Math.random() < 0.015) {
      const bx = Math.random() * W;
      for (let i = 0; i < 5; i++) {
        const e = makeEmber();
        e.x = bx + (Math.random() - 0.5) * 40;
        e.y = H - 10;
        e.vy *= 1.5;
        embers.push(e);
      }
    }
    ctx.globalCompositeOperation = 'source-over';
  }
  draw();
}
