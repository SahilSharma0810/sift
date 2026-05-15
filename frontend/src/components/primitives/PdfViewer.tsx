import { useEffect, useRef } from 'react'
import * as pdfjs from 'pdfjs-dist'

import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export type BboxRect = {
  name: string
  bbox: [number, number, number, number]
}

export function PdfViewer({
  src,
  bboxes = [],
  activeField = null,
  onHoverBbox,
}: {
  src: string
  bboxes?: BboxRect[]
  activeField?: string | null
  onHoverBbox?: (name: string | null) => void
}) {
  const stageRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!stageRef.current) return
    const stage = stageRef.current

    stage.querySelectorAll('canvas').forEach((c) => c.remove())
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
        canvas.style.maxWidth = '100%'
        canvas.style.height = 'auto'
        canvas.style.boxShadow = 'var(--shadow-product)'
        canvas.style.display = 'block'
        if (cancelled) return
        stage.insertBefore(canvas, stage.firstChild)
        await page.render({ canvasContext: context, viewport }).promise
      } catch {
        if (!cancelled) {
          const msg = document.createElement('div')
          msg.textContent = 'Could not render this PDF.'
          msg.style.color = 'var(--ink-60)'
          stage.appendChild(msg)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [src])

  return (
    <div
      ref={stageRef}
      style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}
    >
      {bboxes.length > 0 && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
          }}
        >
          {bboxes.map(({ name, bbox }) => {
            const [x0, y0, x1, y1] = bbox
            return (
              <div
                key={name}
                className="bbox"
                data-active={activeField === name ? 'true' : 'false'}
                onMouseEnter={() => onHoverBbox?.(name)}
                onMouseLeave={() => onHoverBbox?.(null)}
                style={{
                  position: 'absolute',
                  left: `${x0 * 100}%`,
                  top: `${y0 * 100}%`,
                  width: `${(x1 - x0) * 100}%`,
                  height: `${(y1 - y0) * 100}%`,
                  pointerEvents: 'auto',
                }}
                title={name}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
