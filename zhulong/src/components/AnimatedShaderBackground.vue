<template>
  <div ref="containerRef" class="shader-background" aria-hidden="true">
    <div class="meteor-layer">
      <span
        v-for="meteor in meteors"
        :key="meteor.id"
        class="meteor"
        :class="[meteor.side, { warm: meteor.warm }]"
        :style="{
          '--meteor-x': meteor.x,
          '--meteor-y': meteor.y,
          '--meteor-length': meteor.length,
          '--meteor-duration': meteor.duration,
          '--meteor-delay': meteor.delay,
          '--meteor-scale': meteor.scale
        }"
      ></span>
      <span
        v-for="streak in stationaryStreaks"
        :key="streak.id"
        class="stationary-streak"
        :class="[streak.side, { warm: streak.warm }]"
        :style="{
          '--streak-x': streak.x,
          '--streak-y': streak.y,
          '--streak-length': streak.length,
          '--streak-angle': streak.angle,
          '--streak-delay': streak.delay,
          '--streak-opacity': streak.opacity
        }"
      ></span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'

const containerRef = ref(null)
const meteors = [
  { id: 1, side: 'left', x: '4%', y: '4%', length: '154px', duration: '7.2s', delay: '-1.1s', scale: 0.82, warm: false },
  { id: 2, side: 'left', x: '12%', y: '23%', length: '188px', duration: '8.6s', delay: '-5.6s', scale: 0.92, warm: false },
  { id: 3, side: 'left', x: '20%', y: '46%', length: '126px', duration: '6.9s', delay: '-3.8s', scale: 0.7, warm: true },
  { id: 4, side: 'left', x: '-4%', y: '62%', length: '178px', duration: '9.4s', delay: '-7.2s', scale: 0.86, warm: false },
  { id: 5, side: 'right', x: '72%', y: '2%', length: '174px', duration: '7.7s', delay: '-2.9s', scale: 0.86, warm: false },
  { id: 6, side: 'right', x: '80%', y: '25%', length: '132px', duration: '6.5s', delay: '-4.7s', scale: 0.72, warm: true },
  { id: 7, side: 'right', x: '87%', y: '48%', length: '196px', duration: '9.2s', delay: '-6.3s', scale: 0.94, warm: false },
  { id: 8, side: 'right', x: '76%', y: '70%', length: '148px', duration: '8.1s', delay: '-1.9s', scale: 0.78, warm: false }
]
const stationaryStreaks = [
  { id: 'left-1', side: 'left', x: '2%', y: '22%', length: '172px', angle: '34deg', delay: '-0.6s', opacity: 0.58, warm: false },
  { id: 'left-2', side: 'left', x: '10%', y: '38%', length: '138px', angle: '34deg', delay: '-2.8s', opacity: 0.52, warm: true },
  { id: 'left-3', side: 'left', x: '18%', y: '55%', length: '196px', angle: '34deg', delay: '-1.7s', opacity: 0.66, warm: false },
  { id: 'left-4', side: 'left', x: '5%', y: '72%', length: '152px', angle: '34deg', delay: '-3.6s', opacity: 0.48, warm: false },
  { id: 'left-5', side: 'left', x: '20%', y: '84%', length: '118px', angle: '34deg', delay: '-1.2s', opacity: 0.44, warm: true },
  { id: 'right-1', side: 'right', x: '74%', y: '19%', length: '158px', angle: '34deg', delay: '-2.1s', opacity: 0.56, warm: false },
  { id: 'right-2', side: 'right', x: '84%', y: '34%', length: '192px', angle: '34deg', delay: '-0.9s', opacity: 0.64, warm: true },
  { id: 'right-3', side: 'right', x: '77%', y: '51%', length: '136px', angle: '34deg', delay: '-3.4s', opacity: 0.54, warm: false },
  { id: 'right-4', side: 'right', x: '88%', y: '68%', length: '176px', angle: '34deg', delay: '-2.5s', opacity: 0.5, warm: false },
  { id: 'right-5', side: 'right', x: '73%', y: '82%', length: '124px', angle: '34deg', delay: '-4.1s', opacity: 0.46, warm: true }
]
let renderer
let material
let geometry
let frameId
let resizeObserver

