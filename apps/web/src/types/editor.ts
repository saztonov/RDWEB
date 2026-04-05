/**
 * Типы состояния редактора.
 * Interaction state machine адаптирована из legacy interaction_state.py.
 */

/** Состояния взаимодействия — взаимоисключающие (из legacy InteractionState enum) */
export enum InteractionState {
  IDLE = 'IDLE',
  DRAWING_RECT = 'DRAWING_RECT',
  DRAWING_POLYGON = 'DRAWING_POLYGON',
  SELECTING = 'SELECTING',
  MOVING_BLOCK = 'MOVING_BLOCK',
  RESIZING_BLOCK = 'RESIZING_BLOCK',
  DRAGGING_POLYGON_VERTEX = 'DRAGGING_POLYGON_VERTEX',
  DRAGGING_POLYGON_EDGE = 'DRAGGING_POLYGON_EDGE',
  PANNING = 'PANNING',
}

/** Метаданные страницы документа */
export interface PageMeta {
  id: string
  pageNumber: number
  width: number
  height: number
  rotation: number
}

/** Идентификатор resize handle (из legacy page_viewer_resize.py) */
export type ResizeHandle =
  | 'tl' | 'tr' | 'bl' | 'br'  // углы
  | 't' | 'b' | 'l' | 'r'       // середины сторон

/** Точка в координатах страницы */
export interface PagePoint {
  x: number
  y: number
}

/** Hit zone для handles (из legacy: 15px для resize, 12px для edge) */
export const HANDLE_HIT_ZONE = 15
export const EDGE_HIT_ZONE = 12
export const HANDLE_SIZE = 8
