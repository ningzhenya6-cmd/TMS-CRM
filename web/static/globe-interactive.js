// Node data
var nodes = [
  {label:'🇬🇧 英国',r:48,a:0,ring:'outer'},{label:'🇺🇸 美国',r:48,a:45,ring:'outer'},
  {label:'🇦🇺 澳洲',r:48,a:90,ring:'outer'},{label:'🇨🇦 加拿大',r:48,a:135,ring:'outer'},
  {label:'🇸🇬 新加坡',r:48,a:180,ring:'outer'},{label:'🇭🇰 香港',r:48,a:225,ring:'outer'},
  {label:'🇯🇵 日本',r:48,a:270,ring:'outer'},{label:'🇩🇪 德国',r:48,a:315,ring:'outer'},
  {label:'论文辅导',r:36,a:0,ring:'mid'},{label:'考前突击',r:36,a:72,ring:'mid'},
  {label:'同步课程',r:36,a:144,ring:'mid'},{label:'挂科申诉',r:36,a:216,ring:'mid'},
  {label:'选课规划',r:36,a:288,ring:'mid'},
  {label:'理工',r:24,a:0,ring:'inner'},{label:'商科',r:24,a:90,ring:'inner'},
  {label:'人文',r:24,a:180,ring:'inner'},{label:'法学',r:24,a:270,ring:'inner'},
];

var globeScene = document.getElementById('globeScene');
var nodeEls = [], maxR = 48, activeNode = null;

// Create nodes with labels + tap interaction
nodes.forEach(function(n) {
  var el = document.createElement('div');
  el.className = 'kg-node';
  el.innerHTML = '<div class="kg-node-dot"></div><div class="kg-node-label">' + n.label + '</div>';
  
  el.addEventListener('click', function(e) {
    e.stopPropagation();
    if (activeNode) activeNode.el.classList.remove('active');
    if (activeNode === n) { activeNode = null; return; }
    el.classList.add('active');
    activeNode = n;
  });
  el.addEventListener('touchend', function(e) {
    e.stopPropagation(); e.preventDefault();
    if (activeNode) activeNode.el.classList.remove('active');
    if (activeNode === n) { activeNode = null; return; }
    el.classList.add('active');
    activeNode = n;
  });
  
  globeScene.appendChild(el);
  nodeEls.push({el: el, r: n.r, a: n.a, ring: n.ring, angle: n.a});
});

// Orbit motion
var speeds = {outer: 5, mid: -7.5, inner: 11};
function positionNodes(now) {
  nodeEls.forEach(function(n) {
    var ang = ((n.angle + speeds[n.ring] * now / 1000) % 360 + 360) % 360;
    var rad = ang * Math.PI / 180;
    var x = 50 + (n.r / maxR) * 47.5 * Math.cos(rad);
    var y = 50 + (n.r / maxR) * 47.5 * Math.sin(rad);
    n.el.style.left = x + '%';
    n.el.style.top = y + '%';
    n._x = x; n._y = y;
  });
  updateConnections();
}

// Dynamic lines
var svg = document.getElementById('globeConnections');
function updateConnections() {
  var lines = [];
  for (var i = 0; i < nodeEls.length; i++) {
    for (var j = i + 1; j < nodeEls.length; j++) {
      var dx = nodeEls[i]._x - nodeEls[j]._x, dy = nodeEls[i]._y - nodeEls[j]._y;
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d < 30) lines.push({x1: nodeEls[i]._x, y1: nodeEls[i]._y, x2: nodeEls[j]._x, y2: nodeEls[j]._y, d: d});
    }
  }
  svg.innerHTML = lines.map(function(l) {
    return '<line x1="' + l.x1 + '%" y1="' + l.y1 + '%" x2="' + l.x2 + '%" y2="' + l.y2 + '%" ' +
      'stroke="rgba(184,134,76,' + (0.08 * (1 - l.d / 30)).toFixed(3) + ')" stroke-width="0.3" vector-effect="non-scaling-stroke"/>';
  }).join('');
}

// Animation loop
var t0 = performance.now();
function tick(t) { positionNodes(t - t0); requestAnimationFrame(tick); }
requestAnimationFrame(tick);

