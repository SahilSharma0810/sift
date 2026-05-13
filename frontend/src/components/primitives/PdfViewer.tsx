import { useEffect, useRef } from 'react'
import * as pdfjs from 'pdfjs-dist'

// Configure worker URL — Vite resolves the module URL at build time.
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export function PdfViewer({ src }: { src: string }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''
    let cancelled = false

    void (async () => {
      try {
        const doc = await pdfjs.getDocument(src).promise
        const page = await doc.getPage(1)
        const viewport = page.getViewport({ scale: 1.5 })
        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d')!
        canvas.width = viewport.width
        canvas.height = viewport.height
        canvas.className = 'max-w-full shadow'
        if (cancelled) return
        container.appendChild(canvas)
        await page.render({ canvasContext: context, viewport }).promise
      } catch {
        if (!cancelled) {
          container.textContent = 'Could not render this PDF.'
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [src])

  return (
    <div ref={containerRef} className="flex justify-center bg-muted/20 p-4" />
  )
}
