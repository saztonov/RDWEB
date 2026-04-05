/**
 * API клиент для работы с блоками документа.
 * Endpoints: GET/POST /documents/{id}/blocks, PATCH/DELETE/restore /blocks/{id}
 */

import type { Block, CreateBlockPayload, UpdateBlockPayload } from '../types/block'
import { apiFetch } from './client'

/** Ответ API — snake_case из backend */
interface BlockApiResponse {
  id: string
  document_id: string
  page_number: number
  block_kind: string
  shape_type: string
  bbox_json: { x: number; y: number; width: number; height: number }
  polygon_json: [number, number][] | null
  reading_order: number | null
  geometry_rev: number
  content_rev: number
  manual_lock: boolean
  route_source_id: string | null
  route_model_name: string | null
  prompt_template_id: string | null
  current_text: string | null
  current_status: string
  deleted_at: string | null
  created_at: string
  updated_at: string
}

/** Конвертация snake_case → camelCase */
function mapBlock(raw: BlockApiResponse): Block {
  return {
    id: raw.id,
    documentId: raw.document_id,
    pageNumber: raw.page_number,
    blockKind: raw.block_kind as Block['blockKind'],
    shapeType: raw.shape_type as Block['shapeType'],
    bboxJson: raw.bbox_json,
    polygonJson: raw.polygon_json,
    readingOrder: raw.reading_order,
    geometryRev: raw.geometry_rev,
    contentRev: raw.content_rev,
    manualLock: raw.manual_lock,
    routeSourceId: raw.route_source_id,
    routeModelName: raw.route_model_name,
    promptTemplateId: raw.prompt_template_id,
    currentText: raw.current_text,
    currentStatus: raw.current_status as Block['currentStatus'],
    deletedAt: raw.deleted_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** Получить блоки страницы документа */
export async function getBlocks(
  documentId: string,
  page: number,
  includeDeleted = false,
): Promise<Block[]> {
  const params = new URLSearchParams({ page: String(page) })
  if (includeDeleted) params.set('include_deleted', 'true')
  const data = await apiFetch<{ blocks: BlockApiResponse[] }>(
    `/documents/${documentId}/blocks?${params}`,
  )
  return data.blocks.map(mapBlock)
}

/** Создать блок */
export async function createBlock(
  documentId: string,
  payload: CreateBlockPayload,
): Promise<Block> {
  const raw = await apiFetch<BlockApiResponse>(
    `/documents/${documentId}/blocks`,
    {
      method: 'POST',
      body: JSON.stringify({
        block_kind: payload.blockKind,
        shape_type: payload.shapeType,
        page_number: payload.pageNumber,
        bbox_json: payload.bboxJson,
        polygon_json: payload.polygonJson ?? null,
      }),
    },
  )
  return mapBlock(raw)
}

/** Обновить блок (geometry, route, prompt) */
export async function patchBlock(
  blockId: string,
  payload: UpdateBlockPayload,
): Promise<Block> {
  // Конвертация в snake_case
  const body: Record<string, unknown> = {}
  if (payload.bboxJson !== undefined) body.bbox_json = payload.bboxJson
  if (payload.polygonJson !== undefined) body.polygon_json = payload.polygonJson
  if (payload.shapeType !== undefined) body.shape_type = payload.shapeType
  if (payload.routeSourceId !== undefined) body.route_source_id = payload.routeSourceId
  if (payload.routeModelName !== undefined) body.route_model_name = payload.routeModelName
  if (payload.promptTemplateId !== undefined) body.prompt_template_id = payload.promptTemplateId

  const raw = await apiFetch<BlockApiResponse>(`/blocks/${blockId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return mapBlock(raw)
}

/** Soft delete блока */
export async function deleteBlock(blockId: string): Promise<void> {
  await apiFetch(`/blocks/${blockId}`, { method: 'DELETE' })
}

/** Восстановить soft-deleted блок */
export async function restoreBlock(blockId: string): Promise<Block> {
  const raw = await apiFetch<BlockApiResponse>(`/blocks/${blockId}/restore`, {
    method: 'POST',
  })
  return mapBlock(raw)
}