// Mouse 3D tilt
var heroSide = document.getElementById('heroSide');
heroSide.addEventListener('mousemove', function(e) {
  var r = heroSide.getBoundingClientRect();
  globeScene.style.transform = 'rotateY(' + ((e.clientX - r.left - r.width / 2) / r.width * 14) + 'deg) rotateX(' + (-(e.clientY - r.top - r.height / 2) / r.height * 14) + 'deg)';
});
heroSide.addEventListener('mouseleave', function() { globeScene.style.transform = 'rotateY(0deg) rotateX(0deg)'; });

// Touch 3D tilt
heroSide.addEventListener('touchmove', function(e) {
  var r = heroSide.getBoundingClientRect();
  globeScene.style.transform = 'rotateY(' + ((e.touches[0].clientX - r.left - r.width / 2) / r.width * 14) + 'deg) rotateX(' + (-(e.touches[0].clientY - r.top - r.height / 2) / r.height * 14) + 'deg)';
}, {passive: true});
heroSide.addEventListener('touchend', function() { globeScene.style.transform = 'rotateY(0deg) rotateX(0deg)'; });

// Particles
var canvas = document.getElementById('globeParticles'), ctx = canvas.getContext('2d'), pts = [];
function resizeCanvas() { canvas.width = canvas.offsetWidth; canvas.height = canvas.offsetHeight; }
resizeCanvas();
window.addEventListener('resize', resizeCanvas);
for (var i = 0; i < 80; i++) {
  pts.push({x: Math.random() * 100, y: Math.random() * 100, r: Math.random() * 0.4 + 0.2,
    vx: (Math.random() - 0.5) * 0.15, vy: (Math.random() - 0.5) * 0.15, a: Math.random() * 0.2 + 0.06});
}
function drawParticles() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var w = canvas.width, h = canvas.height;
  pts.forEach(function(p) {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = 100; if (p.x > 100) p.x = 0;
    if (p.y < 0) p.y = 100; if (p.y > 100) p.y = 0;
    ctx.beginPath();
    ctx.arc(p.x / 100 * w, p.y / 100 * h, p.r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(184,134,76,' + p.a + ')';
    ctx.fill();
  });
  for (var i = 0; i < pts.length; i++) {
    for (var j = i + 1; j < pts.length; j++) {
      var dx = (pts[i].x - pts[j].x) / 100 * w, dy = (pts[i].y - pts[j].y) / 100 * h;
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d < 55) {
        ctx.beginPath();
        ctx.moveTo(pts[i].x / 100 * w, pts[i].y / 100 * h);
        ctx.lineTo(pts[j].x / 100 * w, pts[j].y / 100 * h);
        ctx.strokeStyle = 'rgba(184,134,76,' + (0.03 * (1 - d / 55)) + ')';
        ctx.lineWidth = 0.3; ctx.stroke();
      }
    }
  }
  requestAnimationFrame(drawParticles);
}
drawParticles();

// Center orb click -> info overlay
var infoOverlay = document.getElementById('infoOverlay');
var infoBackdrop = document.getElementById('infoBackdrop');
var centerOrb = document.querySelector('.kg-orb');

window.closeInfo = function() {
  if (infoOverlay) infoOverlay.classList.remove('show');
  if (infoBackdrop) infoBackdrop.classList.remove('show');
};

if (centerOrb && infoOverlay) {
  centerOrb.style.pointerEvents = 'auto';
  centerOrb.style.cursor = 'pointer';
  centerOrb.addEventListener('click', function(e) {
    e.stopPropagation();
    var sh = infoOverlay.classList.contains('show');
    if (sh) { closeInfo(); return; }
    infoOverlay.classList.add('show');
    if (infoBackdrop) infoBackdrop.classList.add('show');
  });
  centerOrb.addEventListener('touchend', function(e) {
    e.stopPropagation(); e.preventDefault();
    var sh = infoOverlay.classList.contains('show');
    if (sh) { closeInfo(); return; }
    infoOverlay.classList.add('show');
    if (infoBackdrop) infoBackdrop.classList.add('show');
  });
}

if (infoBackdrop) {
  infoBackdrop.addEventListener('click', closeInfo);
  infoBackdrop.addEventListener('touchend', function(e) { e.preventDefault(); closeInfo(); });
}

// Tap background -> deselect node
heroSide.addEventListener('click', function(e) {
  if (e.target === heroSide || e.target.id === 'globeParticles' || e.target.id === 'globeConnections') {
    if (activeNode) { activeNode.el.classList.remove('active'); activeNode = null; }
    if (infoOverlay && infoOverlay.classList.contains('show')) closeInfo();
  }
});
