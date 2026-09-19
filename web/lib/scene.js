// Night harbour. Water, fog, beacons, mouse ripples, a light post pass.
import * as THREE from "three";

const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isMobile = matchMedia("(max-width: 720px)").matches;

const MOODS = {
  calm:   { tint: [0.14, 0.24, 0.30], glow: 0.28, foam: [0.32, 0.42, 0.44] },
  court:  { tint: [0.22, 0.18, 0.32], glow: 0.34, foam: [0.42, 0.34, 0.50] },
  clear:  { tint: [0.14, 0.30, 0.22], glow: 0.36, foam: [0.34, 0.50, 0.40] },
  hold:   { tint: [0.30, 0.14, 0.26], glow: 0.36, foam: [0.50, 0.30, 0.46] },
  pilot:  { tint: [0.12, 0.28, 0.34], glow: 0.36, foam: [0.28, 0.48, 0.52] },
  chaos:  { tint: [0.34, 0.12, 0.14], glow: 0.44, foam: [0.54, 0.22, 0.20] },
  ledger: { tint: [0.20, 0.24, 0.28], glow: 0.30, foam: [0.46, 0.44, 0.36] },
};

const WATER_VERT = /* glsl */`
uniform float uTime;
uniform float uScroll;
uniform vec2 uMouse;
uniform vec3 uRipple;
varying vec2 vUv;
varying float vWave;
varying vec3 vWorld;
void main(){
  vUv = uv;
  vec3 p = position;
  float t = uTime;
  float w = sin(p.x * 0.11 + t * 0.55) * 0.42;
  w += sin(p.y * 0.19 - t * 0.72) * 0.26;
  w += sin((p.x * 0.37 + p.y * 0.21) + t * 1.15) * 0.12;
  w += sin((p.x - p.y) * 0.08 + t * 0.32) * 0.18;
  vec2 m = uMouse * vec2(22.0, -16.0);
  float md = distance(p.xy, m);
  w += exp(-md * 0.11) * 0.95;
  float d = distance(p.xy, uRipple.xy);
  float age = uRipple.z;
  float ring = sin(d * 1.55 - age * 7.4) * exp(-d * 0.11) * exp(-age * 0.72);
  ring *= smoothstep(0.0, 0.08, age);
  w += ring * 2.1;
  p.z += w - uScroll * 0.8;
  vWave = w;
  vec4 world = modelMatrix * vec4(p, 1.0);
  vWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
}`;

const WATER_FRAG = /* glsl */`
precision highp float;
uniform vec3 uDeep;
uniform vec3 uFoam;
uniform float uGlow;
uniform float uTime;
uniform float uScroll;
uniform vec2 uMouse;
varying vec2 vUv;
varying float vWave;
varying vec3 vWorld;
void main(){
  float h = clamp(vWave * 1.15 + 0.42, 0.0, 1.0);
  vec3 deep = uDeep;
  vec3 mid = mix(uDeep, uFoam, 0.35);
  vec3 col = mix(deep, mid, h);
  col = mix(col, uFoam, pow(h, 3.2) * 0.28);
  float spec = pow(max(h, 0.0), 8.0) * 0.22 * uGlow;
  col += vec3(0.55, 0.68, 0.74) * spec;
  vec2 m = uMouse * 0.5 + 0.5;
  float lane = exp(-abs(vUv.x - m.x) * 11.0) * exp(-abs(vUv.y - (1.0 - m.y)) * 6.0);
  col += uFoam * lane * 0.08 * uGlow;
  float caust = sin((vUv.x * 38.0 + vUv.y * 22.0) + uTime * 1.4);
  caust *= sin((vUv.x * 17.0 - vUv.y * 29.0) - uTime * 0.9);
  col += uFoam * caust * 0.018 * h * uGlow;
  float horizon = smoothstep(0.22, 0.92, vUv.y);
  vec3 mist = vec3(0.05, 0.08, 0.10);
  col = mix(col, mist, horizon * 0.55);
  float depth = smoothstep(-2.0, 8.0, vWorld.z);
  col = mix(col, deep * 1.15, depth * 0.18);
  gl_FragColor = vec4(col, 1.0);
}`;

