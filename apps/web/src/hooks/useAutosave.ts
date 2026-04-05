/**
 * Hook для автоматического сохранения dirty блоков.
 * Debounce 800ms — после последнего изменения геометрии отправляет PATCH.
 */

import { useEffect, useRef } from 'react'
import { patchBlock } from '../api/blocksApi'
import { useEditorStore } from '../store/useEditorStore'

const DEBOUNCE_MS = 800

export function useAutosave() {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // Подписка на изменение dirtyBlockIds
    const unsub = useEditorStore.subscribe(
      (state) => state.dirtyBlockIds,
      (dirtyIds) => {
        if (dirtyIds.size === 0) return

        // Сбросить предыдущий таймер
        if (timerRef.current) {
          clearTimeout(timerRef.current)
        }

        timerRef.current = setTimeout(async () => {
          const store = useEditorStore.getState()
          const ids = Array.from(store.dirtyBlockIds)
          if (ids.length === 0) return

          store.setSaving(true)

          for (const blockId of ids) {
            // Найти блок в store
            let block = null
            for (const blocks of Object.values(store.blocksByPage)) {
              block = blocks.find((b) => b.id === blockId)
              if (block) break
            }

            if (!block) {
              store.clearDirty(blockId)
              continue
            }

            try {
              const updated = await patchBlock(blockId, {
                bboxJson: block.bboxJson,
                polygonJson: block.polygonJson,
                shapeType: block.shapeType,
              })
              // Обновить geometryRev из ответа сервера
              store.updateBlockInStore(updated)
              store.clearDirty(blockId)
            } catch (err) {
              console.error('Ошибка autosave блока:', blockId, err)
              // Оставляем dirty для повторной попытки
            }
          }

          store.setSaving(false)
        }, DEBOUNCE_MS)
      },
    )

    // Flush при уходе со страницы
    const handleBeforeUnload = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      // Синхронный flush невозможен, но мы пытаемся
      const store = useEditorStore.getState()
      if (store.dirtyBlockIds.size > 0) {
        // sendBeacon не подходит для PATCH, но предупредим
        console.warn('Есть несохранённые изменения блоков:', store.dirtyBlockIds.size)
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      unsub()
      window.removeEventListener('beforeunload', handleBeforeUnload)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [])
}
