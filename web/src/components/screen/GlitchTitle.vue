<script setup lang="ts">
/** 故障风标题（§4.1）：渐变文字；每 8 秒 120ms 故障抖动（RGB 通道错位 + clip-path 切片）。只动 opacity/transform。 */
</script>

<template>
  <div class="gt">
    <span class="br l" aria-hidden="true">◤</span>
    <h1 class="wrap">
      <span class="txt main fx-rich"><span class="cn">情报局</span><span class="dot">·</span><span class="en">INTEL BUREAU</span></span>
      <span class="txt ghost a fx-rich" aria-hidden="true"><span class="cn">情报局</span><span class="dot">·</span><span class="en">INTEL BUREAU</span></span>
      <span class="txt ghost b fx-rich" aria-hidden="true"><span class="cn">情报局</span><span class="dot">·</span><span class="en">INTEL BUREAU</span></span>
    </h1>
    <span class="br r" aria-hidden="true">◢</span>
  </div>
</template>

<style scoped>
.gt { position: relative; display: flex; align-items: center; gap: 10px; }
.br { font-size: 14px; color: var(--cyan); text-shadow: 0 0 8px var(--cyan); line-height: 1; }
.br.l { align-self: flex-start; margin-top: 2px; }
.br.r { align-self: flex-end; margin-bottom: 2px; color: var(--violet); text-shadow: 0 0 8px var(--violet); }
.wrap { position: relative; margin: 0; font-size: 0; line-height: 1; }
.txt {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 6px;
  line-height: 1.1;
  white-space: nowrap;
}
.cn { font-family: var(--font-cn); font-weight: 800; letter-spacing: 8px; }
.dot { letter-spacing: 0; opacity: 0.7; }
.en { font-size: 26px; }
.main {
  background: linear-gradient(90deg, #22e4ff 0%, #79dcff 38%, #8b5cff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  filter: drop-shadow(0 0 10px rgba(34, 228, 255, 0.35));
  animation: kf-glitch-main 8s steps(1) infinite;
}
.ghost { position: absolute; inset: 0; pointer-events: none; opacity: 0; mix-blend-mode: screen; }
.ghost.a { color: #ff3db8; clip-path: polygon(0 6%, 100% 6%, 100% 44%, 0 44%); animation: kf-glitch-a 8s linear infinite; }
.ghost.b { color: #22e4ff; clip-path: polygon(0 56%, 100% 56%, 100% 92%, 0 92%); animation: kf-glitch-b 8s linear infinite; }
@keyframes kf-glitch-main {
  0%, 96.9%, 98.5%, 100% { transform: none; }
  97% { transform: translateX(1px) skewX(-4deg); }
  97.8% { transform: translateX(-1px) skewX(3deg); }
}
@keyframes kf-glitch-a {
  0%, 96.9% { opacity: 0; transform: none; }
  97% { opacity: 0.85; transform: translate(-4px, -1px); }
  97.6% { opacity: 0.85; transform: translate(3px, 0); }
  98.3% { opacity: 0.6; transform: translate(-2px, 1px); }
  98.5%, 100% { opacity: 0; transform: none; }
}
@keyframes kf-glitch-b {
  0%, 96.9% { opacity: 0; transform: none; }
  97.1% { opacity: 0.85; transform: translate(4px, 1px); }
  97.8% { opacity: 0.8; transform: translate(-3px, 0); }
  98.4% { opacity: 0.5; transform: translate(2px, -1px); }
  98.5%, 100% { opacity: 0; transform: none; }
}
</style>
