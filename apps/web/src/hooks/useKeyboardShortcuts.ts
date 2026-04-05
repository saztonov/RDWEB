/**
 * Hook для keyboard shortcuts в редакторе.
 * Адаптировано из legacy hotkeys_dialog.py.
 *
 * Ctrl+1/2/3 — тип блока (text/image/stamp)
 * Ctrl+Q — toggle rect/polygon
 * Delete — удалить выделенные блоки
 * Escape — отменить рисование / снять выделение
 * ←/→ — навигация по страницам
 */

import { useEffect } from 'react'
import { BlockKind } from '../types/block'
import { InteractionState } from '../types/editor'
import { useEditorStore } from '../store/useEditorStore'

export function useKeyboardShortcuts() {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const store = useEditorStore.getState()

      // Не перехватывать если фокус в input/textarea
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      // Ctrl+1 — text
      if (e.ctrlKey && e.key === '1') {
        e.preventDefault()
        store.setActiveBlockKind(BlockKind.TEXT)
        return
      }

      // Ctrl+2 — image
      if (e.ctrlKey && e.key === '2') {
        e.preventDefault()
        store.setActiveBlockKind(BlockKind.IMAGE)
        return
      }

      // Ctrl+3 — stamp
      if (e.ctrlKey && e.key === '3') {
        e.preventDefault()
        store.setActiveBlockKind(BlockKind.STAMP)
        return
      }

      // Ctrl+Q — toggle rect/polygon
      if (e.ctrlKey && (e.key === 'q' || e.key === 'Q' || e.key === 'й' || e.key === 'Й')) {
        e.preventDefault()
        store.toggleShapeType()
        return
      }

      // Delete — удалить выделенные блоки
      if (e.key === 'Delete') {
        e.preventDefault()
        if (store.selectedIds.size > 0) {
          store.softDeleteSelected()
        }
        return
      }

      // Escape — отменить рисование или снять выделение
      if (e.key === 'Escape') {
        e.preventDefault()
        if (store.interactionState !== InteractionState.IDLE) {
          store.resetInteraction()
        } else {
          store.clearSelection()
        }
        return
      }

      // ← — предыдущая страница
      if (e.key === 'ArrowLeft' && !e.ctrlKey) {
        e.preventDefault()
        store.prevPage()
        return
      }

      // → — следующая страница
      if (e.key === 'ArrowRight' && !e.ctrlKey) {
        e.preventDefault()
        store.nextPage()
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])
}
