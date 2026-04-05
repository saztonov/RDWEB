/**
 * API клиент для работы с документами.
 * Используется DocumentEditorPage для загрузки метаданных документа.
 */

import type { PageMeta } from '../types/editor'
import { apiFetch } from './client'

/** Ответ API для документа */
interface DocumentDetailApiResponse {
  id: string
  workspace_id: string
  title: string
  status: string
  page_count: number
  pages: Array<{
    id: string
    page_number: number
    width: number
    height: number
    rotation: number
  }>
  blocks_count: number
  recognized_count: number
  failed_count: number
  created_at: string
  updated_at: string
}

export interface DocumentDetail {
  id: string
  workspaceId: string
  title: string
  status: string
  pageCount: number
  pages: PageMeta[]
  blocksCount: number
  recognizedCount: number
  failedCount: number
}

/** Получить документ с pages */
export async function getDocument(documentId: string): Promise<DocumentDetail> {
  const raw = await apiFetch<DocumentDetailApiResponse>(`/documents/${documentId}`)
  return {
    id: raw.id,
    workspaceId: raw.workspace_id,
    title: raw.title,
    status: raw.status,
    pageCount: raw.page_count,
    pages: raw.pages.map((p) => ({
      id: p.id,
      pageNumber: p.page_number,
      width: p.width,
      height: p.height,
      rotation: p.rotation,
    })),
    blocksCount: raw.blocks_count,
    recognizedCount: raw.recognized_count,
    failedCount: raw.failed_count,
  }
}