const fitRenderer = () => {
  if (!containerRef.value || !renderer || !material) return

  const { clientWidth, clientHeight } = containerRef.value
  const width = Math.max(clientWidth, 1)
  const height = Math.max(clientHeight, 1)

  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
  material.uniforms.iResolution.value.set(width, height)
}

onMounted(() => {
  const container = containerRef.value
  const scene = new THREE.Scene()
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance'
  })
  renderer.setClearColor(0x020511, 1)
  container.appendChild(renderer.domElement)

  material = new THREE.ShaderMaterial({
    uniforms: {
      iTime: { value: 0 },
      iResolution: { value: new THREE.Vector2(1, 1) }
    },
    vertexShader: `
      void main() {
        gl_Position = vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float iTime;
      uniform vec2 iResolution;

      #define NUM_OCTAVES 3

      float rand(vec2 n) {
        return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
      }

      float noise(vec2 p) {
        vec2 ip = floor(p);
        vec2 u = fract(p);
        u = u * u * (3.0 - 2.0 * u);
        float res = mix(
          mix(rand(ip), rand(ip + vec2(1.0, 0.0)), u.x),
          mix(rand(ip + vec2(0.0, 1.0)), rand(ip + vec2(1.0, 1.0)), u.x),
          u.y
        );
        return res * res;
      }

      float fbm(vec2 x) {
        float v = 0.0;
        float a = 0.32;
        vec2 shift = vec2(100.0);
        mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
        for (int i = 0; i < NUM_OCTAVES; ++i) {
          v += a * noise(x);
          x = rot * x * 2.0 + shift;
          a *= 0.42;
        }
        return v;
      }

      void main() {
        vec2 shake = vec2(sin(iTime * 0.9) * 0.003, cos(iTime * 1.7) * 0.003);
        vec2 centered = (gl_FragCoord.xy + shake * iResolution.xy) - (iResolution.xy * 0.5 + vec2(iResolution.x * 0.24, 0.0));
        vec2 p = centered / iResolution.y * mat2(5.0, -3.4, 3.4, 5.0);
        vec2 v;
        vec4 o = vec4(0.0);

        float f = 2.0 + fbm(p + vec2(iTime * 1.8, 0.0)) * 0.55;

        for (float i = 0.0; i < 35.0; i++) {
          float sideBalance = 0.78 + 0.22 * cos(i * 1.7);
          v = p + cos(i * i + (iTime + p.x * 0.08) * 0.03 + i * vec2(13.0, 11.0)) * (3.15 * sideBalance);
          float tailNoise = fbm(v + vec2(iTime * 0.45, i)) * 0.32 * (1.0 - (i / 35.0));
          vec4 auroraColors = vec4(
            0.12 + 0.44 * sin(i * 0.16 + iTime * 0.20),
            0.26 + 0.34 * cos(i * 0.28 + iTime * 0.22),
            0.62 + 0.24 * sin(i * 0.38 + iTime * 0.18),
            1.0
          );
          vec4 ember = vec4(0.85, 0.30, 0.13, 1.0) * smoothstep(0.74, 1.0, sin(i * 0.35 + iTime * 0.35));
          vec4 currentContribution = (auroraColors + ember * 0.22) * exp(sin(i * i + iTime * 0.48)) / length(max(v, vec2(v.x * f * 0.015, v.y * 1.5)));
          float thinnessFactor = smoothstep(0.0, 1.0, i / 35.0) * 0.62;
          float centerWeight = smoothstep(1.65, 0.18, length(centered / iResolution.y));
          o += currentContribution * (1.0 + tailNoise * 0.8) * thinnessFactor * (0.68 + centerWeight * 0.36);
        }

        o = tanh(pow(o / 104.0, vec4(1.58)));
        vec3 base = vec3(0.008, 0.016, 0.045);
        vec3 vignetteColor = mix(base, o.rgb * 1.28, 0.94);
        float vignette = smoothstep(1.15, 0.18, length((gl_FragCoord.xy - (iResolution.xy * 0.5 + vec2(iResolution.x * 0.12, 0.0))) / iResolution.y));
        gl_FragColor = vec4(vignetteColor * (0.64 + vignette * 0.74), 1.0);
      }
    `
  })

  geometry = new THREE.PlaneGeometry(2, 2)
  scene.add(new THREE.Mesh(geometry, material))

  fitRenderer()
  resizeObserver = new ResizeObserver(fitRenderer)
  resizeObserver.observe(container)

  const animate = () => {
    material.uniforms.iTime.value += 0.016
    renderer.render(scene, camera)
    frameId = window.requestAnimationFrame(animate)
  }
  animate()
})

