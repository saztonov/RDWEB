/**
 * Тесты Zustand store: interaction state machine, selection, zoom, pagination.
 *
 * Не тестируем API-зависимые actions (loadDocument, addBlock и т.д.) —
 * для этого нужны моки. Тестируем чистую логику state machine.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useEditorStore } from '../store/useEditorStore'
import { InteractionState } from '../types/editor'
import { BlockKind, ShapeType } from '../types/block'

// Сброс store перед каждым тестом
beforeEach(() => {
  useEditorStore.setState({
    documentId: null,
    documentTitle: '',
    pages: [],
    currentPage: 1,
    totalPages: 0,
    pdfUrl: null,
    documentLoading: false,
    documentError: null,
    blocksByPage: {},
    loadingPages: new Set(),
    selectedIds: new Set(),
    hoveredId: null,
    interactionState: InteractionState.IDLE,
    activeBlockKind: 'text' as BlockKind,
    activeShapeType: ShapeType.RECTANGLE,
    drawingPoints: [],
    drawingOrigin: null,
    drawingCurrent: null,
    resizeHandle: null,
    dragOrigin: null,
    dragVertexIdx: null,
    dragEdgeIdx: null,
    originalBbox: null,
    originalPolygonPoints: null,
    zoom: 1,
    inspectedBlockId: null,
    inspectedDetail: null,
    inspectedAttempts: [],
    inspectorLoading: false,
    activeRunId: null,
    runProgress: null,
    dirtyBlockIds: new Set(),
    saving: false,
  })
})

describe('Interaction State Machine', () => {
  it('начинает с IDLE', () => {
    expect(useEditorStore.getState().interactionState).toBe(InteractionState.IDLE)
  })

  it('переходит из IDLE в DRAWING_RECT', () => {
    useEditorStore.getState().transitionTo(InteractionState.DRAWING_RECT)
    expect(useEditorStore.getState().interactionState).toBe(InteractionState.DRAWING_RECT)
  })

  it('переходит из DRAWING_RECT обратно в IDLE', () => {
    useEditorStore.getState().transitionTo(InteractionState.DRAWING_RECT)
    useEditorStore.getState().transitionTo(InteractionState.IDLE)
    expect(useEditorStore.getState().interactionState).toBe(InteractionState.IDLE)
  })

  it('resetInteraction сбрасывает в IDLE и очищает drawing state', () => {
    const store = useEditorStore.getState()
    store.transitionTo(InteractionState.DRAWING_POLYGON)
    store.setDrawingOrigin({ x: 10, y: 20 })
    store.addDrawingPoint({ x: 30, y: 40 })
    store.setDrawingCurrent({ x: 50, y: 60 })

    store.resetInteraction()
    const state = useEditorStore.getState()
    expect(state.interactionState).toBe(InteractionState.IDLE)
    expect(state.drawingOrigin).toBeNull()
    expect(state.drawingCurrent).toBeNull()
    expect(state.drawingPoints).toEqual([])
  })
})

describe('Block Kind & Shape Type', () => {
  it('начинает с text kind и rect shape', () => {
    const state = useEditorStore.getState()
    expect(state.activeBlockKind).toBe(BlockKind.TEXT)
    expect(state.activeShapeType).toBe(ShapeType.RECTANGLE)
  })

  it('переключает block kind', () => {
    useEditorStore.getState().setActiveBlockKind(BlockKind.STAMP)
    expect(useEditorStore.getState().activeBlockKind).toBe(BlockKind.STAMP)
  })

  it('toggleShapeType переключает rect <-> polygon', () => {
    useEditorStore.getState().toggleShapeType()
    expect(useEditorStore.getState().activeShapeType).toBe(ShapeType.POLYGON)

    useEditorStore.getState().toggleShapeType()
    expect(useEditorStore.getState().activeShapeType).toBe(ShapeType.RECTANGLE)
  })
})

describe('Selection', () => {
  const block1 = {
    id: 'b1', documentId: 'd1', pageNumber: 1,
    blockKind: BlockKind.TEXT, shapeType: ShapeType.RECTANGLE,
    bboxJson: { x: 0, y: 0, width: 100, height: 50 },
    polygonJson: null, readingOrder: null, geometryRev: 1, contentRev: 0,
    manualLock: false, routeSourceId: null, routeModelName: null,
    promptTemplateId: null, currentText: null, currentStructuredJson: null,
    currentRenderHtml: null, currentAttemptId: null,
    currentStatus: 'pending' as const, lastRecognitionSignature: null,
    deletedAt: null, createdAt: '2026-01-01', updatedAt: '2026-01-01',
  }

  const block2 = { ...block1, id: 'b2', bboxJson: { x: 200, y: 200, width: 100, height: 50 } }

  beforeEach(() => {
    useEditorStore.setState({
      currentPage: 1,
      blocksByPage: { 1: [block1, block2] },
    })
  })

  it('selectBlock выбирает один блок', () => {
    useEditorStore.getState().selectBlock('b1')
    expect(useEditorStore.getState().selectedIds.has('b1')).toBe(true)
    expect(useEditorStore.getState().selectedIds.size).toBe(1)
  })

  it('selectBlock заменяет предыдущий выбор', () => {
    useEditorStore.getState().selectBlock('b1')
    useEditorStore.getState().selectBlock('b2')
    expect(useEditorStore.getState().selectedIds.has('b1')).toBe(false)
    expect(useEditorStore.getState().selectedIds.has('b2')).toBe(true)
  })

  it('toggleSelect добавляет/убирает блок из множества', () => {
    useEditorStore.getState().selectBlock('b1')
    useEditorStore.getState().toggleSelect('b2')
    expect(useEditorStore.getState().selectedIds.size).toBe(2)

    useEditorStore.getState().toggleSelect('b1')
    expect(useEditorStore.getState().selectedIds.size).toBe(1)
    expect(useEditorStore.getState().selectedIds.has('b2')).toBe(true)
  })

  it('clearSelection очищает выбор', () => {
    useEditorStore.getState().selectBlock('b1')
    useEditorStore.getState().clearSelection()
    expect(useEditorStore.getState().selectedIds.size).toBe(0)
  })

  it('selectInRect выбирает блоки пересекающие rect', () => {
    useEditorStore.getState().selectInRect(1, { x: 0, y: 0, width: 150, height: 150 })
    const ids = useEditorStore.getState().selectedIds
    expect(ids.has('b1')).toBe(true)
    expect(ids.has('b2')).toBe(false)
  })
})

describe('Zoom', () => {
  it('начинает с zoom = 1', () => {
    expect(useEditorStore.getState().zoom).toBe(1)
  })

  it('zoomIn увеличивает на 15%', () => {
    useEditorStore.getState().zoomIn()
    expect(useEditorStore.getState().zoom).toBeCloseTo(1.15, 2)
  })

  it('zoomOut уменьшает на ~13%', () => {
    useEditorStore.getState().zoomOut()
    expect(useEditorStore.getState().zoom).toBeCloseTo(1 / 1.15, 2)
  })

  it('setZoom ограничивает диапазон 0.1..5', () => {
    useEditorStore.getState().setZoom(0.01)
    expect(useEditorStore.getState().zoom).toBeGreaterThanOrEqual(0.1)

    useEditorStore.getState().setZoom(10)
    expect(useEditorStore.getState().zoom).toBeLessThanOrEqual(5)
  })
})

describe('Page Navigation', () => {
  beforeEach(() => {
    useEditorStore.setState({
      currentPage: 1,
      totalPages: 5,
      pages: [
        { id: 'p1', pageNumber: 1, width: 612, height: 792, rotation: 0 },
        { id: 'p2', pageNumber: 2, width: 612, height: 792, rotation: 0 },
        { id: 'p3', pageNumber: 3, width: 612, height: 792, rotation: 0 },
        { id: 'p4', pageNumber: 4, width: 612, height: 792, rotation: 0 },
        { id: 'p5', pageNumber: 5, width: 612, height: 792, rotation: 0 },
      ],
    })
  })

  it('nextPage увеличивает currentPage', () => {
    useEditorStore.getState().nextPage()
    expect(useEditorStore.getState().currentPage).toBe(2)
  })

  it('prevPage уменьшает currentPage', () => {
    useEditorStore.getState().setCurrentPage(3)
    useEditorStore.getState().prevPage()
    expect(useEditorStore.getState().currentPage).toBe(2)
  })

  it('nextPage не выходит за пределы', () => {
    useEditorStore.getState().setCurrentPage(5)
    useEditorStore.getState().nextPage()
    expect(useEditorStore.getState().currentPage).toBe(5)
  })

  it('prevPage не уходит ниже 1', () => {
    useEditorStore.getState().prevPage()
    expect(useEditorStore.getState().currentPage).toBe(1)
  })

  it('setCurrentPage очищает selection', () => {
    useEditorStore.setState({ selectedIds: new Set(['b1', 'b2']) })
    useEditorStore.getState().setCurrentPage(2)
    expect(useEditorStore.getState().selectedIds.size).toBe(0)
  })
})

describe('Dirty Tracking', () => {
  it('markDirty добавляет blockId', () => {
    useEditorStore.getState().markDirty('b1')
    expect(useEditorStore.getState().dirtyBlockIds.has('b1')).toBe(true)
  })

  it('clearDirty убирает blockId', () => {
    useEditorStore.getState().markDirty('b1')
    useEditorStore.getState().clearDirty('b1')
    expect(useEditorStore.getState().dirtyBlockIds.has('b1')).toBe(false)
  })

  it('setSaving устанавливает флаг', () => {
    useEditorStore.getState().setSaving(true)
    expect(useEditorStore.getState().saving).toBe(true)
  })
})

describe('Drawing State', () => {
  it('setDrawingOrigin/Current', () => {
    useEditorStore.getState().setDrawingOrigin({ x: 10, y: 20 })
    useEditorStore.getState().setDrawingCurrent({ x: 50, y: 60 })
    expect(useEditorStore.getState().drawingOrigin).toEqual({ x: 10, y: 20 })
    expect(useEditorStore.getState().drawingCurrent).toEqual({ x: 50, y: 60 })
  })

  it('addDrawingPoint накапливает точки polygon', () => {
    useEditorStore.getState().addDrawingPoint({ x: 0, y: 0 })
    useEditorStore.getState().addDrawingPoint({ x: 100, y: 0 })
    useEditorStore.getState().addDrawingPoint({ x: 100, y: 100 })
    expect(useEditorStore.getState().drawingPoints).toHaveLength(3)
  })

  it('setDrawingPoints заменяет массив', () => {
    useEditorStore.getState().addDrawingPoint({ x: 1, y: 1 })
    useEditorStore.getState().setDrawingPoints([{ x: 0, y: 0 }])
    expect(useEditorStore.getState().drawingPoints).toHaveLength(1)
  })
})
