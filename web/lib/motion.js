// Thin GSAP layer. Everything here degrades when GSAP is missing or
// the user prefers reduced motion. Animate transform + opacity only.

const g = window.gsap || null;
export const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const gsap = g;

/** Smooth-scroll the window. No ScrollToPlugin required. */
export function scrollToY(y, duration = 0.95) {
  const top = Math.max(0, y);
  if (!g || reduced) {
    window.scrollTo({ top, behavior: "smooth" });
    return;
  }
  const obj = { y: scrollY };
  g.to(obj, {
    y: top,
    duration,
    ease: "power3.inOut",
    overwrite: true,
    onUpdate: () => window.scrollTo(0, obj.y),
  });
}

/** Opening title card. Runs once per session. */
export function playBoot(root, onDone) {
  if (!root) { onDone?.(); return; }
  if (!g || reduced) {
    document.body.classList.add("is-live");
    root.remove();
    onDone?.();
    return;
  }
  const mark = root.querySelector(".boot-mark");
  const logo = root.querySelector(".boot-logo");
  const lines = root.querySelectorAll(".boot-line");
  const tl = g.timeline({
    defaults: { ease: "power3.out" },
    onComplete: () => {
      document.body.classList.add("is-live");
      g.to(root, {
        opacity: 0,
        duration: 0.7,
        delay: 0.12,
        onComplete: () => { root.remove(); onDone?.(); },
      });
    },
  });
  g.set(root, { opacity: 1 });
  if (logo) tl.fromTo(logo, { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 });
  if (mark) tl.fromTo(mark, { y: 36, opacity: 0 }, { y: 0, opacity: 1, duration: 0.9 }, "-=0.15");
  if (lines.length) tl.fromTo(lines, { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, stagger: 0.1 }, "-=0.4");
}

/**
 * Smooth harbour parallax. Transform + opacity only, lerped on the ticker
 * so we do not need ScrollTrigger. scene.setScroll drives the 3D camera.
 */
export function mountParallax(sceneApi) {
  if (!g || reduced) return () => {};
  let current = 0;
  const max = () => Math.max(1, document.documentElement.scrollHeight - innerHeight);

  const tick = () => {
    const target = scrollY;
    current += (target - current) * 0.08;
    const p = Math.min(1, current / max());
    sceneApi?.setScroll?.(p);
    const sea = document.getElementById("sea");
    const fogFar = document.getElementById("fog-far");
    const fogNear = document.getElementById("fog-near");
    const horizon = document.getElementById("horizon");
    const title = document.querySelector(".js-para-title");
    const copy = document.querySelector(".js-para-copy");
    const hubs = document.querySelector(".js-para-hubs");
    const docket = document.querySelector(".js-para-docket");
    if (sea) g.set(sea, { y: current * 0.22 });
    if (horizon) g.set(horizon, { y: current * 0.14 });
    if (fogFar) g.set(fogFar, { y: current * 0.08 });
    if (fogNear) g.set(fogNear, { y: current * -0.06 });
    if (title) g.set(title, { y: current * -0.18 });
    if (copy) g.set(copy, { y: current * -0.09 });
    if (hubs) g.set(hubs, { y: current * 0.06 });
    if (docket) g.set(docket, { y: current * -0.03 });
  };
  g.ticker.add(tick);
  return () => g.ticker.remove(tick);
}

/** Stagger-in a set of nodes (cards, rows). */
export function enter(nodes, { y = 22, stagger = 0.045, duration = 0.62, delay = 0 } = {}) {
  const list = Array.from(nodes || []);
  if (!list.length) return;
  if (!g || reduced) {
    list.forEach((n) => { n.style.opacity = ""; n.style.transform = ""; });
    return;
  }
  g.fromTo(
    list,
    { opacity: 0, y, rotateX: 6 },
    { opacity: 1, y: 0, rotateX: 0, duration, delay, stagger, overwrite: "auto", clearProps: "transform" },
  );
}

/** Cross-fade the main view container. */
export function swapView(container, renderFn) {
  if (!g || reduced) {
    renderFn();
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    g.to(container, {
      opacity: 0,
      y: -10,
      duration: 0.2,
      ease: "power2.in",
      onComplete: () => {
        renderFn();
        g.fromTo(
          container,
          { opacity: 0, y: 16 },
          { opacity: 1, y: 0, duration: 0.55, clearProps: "transform", onComplete: resolve },
        );
      },
    });
  });
}

/** Animate a number in a node. */
export function countTo(node, to, { duration = 0.9, format = (v) => Math.round(v).toLocaleString() } = {}) {
  const from = Number(node.dataset.value ?? 0) || 0;
  node.dataset.value = String(to);
  if (!g || reduced || from === to) {
    node.textContent = format(to);
    return;
  }
  const obj = { v: from };
  g.to(obj, {
    v: to,
    duration,
    ease: "power2.out",
    onUpdate: () => { node.textContent = format(obj.v); },
    onComplete: () => { node.textContent = format(to); },
  });
}

