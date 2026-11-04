<script setup lang="ts">
import { confirmState, settleConfirm } from './confirm'
import Modal from './Modal.vue'
</script>

<template>
  <Modal :open="confirmState.open" :title="confirmState.title" code="CONFIRM" :width="460" @close="settleConfirm(false)">
    <p class="msg">{{ confirmState.message }}</p>
    <p v-if="confirmState.detail" class="detail">{{ confirmState.detail }}</p>
    <template #foot>
      <button class="btn" @click="settleConfirm(false)">取消</button>
      <button class="btn" :class="confirmState.danger ? 'danger' : 'primary'" @click="settleConfirm(true)">{{ confirmState.okText }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.msg { margin: 0; font-size: 14px; line-height: 1.7; color: var(--text-0); white-space: pre-line; }
.detail { margin: 10px 0 0; font-size: 12.5px; line-height: 1.7; color: var(--text-2); white-space: pre-line; }
</style>