const POST_VERT = /* glsl */`
varying vec2 vUv;
void main(){
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;

const POST_FRAG = /* glsl */`
precision highp float;
uniform sampler2D tDiffuse;
uniform vec2 uMouse;
uniform vec2 uRes;
uniform float uTime;
varying vec2 vUv;
void main(){
  vec2 uv = vUv;
  vec2 fromC = uv - 0.5;
  float dist = length(fromC);
  uv += fromC * dist * 0.018;
  vec2 chroma = fromC * (0.0022 + length(uMouse) * 0.0016);
  vec3 col;
  col.r = texture2D(tDiffuse, uv + chroma).r;
  col.g = texture2D(tDiffuse, uv).g;
  col.b = texture2D(tDiffuse, uv - chroma).b;
  vec3 acc = col;
  acc += texture2D(tDiffuse, uv + vec2( 0.003, 0.0)).rgb;
  acc += texture2D(tDiffuse, uv + vec2(-0.003, 0.0)).rgb;
  acc += texture2D(tDiffuse, uv + vec2(0.0,  0.003)).rgb;
  acc += texture2D(tDiffuse, uv + vec2(0.0, -0.003)).rgb;
  vec3 bloom = max(acc / 5.0 - 0.52, 0.0);
  col += bloom * 0.18;
  float grain = fract(sin(dot(uv * uRes + uTime * 9.0, vec2(12.9898, 78.233))) * 43758.5453);
  col += (grain - 0.5) * 0.03;
  float vig = mix(1.0, smoothstep(1.12, 0.28, dist), 0.62);
  col *= vig;
  gl_FragColor = vec4(col, 1.0);
}`;

class HarborScene {
  constructor(canvas) {
    this.canvas = canvas;
    this.enabled = !reduced;
    this.raf = 0;
    this.disposables = [];
    if (!this.enabled) {
      canvas.style.display = "none";
      return;
    }

    this.mood = { tint: [...MOODS.calm.tint], glow: MOODS.calm.glow, foam: [...MOODS.calm.foam] };
    this.target = { tint: [...MOODS.calm.tint], glow: MOODS.calm.glow, foam: [...MOODS.calm.foam] };
    this.mouse = { x: 0, y: 0, tx: 0, ty: 0 };
    this.scroll = 0;
    this.t = 0;
    this.ripple = new THREE.Vector3(0, 0, 8);

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: !isMobile, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x071018, 1);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x071018, 0.026);
    this.camera = new THREE.PerspectiveCamera(46, 1, 0.1, 220);
    this.camera.position.set(0, 4.2, 16);

    this.waterGeo = new THREE.PlaneGeometry(96, 96, isMobile ? 48 : 96, isMobile ? 48 : 96);
    this.waterMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uScroll: { value: 0 },
        uDeep: { value: new THREE.Color(0x07141c) },
        uFoam: { value: new THREE.Color(0x5a7e86) },
        uGlow: { value: 0.28 },
        uMouse: { value: new THREE.Vector2() },
        uRipple: { value: this.ripple },
      },
      vertexShader: WATER_VERT,
      fragmentShader: WATER_FRAG,
    });
    this.water = new THREE.Mesh(this.waterGeo, this.waterMat);
    this.water.rotation.x = -Math.PI / 2;
    this.water.position.y = -0.2;
    this.scene.add(this.water);
    this.disposables.push(this.waterGeo, this.waterMat);

    const starN = isMobile ? 420 : 1100;
    const starPos = new Float32Array(starN * 3);
    for (let i = 0; i < starN; i++) {
      starPos[i * 3] = (Math.random() - 0.5) * 90;
      starPos[i * 3 + 1] = 6 + Math.random() * 32;
      starPos[i * 3 + 2] = -12 - Math.random() * 55;
    }
    this.starGeo = new THREE.BufferGeometry();
    this.starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    this.starMat = new THREE.PointsMaterial({ color: 0xcfe4ea, size: 0.05, transparent: true, opacity: 0.38, depthWrite: false });
    this.stars = new THREE.Points(this.starGeo, this.starMat);
    this.scene.add(this.stars);
    this.disposables.push(this.starGeo, this.starMat);

    const sprayN = isMobile ? 220 : 480;
    const spray = new Float32Array(sprayN * 3);
    for (let i = 0; i < sprayN; i++) {
      spray[i * 3] = (Math.random() - 0.5) * 46;
      spray[i * 3 + 1] = Math.random() * 2.8;
      spray[i * 3 + 2] = (Math.random() - 0.5) * 46;
    }
    this.sprayGeo = new THREE.BufferGeometry();
    this.sprayGeo.setAttribute("position", new THREE.BufferAttribute(spray, 3));
    this.sprayMat = new THREE.PointsMaterial({ color: 0xa8d4dc, size: 0.04, transparent: true, opacity: 0.16, depthWrite: false });
    this.spray = new THREE.Points(this.sprayGeo, this.sprayMat);
    this.scene.add(this.spray);
    this.disposables.push(this.sprayGeo, this.sprayMat);

    this.pylonGeo = new THREE.CylinderGeometry(0.07, 0.16, 2.6, 6);
    this.pylonMat = new THREE.MeshBasicMaterial({ color: 0x8aa8b0, transparent: true, opacity: 0.16 });
    this.pylons = [-18, -7, 6, 17].map((x, i) => {
      const mesh = new THREE.Mesh(this.pylonGeo, this.pylonMat);
      mesh.position.set(x, 1.05, -9 - (i % 2) * 5);
      this.scene.add(mesh);
      return mesh;
    });
    this.disposables.push(this.pylonGeo, this.pylonMat);

    this.beacons = this.pylons.map((mesh, i) => {
      const light = new THREE.PointLight(i % 2 ? 0x6a9a94 : 0xc4a56a, 0.7, 22, 2.2);
      light.position.copy(mesh.position);
      light.position.y += 1.4;
      this.scene.add(light);
      return light;
    });

    this.rt = new THREE.WebGLRenderTarget(1, 1, { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    this.postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.postMat = new THREE.ShaderMaterial({
      uniforms: {
        tDiffuse: { value: this.rt.texture },
        uMouse: { value: new THREE.Vector2() },
        uRes: { value: new THREE.Vector2(1, 1) },
        uTime: { value: 0 },
      },
      vertexShader: POST_VERT,
      fragmentShader: POST_FRAG,
    });
    this.postGeo = new THREE.PlaneGeometry(2, 2);
    this.postMesh = new THREE.Mesh(this.postGeo, this.postMat);
    this.postScene = new THREE.Scene();
    this.postScene.add(this.postMesh);
    this.disposables.push(this.postGeo, this.postMat, this.rt);

    this.onMove = (e) => {
      this.mouse.tx = (e.clientX / innerWidth) * 2 - 1;
      this.mouse.ty = (e.clientY / innerHeight) * 2 - 1;
    };
    this.onDown = (e) => this.splash(e.clientX, e.clientY);
    addEventListener("pointermove", this.onMove, { passive: true });
    addEventListener("pointerdown", this.onDown, { passive: true });

    this.resize();
    this.onResize = () => this.resize();
    addEventListener("resize", this.onResize);
    this.loop = this.loop.bind(this);
    this.raf = requestAnimationFrame(this.loop);
  }

  resize() {
    const w = innerWidth;
    const h = innerHeight;
    const dpr = Math.min(devicePixelRatio, 2);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.rt.setSize(Math.floor(w * dpr), Math.floor(h * dpr));
    this.postMat.uniforms.uRes.value.set(w, h);
  }

  setMood(name) {
    const m = MOODS[name] || MOODS.calm;
    this.target.tint = [...m.tint];
    this.target.glow = m.glow;
    this.target.foam = [...m.foam];
  }

  setScroll(p) {
    this.scroll = p;
  }

  splash(clientX, clientY) {
    this.ripple.x = ((clientX / innerWidth) * 2 - 1) * 22;
    this.ripple.y = ((clientY / innerHeight) * 2 - 1) * -16;
    this.ripple.z = 0.02;
  }

  shock() {
    this.ripple.z = 0.02;
  }

  loop() {
    this.t += 0.016;
    this.mouse.x += (this.mouse.tx - this.mouse.x) * 0.075;
    this.mouse.y += (this.mouse.ty - this.mouse.y) * 0.075;
    if (this.ripple.z < 8) this.ripple.z += 0.026;

    for (let i = 0; i < 3; i++) {
      this.mood.tint[i] += (this.target.tint[i] - this.mood.tint[i]) * 0.045;
      this.mood.foam[i] += (this.target.foam[i] - this.mood.foam[i]) * 0.045;
    }
    this.mood.glow += (this.target.glow - this.mood.glow) * 0.045;

    this.waterMat.uniforms.uTime.value = this.t;
    this.waterMat.uniforms.uScroll.value = this.scroll;
    this.waterMat.uniforms.uGlow.value = this.mood.glow;
    this.waterMat.uniforms.uMouse.value.set(this.mouse.x, this.mouse.y);
    this.waterMat.uniforms.uDeep.value.setRGB(this.mood.tint[0] * 0.22, this.mood.tint[1] * 0.28, this.mood.tint[2] * 0.34);
    this.waterMat.uniforms.uFoam.value.setRGB(this.mood.foam[0], this.mood.foam[1], this.mood.foam[2]);
    this.postMat.uniforms.uTime.value = this.t;
    this.postMat.uniforms.uMouse.value.set(this.mouse.x, this.mouse.y);

    const s = this.scroll;
    this.camera.position.x = this.mouse.x * 2.2;
    this.camera.position.y = 4.1 + this.mouse.y * 0.7 + s * 4.2;
    this.camera.position.z = 16.5 - s * 5.5;
    this.camera.lookAt(this.mouse.x * 3.2, 0.15 - s * 1.8, -11);

    this.stars.rotation.z = this.t * 0.004;
    this.spray.rotation.y = this.t * 0.028;
    this.spray.position.y = Math.sin(this.t * 0.42) * 0.18;
    this.beacons.forEach((l, i) => {
      l.intensity = 0.45 + Math.sin(this.t * 1.15 + i) * 0.22;
    });

    this.renderer.setRenderTarget(this.rt);
    this.renderer.render(this.scene, this.camera);
    this.renderer.setRenderTarget(null);
    this.renderer.render(this.postScene, this.postCam);
    this.raf = requestAnimationFrame(this.loop);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    removeEventListener("pointermove", this.onMove);
    removeEventListener("pointerdown", this.onDown);
    removeEventListener("resize", this.onResize);
    this.disposables.forEach((d) => d.dispose?.());
    this.renderer.dispose();
  }
}

let instance = null;
export function mountScene(canvas) {
  if (instance) return instance;
  try {
    instance = new HarborScene(canvas);
    if (!instance.enabled) instance = null;
  } catch (err) {
    console.warn("[scene] WebGL unavailable, running flat.", err);
    instance = null;
  }
  addEventListener("pagehide", () => instance?.dispose?.(), { once: true });
  return instance;
}
export const scene = {
  setMood: (m) => instance?.setMood(m),
  setScroll: (p) => instance?.setScroll(p),
  splash: (x, y) => instance?.splash(x, y),
  shock: () => instance?.shock(),
};