/** Pop feedback on a node (buttons, counters). */
export function pulse(node, scale = 1.06) {
  if (!g || reduced || !node) return;
  g.fromTo(node, { scale }, { scale: 1, duration: 0.45, ease: "elastic.out(1, 0.5)", clearProps: "transform" });
}

/** Collapse & remove nodes (pilot queue after replay). */
export function collapseOut(nodes, { stagger = 0.08 } = {}) {
  const list = Array.from(nodes || []);
  if (!list.length) return Promise.resolve();
  if (!g || reduced) {
    list.forEach((n) => n.remove());
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    g.to(list, {
      opacity: 0,
      x: 48,
      scale: 0.96,
      duration: 0.48,
      stagger,
      ease: "power2.in",
      onComplete: () => { list.forEach((n) => n.remove()); resolve(); },
    });
  });
}

/** Shake the whole shell briefly (chaos smash). */
export function shake(node, intensity = 7) {
  if (!g || reduced || !node) return;
  g.fromTo(
    node,
    { x: -intensity },
    { x: intensity, duration: 0.045, repeat: 8, yoyo: true, ease: "none", clearProps: "transform" },
  );
}

/** Drawer open/close helper. */
export function slideIn(node, from = 60) {
  if (!g || reduced) return;
  g.fromTo(node, { x: from, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, clearProps: "transform" });
}

/**
 * Magnetic hover: element leans toward the cursor by a few pixels.
 * Cheap: transform only, driven on pointermove, reset on leave.
 */
export function magnetize(root, selector, strength = 6) {
  if (reduced || !g) return () => {};
  const quick = new WeakMap();
  const onMove = (e) => {
    const el = e.target.closest?.(selector);
    if (!el || !root.contains(el)) return;
    const r = el.getBoundingClientRect();
    const dx = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const dy = ((e.clientY - r.top) / r.height - 0.5) * 2;
    let qs = quick.get(el);
    if (!qs) {
      qs = {
        x: g.quickTo(el, "x", { duration: 0.35, ease: "power3" }),
        y: g.quickTo(el, "y", { duration: 0.35, ease: "power3" }),
      };
      quick.set(el, qs);
    }
    qs.x(dx * strength);
    qs.y(dy * strength);
  };
  const onOut = (e) => {
    const el = e.target.closest?.(selector);
    if (!el || el.contains(e.relatedTarget)) return;
    const qs = quick.get(el);
    if (qs) { qs.x(0); qs.y(0); }
  };
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerout", onOut);
  return () => {
    root.removeEventListener("pointermove", onMove);
    root.removeEventListener("pointerout", onOut);
  };
}

/**
 * Perspective tilt on cards. Rotation only. Caps at a few degrees so
 * projectors do not get motion-sick and so it stays 60fps.
 */
export function tiltify(root, selector, { max = 7, glare = true, ignore = "" } = {}) {
  if (reduced || !g) return () => {};
  const map = new WeakMap();
  const flatten = (el) => {
    const q = map.get(el);
    if (q) { q.rx(0); q.ry(0); }
    el.classList.remove("lit");
  };
  const onMove = (e) => {
    const el = e.target.closest?.(selector);
    if (!el || !root.contains(el)) return;
    if (ignore && e.target.closest?.(ignore)) {
      flatten(el);
      return;
    }
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--mx", `${px * 100}%`);
    el.style.setProperty("--my", `${py * 100}%`);
    let q = map.get(el);
    if (!q) {
      q = {
        rx: g.quickTo(el, "rotationX", { duration: 0.16, ease: "power3" }),
        ry: g.quickTo(el, "rotationY", { duration: 0.16, ease: "power3" }),
      };
      map.set(el, q);
    }
    q.ry((px - 0.5) * max * 2);
    q.rx((0.5 - py) * max * 2);
    if (glare) el.classList.add("lit");
  };
  const onOut = (e) => {
    const el = e.target.closest?.(selector);
    if (!el || el.contains(e.relatedTarget)) return;
    flatten(el);
  };
  const onDown = (e) => {
    if (!ignore || !e.target.closest?.(ignore)) return;
    const el = e.target.closest?.(selector);
    if (el) flatten(el);
  };
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerout", onOut);
  root.addEventListener("pointerdown", onDown);
  return () => {
    root.removeEventListener("pointermove", onMove);
    root.removeEventListener("pointerout", onOut);
    root.removeEventListener("pointerdown", onDown);
  };
}

/** Soft spotlight that follows the cursor. CSS vars only, no React state. */
export function mountSpotlight(el) {
  if (!el) return () => {};
  if (reduced || !g) {
    el.style.opacity = "0";
    return () => {};
  }
  const xTo = g.quickTo(el, "x", { duration: 0.55, ease: "power3" });
  const yTo = g.quickTo(el, "y", { duration: 0.55, ease: "power3" });
  const onMove = (e) => {
    xTo(e.clientX - innerWidth * 0.5);
    yTo(e.clientY - innerHeight * 0.5);
  };
  addEventListener("pointermove", onMove, { passive: true });
  return () => removeEventListener("pointermove", onMove);
}