onBeforeUnmount(() => {
  if (frameId) window.cancelAnimationFrame(frameId)
  if (resizeObserver) resizeObserver.disconnect()
  if (renderer?.domElement?.parentNode) {
    renderer.domElement.parentNode.removeChild(renderer.domElement)
  }
  geometry?.dispose()
  material?.dispose()
  renderer?.dispose()
})
</script>

<style scoped>
.shader-background {
  position: absolute;
  inset: 0;
  background: #020511;
  overflow: hidden;
  isolation: isolate;
}

.shader-background::after {
  content: '';
  position: absolute;
  top: 18%;
  right: 28%;
  bottom: 2%;
  left: 28%;
  z-index: 2;
  background: radial-gradient(ellipse at center, rgba(2, 5, 12, 0.58) 0%, rgba(2, 5, 12, 0.4) 48%, rgba(2, 5, 12, 0) 80%);
  pointer-events: none;
}

.shader-background :deep(canvas) {
  position: relative;
  z-index: 0;
  display: block;
  width: 100%;
  height: 100%;
  filter: brightness(0.52) saturate(1.48) contrast(1.08);
}

.meteor-layer {
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: hidden;
  pointer-events: none;
  mix-blend-mode: screen;
}

.meteor-layer::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.34;
  background-image:
    radial-gradient(circle at 12% 18%, rgba(178, 225, 255, 0.62) 0 1px, transparent 1.6px),
    radial-gradient(circle at 76% 23%, rgba(255, 232, 175, 0.48) 0 1px, transparent 1.5px),
    radial-gradient(circle at 34% 67%, rgba(148, 211, 255, 0.52) 0 0.8px, transparent 1.4px),
    radial-gradient(circle at 88% 75%, rgba(177, 223, 255, 0.45) 0 1px, transparent 1.6px),
    radial-gradient(circle at 52% 42%, rgba(255, 255, 255, 0.32) 0 0.8px, transparent 1.3px);
}

.meteor {
  width: var(--meteor-length);
  height: 2px;
  position: absolute;
  top: var(--meteor-y);
  left: var(--meteor-x);
  border-radius: 1px;
  opacity: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(64, 173, 255, 0.07) 24%, rgba(83, 192, 255, 0.52) 76%, rgba(222, 246, 255, 0.88) 96%, transparent 100%);
  box-shadow: 0 0 6px rgba(55, 181, 255, 0.4);
  filter: drop-shadow(0 0 7px rgba(66, 185, 255, 0.4));
  clip-path: polygon(0 46%, 94% 12%, 100% 50%, 94% 88%, 0 54%);
  transform-origin: right center;
  animation: meteor-flight-left var(--meteor-duration) cubic-bezier(0.22, 0.6, 0.34, 1) var(--meteor-delay) infinite;
  will-change: transform, opacity;
}

