/**
 * Мемоизированные селекторы для Zustand store.
 * Используются компонентами для подписки на конкретные срезы state.
 */

import type { Block } from '../types/block'
import type { EditorStore } from './useEditorStore'

/** Блоки текущей страницы */
export const selectBlocksForCurrentPage = (state: EditorStore): Block[] =>
  state.blocksByPage[state.currentPage] ?? []

/** Блоки конкретной страницы (для OverlaySvg) */
export const selectBlocksForPage =
  (page: number) =>
  (state: EditorStore): Block[] =>
    state.blocksByPage[page] ?? []

/** Множество выделенных ID */
export const selectSelectedIds = (state: EditorStore): Set<string> =>
  state.selectedIds

/** Проверка: блок выделен? */
export const selectIsBlockSelected =
  (blockId: string) =>
  (state: EditorStore): boolean =>
    state.selectedIds.has(blockId)

/** Получить выделенные блоки (для sidebar) */
export const selectSelectedBlocks = (state: EditorStore): Block[] => {
  const blocks = state.blocksByPage[state.currentPage] ?? []
  return blocks.filter((b) => state.selectedIds.has(b.id))
}

/** Interaction state */
export const selectInteractionState = (state: EditorStore) =>
  state.interactionState

/** Активный block kind */
export const selectActiveBlockKind = (state: EditorStore) =>
  state.activeBlockKind

/** Активный shape type */
export const selectActiveShapeType = (state: EditorStore) =>
  state.activeShapeType

/** Zoom level */
export const selectZoom = (state: EditorStore) => state.zoom

/** Страницы документа */
export const selectPages = (state: EditorStore) => state.pages

/** Текущая страница */
export const selectCurrentPage = (state: EditorStore) => state.currentPage

/** Загружается ли страница блоков */
export const selectIsPageLoading =
  (page: number) =>
  (state: EditorStore): boolean =>
    state.loadingPages.has(page)

/** Есть ли несохранённые изменения */
export const selectHasDirtyBlocks = (state: EditorStore): boolean =>
  state.dirtyBlockIds.size > 0

/** Drawing state для превью */
export const selectDrawingState = (state: EditorStore) => ({
  origin: state.drawingOrigin,
  current: state.drawingCurrent,
  points: state.drawingPoints,
  interactionState: state.interactionState,
  activeBlockKind: state.activeBlockKind,
})
