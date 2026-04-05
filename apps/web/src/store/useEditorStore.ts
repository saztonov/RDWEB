/**
 * Единый Zustand store для Document Editor.
 *
 * Слайсы: document, blocks, selection, interaction, viewport, autosave.
 * Interaction state machine адаптирована из legacy interaction_state.py:
 * взаимоисключающие состояния, переход только IDLE ↔ active.
 */

import { create } from 'zustand'
import { subscribeWithSelector } from 'zustand/middleware'

import * as blocksApi from '../api/blocksApi'
import * as recognitionApi from '../api/recognitionApi'
import { getDocument, getDownloadUrl } from '../api/documentsApi'
import type {
  Block,
  BlockCoords,
  BlockDetail,
  BlockKind,
  CreateBlockPayload,
  RecognitionAttempt,
  RecognitionRun,
} from '../types/block'
import { ShapeType } from '../types/block'
import type { PageMeta, PagePoint, ResizeHandle } from '../types/editor'
import { InteractionState } from '../types/editor'

// ──────────────────────────────────────────────────────────────────
// State shape
// ──────────────────────────────────────────────────────────────────

export interface EditorState {
  // ── Document slice ──
  documentId: string | null
  documentTitle: string
  pages: PageMeta[]
  currentPage: number
  totalPages: number
  pdfUrl: string | null
  documentLoading: boolean
  documentError: string | null

  // ── Blocks slice ──
  blocksByPage: Record<number, Block[]>
  loadingPages: Set<number>

  // ── Selection slice ──
  selectedIds: Set<string>
  hoveredId: string | null

  // ── Interaction slice ──
  interactionState: InteractionState
  activeBlockKind: BlockKind
  activeShapeType: ShapeType
  /** Точки при рисовании polygon */
  drawingPoints: PagePoint[]
  /** Начальная точка при рисовании rect / rubber-band */
  drawingOrigin: PagePoint | null
  /** Текущая точка при рисовании (для превью) */
  drawingCurrent: PagePoint | null
  /** Какой resize handle захвачен */
  resizeHandle: ResizeHandle | null
  /** Начальная позиция drag */
  dragOrigin: PagePoint | null
  /** Индекс вершины polygon при drag */
  dragVertexIdx: number | null
  /** Индекс ребра polygon при drag */
  dragEdgeIdx: number | null
  /** Исходный bbox перед resize/move */
  originalBbox: BlockCoords | null
  /** Исходные polygon points перед drag */
  originalPolygonPoints: [number, number][] | null

  // ── Viewport slice ──
  zoom: number

  // ── Inspector slice ──
  inspectedBlockId: string | null
  inspectedDetail: BlockDetail | null
  inspectedAttempts: RecognitionAttempt[]
  inspectorLoading: boolean

  // ── Recognition slice ──
  activeRunId: string | null
  runProgress: RecognitionRun | null

  // ── Autosave slice ──
  dirtyBlockIds: Set<string>
  saving: boolean
}

// ──────────────────────────────────────────────────────────────────
// Actions
// ──────────────────────────────────────────────────────────────────

export interface EditorActions {
  // ── Document ──
  loadDocument: (id: string) => Promise<void>
  setCurrentPage: (page: number) => void
  nextPage: () => void
  prevPage: () => void
  setPdfUrl: (url: string) => void

  // ── Blocks ──
  loadBlocksForPage: (page: number) => Promise<void>
  addBlock: (payload: CreateBlockPayload) => Promise<Block | null>
  updateBlockGeometry: (
    blockId: string,
    bbox: BlockCoords,
    polygon?: [number, number][] | null,
  ) => void
  updateBlockInStore: (block: Block) => void
  softDeleteBlock: (blockId: string) => Promise<void>
  restoreBlock: (blockId: string) => Promise<void>
  softDeleteSelected: () => Promise<void>

  // ── Selection ──
  selectBlock: (id: string) => void
  toggleSelect: (id: string) => void
  selectInRect: (pageNumber: number, rect: BlockCoords) => void
  clearSelection: () => void
  setHoveredId: (id: string | null) => void

  // ── Interaction ──
  transitionTo: (state: InteractionState) => void
  setActiveBlockKind: (kind: BlockKind) => void
  toggleShapeType: () => void
  setDrawingPoints: (points: PagePoint[]) => void
  addDrawingPoint: (point: PagePoint) => void
  setDrawingOrigin: (point: PagePoint | null) => void
  setDrawingCurrent: (point: PagePoint | null) => void
  setResizeHandle: (handle: ResizeHandle | null) => void
  setDragOrigin: (point: PagePoint | null) => void
  setDragVertexIdx: (idx: number | null) => void
  setDragEdgeIdx: (idx: number | null) => void
  setOriginalBbox: (bbox: BlockCoords | null) => void
  setOriginalPolygonPoints: (points: [number, number][] | null) => void
  resetInteraction: () => void

