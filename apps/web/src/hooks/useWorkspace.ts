/**
 * Хук для получения текущего workspace.
 *
 * Для MVP: автоматически выбирает первый доступный workspace пользователя.
 * Хранит выбранный workspaceId в localStorage для persistence.
 */

import { useEffect, useState, useCallback } from 'react'
import { apiFetch } from '../api/client'

interface Workspace {
  id: string
  name: string
  slug: string
  myRole: string
  memberCount: number
}

interface WorkspaceListApiResponse {
  workspaces: Array<{
    id: string
    name: string
    slug: string
    my_role: string
    member_count: number
    created_at: string
  }>
}

const STORAGE_KEY = 'rdweb-workspace-id'

export function useWorkspace() {
  const [workspaceId, setWorkspaceId] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  )
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)

  const loadWorkspaces = useCallback(async () => {
    setLoading(true)
    try {
      const raw = await apiFetch<WorkspaceListApiResponse>('/workspaces/')
      const list = raw.workspaces.map((w) => ({
        id: w.id,
        name: w.name,
        slug: w.slug,
        myRole: w.my_role,
        memberCount: w.member_count,
      }))
      setWorkspaces(list)

      // Auto-select: если текущий workspace не в списке — взять первый
      const saved = localStorage.getItem(STORAGE_KEY)
      if (list.length > 0) {
        const validSaved = saved && list.some((w) => w.id === saved)
        const selectedId = validSaved ? saved : list[0].id
        setWorkspaceId(selectedId)
        localStorage.setItem(STORAGE_KEY, selectedId)
      }
    } catch {
      // Если не удалось загрузить — не блокируем
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadWorkspaces()
  }, [loadWorkspaces])

  const selectWorkspace = useCallback((id: string) => {
    setWorkspaceId(id)
    localStorage.setItem(STORAGE_KEY, id)
  }, [])

  return {
    workspaceId,
    workspaces,
    loading,
    selectWorkspace,
    refreshWorkspaces: loadWorkspaces,
  }
}
