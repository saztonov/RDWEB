/**
 * API клиент для работы с документами.
 *
 * Endpoints: список, детали, upload (presigned URL), finalize, download URL.
 */

import type { PageMeta } from '../types/editor'
import { apiFetch } from './client'

// ─── Типы ответов API ────────────────────────────────────────────────────────

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

interface DocumentApiResponse {
  id: string
  workspace_id: string
  title: string
  status: string
  page_count: number
  created_by: string | null
  created_at: string
  updated_at: string
}

interface DocumentListApiResponse {
  documents: DocumentApiResponse[]
  meta: { total: number; limit: number; offset: number }
}

interface UploadUrlApiResponse {
  document_id: string
  upload_url: string
  r2_key: string
}

interface FinalizeApiResponse {
  document_id: string
  status: string
  page_count: number
}

interface DownloadUrlApiResponse {
  download_url: string
  expires_in: number
}

// ─── Публичные типы ──────────────────────────────────────────────────────────

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

export interface DocumentListItem {
  id: string
  workspaceId: string
  title: string
  status: string
  pageCount: number
  createdBy: string | null
  createdAt: string
  updatedAt: string
}

export interface DocumentListResult {
  documents: DocumentListItem[]
  total: number
}

export interface UploadUrlResult {
  documentId: string
  uploadUrl: string
  r2Key: string
}

export interface FinalizeResult {
  documentId: string
  status: string
  pageCount: number
}

// ─── API функции ─────────────────────────────────────────────────────────────

/** Получить список документов workspace */
export async function listDocuments(
  workspaceId: string,
  limit = 50,
  offset = 0,
): Promise<DocumentListResult> {
  const raw = await apiFetch<DocumentListApiResponse>(
    `/documents/?workspace_id=${encodeURIComponent(workspaceId)}&limit=${limit}&offset=${offset}`,
  )
  return {
    documents: raw.documents.map((d) => ({
      id: d.id,
      workspaceId: d.workspace_id,
      title: d.title,
      status: d.status,
      pageCount: d.page_count,
      createdBy: d.created_by,
      createdAt: d.created_at,
      updatedAt: d.updated_at,
    })),
    total: raw.meta.total,
  }
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

/** Получить presigned PUT URL для загрузки PDF в R2 */
export async function createUploadUrl(
  workspaceId: string,
  title: string,
): Promise<UploadUrlResult> {
  const raw = await apiFetch<UploadUrlApiResponse>('/documents/upload-url', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, title }),
  })
  return {
    documentId: raw.document_id,
    uploadUrl: raw.upload_url,
    r2Key: raw.r2_key,
  }
}

/** Финализировать загрузку PDF — извлечь pages metadata */
export async function finalizeUpload(documentId: string): Promise<FinalizeResult> {
  const raw = await apiFetch<FinalizeApiResponse>('/documents/finalize', {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId }),
  })
  return {
    documentId: raw.document_id,
    status: raw.status,
    pageCount: raw.page_count,
  }
}

/** Получить presigned GET URL для скачивания оригинального PDF из R2 */
export async function getDownloadUrl(documentId: string): Promise<string> {
  const raw = await apiFetch<DownloadUrlApiResponse>(`/documents/${documentId}/download-url`)
  return raw.download_url
}

/** Скачать export документа (HTML или Markdown) */
export async function exportDocument(
  documentId: string,
  format: 'html' | 'markdown',
  includeCropLinks = true,
  includeStampInfo = true,
): Promise<void> {
  const token = localStorage.getItem('sb-auth-token')
  let authHeader = ''
  if (token) {
    try {
      const parsed = JSON.parse(token)
      if (parsed.access_token) authHeader = `Bearer ${parsed.access_token}`
    } catch { /* ignore */ }
  }

  const response = await fetch(`/api/documents/${documentId}/exports`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body: JSON.stringify({
      output_format: format,
      include_crop_links: includeCropLinks,
      include_stamp_info: includeStampInfo,
    }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Ошибка экспорта: ${response.status}`)
  }

  // Скачать как файл
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?(.+?)"?$/)
  const fileName = match?.[1] || `export.${format === 'html' ? 'html' : 'md'}`

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}
