// Triggering a browser file download from data already in memory or fetched
// as a Blob (Results page downloads, SPECS section 4.3).

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function downloadJson(value: unknown, filename: string): void {
  triggerBlobDownload(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }), filename)
}
