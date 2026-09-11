import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import Backdrop from "./Backdrop.jsx";

/* ============================================================================
   الشفق الحيّ — خلفية GPU بشيدر واحد، بلا three.js ولا أي تبعية.

   حقل ضوء سائل (fbm مشوَّه بنفسه) بألوان العلامة، يميل نحو المؤشّر، ويخفت كلما
   نزلت في الصفحة حتى لا ينافس المحتوى. التكلفة محسوبة:
   · يُرسم بنصف الدقة (ثلثها على الجوال) ثم يكبّره المتصفح — التدرّج ناعم أصلاً.
   · 30 إطاراً في الثانية كحدّ أقصى، ويتوقف تماماً والتبويب مخفي.
   · تقليل الحركة ⇒ إطار واحد ثابت. لا WebGL أو فقد السياق ⇒ الخلفية القديمة.
   ========================================================================== */

const VERT = "attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}";

const FRAG = `precision mediump float;
uniform vec2 uR; uniform float uT; uniform vec2 uM; uniform float uS; uniform float uQ;
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
  return mix(mix(h(i), h(i+vec2(1.0,0.0)), u.x), mix(h(i+vec2(0.0,1.0)), h(i+vec2(1.0,1.0)), u.x), u.y); }
float fbm(vec2 p){ float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) { v += a*n(p); p = p*2.03 + vec2(1.7, 9.2); a *= 0.5; } return v; }
void main(){
  vec2 uv = gl_FragCoord.xy / uR;
  vec2 p = (gl_FragCoord.xy - 0.5*uR) / uR.y;
  float t = uT * 0.045;
  vec2 q = vec2(fbm(p*1.25 + vec2(0.0, t)), fbm(p*1.25 + vec2(5.2, -t)));
  float f = fbm(p*1.05 + q*1.7 + vec2(0.6*t, -0.4*t));
  vec2 m = (uM - 0.5*uR) / uR.y;
  float d = length(p - m);
  f += 0.2 * exp(-d*d*4.5);
  vec3 base = vec3(0.020, 0.027, 0.051);
  vec3 c = base;
  c = mix(c, vec3(0.486, 0.424, 0.965), smoothstep(0.45, 0.98, f) * 0.60);
  c = mix(c, vec3(0.133, 0.827, 0.933), smoothstep(0.64, 1.10, f + 0.12*q.x) * 0.48);
  c = mix(c, vec3(0.176, 0.831, 0.655), smoothstep(0.80, 1.22, f + 0.20*q.y) * 0.26);
  float lift = mix(0.30, 1.0, smoothstep(0.0, 1.0, uv.y));
  float vig = smoothstep(1.45, 0.25, length(p * vec2(0.72, 1.0)));
  float k = lift * vig * mix(1.0, 0.42, uS) * mix(1.0, 0.5, uQ);
  gl_FragColor = vec4(mix(base, c, k), 1.0);
}`;

function shader(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); return null; }
  return s;
}

const fixed = { position: "fixed", inset: 0, pointerEvents: "none" };

