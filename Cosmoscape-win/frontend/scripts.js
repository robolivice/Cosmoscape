let clickableStars = [];
let galaxyMeshes = [], galaxyHits = [], galaxyList = [];
let currentGalaxy = null, homeView = null;
let scene, camera, renderer, controls, raycaster, mouse;
let isFlying = false;
let inTransit = false;
let currentStar = null;
let currentMarkdown = "";
const clock = new THREE.Clock();
const textureLoader = new THREE.TextureLoader();
renderer = new THREE.WebGLRenderer({ antialias: true });
const ktx2Loader = new THREE.KTX2Loader()
    .setTranscoderPath('static/vendor/three/examples/js/libs/basis/')
    .detectSupport(renderer);
function loadTex(url) {
    if (!url.endsWith('.ktx2')) return textureLoader.load(url);
    const tex = new THREE.CompressedTexture();
    ktx2Loader.load(url, loaded => {
        tex.copy(loaded);
        tex.encoding = THREE.LinearEncoding;
        tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
        tex.needsUpdate = true;
    }, undefined, err => console.error('KTX2 failed:', url, err));
    return tex;
}
const dayTexture = loadTex('/static/textures/earth_day.ktx2');
const nightTexture = loadTex('/static/textures/earth_night.ktx2');
const starTex = loadTex('/static/textures/sun.ktx2');
const AU_UNIT = 20;
const au = v => v * AU_UNIT;
let activeSystem = null;
let showAllNames = false;
document.getElementById('show-names').addEventListener('change', e => { showAllNames = e.target.checked; });

