/**
 * Типы блоков документа.
 * Соответствуют БД schema: block_kind, shape_type, blocks table.
 * Block kinds: ТОЛЬКО text, stamp, image — БЕЗ table.
 */

export enum BlockKind {
  TEXT = 'text',
  STAMP = 'stamp',
  IMAGE = 'image',
}

export enum ShapeType {
  RECTANGLE = 'rect',
  POLYGON = 'polygon',
}

/** Bounding box блока в координатах страницы (px) */
export interface BlockCoords {
  x: number
  y: number
  width: number
  height: number
}

/** Статусы блока — соответствуют CHECK constraint в БД */
export type BlockStatus =
  | 'pending'
  | 'queued'
  | 'processing'
  | 'recognized'
  | 'failed'
  | 'manual_review'
  | 'skipped'

/** Блок документа — соответствует строке таблицы blocks */
export interface Block {
  id: string
  documentId: string
  pageNumber: number
  blockKind: BlockKind
  shapeType: ShapeType
  bboxJson: BlockCoords
  polygonJson: [number, number][] | null
  readingOrder: number | null
  geometryRev: number
  contentRev: number
  manualLock: boolean
  routeSourceId: string | null
  routeModelName: string | null
  promptTemplateId: string | null
  currentText: string | null
  currentStructuredJson: Record<string, unknown> | null
  currentRenderHtml: string | null
  currentAttemptId: string | null
  currentStatus: BlockStatus
  lastRecognitionSignature: string | null
  deletedAt: string | null
  createdAt: string
  updatedAt: string
}

/** Payload для создания блока (POST) */
export interface CreateBlockPayload {
  blockKind: BlockKind
  shapeType: ShapeType
  pageNumber: number
  bboxJson: BlockCoords
  polygonJson?: [number, number][]
}

/** Payload для обновления блока (PATCH) */
export interface UpdateBlockPayload {
  bboxJson?: BlockCoords
  polygonJson?: [number, number][] | null
  shapeType?: ShapeType
  routeSourceId?: string | null
  routeModelName?: string | null
  promptTemplateId?: string | null
}

/** Payload для ручной правки текста блока */
export interface ManualEditPayload {
  currentText?: string
  currentStructuredJson?: Record<string, unknown>
}

/** Payload для принятия candidate attempt */
export interface AcceptAttemptPayload {
  attemptId: string
}

/** Попытка распознавания блока (recognition_attempts row) */
export interface RecognitionAttempt {
  id: string
  runId: string | null
  blockId: string
  geometryRev: number | null
  sourceId: string | null
  modelName: string | null
  promptTemplateId: string | null
  attemptNo: number | null
  fallbackNo: number
  status: string
  normalizedText: string | null
  structuredJson: Record<string, unknown> | null
  renderHtml: string | null
  qualityFlagsJson: Record<string, unknown> | null
  errorCode: string | null
  errorMessage: string | null
  selectedAsCurrent: boolean
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
}

/** Сводка dirty-блоков для smart rerun */
export interface DirtySummary {
  total: number
  dirtyCount: number
  lockedCount: number
  dirtyBlockIds: string[]
}

/** Recognition run */
export interface RecognitionRun {
  id: string
  documentId: string
  initiatedBy: string | null
  runMode: 'smart' | 'full' | 'block_rerun'
  status: string
  totalBlocks: number
  dirtyBlocks: number
  processedBlocks: number
  recognizedBlocks: number
  failedBlocks: number
  manualReviewBlocks: number
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
}

/** Provenance текущего attempt (из /blocks/{id}/detail) */
export interface AttemptProvenance {
  id: string
  sourceId: string | null
  sourceName?: string
  modelName: string | null
  promptTemplateId: string | null
  promptKey?: string
  promptVersion?: number
  attemptNo: number | null
  fallbackNo: number
  status: string
  startedAt: string | null
  finishedAt: string | null
}

/** Полная деталь блока (из /blocks/{id}/detail) */
export interface BlockDetail {
  block: Block
  currentAttempt: AttemptProvenance | null
  attemptsCount: number
  pendingCandidate: {
    id: string
    normalizedText: string | null
    modelName: string | null
    createdAt: string
  } | null
}

/** Цвета блоков по типу (из legacy page_viewer_blocks.py) */
export const BLOCK_COLORS: Record<BlockKind, string> = {
  [BlockKind.TEXT]: 'rgb(0, 255, 0)',
  [BlockKind.STAMP]: 'rgb(30, 144, 255)',
  [BlockKind.IMAGE]: 'rgb(255, 140, 0)',
}

/** Цвет выделения */
export const SELECTION_COLOR = 'rgb(0, 120, 255)'

/** Минимальный размер блока (px в координатах страницы) */
export const MIN_BLOCK_SIZE = 10

/** Минимальное количество вершин для polygon */
export const MIN_POLYGON_VERTICES = 3
