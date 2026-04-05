/**
 * Тесты мемоизированных селекторов Zustand store.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useEditorStore } from '../store/useEditorStore'
import {
  selectBlocksForCurrentPage,
  selectBlocksForPage,
  selectSelectedIds,
  selectIsBlockSelected,
  selectSelectedBlocks,
  selectHasDirtyBlocks,
  selectZoom,
  selectCurrentPage,
  selectIsPageLoading,
} from '../store/selectors'
import { BlockKind, ShapeType } from '../types/block'
import { InteractionState } from '../types/editor'
import type { Block } from '../types/block'

const makeBlock = (id: string, page: number): Block => ({
  id,
  documentId: 'd1',
  pageNumber: page,
  blockKind: BlockKind.TEXT,
  shapeType: ShapeType.RECTANGLE,
  bboxJson: { x: 0, y: 0, width: 100, height: 50 },
  polygonJson: null,
  readingOrder: null,
  geometryRev: 1,
  contentRev: 0,
  manualLock: false,
  routeSourceId: null,
  routeModelName: null,
  promptTemplateId: null,
  currentText: null,
  currentStructuredJson: null,
  currentRenderHtml: null,
  currentAttemptId: null,
  currentStatus: 'pending',
  lastRecognitionSignature: null,
  deletedAt: null,
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
})

beforeEach(() => {
  useEditorStore.setState({
    currentPage: 1,
    totalPages: 3,
    zoom: 1,
    blocksByPage: {
      1: [makeBlock('b1', 1), makeBlock('b2', 1)],
      2: [makeBlock('b3', 2)],
    },
    selectedIds: new Set(['b1']),
    loadingPages: new Set([3]),
    dirtyBlockIds: new Set(),
    interactionState: InteractionState.IDLE,
  })
})

describe('selectors', () => {
  it('selectBlocksForCurrentPage возвращает блоки текущей страницы', () => {
    const state = useEditorStore.getState()
    const blocks = selectBlocksForCurrentPage(state)
    expect(blocks).toHaveLength(2)
    expect(blocks[0].id).toBe('b1')
  })

  it('selectBlocksForPage(2) возвращает блоки второй страницы', () => {
    const state = useEditorStore.getState()
    expect(selectBlocksForPage(2)(state)).toHaveLength(1)
    expect(selectBlocksForPage(2)(state)[0].id).toBe('b3')
  })

  it('selectBlocksForPage для несуществующей страницы возвращает []', () => {
    const state = useEditorStore.getState()
    expect(selectBlocksForPage(99)(state)).toEqual([])
  })

  it('selectSelectedIds возвращает Set', () => {
    const ids = selectSelectedIds(useEditorStore.getState())
    expect(ids).toBeInstanceOf(Set)
    expect(ids.has('b1')).toBe(true)
  })

  it('selectIsBlockSelected проверяет выделение', () => {
    const state = useEditorStore.getState()
    expect(selectIsBlockSelected('b1')(state)).toBe(true)
    expect(selectIsBlockSelected('b2')(state)).toBe(false)
  })

  it('selectSelectedBlocks фильтрует блоки текущей страницы', () => {
    const state = useEditorStore.getState()
    const selected = selectSelectedBlocks(state)
    expect(selected).toHaveLength(1)
    expect(selected[0].id).toBe('b1')
  })

  it('selectHasDirtyBlocks', () => {
    expect(selectHasDirtyBlocks(useEditorStore.getState())).toBe(false)
    useEditorStore.getState().markDirty('b1')
    expect(selectHasDirtyBlocks(useEditorStore.getState())).toBe(true)
  })

  it('selectZoom', () => {
    expect(selectZoom(useEditorStore.getState())).toBe(1)
  })

  it('selectCurrentPage', () => {
    expect(selectCurrentPage(useEditorStore.getState())).toBe(1)
  })

  it('selectIsPageLoading', () => {
    const state = useEditorStore.getState()
    expect(selectIsPageLoading(3)(state)).toBe(true)
    expect(selectIsPageLoading(1)(state)).toBe(false)
  })
})