function seededRng(seed) {
    let a = seed >>> 0;
    return () => {
        a = (a + 0x6D2B79F5) >>> 0;
        let t = a;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
const _sunW = new THREE.Vector3(), _earthW = new THREE.Vector3();
const earthMaterial = new THREE.ShaderMaterial({
    uniforms: {
        uDayTexture: { value: dayTexture },
        uNightTexture: { value: nightTexture },
        uSunDirection: { value: new THREE.Vector3() }
    },
    vertexShader: `
                varying vec2 vUv;
                varying vec3 vNormal;
                void main() {
                    vUv = uv;
                    // Pass world-space normals to match light vectors
                    vNormal = normalize(vec3(modelMatrix * vec4(normal, 0.0))); 
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
    fragmentShader: `
                uniform sampler2D uDayTexture;
                uniform sampler2D uNightTexture;
                uniform vec3 uSunDirection;
                varying vec2 vUv;
                varying vec3 vNormal;
                void main() {
                    // Compare surface direction to sun direction
                    float intensity = dot(vNormal, uSunDirection);
                    // Create a soft twilight transition zone
                    float mixAmount = smoothstep(-0.15, 0.15, intensity);
                    
                    vec4 dayColor = texture2D(uDayTexture, vUv);
                    vec4 nightColor = texture2D(uNightTexture, vUv);
                    
                    gl_FragColor = mix(nightColor, dayColor, mixAmount);
                }
            `
});
const MARK_DIST = 3000;
const NAME_DIST_1 = 250;
const NAME_DIST_2 = 60;
const HOVER_DIST = 300;
let labelEls = [], pinned = null;
const _v = new THREE.Vector3();
const prettyName = n => n.replace(/_/g, ' ');

function buildLabels(stars) {
    const box = document.getElementById('labels');
    box.querySelectorAll('.lbl.auto').forEach(e => e.remove());
    labelEls = [];
    stars.forEach(s => {
        if (!s.cur) return;
        const el = document.createElement('div');
        el.className = 'lbl auto ' + (s.cur === 1 ? 't1' : 't2');
        el.style.display = 'none';
        const ring = document.createElement('span'); ring.className = 'ring';
        const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = prettyName(s.name);
        el.append(ring, nm);
        box.appendChild(el);
        labelEls.push({ el, nm, s });
    });
}

function updateLabels() {
    const box = document.getElementById('labels');
    const cg = currentGalaxy;
    if (!cg || !cg.isMW || activeSystem) { box.style.display = 'none'; return; }
    box.style.display = 'block';
    box.style.opacity = inTransit ? 0 : 1;
    const W = window.innerWidth, H = window.innerHeight;
    const place = (el, v) => { el.style.transform = `translate(${(v.x * 0.5 + 0.5) * W}px, ${(-v.y * 0.5 + 0.5) * H}px)`; };
    for (const L of labelEls) {
        _v.set(L.s.x, L.s.y, L.s.z).applyMatrix4(cg.pivot.matrixWorld);
        const d = camera.position.distanceTo(_v);
        const t1 = L.s.cur === 1;
        if (!t1 && !showAllNames) { L.el.style.display = 'none'; continue; }
        const showMark = t1 ? d < MARK_DIST : d < NAME_DIST_2;
        _v.project(camera);
        if (!showMark || _v.z > 1 || _v.z < -1) { L.el.style.display = 'none'; continue; }
        L.el.style.display = 'block';
        place(L.el, _v);
        L.nm.style.display = d < (t1 ? NAME_DIST_1 : NAME_DIST_2) ? 'block' : 'none';
    }
    const pin = document.getElementById('pin');
    if (pinned) {
        _v.set(pinned.x, pinned.y, pinned.z).applyMatrix4(cg.pivot.matrixWorld).project(camera);
        if (_v.z > 1 || _v.z < -1) pin.style.display = 'none';
        else { pin.style.display = 'block'; place(pin, _v); pin.querySelector('.nm').textContent = prettyName(pinned.name); }
    } else pin.style.display = 'none';
}

let lastHover = 0;
window.addEventListener('pointermove', e => {
    const now = performance.now();
    if (now - lastHover < 50) return;
    lastHover = now;
    const tip = document.getElementById('tip'), cg = currentGalaxy;
    if (!cg || !cg.isMW || activeSystem || isFlying || e.buttons ||
        e.target.closest('#ui') || e.target.closest('.xbutton') || e.target.closest('#info-panel')) { tip.style.display = 'none'; return; }
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    raycaster.params.Points.threshold = camera.position.distanceTo(controls.target) * 0.004;
    const hit = raycaster.intersectObject(cg.points, false)[0];
    if (hit && cg.points.visible && hit.distance < HOVER_DIST) {
        tip.querySelector('.nm').textContent = prettyName(cg.names[hit.index]);
        tip.style.transform = `translate(${e.clientX}px, ${e.clientY - 8}px)`;
        tip.style.display = 'block';
        document.body.style.cursor = 'pointer';
    } else { tip.style.display = 'none'; document.body.style.cursor = ''; }
});

let searchTimer = null;
document.getElementById('search').addEventListener('input', e => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim(), box = document.getElementById('results');
    if (q.length < 2) { box.innerHTML = ''; return; }
    searchTimer = setTimeout(async () => {
        try {
            const res = await (await fetch('/search/?q=' + encodeURIComponent(q))).json();
            box.innerHTML = '';
            res.forEach(s => {
                const d = document.createElement('div');
                d.className = 'result';
                d.textContent = prettyName(s.name);
                d.onclick = () => { box.innerHTML = ''; goToStar(s); };
                box.appendChild(d);
            });
            if (!res.length) box.textContent = 'No match';
        } catch (err) { box.textContent = 'Search failed'; }
    }, 250);
});
document.getElementById('search').addEventListener('keydown', e => e.stopPropagation());

async function goToStar(s) {
    const cg = currentGalaxy;
    if (!cg || !cg.isMW) { document.getElementById('status').innerText = 'Enter the Milky Way first, then search.'; return; }
    if (isFlying) return;
    if (MERGED.has(s.name)) s = cg.stars.find(t => t.name === 'Alpha_Centauri') || s;
    if (activeSystem) await exitSystem();
    if (!cg.stars.some(t => t.name === s.name)) {
        const c = teffToColor(s.teff), m = s.mag == null ? 15 : s.mag;
        const b = Math.min(Math.max(1 - (m - 8) / 14, 0.25), 1);
        s.rgb = [c.r * b, c.g * b, c.b * b];
        cg.stars.push(s);
        cg.lastC = null;
    }
    pinned = s;
    isFlying = true;
    try {
        document.getElementById('status').innerText = `HYPERDRIVE ENGAGED → ${prettyName(s.name)}`;
        const marker = new THREE.Object3D();
        marker.position.copy(cg.pivot.localToWorld(new THREE.Vector3(s.x, s.y, s.z)));
        const dist = camera.position.distanceTo(marker.position);
        await flyTo(marker, Math.min(dist * 0.8, 15));
    }
    finally {
        isFlying = false;
    }

    document.getElementById('status').innerText = `ARRIVED: ${prettyName(s.name)}`;
}

function makeGalaxyTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    const g = c.getContext('2d');
    g.translate(256, 256);
    const glow = g.createRadialGradient(0, 0, 0, 0, 0, 256);
    glow.addColorStop(0, 'rgba(255,240,200,1)');
    glow.addColorStop(0.15, 'rgba(255,220,160,0.7)');
    glow.addColorStop(0.5, 'rgba(120,150,255,0.25)');
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = glow;
    g.fillRect(-256, -256, 512, 512);
    for (let arm = 0; arm < 2; arm++) {
        for (let i = 0; i < 1800; i++) {
            const t = Math.sqrt(Math.random());
            const a = arm * Math.PI + t * 4 + (Math.random() - 0.5) * 0.7;
            const r = t * 240;
            g.fillStyle = `rgba(200,220,255,${0.05 + Math.random() * 0.25})`;
            g.beginPath();
            g.arc(Math.cos(a) * r, -Math.sin(a) * r, 0.8 + Math.random() * 1.6, 0, Math.PI * 2);
            g.fill();
        }
    }
    return new THREE.CanvasTexture(c);
}

const TEX = { rot: -Math.PI / 2, scale: 1.24, flip: false };
const MW_LAYERS = 1
function applyTexAlign(mesh) {
    mesh.rotation.z = TEX.rot;
    mesh.scale.set(TEX.scale * (TEX.flip ? -1 : 1), TEX.scale, 1);
}
window.addEventListener('keydown', e => {
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
    const mw = galaxyMeshes.find(p => p.userData.name === 'Milky_Way');
    if (!mw) return;
    if (e.key === '[') TEX.rot -= 0.02;
    else if (e.key === ']') TEX.rot += 0.02;
    else if (e.key === ',') TEX.scale *= 0.99;
    else if (e.key === '.') TEX.scale *= 1.01;
    else if (e.key === 'm') TEX.flip = !TEX.flip;
    else return;
    mw.userData.layers.forEach(applyTexAlign);
    document.getElementById('status').innerText =
        `TEX rot=${TEX.rot.toFixed(3)} scale=${TEX.scale.toFixed(3)} flip=${TEX.flip}`;
});

const MW_LAYER_GAP = 15;
function makeDiscMask() {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const g = c.getContext('2d');
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grad.addColorStop(0, '#fff');
    grad.addColorStop(0.70, '#fff');
    grad.addColorStop(0.80, '#bbb');
    grad.addColorStop(0.90, '#444');
    grad.addColorStop(1, '#000');
    g.fillStyle = grad; g.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(c);
}

function createGalaxyMesh(g) {
    const tex = g.texture ? loadTex(g.texture) : makeGalaxyTexture();
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
    const isMW = g.name === 'Milky_Way';
    const n = isMW ? MW_LAYERS : 1;
    const baseOpacity = 1 / n;
    const mat = new THREE.MeshBasicMaterial({
        map: tex, transparent: true, opacity: baseOpacity, depthWrite: false,
        side: THREE.DoubleSide, blending: THREE.AdditiveBlending
    });
    if (isMW) mat.alphaMap = makeDiscMask();
    const pivot = new THREE.Group();
    const layers = [];
    for (let i = 0; i < n; i++) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(g.display, g.display), mat);
        m.rotation.x = -Math.PI / 2;
        m.position.y = (i - (n - 1) / 2) * MW_LAYER_GAP;
        if (isMW) applyTexAlign(m);
        pivot.add(m);
        layers.push(m);
    }
    pivot.position.set(g.x, g.y, g.z);
    pivot.rotation.x = isMW ? 0 : g.tilt;
    pivot.userData = { name: g.name, info: g, mesh: layers[Math.floor(n / 2)], layers, baseOpacity };
    return pivot;
}

async function loadGalaxies() {
    galaxyMeshes.forEach(p => scene.remove(p));
    galaxyMeshes = [];
    galaxyHits = [];
    try {
        const res = await fetch('/galaxies/');
        galaxyList = await res.json();
        galaxyList.forEach(g => {
            document.getElementById('status').innerText = "SYS STATUS: ONLINE // CLICK A GALAXY TO ENTER";
            const pivot = createGalaxyMesh(g);
            scene.add(pivot);
            galaxyMeshes.push(pivot);
            galaxyHits.push(pivot.userData.mesh);
        });
        try {
            const st = await (await fetch('/api/status')).json();
            if (st.stars < 1000) {
                document.getElementById('status').innerText = 'Starter data only. Press Import Database for the full catalog.';
            }
        } catch (e) { }
    } catch (e) {
        console.error('galaxy load failed', e);
    }
}

function teffToColor(teff) {
    const t = Math.min(Math.max(teff || 5500, 2500), 20000);
    const k = (t - 2500) / 17500;
    return new THREE.Color().setHSL(0.02 + 0.6 * k, 0.8, 0.65);
}

function buildGalaxyCloud(pivot, stars) {
    const isMW = pivot.userData.name === 'Milky_Way';
    const cap = stars.length;
    const pos = new Float32Array(cap * 3), col = new Float32Array(cap * 3);
    stars.forEach((s, i) => {
        const c = teffToColor(s.teff);
        const m = s.mag == null ? 15 : s.mag;
        const b = Math.min(Math.max(1 - (m - 8) / 14, 0.25), 1);
        s.rgb = [c.r * b, c.g * b, c.b * b];
        if (!isMW) { pos.set([s.x, s.y, s.z], i * 3); col.set(s.rgb, i * 3); }
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geo.setDrawRange(0, isMW ? 0 : stars.length);
    const points = new THREE.Points(geo, new THREE.PointsMaterial({
        size: 2.5, sizeAttenuation: false, map: dotTex, vertexColors: true,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending
    }));
    points.frustumCulled = false;
    pivot.add(points);
    return points;
}
let planetMap = {};            
const MODEL_SCALE = 0.03;
const MODEL_RADIUS = 20;
const MODEL_MAX = 40;
const MODEL_VIEW_DIST = 120;
let lastStream = 0;

function removeModel(m) {
    currentGalaxy.pivot.remove(m);
    m.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    const i = clickableStars.indexOf(m);
    if (i >= 0) clickableStars.splice(i, 1);
    m.userData.members.forEach(mem => {
        const j = hitTargets.indexOf(mem.core);
        if (j >= 0) hitTargets.splice(j, 1);
    });
}

function clearModels() {
    if (!currentGalaxy || !currentGalaxy.models) return;
    currentGalaxy.models.forEach(removeModel);
    currentGalaxy.models.clear();
}

const DOT_RADIUS = 500;
function updateModels(now) {
    const cg = currentGalaxy;
    if (!cg || !cg.isMW || activeSystem || now - lastStream < 250) return;
    lastStream = now;
    const camDist = camera.position.distanceTo(controls.target);
    const wantModels = false;
    const c = cg.pivot.worldToLocal(controls.target.clone());
    const moved = !cg.lastC || cg.lastC.distanceTo(c) > 4;
    if (!moved && !cg.pending && wantModels === cg.hadModels) return;
    cg.hadModels = wantModels;

    if (moved) {
        cg.lastC = c.clone();
        const geo = cg.points.geometry;
        const P = geo.attributes.position.array, C = geo.attributes.color.array;
        const r2 = DOT_RADIUS * DOT_RADIUS;
        const names = [];
        let n = 0;
        for (const s of cg.stars) {
            const dx = s.x - c.x, dy = s.y - c.y, dz = s.z - c.z;
            const d2 = dx * dx + dy * dy + dz * dz;
            if (d2 >= r2) continue;
            const f = 1 - THREE.MathUtils.smoothstep(Math.sqrt(d2), DOT_RADIUS * 0.55, DOT_RADIUS);
            P[n * 3] = s.x; P[n * 3 + 1] = s.y; P[n * 3 + 2] = s.z;
            C[n * 3] = s.rgb[0] * f; C[n * 3 + 1] = s.rgb[1] * f; C[n * 3 + 2] = s.rgb[2] * f;
            names.push(s.name);
            n++;
        }
        geo.attributes.position.needsUpdate = true;
        geo.attributes.color.needsUpdate = true;
        geo.setDrawRange(0, n);
        geo.computeBoundingSphere();
        cg.names = names;
    }

    const keep2 = (MODEL_RADIUS * 1.4) ** 2;
    cg.models.forEach((m, name) => {
        if (!wantModels || m.position.distanceToSquared(c) > keep2) { removeModel(m); cg.models.delete(name); }
    });
    cg.pending = false;
    if (!wantModels) return;

    const add2 = MODEL_RADIUS * MODEL_RADIUS, cand = [];
    for (const s of cg.stars) {
        if (cg.models.has(s.name) || MERGED.has(s.name)) continue;
        const dx = s.x - c.x, dy = s.y - c.y, dz = s.z - c.z;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < add2) cand.push([d2, s]);
    }
    cand.sort((a, b) => a[0] - b[0]);
    let made = 0;
    for (const [, s] of cand) {
        if (cg.models.size >= MODEL_MAX) break;
        if (made >= 20) { cg.pending = true; break; }
        s.planets = planetMap[s.name];
        const m = createStarSystem(s, true);
        m.scale.setScalar(MODEL_SCALE);
        m.userData.lite = true;
        cg.pivot.add(m);
        cg.models.set(s.name, m);
        clickableStars.push(m);
        m.userData.members.forEach(mem => hitTargets.push(mem.core));
        made++;
    }
}
const MESH_FADE_NEAR = 150, MESH_FADE_FAR = 700;
function updateMeshFade() {
    const cg = currentGalaxy;
    if (!cg || !cg.isMW) return;
    const d = camera.position.distanceTo(controls.target);
    const f = THREE.MathUtils.smoothstep(d, MESH_FADE_NEAR, MESH_FADE_FAR);
    const u = cg.pivot.userData;
    u.mesh.material.opacity = u.baseOpacity * f;
    u.layers.forEach(l => l.visible = f > 0.01);
    cg.points.material.opacity = (1 - f) * galaxyFade;
    cg.points.visible = f < 0.99 && galaxyFade > 0.01;
}

const hide = document.getElementById('back-btn');
const show = document.getElementById('main-btn');
async function enterGalaxy(pivot) {
    const g = pivot.userData.info;
    isFlying = true;
    document.getElementById('info-panel').style.display = 'none';
    document.getElementById('status').innerText = `HYPERDRIVE ENGAGED → ${g.name}`;
    homeView = { pos: camera.position.clone(), target: controls.target.clone() };
    const view = new THREE.Vector3(0, 1, 0.7).applyQuaternion(pivot.quaternion);
    await (g.name === 'Milky_Way' ? flyTo(new THREE.Object3D(), 1500, view) : flyTo(pivot, g.display * 0.9, view));
    document.getElementById('status').innerText = `LOADING ${g.name}...`;
    try {
        const res = await fetch(`/galaxy/${encodeURIComponent(g.name)}/stars`);
        const stars = (await res.json()).filter(s => !MERGED.has(s.name));
        const points = buildGalaxyCloud(pivot, stars);
        currentGalaxy = { pivot, points, names: stars.map(s => s.name), stars, models: new Map(), skip: new Set(), isMW: g.name === 'Milky_Way' };
        buildLabels(stars);
        if (g.name === 'Milky_Way') {
            try { planetMap = await (await fetch('/planets/')).json(); } catch (e) { planetMap = {}; }
        }
        galaxyMeshes.forEach(p => { if (p !== pivot) p.visible = false; });
        hide.classList.remove('hide');
        show.classList.add('hide')
        document.getElementById('back-btn').style.display = 'inline-block';
        document.getElementById('status').innerText = `${g.name}: ${stars.length} STARS`;
    } catch (e) {
        console.error('enterGalaxy failed:', e);
        document.getElementById('status').innerText = "Galaxy load failed.";
    }
    isFlying = false;
}

async function exitGalaxy() {
    pinned = null;
    if (!currentGalaxy || isFlying) return;
    if (activeSystem) { exitSystem(); return; }
    const { pivot, points } = currentGalaxy;
    clearModels();
    pivot.remove(points);
    points.geometry.dispose();
    points.material.dispose();
    pivot.userData.mesh.material.opacity = pivot.userData.baseOpacity;
    pivot.userData.layers.forEach(l => l.visible = true);
    currentGalaxy = null;
    clickableStars.forEach(s => scene.remove(s));
    clickableStars = []; hitTargets = [];
    galaxyMeshes.forEach(p => p.visible = true);
    show.classList.remove('hide');
    document.getElementById('back-btn').style.display = 'none';
    document.getElementById('info-panel').style.display = 'none';

    const home = new THREE.Object3D();
    home.position.copy(homeView.target);
    home.userData.name = 'home';
    isFlying = true;
    await flyTo(home, homeView.pos.distanceTo(homeView.target));
    isFlying = false;
    document.getElementById('status').innerText = 'Back at galaxy view.';
}

function makeDotTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(0.4, 'rgba(255,255,255,0.8)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
}
const dotTex = makeDotTexture();
const YEAR_SECONDS = 10;
const DAY_SECONDS = 4;
const ringTex = loadTex('/static/textures/saturn_ring.ktx2');
let hitTargets = [];

function orbitSpeed(def) {
    const ys = def.yearSeconds || YEAR_SECONDS;
    return def.period ? (2 * Math.PI) / ((def.period / 365.25) * ys) : def.speed;
}

function solveKepler(M, e) {
    let E = M;
    for (let i = 0; i < 6; i++) E -= (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E));
    return E;
}
function orbitPos(o, t) {
    const n = (2 * Math.PI) / ((o.period * YEAR_SECONDS) / (o.boost || 1));
    const E = solveKepler((o.phase || 0) + n * t, o.e);
    const b = o.a * Math.sqrt(1 - o.e * o.e);
    return [o.a * (Math.cos(E) - o.e) * o.scale, 0, b * Math.sin(E) * o.scale];
}
function spinSpeed(def) {
    return def.spinHours ? (2 * Math.PI) / ((def.spinHours / 23.93) * DAY_SECONDS) : 1;
}

function makeRing(size) {
    const inner = size * 1.25, outer = size * 2.4;
    const geo = new THREE.RingGeometry(inner, outer, 128);
    const pos = geo.attributes.position, uv = geo.attributes.uv, v = new THREE.Vector3();
    for (let i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i);
        uv.setXY(i, (v.length() - inner) / (outer - inner), 0.5);
    }
    const ring = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
        map: ringTex, side: THREE.DoubleSide, transparent: true, depthWrite: false
    }));
    ring.rotation.x = Math.PI / 2;
    return ring;
}

function initEngine() {
    scene = new THREE.Scene();
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const sun = new THREE.DirectionalLight(0xffffff, 0);
    sun.position.set(50, 80, 50);
    scene.add(sun);
    earthMaterial.uniforms.uSunDirection.value.copy(sun.position).normalize();
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 30000);

    renderer.setSize(window.innerWidth, window.innerHeight);
    document.body.appendChild(renderer.domElement);
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.maxDistance = 9000;
    controls.minDistance = 1;
    if (controls.listenToKeyEvents) controls.listenToKeyEvents(window);
    controls.keyPanSpeed = 30;
    camera.position.set(0, 40, 120);
    controls.update();

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    const bgGeom = new THREE.BufferGeometry();
    const bgPos = [];
    for (let i = 0; i < 3000; i++) {
        const r = 12000 + Math.random() * 2000;
        const th = Math.random() * Math.PI * 2;
        const ph = Math.acos(2 * Math.random() - 1);
        bgPos.push(r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th));
    }
    bgGeom.setAttribute('position', new THREE.Float32BufferAttribute(bgPos, 3));
    bgStars = new THREE.Points(bgGeom, new THREE.PointsMaterial({
        color: 0x999999, size: 2.5, sizeAttenuation: false,
        map: dotTex, transparent: true, depthWrite: false, alphaTest: 0.01
    }));
    bgStars.frustumCulled = false;
    scene.add(bgStars);

    loadGalaxies();
    window.addEventListener('click', onSpaceClick);

    animate();
}

let trueScale = false;
let timeScale = 1, paused = false, simTime = 0;

document.getElementById('true-scale').addEventListener('change', e => {
    trueScale = e.target.checked;
    document.getElementById('status').innerText =
        `Alpha Centauri scale: ${trueScale ? 'TRUE' : 'compact'} (applies next time you enter the system)`;
});
document.getElementById('time-slider').addEventListener('input', e => {
    timeScale = Math.pow(10, parseFloat(e.target.value));
    document.getElementById('time-label').innerText =
        (timeScale < 10 ? timeScale.toFixed(1) : Math.round(timeScale)) + 'x';
});
document.getElementById('pause-time').addEventListener('change', e => { paused = e.target.checked; });

function alphaCenSystem() {
    const proxSize = 1.1;
    const planets = [
        { sma: 0.029, size: 0.3, period: 5.12, color: 0x7ddc8a },
        { sma: 0.0485, size: 0.4, period: 11.19, color: 0xc2713b }
    ].map((p, i) => ({
        orbit: Math.max(trueScale ? au(p.sma) : 3.0 + i * 1.2, proxSize * 1.8 + i * 0.6),
        size: p.size, period: p.period, yearSeconds: 600, spinHours: 24, color: p.color
    }));
    const proxOrbit = trueScale
        ? { a: au(8700), e: 0.5, period: 547000, phase: 1.0, scale: 1 }
        : { a: 1000, e: 0.2, period: 547000, phase: 1.0, scale: 1 };
    return {
        stars: [
            { name: 'Alpha_Centauri_A', color: 0xfff1c9, size: 2.0, orbit: { ...AB_ORBIT, scale: -0.457 } },
            { name: 'Alpha_Centauri_B', color: 0xffb35c, size: 1.6, orbit: { ...AB_ORBIT, scale: 0.543 } },
            { name: 'Proxima_Centauri', color: 0xff6b6b, size: proxSize, orbit: proxOrbit, planets }
        ]
    };
}

const ARRIVE_R = 3;
const ZOOM_RATIO = 40;
let galaxyFade = 1;
let zoomFx = null;
let bgStars = null;

function startZoomFx(group, starPos, r0, r1) {
    const lines = [];
    group.traverse(o => { if (o.isLine) lines.push(o.material); });
    zoomFx = { pos: starPos.clone(), l0: Math.log(r0), l1: Math.log(r1), group, lines };
    updateZoomFx();
}
function updateZoomFx() {
    if (!zoomFx) return;
    const d = camera.position.distanceTo(zoomFx.pos);
    const k = THREE.MathUtils.smoothstep(Math.log(Math.max(d, 1e-6)), zoomFx.l0, zoomFx.l1);
    galaxyFade = k;
    zoomFx.lines.forEach(m => { m.opacity = 0.25 * (1 - k); });
    zoomFx.group.visible = k < 0.999;
    camera.near = Math.min(0.1, Math.max(0.0002, d * 0.01));
    camera.updateProjectionMatrix();
}
function endZoomFx() {
    if (!zoomFx) return;
    zoomFx.lines.forEach(m => { m.opacity = 0.25; });
    zoomFx.group.visible = true;
    zoomFx = null;
    galaxyFade = 1;
}

function systemExtent(group) {
    let extent = 10;
    group.userData.members.forEach(m => {
        const o = m.orbit;
        const off = o ? o.a * (1 + o.e) * Math.abs(o.scale || 1) : 0;
        if (off > 20000) return;
        let far = 0;
        m.bodies.forEach(b => { far = Math.max(far, b.radius); });
        extent = Math.max(extent, off + far);
    });
    return extent;
}

async function enterSystem(name) {
    pinned = null;
    const cg = currentGalaxy;
    if (!cg || isFlying || activeSystem) return;
    const star = cg.stars.find(s => s.name === name);
    if (!star) return;
    const sysName = MERGED.has(name) ? 'Alpha_Centauri' : name;
    isFlying = true; inTransit = true;
    let group = null, done = false;
    try {
        document.getElementById('info-panel').style.display = 'none';
        document.getElementById('status').innerText = `HYPERDRIVE ENGAGED → ${sysName}`;

        const marker = new THREE.Object3D();
        marker.position.copy(cg.pivot.localToWorld(new THREE.Vector3(star.x, star.y, star.z)));
        const saved = { pos: camera.position.clone(), target: controls.target.clone(), starPos: marker.position.clone() };

        group = createStarSystem({
            name: sysName, teff: star.teff, planets: planetMap[sysName] || planetMap[name],
            x: 0, y: 0, z: 0
        });
        const d = Math.min(Math.max(systemExtent(group) * 1.5, 40), 8000);
        const dist = camera.position.distanceTo(marker.position);
        const rEnd = Math.max(Math.min(ARRIVE_R, dist / ZOOM_RATIO), 0.01);
        const s = rEnd / d;
        group.scale.setScalar(s);
        group.position.copy(marker.position);
        scene.add(group);
        clickableStars.push(group);
        startZoomFx(group, marker.position, rEnd * 1.05, Math.max(Math.min(dist, rEnd * 30), rEnd * 1.6));

        const h = new THREE.Vector3(camera.position.x - marker.position.x, 0, camera.position.z - marker.position.z);
        if (h.lengthSq() < 1e-10) h.set(0, 0, 1);
        const dirv = h.normalize().setY(0.47).normalize();
        await flyTo(marker, rEnd, dirv, dist < ARRIVE_R * 120 ? 2600 : undefined);

        const rel = camera.position.clone().sub(marker.position).divideScalar(s);
        endZoomFx();
        group.scale.setScalar(1);
        group.position.set(0, 0, 0);
        cg.pivot.visible = false;
        group.userData.members.forEach(m => hitTargets.push(m.core));
        camera.near = 0.05; camera.updateProjectionMatrix();
        controls.minDistance = 3;
        camera.position.copy(rel);
        controls.target.set(0, 0, 0);
        controls.update();
        activeSystem = { group, saved, s, d, starPos: saved.starPos };
        done = true;

        document.getElementById('time-ui').style.display = 'block';
        document.getElementById('status').innerText = `SYSTEM: ${sysName}  (1 AU = ${AU_UNIT} units)`;
        showDetails(sysName);
    } finally {
        if (!done && group) {
            endZoomFx();
            scene.remove(group);
            clickableStars = clickableStars.filter(g => g !== group);
        }
        inTransit = false;
        isFlying = false;
    }
}

async function exitSystem() {
    if (!activeSystem || isFlying) return;
    isFlying = true; inTransit = true;
    try {
        const { group, saved, s, d, starPos } = activeSystem;
        const cg = currentGalaxy;
        document.getElementById('info-panel').style.display = 'none';
        document.getElementById('time-ui').style.display = 'none';
        document.getElementById('status').innerText = 'HYPERDRIVE ENGAGED → galaxy';

        const rEnd = s * d;
        const relCam = camera.position.clone();
        const relTgt = controls.target.clone();
        group.position.copy(starPos);
        group.scale.setScalar(s);
        camera.position.copy(starPos).addScaledVector(relCam, s);
        controls.target.copy(starPos).addScaledVector(relTgt, s);
        controls.minDistance = 0;
        cg.pivot.visible = true;
        cg.lastC = null; lastStream = 0;
        startZoomFx(group, starPos, rEnd * 1.05, rEnd * 30);

        const out = Math.min(Math.max(saved.pos.distanceTo(saved.starPos), rEnd * 36), 8500);
        const marker = new THREE.Object3D();
        marker.position.copy(starPos);
        await flyTo(marker, out, relCam.clone().normalize(), 2600);

        scene.remove(group);
        group.traverse(o => { if (o.geometry) o.geometry.dispose(); });
        endZoomFx();
        clickableStars = []; hitTargets = [];
        activeSystem = null;
        camera.near = 0.1; camera.updateProjectionMatrix();
        controls.minDistance = 1;
        document.getElementById('status').innerText =
            `${cg.pivot.userData.name}: ${cg.stars.length} STARS`;
    } finally {
        inTransit = false;
        isFlying = false;
    }
}

let importing = false;
async function syncData() {
    const statusEl = document.getElementById('status');
    const btn = document.getElementById('main-btn');
    if (currentGalaxy) { statusEl.innerText = 'Go back to the galaxy view first.'; return; }
    if (importing) return;
    importing = true;
    btn.disabled = true;
    statusEl.innerText = 'Starting import...';
    try {
        await fetch('/api/import-data', { method: 'POST' });
        while (true) {
            await new Promise(r => setTimeout(r, 500));
            const s = await (await fetch('/api/import-status')).json();
            if (s.status === 'running') {
                statusEl.innerText = `${s.message}... ${s.progress}%`;
            } else if (s.status === 'done') {
                statusEl.innerText = 'Database imported!';
                await loadGalaxies();
                break;
            } else if (s.status === 'error') {
                statusEl.innerText = 'Import failed: ' + s.message;
                break;
            } else {
                break;
            }
        }
    } catch (e) {
        statusEl.innerText = 'Server communication anomaly.';
    } finally {
        importing = false;
        btn.disabled = false;
    }
}

function hashName(s) {
    let h = 0;
    for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return h;
}

function randomPlanetDefs(seed, colors, starSize) {
    const rnd = seededRng(seed);
    const n = 3 + Math.floor(rnd() * 6);
    let a = 0.25 + rnd() * 0.5;
    const out = [];
    for (let i = 0; i < n; i++) {
        const giant = a > 2.5 && rnd() < 0.6;
        out.push({
            orbit: Math.max(au(a), starSize * 1.8 + i * 0.5),
            size: giant ? 0.9 + rnd() * 0.6 : 0.25 + rnd() * 0.35,
            period: Math.max(365.25 * Math.pow(a, 1.5), 30),
            spinHours: 10 + rnd() * 30,
            tilt: rnd() * 30,
            color: colors[Math.floor(rnd() * colors.length)],
            ring: giant && rnd() < 0.3
        });
        a *= 1.4 + rnd() * 0.8;
    }
    return out;
}

function realPlanetDefs(list, starSize) {
    const sorted = list.filter(p => p.sma || p.period)
        .map(p => ({ ...p, sma: p.sma || Math.pow(p.period / 365.25, 2 / 3) }))
        .sort((a, b) => a.sma - b.sma).slice(0, 12);
    return sorted.map((p, i) => {
        const r = p.rade || 2;
        return {
            orbit: Math.max(au(p.sma), starSize * 1.8 + i * 0.4),
            size: Math.min(Math.max(0.2 + 0.1 * Math.sqrt(r), 0.25), 0.9),
            period: Math.max(p.period || 365.25 * Math.pow(p.sma, 1.5), 30),
            spinHours: 24,
            color: r < 1.6 ? 0xb08968 : r < 6 ? 0x6fa8dc : 0xd9a066
        };
    });
}

const AB_ORBIT = { a: 23.4 * AU_UNIT, e: 0.52, period: 79.9, boost: 20 };

const REAL_SYSTEMS = {
    Sol: {
        stars: [{
            name: 'Sol', color: 0xffffff, size: 2,
            planets: [
                { orbit: au(0.387), size: 0.3, period: 87.97, spinHours: 1407.6, tilt: 0.03, texture: '/static/textures/mercury.ktx2' },
                { orbit: au(0.723), size: 0.55, period: 224.7, spinHours: 5832.5, tilt: 177.4, texture: '/static/textures/venus.ktx2' },
                { orbit: au(1.0), size: 0.6, period: 365.25, spinHours: 23.93, tilt: 23.4, texture: '/static/textures/earth.ktx2' },
                { orbit: au(1.524), size: 0.4, period: 687, spinHours: 24.62, tilt: 25.2, texture: '/static/textures/mars.ktx2' },
                { orbit: au(5.203), size: 1.3, period: 4332.6, spinHours: 9.93, tilt: 3.1, texture: '/static/textures/jupiter.ktx2' },
                { orbit: au(9.537), size: 1.1, period: 10759, spinHours: 10.66, tilt: 26.7, texture: '/static/textures/saturn.ktx2', ring: true },
                { orbit: au(19.19), size: 0.8, period: 30687, spinHours: 17.24, tilt: 97.8, texture: '/static/textures/uranus.ktx2' },
                { orbit: au(30.07), size: 0.8, period: 60190, spinHours: 16.11, tilt: 28.3, texture: '/static/textures/neptune.ktx2' }
            ]
        }]
    },
    Alpha_Centauri: {
        stars: [
            { name: 'Alpha_Centauri_A', color: 0xfff1c9, size: 2.0, orbit: { ...AB_ORBIT, scale: -0.457 } },
            { name: 'Alpha_Centauri_B', color: 0xffb35c, size: 1.6, orbit: { ...AB_ORBIT, scale: 0.543 } },
            {
                name: 'Proxima_Centauri', color: 0xff6b6b, size: 1.1,
                orbit: { a: 40, e: 0.5, period: 547000, phase: 1.0, scale: 1 },
                planets: [
                    { orbit: 3.0, size: 0.4, period: 11.19, yearSeconds: 600, spinHours: 24, color: 0xc2713b },
                    { orbit: 4.2, size: 0.3, period: 5.12, yearSeconds: 600, spinHours: 24, color: 0x7ddc8a }
                ]
            }
        ]
    }
};
REAL_SYSTEMS.Sun = REAL_SYSTEMS.Sol;
const MERGED = new Set(['Proxima_Centauri']);
REAL_SYSTEMS.Sun = REAL_SYSTEMS.Sol;

function createStarSystem(star, lite) {
    const group = new THREE.Group();
    group.position.set(star.x, star.y, star.z);

    const seed = hashName(star.name);
    const starColors = [0xffdb66, 0xff8c42, 0x9ec5ff, 0xffffff, 0xff6b6b];
    const planetColors = [0x4f9dff, 0xc2713b, 0x7ddc8a, 0xd9c28b, 0xb48cff];
    const real = star.name === 'Alpha_Centauri' ? alphaCenSystem() : REAL_SYSTEMS[star.name];
    const hasReal = star.planets && star.planets.length;
    const sSize = star.teff ? Math.min(Math.max(star.teff / 3500, 1), 2.6) : 2;
    const starDefs = real ? real.stars : [{
        name: star.name,
        color: star.teff ? teffToColor(star.teff) : starColors[seed % starColors.length],
        size: sSize,
        planets: hasReal ? realPlanetDefs(star.planets, sSize) : randomPlanetDefs(seed, planetColors, sSize)
    }];

    const members = [];
    starDefs.forEach((sd, si) => {
        const sg = new THREE.Group();
        sg.userData.name = sd.name;
        const size = sd.size || 2;

        const core = new THREE.Mesh(
            new THREE.SphereGeometry(size, lite ? 20 : 32, lite ? 20 : 32),
            new THREE.MeshBasicMaterial({ map: starTex, color: sd.color })
        );
        const glow = lite
            ? new THREE.Sprite(new THREE.SpriteMaterial({
                map: dotTex, color: sd.color, transparent: true, opacity: 0.9,
                blending: THREE.AdditiveBlending, depthWrite: false
            }))
            : new THREE.Mesh(
                new THREE.SphereGeometry(size * 1.7, 32, 32),
                new THREE.MeshBasicMaterial({
                    color: sd.color, transparent: true, opacity: 0.2,
                    blending: THREE.AdditiveBlending, depthWrite: false
                }));
        if (lite) glow.scale.setScalar(size * 5);
        sg.add(core, glow);
        sg.add(new THREE.PointLight(0xffffff, 1, 0, 1));

        const bodies = [];
        (sd.planets || []).forEach((def, i) => {
            const holder = new THREE.Group();
            holder.rotation.z = THREE.MathUtils.degToRad(def.tilt || 0);
            let mat;
            if (def.texture && def.texture.includes('earth')) {
                mat = earthMaterial;
            } else if (def.texture) {
                mat = new THREE.MeshStandardMaterial({ map: loadTex(def.texture) });
            } else {
                mat = new THREE.MeshStandardMaterial({ color: def.color, roughness: 0.8 });
            }
            const mesh = new THREE.Mesh(new THREE.SphereGeometry(def.size, lite ? 16 : 48, lite ? 16 : 48), mat);
            holder.add(mesh);
            if (def.ring) holder.add(makeRing(def.size));
            sg.add(holder);

            const pts = [];
            for (let k = 0; k < 256; k++) {
                const a = (k / 256) * Math.PI * 2;
                pts.push(new THREE.Vector3(Math.cos(a) * def.orbit, 0, Math.sin(a) * def.orbit));
            }
            const path = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts),
                new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.25 }));
            sg.add(path);

            bodies.push({
                holder, mesh, radius: def.orbit,
                angle: ((seed >> (i * 3)) % 628) / 100,
                orbitSpeed: orbitSpeed(def),
                spinSpeed: spinSpeed(def)
            });
        });

        group.add(sg);
        members.push({ group: sg, core, glow, bodies, orbit: sd.orbit, phase: ((seed + si * 37) % 100) / 10 });
    });

    group.userData = { name: star.name, members };
    return group;
}

function flyTo(target, distance, dirOverride, duration) {
    return new Promise(resolve => {
        const startPos = camera.position.clone();
        const startTarget = controls.target.clone();
        const endTarget = target.getWorldPosition(new THREE.Vector3());
        const d0 = startPos.clone().sub(startTarget);
        const r0 = Math.max(d0.length(), 1e-6);
        d0.normalize();
        const d1 = dirOverride ? dirOverride.clone().normalize() : startPos.clone().sub(endTarget).normalize();
        const r1 = Math.max(distance || (target.userData.name === 'Sol' ? 30 : 16), 1e-6);
        const endPos = endTarget.clone().addScaledVector(d1, r1);
        const travel = startPos.distanceTo(endPos);
        const dur = duration || Math.min(Math.max(700 + 700 * Math.log10(1 + travel), 800), 4200);
        const qFull = new THREE.Quaternion().setFromUnitVectors(d0, d1);
        const q = new THREE.Quaternion();
        const dir = new THREE.Vector3();
        const startFov = camera.fov;
        const savedMin = controls.minDistance;
        const t0 = performance.now();
        controls.enabled = false;
        controls.minDistance = 0;

        function step(now) {
            const k = Math.min(Math.max((now - t0) / dur, 0), 1);
            const e = k * k * k * (k * (k * 6 - 15) + 10);
            controls.target.lerpVectors(startTarget, endTarget, e);
            q.set(0, 0, 0, 1).slerp(qFull, e);
            dir.copy(d0).applyQuaternion(q);
            const r = r0 * Math.pow(r1 / r0, e);
            camera.position.copy(controls.target).addScaledVector(dir, r);
            camera.fov = startFov + 12 * Math.sin(Math.PI * k);
            camera.updateProjectionMatrix();
            if (k < 1) {
                requestAnimationFrame(step);
            } else {
                camera.position.copy(endPos);
                controls.target.copy(endTarget);
                camera.fov = startFov;
                camera.updateProjectionMatrix();
                controls.minDistance = savedMin;
                controls.enabled = true;
                resolve();
            }
        }
        requestAnimationFrame(step);
    });
}

async function loadStars() {
    if (!scene) return;

    clickableStars.forEach(s => scene.remove(s));
    clickableStars = [];
    hitTargets = [];

    try {
        const res = await fetch('/objects/');
        const data = await res.json();

        if (data.length === 0) {
            document.getElementById('status').innerText = "Database empty. Press 'Sync Real Data' to deploy!";
            return;
        }

        data.forEach(star => {
            if (MERGED.has(star.name)) return;
            const system = createStarSystem(star);
            scene.add(system);
            clickableStars.push(system);
            system.userData.members.forEach(m => hitTargets.push(m.core));
        });

        document.getElementById('status').innerText = `SYS STATUS: ONLINE // ${data.length} SYSTEMS LOADED`;
    } catch (e) {
        document.getElementById('status').innerText = "Data translation error.";
    }
}

let downPos = null;
window.addEventListener('pointerdown', e => { downPos = { x: e.clientX, y: e.clientY }; });

function flyToSystem(target) {
    const name = target.userData.name;
    if (!name) return;
    isFlying = true;
    document.getElementById('info-panel').style.display = 'none';
    document.getElementById('status').innerText = `HYPERDRIVE ENGAGED → ${name}`;
    flyTo(target, target.parent.userData.lite ? 4 : undefined).then(() => {
        isFlying = false;
        document.getElementById('status').innerText = `ARRIVED: ${name}`;
        showDetails(name);
    });
}

function onSpaceClick(e) {
    if (isFlying || e.target.closest('#ui') || e.target.closest('.xbutton') || e.target.closest('#info-panel')) return;
    if (downPos && Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y) > 5) return;

    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);

    if (currentGalaxy) {
        if (activeSystem) {
            const sh = raycaster.intersectObjects(hitTargets, false)[0];
            if (sh) showDetails(sh.object.parent.userData.name);
            return;
        }
        raycaster.params.Points.threshold = camera.position.distanceTo(controls.target) * 0.004;
        const hit = raycaster.intersectObject(currentGalaxy.points, false)[0];
        if (hit && currentGalaxy.points.visible) enterSystem(currentGalaxy.names[hit.index]);
        return;
    }

    const starHit = raycaster.intersectObjects(hitTargets, false)[0];
    const galHit = raycaster.intersectObjects(galaxyHits, false)[0];

    if (galHit && (!starHit || galHit.distance < starHit.distance)) {
        enterGalaxy(galHit.object.parent);
        return;
    }
    if (!starHit) return;

    flyToSystem(starHit.object.parent);
}