.meteor.right {
  animation-name: meteor-flight-right;
}

.meteor.warm {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 155, 68, 0.045) 24%, rgba(255, 190, 92, 0.45) 76%, rgba(255, 243, 200, 0.86) 96%, transparent 100%);
  box-shadow: 0 0 6px rgba(255, 177, 67, 0.34);
  filter: drop-shadow(0 0 7px rgba(255, 168, 62, 0.34));
}

.stationary-streak {
  width: var(--streak-length);
  height: 1.5px;
  position: absolute;
  top: var(--streak-y);
  left: var(--streak-x);
  opacity: var(--streak-opacity);
  background: linear-gradient(90deg, transparent 0%, rgba(62, 160, 232, 0.08) 20%, rgba(75, 182, 251, 0.64) 78%, rgba(194, 234, 255, 0.76) 96%, transparent 100%);
  box-shadow: 0 0 8px rgba(45, 166, 239, 0.4);
  filter: drop-shadow(0 0 7px rgba(54, 173, 244, 0.38));
  clip-path: polygon(0 45%, 95% 12%, 100% 50%, 95% 88%, 0 55%);
  transform: rotate(var(--streak-angle));
  transform-origin: center;
  animation: stationary-shimmer 4.8s ease-in-out var(--streak-delay) infinite alternate;
}

.stationary-streak.warm {
  background: linear-gradient(90deg, transparent 0%, rgba(255, 156, 66, 0.05) 20%, rgba(255, 184, 82, 0.52) 78%, rgba(255, 235, 184, 0.7) 96%, transparent 100%);
  box-shadow: 0 0 7px rgba(255, 161, 59, 0.27);
  filter: drop-shadow(0 0 6px rgba(255, 164, 61, 0.25));
}

@keyframes meteor-flight-left {
  0%, 5% {
    opacity: 0;
    transform: translate3d(-16vw, -18vh, 0) rotate(35deg) scaleX(0.38) scale(var(--meteor-scale));
  }
  10% {
    opacity: 0.96;
  }
  28% {
    opacity: 0.78;
    transform: translate3d(3vw, 5vh, 0) rotate(35deg) scaleX(1) scale(var(--meteor-scale));
  }
  43%, 100% {
    opacity: 0;
    transform: translate3d(24vw, 32vh, 0) rotate(35deg) scaleX(0.72) scale(var(--meteor-scale));
  }
}

@keyframes meteor-flight-right {
  0%, 5% {
    opacity: 0;
    transform: translate3d(-4vw, -18vh, 0) rotate(35deg) scaleX(0.38) scale(var(--meteor-scale));
  }
  10% {
    opacity: 0.96;
  }
  28% {
    opacity: 0.78;
    transform: translate3d(8vw, 5vh, 0) rotate(35deg) scaleX(1) scale(var(--meteor-scale));
  }
  43%, 100% {
    opacity: 0;
    transform: translate3d(28vw, 32vh, 0) rotate(35deg) scaleX(0.72) scale(var(--meteor-scale));
  }
}

@keyframes stationary-shimmer {
  from {
    opacity: 0.18;
  }
  to {
    opacity: var(--streak-opacity);
  }
}

@media (max-width: 768px) {
  .shader-background::after {
    right: 13%;
    left: 13%;
    opacity: 0.48;
  }

  .shader-background :deep(canvas) {
    filter: brightness(0.58) saturate(1.42) contrast(1.06);
  }

  .meteor:nth-child(even) {
    display: none;
  }

  .stationary-streak {
    animation: none;
    opacity: 0.24;
  }

  .stationary-streak.left {
    left: -10%;
  }

  .stationary-streak.right {
    left: 78%;
  }

}

@media (prefers-reduced-motion: reduce) {
  .meteor,
  .stationary-streak {
    animation: none;
  }

  .meteor {
    opacity: 0.14;
    transform: rotate(35deg) scale(var(--meteor-scale));
  }
}
</style>
