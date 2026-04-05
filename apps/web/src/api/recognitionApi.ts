/**
 * API клиент для recognition runs и dirty detection.
 * Endpoints: /documents/{id}/recognition/*, /recognition/runs/{id}
 */

import type { DirtySummary, RecognitionRun } from '../types/block'
import { apiFetch } from './client'

/** Ответ API для recognition run — snake_case */
interface RunApiResponse {
  id: string
  document_id: string
  initiated_by: string | null
  run_mode: string
  status: string
  total_blocks: number
  dirty_blocks: number
  processed_blocks: number
  recognized_blocks: number
  failed_blocks: number
  manual_review_blocks: number
  started_at: string | null
  finished_at: string | null
  created_at: string
}

function mapRun(raw: RunApiResponse): RecognitionRun {
  return {
    id: raw.id,
    documentId: raw.document_id,
    initiatedBy: raw.initiated_by,
    runMode: raw.run_mode as RecognitionRun['runMode'],
    status: raw.status,
    totalBlocks: raw.total_blocks,
    dirtyBlocks: raw.dirty_blocks,
    processedBlocks: raw.processed_blocks,
    recognizedBlocks: raw.recognized_blocks,
    failedBlocks: raw.failed_blocks,
    manualReviewBlocks: raw.manual_review_blocks,
    startedAt: raw.started_at,
    finishedAt: raw.finished_at,
    createdAt: raw.created_at,
  }
}

/** Запуск recognition run */
export async function startRecognition(
  documentId: string,
  runMode: 'smart' | 'full' | 'block_rerun',
  blockIds?: string[],
): Promise<{ run: RecognitionRun; targetBlockIds: string[] }> {
  const data = await apiFetch<{
    run: RunApiResponse
    target_block_ids: string[]
  }>(`/documents/${documentId}/recognition/start`, {
    method: 'POST',
    body: JSON.stringify({
      run_mode: runMode,
      block_ids: blockIds ?? null,
    }),
  })
  return {
    run: mapRun(data.run),
    targetBlockIds: data.target_block_ids,
  }
}

/** Сводка dirty-блоков документа */
export async function getDirtySummary(
  documentId: string,
): Promise<DirtySummary> {
  const data = await apiFetch<{
    total: number
    dirty_count: number
    locked_count: number
    dirty_block_ids: string[]
  }>(`/documents/${documentId}/recognition/dirty`)
  return {
    total: data.total,
    dirtyCount: data.dirty_count,
    lockedCount: data.locked_count,
    dirtyBlockIds: data.dirty_block_ids,
  }
}

/** Список recognition runs документа */
export async function getRecognitionRuns(
  documentId: string,
): Promise<RecognitionRun[]> {
  const data = await apiFetch<{ runs: RunApiResponse[] }>(
    `/documents/${documentId}/recognition/runs`,
  )
  return data.runs.map(mapRun)
}

/** Статус конкретного recognition run */
export async function getRunStatus(runId: string): Promise<RecognitionRun> {
  const raw = await apiFetch<RunApiResponse>(`/recognition/runs/${runId}`)
  return mapRun(raw)
}
