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
  currentStatus: BlockStatus
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
