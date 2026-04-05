/**
 * API для управления prompt templates, profile routes и block prompt override.
 * Единственный источник промптов для OCR — таблица prompt_templates в БД.
 */

import { apiFetch } from './client'

// ── Типы ────────────────────────────────────────────────────────────────────

export interface PromptTemplate {
  id: string
  template_key: string
  version: number
  is_active: boolean
  document_profile_id: string | null
  block_kind: 'text' | 'stamp' | 'image'
  source_type: 'openrouter' | 'lmstudio'
  model_pattern: string | null
  system_template: string
  user_template: string
  output_schema_json: Record<string, unknown> | null
  parser_strategy: string
  notes: string | null
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface PaginatedMeta {
  total: number
  limit: number
  offset: number
}

export interface PromptTemplateListResponse {
  templates: PromptTemplate[]
  meta: PaginatedMeta
}

export interface PromptTemplateVersionsResponse {
  template_key: string
  versions: PromptTemplate[]
}

export interface ProfileRouteRef {
  id: string
  document_profile_name: string
  block_kind: string
}

export interface BlockRef {
  id: string
  document_title: string
  page_number: number
  block_kind: string
}

export interface PromptTemplateUsageResponse {
  profile_routes: ProfileRouteRef[]
  blocks: BlockRef[]
}

export interface ProfileRoute {
  id: string
  document_profile_id: string
  document_profile_name: string | null
  block_kind: string
  primary_source_id: string
  primary_model_name: string
  fallback_chain_json: unknown[]
  default_prompt_template_id: string | null
  created_at: string
  updated_at: string
}

export interface CreateTemplateRequest {
  template_key: string
  document_profile_id?: string | null
  block_kind: string
  source_type: string
  model_pattern?: string | null
  system_template: string
  user_template: string
  output_schema_json?: Record<string, unknown> | null
  parser_strategy?: string
  notes?: string | null
}

export interface NewVersionRequest {
  system_template: string
  user_template: string
  document_profile_id?: string | null
  block_kind?: string | null
  source_type?: string | null
  model_pattern?: string | null
  output_schema_json?: Record<string, unknown> | null
  parser_strategy?: string | null
  notes?: string | null
}

export interface TemplateFilters {
  document_profile_id?: string
  block_kind?: string
  source_type?: string
  model_pattern?: string
  is_active?: boolean
  limit?: number
  offset?: number
}

// ── Prompt Templates API ────────────────────────────────────────────────────

export function fetchTemplates(filters?: TemplateFilters) {
  const params = new URLSearchParams()
  if (filters) {
    if (filters.document_profile_id) params.set('document_profile_id', filters.document_profile_id)
    if (filters.block_kind) params.set('block_kind', filters.block_kind)
    if (filters.source_type) params.set('source_type', filters.source_type)
    if (filters.model_pattern) params.set('model_pattern', filters.model_pattern)
    if (filters.is_active !== undefined) params.set('is_active', String(filters.is_active))
    if (filters.limit) params.set('limit', String(filters.limit))
    if (filters.offset) params.set('offset', String(filters.offset))
  }
  const qs = params.toString()
  return apiFetch<PromptTemplateListResponse>(`/prompt-templates/${qs ? `?${qs}` : ''}`)
}

export function fetchTemplate(id: string) {
  return apiFetch<PromptTemplate>(`/prompt-templates/${id}`)
}

export function createTemplate(data: CreateTemplateRequest) {
  return apiFetch<PromptTemplate>('/prompt-templates/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function cloneTemplate(id: string, newKey?: string) {
  return apiFetch<PromptTemplate>(`/prompt-templates/${id}/clone`, {
    method: 'POST',
    body: JSON.stringify(newKey ? { new_template_key: newKey } : {}),
  })
}

export function createNewVersion(id: string, data: NewVersionRequest) {
  return apiFetch<PromptTemplate>(`/prompt-templates/${id}/new-version`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function activateTemplate(id: string) {
  return apiFetch<PromptTemplate>(`/prompt-templates/${id}/activate`, {
    method: 'PATCH',
  })
}

export function fetchVersions(templateKey: string) {
  return apiFetch<PromptTemplateVersionsResponse>(
    `/prompt-templates/by-key/${encodeURIComponent(templateKey)}/versions`,
  )
}

export function fetchUsage(id: string) {
  return apiFetch<PromptTemplateUsageResponse>(`/prompt-templates/${id}/usage`)
}

// ── Profile Routes API ──────────────────────────────────────────────────────

export function fetchProfileRoutes() {
  return apiFetch<{ routes: ProfileRoute[] }>('/profile-routes/')
}

export function updateProfileRoutePrompt(routeId: string, templateId: string) {
  return apiFetch<ProfileRoute>(`/profile-routes/${routeId}`, {
    method: 'PATCH',
    body: JSON.stringify({ default_prompt_template_id: templateId }),
  })
}

// ── Block Prompt Override API ───────────────────────────────────────────────

export function setBlockPromptOverride(blockId: string, templateId: string | null) {
  return apiFetch<{ ok: boolean }>(`/blocks/${blockId}/prompt-override`, {
    method: 'PATCH',
    body: JSON.stringify({ prompt_template_id: templateId }),
  })
}
