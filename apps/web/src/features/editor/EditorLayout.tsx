/**
 * Layout редактора: toolbar сверху, sidebar слева, viewport по центру,
 * inspector справа (если выбран блок).
 */

import type { PDFDocumentProxy } from 'pdfjs-dist'

import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts'
import { useAutosave } from '../../hooks/useAutosave'
import { useEditorStore } from '../../store/useEditorStore'
import { EditorToolbar } from './EditorToolbar'
import { EditorSidebar } from './EditorSidebar'
import { BlockInspector } from './BlockInspector'
import { Viewport } from '../viewport/Viewport'

interface EditorLayoutProps {
  pdfDocument: PDFDocumentProxy
}

export function EditorLayout({ pdfDocument }: EditorLayoutProps) {
  // Глобальные hooks
  useKeyboardShortcuts()
  useAutosave()

  const inspectedBlockId = useEditorStore((s) => s.inspectedBlockId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <EditorToolbar />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <EditorSidebar />
        <Viewport pdfDocument={pdfDocument} />
        {inspectedBlockId && <BlockInspector />}
      </div>
    </div>
  )
}