export default function Aurora({ quiet = false }) {
  const canvasRef = useRef(null);
  const glowRef = useRef(null);
  const reduce = useReducedMotion();
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", {
      antialias: false, alpha: false, depth: false, stencil: false,
      powerPreference: "low-power", preserveDrawingBuffer: false,
    });
    if (!gl) { setFallback(true); return; }
    const vs = shader(gl, gl.VERTEX_SHADER, VERT);
    const fs = shader(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) { setFallback(true); return; }
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { setFallback(true); return; }
    gl.useProgram(prog);

    // مثلث واحد يغطي الشاشة كلها — أرخص من مستطيلين
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = (n) => gl.getUniformLocation(prog, n);
    const uR = U("uR"), uT = U("uT"), uM = U("uM"), uS = U("uS"), uQ = U("uQ");

    const scale = window.innerWidth < 768 ? 0.35 : 0.5;
    const t0 = performance.now();
    const ptr = { x: 0.62, y: 0.28, tx: 0.62, ty: 0.28 };
    let w = 1, h = 1, raf = 0, running = true, last = 0;

    function resize() {
      w = Math.max(1, Math.round(canvas.clientWidth * scale));
      h = Math.max(1, Math.round(canvas.clientHeight * scale));
      canvas.width = w; canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
    function draw(now) {
      ptr.x += (ptr.tx - ptr.x) * 0.05;
      ptr.y += (ptr.ty - ptr.y) * 0.05;
      const sc = Math.min(1, window.scrollY / Math.max(1, window.innerHeight * 1.6));
      gl.uniform2f(uR, w, h);
      gl.uniform1f(uT, reduce ? 14 : (now - t0) / 1000);
      gl.uniform2f(uM, ptr.x * w, (1 - ptr.y) * h);
      gl.uniform1f(uS, sc);
      gl.uniform1f(uQ, quiet ? 1 : 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    function frame(now) {
      if (!running) return;
      raf = requestAnimationFrame(frame);
      if (now - last < 33) return;              // ≤ 30fps — العين لا تفرق في تدرّج بطيء
      last = now;
      draw(now);
    }
    function onMove(e) {
      ptr.tx = e.clientX / window.innerWidth;
      ptr.ty = e.clientY / window.innerHeight;
      const gl2 = glowRef.current;
      if (gl2) {
        gl2.style.setProperty("--px", e.clientX + "px");
        gl2.style.setProperty("--py", e.clientY + "px");
        gl2.style.opacity = "1";
      }
    }
    function onLeave() { if (glowRef.current) glowRef.current.style.opacity = "0"; }
    function onVis() {
      if (document.hidden) { running = false; cancelAnimationFrame(raf); }
      else if (!reduce) { running = true; raf = requestAnimationFrame(frame); }
    }
    function onLost(e) { e.preventDefault(); setFallback(true); }
    function onScrollStill() { draw(performance.now()); }

    resize();
    draw(performance.now());                   // إطار أول متزامن — لا شاشة سوداء أبداً
    const ro = new ResizeObserver(() => { resize(); draw(performance.now()); });
    ro.observe(canvas);
    canvas.addEventListener("webglcontextlost", onLost);
    if (reduce) {
      window.addEventListener("scroll", onScrollStill, { passive: true });
    } else {
      raf = requestAnimationFrame(frame);
      window.addEventListener("pointermove", onMove, { passive: true });
      document.addEventListener("pointerleave", onLeave);
      document.addEventListener("visibilitychange", onVis);
    }
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener("webglcontextlost", onLost);
      window.removeEventListener("scroll", onScrollStill);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [reduce, quiet]);

  if (fallback) return <Backdrop />;

  return (
    <>
      <canvas ref={canvasRef} aria-hidden="true"
              style={{ ...fixed, zIndex: -40, width: "100%", height: "100%", background: "#05070D" }} />
      {/* شبكة تضيء حول المؤشّر فقط */}
      <div ref={glowRef} aria-hidden="true"
           style={{
             ...fixed, zIndex: -30, opacity: 0,
             transition: "opacity .6s cubic-bezier(.16,1,.3,1)",
             backgroundImage:
               "linear-gradient(to right, rgba(255,255,255,.09) 1px, transparent 1px)," +
               "linear-gradient(to bottom, rgba(255,255,255,.09) 1px, transparent 1px)",
             backgroundSize: "56px 56px",
             WebkitMaskImage: "radial-gradient(240px circle at var(--px,50%) var(--py,50%), #000 0%, transparent 70%)",
             maskImage: "radial-gradient(240px circle at var(--px,50%) var(--py,50%), #000 0%, transparent 70%)",
           }} />
      <div aria-hidden="true" className="grain" style={{ ...fixed, zIndex: -20, opacity: 0.13 }} />
      <div aria-hidden="true"
           style={{ ...fixed, zIndex: -15,
                    background: "linear-gradient(180deg, transparent 0%, rgba(5,7,13,.25) 60%, rgba(5,7,13,.7) 100%)" }} />
    </>
  );
}
