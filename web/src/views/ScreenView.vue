<script setup lang="ts">
/**
 * 作战大屏（UI_DESIGN §4）：固定 1920×1080 画布，按 min(w/1920, h/1080) 等比缩放并居中。
 * 纵向：顶栏 72 + 10 + 主区 734 + 10 + 底部 212 + 10 + 跑马灯 32 = 1080。
 */
import { onMounted, ref, watch } from 'vue'
import type { IntelItemDTO } from '@/api/types'
import { useScreenScale, DESIGN_H, DESIGN_W } from '@/composables/useScreenScale'
import { live, loadAux, loadTerminalHistory } from '@/stores/live'
import TopBar from '@/components/screen/TopBar.vue'
import KpiStrip from '@/components/screen/KpiStrip.vue'
import SourceMatrix from '@/components/screen/SourceMatrix.vue'
import GroupRank from '@/components/screen/GroupRank.vue'
import MsgComposition from '@/components/screen/MsgComposition.vue'
import Constellation from '@/components/screen/Constellation.vue'
import HeadlineCarousel from '@/components/screen/HeadlineCarousel.vue'
import AgentSquad from '@/components/screen/AgentSquad.vue'
import BattleLog from '@/components/screen/BattleLog.vue'
import DeliveryPanel from '@/components/screen/DeliveryPanel.vue'
import HeatPanel from '@/components/screen/HeatPanel.vue'
import WindCloud from '@/components/screen/WindCloud.vue'
import RisingSignals from '@/components/screen/RisingSignals.vue'
import Ticker from '@/components/screen/Ticker.vue'
import IntelDrawer from '@/components/intel/IntelDrawer.vue'

const { scale, offsetX, offsetY } = useScreenScale()
const drawerItem = ref<IntelItemDTO | null>(null)

onMounted(() => void loadAux())
watch(() => live.overview !== null, (has) => { if (has) void loadTerminalHistory() }, { immediate: true })
</script>

<template>
  <div class="viewport">
    <div
      class="stage"
      :style="{ width: DESIGN_W + 'px', height: DESIGN_H + 'px', transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }"
    >
      <TopBar />
      <main class="body">
        <section class="col left">
          <SourceMatrix />
          <GroupRank />
          <MsgComposition />
        </section>
        <section class="col mid">
          <KpiStrip />
          <Constellation />
          <HeadlineCarousel @open="drawerItem = $event" />
        </section>
        <section class="col right">
          <AgentSquad />
          <BattleLog />
          <DeliveryPanel />
        </section>
      </main>
      <section class="bottom">
        <HeatPanel />
        <WindCloud />
        <RisingSignals />
      </section>
      <Ticker class="r-ticker" />
      <IntelDrawer :item="drawerItem" @close="drawerItem = null" />
    </div>
  </div>
</template>

<style scoped>
.viewport { position: fixed; inset: 0; z-index: 1; overflow: hidden; }
.stage {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
  display: grid;
  grid-template-rows: 72px 734px 212px 32px;
  row-gap: 10px;
  padding: 0 16px;
  overflow: hidden;
}
.body { display: grid; grid-template-columns: 440px minmax(0, 1fr) 440px; gap: 12px; min-height: 0; }
.col { display: grid; gap: 10px; min-height: 0; min-width: 0; }
.left { grid-template-rows: 206px 282px 226px; }
.mid { grid-template-rows: 108px 424px 182px; }
.right { grid-template-rows: 324px 212px 178px; }
.bottom { display: grid; grid-template-columns: 620px minmax(0, 1fr) 640px; gap: 12px; min-height: 0; }
.r-ticker { margin: 0 -16px; }
.col > :deep(*), .bottom > :deep(*) { min-height: 0; }
</style>