async function showDetails(name) {
    currentStar = name;
    exitEdit();
    document.getElementById('star-name').innerText = name;
    document.getElementById('markdown-body').innerText = "Accessing datalogs...";
    document.getElementById('info-panel').style.display = 'block';

    try {
        const res = await fetch(`/api/info/${encodeURIComponent(name)}`);
        const data = await res.json();
        currentMarkdown = data.content;
        document.getElementById('markdown-body').innerHTML = marked.parse(data.content);
    } catch (err) {
        document.getElementById('markdown-body').innerText = "File processing error.";
    }
}

function startEdit() {
    const editor = document.getElementById('md-editor');
    editor.value = currentMarkdown;
    editor.style.display = 'block';
    document.getElementById('markdown-body').style.display = 'none';
    document.getElementById('edit-btn').style.display = 'none';
    document.getElementById('save-btn').style.display = 'inline-block';
    document.getElementById('cancel-btn').style.display = 'inline-block';
}

function exitEdit() {
    document.getElementById('md-editor').style.display = 'none';
    document.getElementById('markdown-body').style.display = 'block';
    document.getElementById('edit-btn').style.display = 'inline-block';
    document.getElementById('save-btn').style.display = 'none';
    document.getElementById('cancel-btn').style.display = 'none';
}

async function saveRecords() {
    const content = document.getElementById('md-editor').value;
    try {
        const res = await fetch(`/api/info/${encodeURIComponent(currentStar)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) throw new Error();
        currentMarkdown = content;
        document.getElementById('markdown-body').innerHTML = marked.parse(content);
        exitEdit();
        document.getElementById('status').innerText = "Records saved to disk.";
    } catch (err) {
        document.getElementById('status').innerText = "Save failed. Is the server restarted?";
    }
}

function animate() {
    requestAnimationFrame(animate);

    const realDt = clock.getDelta();
    const dt = paused ? 0 : realDt * timeScale;
    const spinDt = paused ? 0 : realDt * Math.min(timeScale, 1);
    simTime += dt;
    const t = simTime;

    clickableStars.forEach(system => {
        const members = system.userData.members || [];
        members.forEach(member => {
            if (member.orbit) {
                const orbitData = member.orbit;
                const pos = orbitPos(orbitData, t);
                member.group.position.set(pos[0], pos[1], pos[2]);
            }

            const bodies = member.bodies || [];
            bodies.forEach(b => {
                b.angle += b.orbitSpeed * dt;
                b.holder.position.x = Math.cos(b.angle) * b.radius;
                b.holder.position.z = Math.sin(b.angle) * b.radius;

                b.mesh.rotation.y += b.spinSpeed * spinDt;
                if (b.mesh.material === earthMaterial) {
                    member.group.getWorldPosition(_sunW);
                    b.holder.getWorldPosition(_earthW);
                    earthMaterial.uniforms.uSunDirection.value.copy(_sunW).sub(_earthW).normalize();
                }
            });
        });
    });

    controls.update();
    updateZoomFx();
    if (bgStars) bgStars.position.copy(camera.position);
    updateMeshFade();
    updateLabels();
    updateModels(performance.now())
    renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
    if (!camera || !renderer) return;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

window.addEventListener('scroll', () => window.scrollTo(0, 0));
window.onload = () => { window.scrollTo(0, 0); initEngine(); };