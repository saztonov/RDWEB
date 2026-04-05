/**
 * Zustand store для admin panel.
 * Слайсы: overview, sources, runs, incidents, events.
 */

import { create } from 'zustand'
import type {
  AdminOverview,
  AdminOcrSource,
  AdminRun,
  AdminRunDetail,
  BlockIncident,
  SystemEvent,
  PaginatedMeta,
  RunsFilters,
  IncidentsFilters,
  EventsFilters,
} from '../api/adminApi'
import {
  fetchAdminOverview,
  fetchAdminSources,
  fetchAdminRuns,
  fetchAdminRunDetail,
  fetchAdminIncidents,
  fetchAdminEvents,
  triggerSourceHealthcheck,
} from '../api/adminApi'

interface AdminState {
  // Overview
  overview: AdminOverview | null
  overviewLoading: boolean
  overviewError: string | null

  // OCR Sources
  sources: AdminOcrSource[]
  sourcesLoading: boolean

  // Recognition Runs
  runs: AdminRun[]
  runsMeta: PaginatedMeta | null
  runsLoading: boolean
  runsFilters: RunsFilters
  selectedRun: AdminRunDetail | null
  selectedRunLoading: boolean

  // Block Incidents
  incidents: BlockIncident[]
  incidentsMeta: PaginatedMeta | null
  incidentsLoading: boolean
  incidentsFilters: IncidentsFilters

  // System Events
  events: SystemEvent[]
  eventsMeta: PaginatedMeta | null
  eventsLoading: boolean
  eventsFilters: EventsFilters

  // Actions
  loadOverview: () => Promise<void>
  loadSources: () => Promise<void>
  loadRuns: (filters?: RunsFilters) => Promise<void>
  loadRunDetail: (runId: string) => Promise<void>
  loadIncidents: (filters?: IncidentsFilters) => Promise<void>
  loadEvents: (filters?: EventsFilters) => Promise<void>
  triggerHealthcheck: (sourceId: string) => Promise<void>

  // SSE updates
  updateOverviewFromSSE: (data: unknown) => void
  prependEventFromSSE: (data: unknown) => void
}

export const useAdminStore = create<AdminState>((set, get) => ({
  // Initial state
  overview: null,
  overviewLoading: false,
  overviewError: null,

  sources: [],
  sourcesLoading: false,

  runs: [],
  runsMeta: null,
  runsLoading: false,
  runsFilters: {},
  selectedRun: null,
  selectedRunLoading: false,

  incidents: [],
  incidentsMeta: null,
  incidentsLoading: false,
  incidentsFilters: {},

  events: [],
  eventsMeta: null,
  eventsLoading: false,
  eventsFilters: {},

  // ── Actions ──

  loadOverview: async () => {
    set({ overviewLoading: true, overviewError: null })
    try {
      const data = await fetchAdminOverview()
      set({ overview: data, overviewLoading: false })
    } catch (e) {
      set({ overviewError: (e as Error).message, overviewLoading: false })
    }
  },

  loadSources: async () => {
    set({ sourcesLoading: true })
    try {
      const { sources } = await fetchAdminSources()
      set({ sources, sourcesLoading: false })
    } catch {
      set({ sourcesLoading: false })
    }
  },

  loadRuns: async (filters?: RunsFilters) => {
    const f = filters ?? get().runsFilters
    set({ runsLoading: true, runsFilters: f })
    try {
      const { runs, meta } = await fetchAdminRuns(f)
      set({ runs, runsMeta: meta, runsLoading: false })
    } catch {
      set({ runsLoading: false })
    }
  },

  loadRunDetail: async (runId: string) => {
    set({ selectedRunLoading: true })
    try {
      const detail = await fetchAdminRunDetail(runId)
      set({ selectedRun: detail, selectedRunLoading: false })
    } catch {
      set({ selectedRunLoading: false })
    }
  },

  loadIncidents: async (filters?: IncidentsFilters) => {
    const f = filters ?? get().incidentsFilters
    set({ incidentsLoading: true, incidentsFilters: f })
    try {
      const { incidents, meta } = await fetchAdminIncidents(f)
      set({ incidents, incidentsMeta: meta, incidentsLoading: false })
    } catch {
      set({ incidentsLoading: false })
    }
  },

  loadEvents: async (filters?: EventsFilters) => {
    const f = filters ?? get().eventsFilters
    set({ eventsLoading: true, eventsFilters: f })
    try {
      const { events, meta } = await fetchAdminEvents(f)
      set({ events, eventsMeta: meta, eventsLoading: false })
    } catch {
      set({ eventsLoading: false })
    }
  },

  triggerHealthcheck: async (sourceId: string) => {
    try {
      await triggerSourceHealthcheck(sourceId)
      // Перезагрузить sources после healthcheck
      get().loadSources()
    } catch {
      // ignore
    }
  },

  // ── SSE Updates ──

  updateOverviewFromSSE: (data: unknown) => {
    // Health data — обновляем services в overview
    const current = get().overview
    if (!current) return
    // Данные приходят как массив health probes
    if (Array.isArray(data)) {
      const updated = { ...current }
      const serviceMap = new Map(updated.services.map((s) => [s.serviceName, s]))
      for (const probe of data) {
        const name = probe.service_name || probe.serviceName
        if (name) {
          serviceMap.set(name, {
            serviceName: name,
            status: probe.status,
            responseTimeMs: probe.response_time_ms ?? probe.responseTimeMs ?? null,
            detailsJson: probe.details_json ?? probe.detailsJson ?? null,
            checkedAt: probe.checked_at ?? probe.checkedAt ?? new Date().toISOString(),
          })
        }
      }
      updated.services = Array.from(serviceMap.values())
      // Пересчитать overall
      const statuses = new Set(updated.services.map((s) => s.status))
      if (statuses.has('unavailable')) updated.overall = 'unavailable'
      else if (statuses.has('degraded')) updated.overall = 'degraded'
      else updated.overall = 'healthy'
      set({ overview: updated })
    }
  },

  prependEventFromSSE: (data: unknown) => {
    const event = data as SystemEvent
    if (!event || !event.id) return
    const current = get().events
    // Prepend, max 200 items
    set({ events: [event, ...current].slice(0, 200) })
  },
}))
