import { reactive } from 'vue'

export const confirmState = reactive({
  open: false,
  title: '',
  message: '',
  detail: '',
  okText: '确定',
  danger: false,
})
let resolver: ((v: boolean) => void) | null = null

/** 确认对话框：await confirm({...}) → true/false */
export function confirm(o: { title: string; message: string; detail?: string; okText?: string; danger?: boolean }): Promise<boolean> {
  resolver?.(false)
  Object.assign(confirmState, { open: true, detail: '', okText: '确定', danger: false, ...o })
  return new Promise((r) => (resolver = r))
}

export function settleConfirm(v: boolean): void {
  confirmState.open = false
  resolver?.(v)
  resolver = null
}
