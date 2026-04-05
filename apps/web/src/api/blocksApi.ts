/**
 * API клиент для работы с блоками документа.
 * Endpoints: GET/POST /documents/{id}/blocks, PATCH/DELETE/restore /blocks/{id}
 */

import type {
  Block,
  BlockDetail,
  CreateBlockPayload,
  ManualEditPayload,
  RecognitionAttempt,
  UpdateBlockPayload,
} from '../types/block'
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
  current_structured_json: Record<string, unknown> | null
  current_render_html: string | null
  current_attempt_id: string | null
  current_status: string
  last_recognition_signature: string | null
  deleted_at: string | null
  created_at: string
  updated_at: string
}

/** Ответ API для recognition_attempts — snake_case */
interface AttemptApiResponse {
  id: string
  run_id: string | null
  block_id: string
  geometry_rev: number | null
  source_id: string | null
  model_name: string | null
  prompt_template_id: string | null
  attempt_no: number | null
  fallback_no: number
  status: string
  normalized_text: string | null
  structured_json: Record<string, unknown> | null
  render_html: string | null
  quality_flags_json: Record<string, unknown> | null
  error_code: string | null
  error_message: string | null
  selected_as_current: boolean
  started_at: string | null
  finished_at: string | null
  created_at: string
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
    currentStructuredJson: raw.current_structured_json,
    currentRenderHtml: raw.current_render_html,
    currentAttemptId: raw.current_attempt_id,
    currentStatus: raw.current_status as Block['currentStatus'],
    lastRecognitionSignature: raw.last_recognition_signature,
    deletedAt: raw.deleted_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  }
}

/** Конвертация attempt snake_case → camelCase */
function mapAttempt(raw: AttemptApiResponse): RecognitionAttempt {
  return {
    id: raw.id,
    runId: raw.run_id,
    blockId: raw.block_id,
    geometryRev: raw.geometry_rev,
    sourceId: raw.source_id,
    modelName: raw.model_name,
    promptTemplateId: raw.prompt_template_id,
    attemptNo: raw.attempt_no,
    fallbackNo: raw.fallback_no,
    status: raw.status,
    normalizedText: raw.normalized_text,
    structuredJson: raw.structured_json,
    renderHtml: raw.render_html,
    qualityFlagsJson: raw.quality_flags_json,
    errorCode: raw.error_code,
    errorMessage: raw.error_message,
    selectedAsCurrent: raw.selected_as_current,
    startedAt: raw.started_at,
    finishedAt: raw.finished_at,
    createdAt: raw.created_at,
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

/** Ручная правка текста/structured_json блока */
export async function editBlockContent(
  blockId: string,
  payload: ManualEditPayload,
): Promise<Block> {
  const body: Record<string, unknown> = {}
  if (payload.currentText !== undefined) body.current_text = payload.currentText
  if (payload.currentStructuredJson !== undefined)
    body.current_structured_json = payload.currentStructuredJson

  const raw = await apiFetch<BlockApiResponse>(`/blocks/${blockId}/content`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return mapBlock(raw)
}

/** Переключить manual_lock на блоке */
export async function toggleBlockLock(
  blockId: string,
  manualLock: boolean,
): Promise<Block> {
  const raw = await apiFetch<BlockApiResponse>(`/blocks/${blockId}/lock`, {
    method: 'PATCH',
    body: JSON.stringify({ manual_lock: manualLock }),
  })
  return mapBlock(raw)
}

/** Перезапуск распознавания одного блока */
export async function rerunBlock(
  blockId: string,
  force = false,
): Promise<{ ok: boolean; run_id: string; target_block_ids: string[] }> {
  return apiFetch(`/blocks/${blockId}/rerun`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })
}

/** Список recognition_attempts блока */
export async function getBlockAttempts(
  blockId: string,
): Promise<RecognitionAttempt[]> {
  const data = await apiFetch<{ attempts: AttemptApiResponse[] }>(
    `/blocks/${blockId}/attempts`,
  )
  return data.attempts.map(mapAttempt)
}

/** Принять candidate attempt как текущий результат */
export async function acceptAttempt(
  blockId: string,
  attemptId: string,
): Promise<Block> {
  const raw = await apiFetch<BlockApiResponse>(
    `/blocks/${blockId}/accept-attempt`,
    {
      method: 'POST',
      body: JSON.stringify({ attempt_id: attemptId }),
    },
  )
  return mapBlock(raw)
}

/** Полная информация о блоке с provenance */
export async function getBlockDetail(blockId: string): Promise<BlockDetail> {
  const data = await apiFetch<{
    block: BlockApiResponse
    current_attempt: Record<string, unknown> | null
    attempts_count: number
    pending_candidate: {
      id: string
      normalized_text: string | null
      model_name: string | null
      created_at: string
    } | null
  }>(`/blocks/${blockId}/detail`)

  return {
    block: mapBlock(data.block),
    currentAttempt: data.current_attempt
      ? {
          id: data.current_attempt.id as string,
          sourceId: (data.current_attempt.source_id as string) ?? null,
          sourceName: (data.current_attempt.source_name as string) ?? undefined,
          modelName: (data.current_attempt.model_name as string) ?? null,
          promptTemplateId:
            (data.current_attempt.prompt_template_id as string) ?? null,
          promptKey: (data.current_attempt.prompt_key as string) ?? undefined,
          promptVersion:
            (data.current_attempt.prompt_version as number) ?? undefined,
          attemptNo: (data.current_attempt.attempt_no as number) ?? null,
          fallbackNo: (data.current_attempt.fallback_no as number) ?? 0,
          status: data.current_attempt.status as string,
          startedAt: (data.current_attempt.started_at as string) ?? null,
          finishedAt: (data.current_attempt.finished_at as string) ?? null,
        }
      : null,
    attemptsCount: data.attempts_count,
    pendingCandidate: data.pending_candidate
      ? {
          id: data.pending_candidate.id,
          normalizedText: data.pending_candidate.normalized_text,
          modelName: data.pending_candidate.model_name,
          createdAt: data.pending_candidate.created_at,
        }
      : null,
  }
}