  // ── Viewport ──
  setZoom: (zoom: number) => void
  zoomIn: () => void
  zoomOut: () => void

  // ── Inspector ──
  openInspector: (blockId: string) => Promise<void>
  closeInspector: () => void
  refreshInspector: () => Promise<void>
  editBlockContent: (
    blockId: string,
    text: string,
    structuredJson?: Record<string, unknown>,
  ) => Promise<void>
  toggleManualLock: (blockId: string, lock: boolean) => Promise<void>
  rerunBlock: (blockId: string, force?: boolean) => Promise<void>
  acceptAttempt: (blockId: string, attemptId: string) => Promise<void>

  // ── Recognition ──
  startRecognition: (runMode: 'smart' | 'full') => Promise<void>
  refreshRunProgress: () => Promise<void>

  // ── Autosave ──
  markDirty: (blockId: string) => void
  clearDirty: (blockId: string) => void
  setSaving: (saving: boolean) => void
}

export type EditorStore = EditorState & EditorActions

// ──────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────

/** Проверка: rect A пересекается с rect B */
function rectsIntersect(a: BlockCoords, b: BlockCoords): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  )
}

// ──────────────────────────────────────────────────────────────────
// Store
// ──────────────────────────────────────────────────────────────────

export const useEditorStore = create<EditorStore>()(
  subscribeWithSelector((set, get) => ({
    // ── Initial state ──
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

    // ────────────────────────────────
    // Document actions
    // ────────────────────────────────

    loadDocument: async (id: string) => {
      set({ documentLoading: true, documentError: null, documentId: id })
      try {
        const doc = await getDocument(id)
        set({
          documentTitle: doc.title,
          pages: doc.pages,
          totalPages: doc.pageCount,
          currentPage: 1,
          documentLoading: false,
        })

        // Запросить presigned download URL для PDF из R2
        if (doc.status === 'ready' || doc.status === 'processing') {
          try {
            const url = await getDownloadUrl(id)
            set({ pdfUrl: url })
          } catch {
            // PDF может быть ещё не загружен — не блокируем работу
          }
        }
      } catch (err) {
        set({
          documentLoading: false,
          documentError: err instanceof Error ? err.message : 'Ошибка загрузки документа',
        })
      }
    },

    setCurrentPage: (page: number) => {
      const { totalPages } = get()
      if (page >= 1 && page <= totalPages) {
        set({ currentPage: page, selectedIds: new Set(), hoveredId: null })
      }
    },

    nextPage: () => {
      const { currentPage, totalPages } = get()
      if (currentPage < totalPages) {
        get().setCurrentPage(currentPage + 1)
      }
    },

    prevPage: () => {
      const { currentPage } = get()
      if (currentPage > 1) {
        get().setCurrentPage(currentPage - 1)
      }
    },

    setPdfUrl: (url: string) => set({ pdfUrl: url }),

    // ────────────────────────────────
    // Blocks actions
    // ────────────────────────────────

    loadBlocksForPage: async (page: number) => {
      const { documentId, loadingPages, blocksByPage } = get()
      if (!documentId || loadingPages.has(page)) return

      // Если уже загружены — не перезагружать
      if (blocksByPage[page] !== undefined) return

      const newLoading = new Set(loadingPages)
      newLoading.add(page)
      set({ loadingPages: newLoading })

      try {
        const blocks = await blocksApi.getBlocks(documentId, page)
        set((state) => {
          const newLoading = new Set(state.loadingPages)
          newLoading.delete(page)
          return {
            blocksByPage: { ...state.blocksByPage, [page]: blocks },
            loadingPages: newLoading,
          }
        })
      } catch {
        set((state) => {
          const newLoading = new Set(state.loadingPages)
          newLoading.delete(page)
          return { loadingPages: newLoading }
        })
      }
    },

    addBlock: async (payload: CreateBlockPayload) => {
      const { documentId } = get()
      if (!documentId) return null

      try {
        const block = await blocksApi.createBlock(documentId, payload)
        set((state) => {
          const pageBlocks = state.blocksByPage[block.pageNumber] ?? []
          return {
            blocksByPage: {
              ...state.blocksByPage,
              [block.pageNumber]: [...pageBlocks, block],
            },
            selectedIds: new Set([block.id]),
          }
        })
        return block
      } catch {
        return null
      }
    },

    updateBlockGeometry: (
      blockId: string,
      bbox: BlockCoords,
      polygon?: [number, number][] | null,
    ) => {
      set((state) => {
        const newBlocksByPage = { ...state.blocksByPage }
        for (const [pageNum, blocks] of Object.entries(newBlocksByPage)) {
          const idx = blocks.findIndex((b) => b.id === blockId)
          if (idx !== -1) {
            const updated = { ...blocks[idx], bboxJson: bbox }
            if (polygon !== undefined) {
              updated.polygonJson = polygon
            }
            updated.geometryRev += 1
            const newBlocks = [...blocks]
            newBlocks[idx] = updated
            newBlocksByPage[Number(pageNum)] = newBlocks
            break
          }
        }

        const newDirty = new Set(state.dirtyBlockIds)
        newDirty.add(blockId)

        return { blocksByPage: newBlocksByPage, dirtyBlockIds: newDirty }
      })
    },

    updateBlockInStore: (block: Block) => {
      set((state) => {
        const pageBlocks = state.blocksByPage[block.pageNumber] ?? []
        const idx = pageBlocks.findIndex((b) => b.id === block.id)
        if (idx === -1) return state

        const newBlocks = [...pageBlocks]
        newBlocks[idx] = block
        return {
          blocksByPage: {
            ...state.blocksByPage,
            [block.pageNumber]: newBlocks,
          },
        }
      })
    },

    softDeleteBlock: async (blockId: string) => {
      await blocksApi.deleteBlock(blockId)
      set((state) => {
        const newBlocksByPage = { ...state.blocksByPage }
        for (const [pageNum, blocks] of Object.entries(newBlocksByPage)) {
          const idx = blocks.findIndex((b) => b.id === blockId)
          if (idx !== -1) {
            newBlocksByPage[Number(pageNum)] = blocks.filter((b) => b.id !== blockId)
            break
          }
        }
        const newSelected = new Set(state.selectedIds)
        newSelected.delete(blockId)
        return { blocksByPage: newBlocksByPage, selectedIds: newSelected }
      })
    },

    restoreBlock: async (blockId: string) => {
      const block = await blocksApi.restoreBlock(blockId)
      set((state) => {
        const pageBlocks = state.blocksByPage[block.pageNumber] ?? []
        return {
          blocksByPage: {
            ...state.blocksByPage,
            [block.pageNumber]: [...pageBlocks, block],
          },
        }
      })
    },

    softDeleteSelected: async () => {
      const { selectedIds } = get()
      const ids = Array.from(selectedIds)
      for (const id of ids) {
        await get().softDeleteBlock(id)
      }
    },

    // ────────────────────────────────
    // Selection actions
    // ────────────────────────────────

    selectBlock: (id: string) => {
      set({ selectedIds: new Set([id]) })
    },

    toggleSelect: (id: string) => {
      set((state) => {
        const newSelected = new Set(state.selectedIds)
        if (newSelected.has(id)) {
          newSelected.delete(id)
        } else {
          newSelected.add(id)
        }
        return { selectedIds: newSelected }
      })
    },

    selectInRect: (pageNumber: number, rect: BlockCoords) => {
      const { blocksByPage } = get()
      const blocks = blocksByPage[pageNumber] ?? []
      const ids = blocks
        .filter((b) => rectsIntersect(b.bboxJson, rect))
        .map((b) => b.id)
      set({ selectedIds: new Set(ids) })
    },

    clearSelection: () => set({ selectedIds: new Set() }),

    setHoveredId: (id: string | null) => set({ hoveredId: id }),

    // ────────────────────────────────
    // Interaction actions
    // ────────────────────────────────

    transitionTo: (newState: InteractionState) => {
      const { interactionState } = get()
      // Правило state machine: active → только IDLE, IDLE → любое
      if (newState === InteractionState.IDLE) {
        set({ interactionState: InteractionState.IDLE })
        return
      }
      if (interactionState !== InteractionState.IDLE) {
        // Нельзя перейти из active в другое active
        return
      }
      set({ interactionState: newState })
    },

    setActiveBlockKind: (kind: BlockKind) => set({ activeBlockKind: kind }),

    toggleShapeType: () => {
      set((state) => ({
        activeShapeType:
          state.activeShapeType === ShapeType.RECTANGLE
            ? ShapeType.POLYGON
            : ShapeType.RECTANGLE,
      }))
    },

    setDrawingPoints: (points: PagePoint[]) => set({ drawingPoints: points }),
    addDrawingPoint: (point: PagePoint) =>
      set((state) => ({ drawingPoints: [...state.drawingPoints, point] })),
    setDrawingOrigin: (point: PagePoint | null) => set({ drawingOrigin: point }),
    setDrawingCurrent: (point: PagePoint | null) => set({ drawingCurrent: point }),
    setResizeHandle: (handle: ResizeHandle | null) => set({ resizeHandle: handle }),
    setDragOrigin: (point: PagePoint | null) => set({ dragOrigin: point }),
    setDragVertexIdx: (idx: number | null) => set({ dragVertexIdx: idx }),
    setDragEdgeIdx: (idx: number | null) => set({ dragEdgeIdx: idx }),
    setOriginalBbox: (bbox: BlockCoords | null) => set({ originalBbox: bbox }),
    setOriginalPolygonPoints: (points: [number, number][] | null) =>
      set({ originalPolygonPoints: points }),

    resetInteraction: () => {
      set({
        interactionState: InteractionState.IDLE,
        drawingPoints: [],
        drawingOrigin: null,
        drawingCurrent: null,
        resizeHandle: null,
        dragOrigin: null,
        dragVertexIdx: null,
        dragEdgeIdx: null,
        originalBbox: null,
        originalPolygonPoints: null,
      })
    },

    // ────────────────────────────────
    // Viewport actions
    // ────────────────────────────────

    setZoom: (zoom: number) => set({ zoom: Math.max(0.1, Math.min(5, zoom)) }),
    zoomIn: () => set((state) => ({ zoom: Math.min(5, state.zoom * 1.15) })),
    zoomOut: () => set((state) => ({ zoom: Math.max(0.1, state.zoom / 1.15) })),

    // ────────────────────────────────
    // Inspector actions
    // ────────────────────────────────

    openInspector: async (blockId: string) => {
      set({ inspectedBlockId: blockId, inspectorLoading: true })
      try {
        const [detail, attempts] = await Promise.all([
          blocksApi.getBlockDetail(blockId),
          blocksApi.getBlockAttempts(blockId),
        ])
        set({
          inspectedDetail: detail,
          inspectedAttempts: attempts,
          inspectorLoading: false,
        })
      } catch {
        set({ inspectorLoading: false })
      }
    },

    closeInspector: () => {
      set({
        inspectedBlockId: null,
        inspectedDetail: null,
        inspectedAttempts: [],
        inspectorLoading: false,
      })
    },

    refreshInspector: async () => {
      const { inspectedBlockId } = get()
      if (!inspectedBlockId) return
      await get().openInspector(inspectedBlockId)
    },

    editBlockContent: async (
      blockId: string,
      text: string,
      structuredJson?: Record<string, unknown>,
    ) => {
      const updated = await blocksApi.editBlockContent(blockId, {
        currentText: text,
        currentStructuredJson: structuredJson,
      })
      get().updateBlockInStore(updated)
      // Обновить inspector если открыт этот блок
      if (get().inspectedBlockId === blockId) {
        await get().refreshInspector()
      }
    },

    toggleManualLock: async (blockId: string, lock: boolean) => {
      const updated = await blocksApi.toggleBlockLock(blockId, lock)
      get().updateBlockInStore(updated)
      if (get().inspectedBlockId === blockId) {
        await get().refreshInspector()
      }
    },

    rerunBlock: async (blockId: string, force?: boolean) => {
      await blocksApi.rerunBlock(blockId, force)
      if (get().inspectedBlockId === blockId) {
        await get().refreshInspector()
      }
    },

    acceptAttempt: async (blockId: string, attemptId: string) => {
      const updated = await blocksApi.acceptAttempt(blockId, attemptId)
      get().updateBlockInStore(updated)
      if (get().inspectedBlockId === blockId) {
        await get().refreshInspector()
      }
    },

    // ────────────────────────────────
    // Recognition actions
    // ────────────────────────────────

    startRecognition: async (runMode: 'smart' | 'full') => {
      const { documentId } = get()
      if (!documentId) return

      const { run } = await recognitionApi.startRecognition(documentId, runMode)
      set({ activeRunId: run.id, runProgress: run })
    },

    refreshRunProgress: async () => {
      const { activeRunId } = get()
      if (!activeRunId) return

      const run = await recognitionApi.getRunStatus(activeRunId)
      set({ runProgress: run })

      // Очистить при завершении
      if (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') {
        set({ activeRunId: null })
      }
    },

    // ────────────────────────────────
    // Autosave actions
    // ────────────────────────────────

    markDirty: (blockId: string) => {
      set((state) => {
        const newDirty = new Set(state.dirtyBlockIds)
        newDirty.add(blockId)
        return { dirtyBlockIds: newDirty }
      })
    },

    clearDirty: (blockId: string) => {
      set((state) => {
        const newDirty = new Set(state.dirtyBlockIds)
        newDirty.delete(blockId)
        return { dirtyBlockIds: newDirty }
      })
    },

    setSaving: (saving: boolean) => set({ saving }),
  })),
)
