<template>
  <div class="boot" role="status" aria-live="polite">
    <svg class="hex fx-loop" viewBox="0 0 100 100" aria-hidden="true">
      <path d="M50 4 90 27v46L50 96 10 73V27z" fill="none" stroke="var(--line-strong)" stroke-width="1.5" />
      <path d="M50 4 90 27v46" fill="none" stroke="var(--cyan)" stroke-width="2.5" stroke-linecap="round" />
    </svg>
    <div class="t disp">INTEL BUREAU</div>
    <div class="s">正在连接情报局后端…</div>
  </div>
</template>

<style scoped>
.boot { position: fixed; inset: 0; z-index: 5; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; }
.hex { width: 72px; height: 72px; animation: kf-spin 1.6s linear infinite; filter: drop-shadow(0 0 8px rgba(34, 228, 255, 0.5)); }
.t { font-size: 15px; letter-spacing: 6px; color: var(--text-0); }
.s { font-size: 12.5px; color: var(--text-2); }
</style>
