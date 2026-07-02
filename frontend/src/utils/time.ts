/** 时间格式化工具 */
export function formatTime(iso: string): string {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) } catch { return iso }
}
export function formatDuration(seconds: number): string {
  if (seconds < 60) return seconds+'s'
  if (seconds < 3600) return Math.round(seconds/60)+'m'
  return (seconds/3600).toFixed(1)+'h'
}
