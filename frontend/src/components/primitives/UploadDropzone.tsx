import { useCallback, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { toast } from 'sonner'

import { useUploadMutation } from '@/state/invoices'
import { cn } from '@/utils/cn'

export function UploadDropzone() {
  const upload = useUploadMutation()
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return
      const file = files[0]
      if (file.type !== 'application/pdf') {
        toast.error('Only PDFs are accepted right now.')
        return
      }
      const id = toast.loading(`Extracting ${file.name}…`)
      try {
        const inv = await upload.mutateAsync(file)
        const vendor =
          inv.current_extraction?.extracted_fields?.vendor_name?.value ?? 'invoice'
        toast.success(`Extracted ${vendor}`, { id })
      } catch (e) {
        toast.error(`Upload failed: ${(e as Error).message}`, { id })
      }
    },
    [upload]
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        void handleFiles(e.dataTransfer.files)
      }}
      onClick={() => fileInput.current?.click()}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors',
        dragging ? 'border-primary bg-accent' : 'border-border hover:bg-accent/40'
      )}
    >
      <Upload className="h-8 w-8 text-muted-foreground" />
      <p className="mt-2 text-sm">
        <span className="font-medium">Drop a PDF</span>{' '}
        <span className="text-muted-foreground">or click to upload</span>
      </p>
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => void handleFiles(e.target.files)}
      />
    </div>
  )
}
