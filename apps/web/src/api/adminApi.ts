/**
 * API клиент для admin panel endpoints.
 */

import { apiFetch } from './client'

// ── Типы ──

export interface ServiceHealth {
  serviceName: string
  status: string
  responseTimeMs: number | null
  detailsJson: Record<string, unknown> | null
  checkedAt: string
}

export interface QueueSummary {
  size: number
  maxCapacity: number
  canAccept: boolean
}

export interface WorkerHeartbeat {
  workerName: string
  queueName: string | null
  host: string | null
  pid: number | null
  memoryMb: number | null
  activeTasks: number
  lastSeenAt: string
}

export interface WorkerSummary {
  activeCount: number
  workers: WorkerHeartbeat[]
}

export interface AdminOverview {
  services: ServiceHealth[]
  overall: string
  queue: QueueSummary | null
  workers: WorkerSummary | null
}

export interface AdminOcrSource {
  id: string
  sourceType: string
  name: string
  baseUrl: string | null
  deploymentMode: string | null
  isEnabled: boolean
  concurrencyLimit: number
  timeoutSec: number
  healthStatus: string
  lastHealthAt: string | null
  capabilitiesJson: Record<string, unknown>
  lastError: string | null
  lastResponseTimeMs: number | null
  cachedModelsCount: number
}

export interface AdminOcrSourceDetail extends AdminOcrSource {
  recentHealthChecks: ServiceHealth[]
  cachedModels: Record<string, unknown>[]
}

export interface AdminRun {
  id: string
  documentId: string
  documentTitle: string | null
  initiatedBy: string | null
  runMode: string
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

export interface AdminRunBlock {
  blockId: string
  pageNumber: number
  blockKind: string
  currentStatus: string
  attemptCount: number
  lastError: string | null
}

export interface AdminRunDetail extends AdminRun {
  blocks: AdminRunBlock[]
}

export interface BlockIncident {
  attemptId: string
  runId: string | null
  blockId: string
  documentId: string
  documentTitle: string | null
  pageNumber: number
  blockKind: string
  sourceId: string | null
  sourceName: string | null
  modelName: string | null
  promptTemplateId: string | null
  attemptNo: number
  fallbackNo: number
  errorCode: string | null
  errorMessage: string | null
  status: string
  createdAt: string
}

export interface SystemEvent {
  id: string
  eventType: string
  severity: string
  sourceService: string | null
  payloadJson: Record<string, unknown>
  createdAt: string
}

export interface PaginatedMeta {
  total: number
  limit: number
  offset: number
}

// ── snake_case → camelCase конверсия ──

function toCamel(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(obj)) {
    const camelKey = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase())
    if (Array.isArray(value)) {
      result[camelKey] = value.map((item) =>
        typeof item === 'object' && item !== null ? toCamel(item as Record<string, unknown>) : item,
      )
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      // Не конвертируем payload_json / details_json / capabilities_json — оставляем как есть
      if (key.endsWith('_json')) {
        result[camelKey] = value
      } else {
        result[camelKey] = toCamel(value as Record<string, unknown>)
      }
    } else {
      result[camelKey] = value
    }
  }
  return result
}

function convertResponse<T>(data: unknown): T {
  if (Array.isArray(data)) {
    return data.map((item) =>
      typeof item === 'object' && item !== null ? toCamel(item as Record<string, unknown>) : item,
    ) as T
  }
  if (typeof data === 'object' && data !== null) {
    return toCamel(data as Record<string, unknown>) as T
  }
  return data as T
}

// ── API Функции ──

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const raw = await apiFetch<unknown>('/admin/health')
  return convertResponse<AdminOverview>(raw)
}

export async function fetchAdminSources(): Promise<{ sources: AdminOcrSource[] }> {
  const raw = await apiFetch<unknown>('/admin/ocr/sources')
  return convertResponse<{ sources: AdminOcrSource[] }>(raw)
}

export async function fetchAdminSourceDetail(sourceId: string): Promise<AdminOcrSourceDetail> {
  const raw = await apiFetch<unknown>(`/admin/ocr/sources/${sourceId}`)
  return convertResponse<AdminOcrSourceDetail>(raw)
}

export async function triggerSourceHealthcheck(sourceId: string): Promise<unknown> {
  return apiFetch(`/admin/ocr/sources/${sourceId}/healthcheck`, { method: 'POST' })
}

export interface RunsFilters {
  status?: string
  documentId?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}

export async function fetchAdminRuns(
  filters: RunsFilters = {},
): Promise<{ runs: AdminRun[]; meta: PaginatedMeta }> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.documentId) params.set('document_id', filters.documentId)
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  const qs = params.toString()
  const raw = await apiFetch<unknown>(`/admin/runs${qs ? `?${qs}` : ''}`)
  return convertResponse<{ runs: AdminRun[]; meta: PaginatedMeta }>(raw)
}

export async function fetchAdminRunDetail(runId: string): Promise<AdminRunDetail> {
  const raw = await apiFetch<unknown>(`/admin/runs/${runId}`)
  return convertResponse<AdminRunDetail>(raw)
}

export interface IncidentsFilters {
  errorCode?: string
  sourceId?: string
  documentId?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}

export async function fetchAdminIncidents(
  filters: IncidentsFilters = {},
): Promise<{ incidents: BlockIncident[]; meta: PaginatedMeta }> {
  const params = new URLSearchParams()
  if (filters.errorCode) params.set('error_code', filters.errorCode)
  if (filters.sourceId) params.set('source_id', filters.sourceId)
  if (filters.documentId) params.set('document_id', filters.documentId)
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  const qs = params.toString()
  const raw = await apiFetch<unknown>(`/admin/incidents${qs ? `?${qs}` : ''}`)
  return convertResponse<{ incidents: BlockIncident[]; meta: PaginatedMeta }>(raw)
}

export interface EventsFilters {
  severity?: string
  sourceService?: string
  eventType?: string
  dateFrom?: string
  dateTo?: string
  runId?: string
  documentId?: string
  blockId?: string
  limit?: number
  offset?: number
}

export async function fetchAdminEvents(
  filters: EventsFilters = {},
): Promise<{ events: SystemEvent[]; meta: PaginatedMeta }> {
  const params = new URLSearchParams()
  if (filters.severity) params.set('severity', filters.severity)
  if (filters.sourceService) params.set('source_service', filters.sourceService)
  if (filters.eventType) params.set('event_type', filters.eventType)
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  if (filters.runId) params.set('run_id', filters.runId)
  if (filters.documentId) params.set('document_id', filters.documentId)
  if (filters.blockId) params.set('block_id', filters.blockId)
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  const qs = params.toString()
  const raw = await apiFetch<unknown>(`/admin/events${qs ? `?${qs}` : ''}`)
  return convertResponse<{ events: SystemEvent[]; meta: PaginatedMeta }>(raw)
}

// ── SSE ──

export function createAdminSSE(): EventSource {
  const token = localStorage.getItem('sb-auth-token')
  let accessToken = ''
  if (token) {
    try {
      const parsed = JSON.parse(token)
      accessToken = parsed.access_token ?? ''
    } catch {
      // ignore
    }
  }

  // EventSource не поддерживает заголовки — передаём token через query param
  // Backend должен принимать ?token= как альтернативу Authorization header
  return new EventSource(`/api/admin/sse?token=${encodeURIComponent(accessToken)}`)
}
