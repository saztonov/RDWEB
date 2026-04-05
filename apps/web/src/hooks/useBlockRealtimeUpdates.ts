/**
 * Supabase Realtime подписка на обновления blocks и recognition_runs.
 *
 * Используется в Document Editor для live updates статуса блоков
 * и прогресса recognition run без перезагрузки страницы.
 *
 * Выбор Supabase Realtime (а не backend SSE):
 * - Уже есть JS-клиент (@supabase/supabase-js)
 * - Row-level фильтрация по document_id из коробки
 * - RLS уже настроен для workspace isolation
 * - Не требует дополнительной инфраструктуры (Redis pub/sub)
 *
 * Использует общий singleton Supabase client из lib/supabase.ts
 * с автоматическим refresh токена через onAuthStateChange.
 */

import { useEffect, useRef } from 'react'
import type { RealtimeChannel } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { useEditorStore } from '../store/useEditorStore'

/**
 * Подписка на Supabase Realtime для live обновлений блоков документа.
 *
 * При UPDATE на blocks с matching document_id:
 * - Обновляет block в EditorStore через updateBlockInStore
 * - Статус, current_text, current_render_html обновляются без reload
 *
 * При наличии activeRunId — также подписывается на recognition_runs
 * для отслеживания прогресса.
 */
export function useBlockRealtimeUpdates(documentId: string | null) {
  const channelRef = useRef<RealtimeChannel | null>(null)
  const runChannelRef = useRef<RealtimeChannel | null>(null)

  const updateBlockInStore = useEditorStore((s) => s.updateBlockInStore)
  const activeRunId = useEditorStore((s) => s.activeRunId)

  // Подписка на blocks
  useEffect(() => {
    if (!documentId) return

    const channel = supabase
      .channel(`blocks:${documentId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'blocks',
          filter: `document_id=eq.${documentId}`,
        },
        (payload) => {
          const row = payload.new as Record<string, unknown>
          if (!row || !row.id) return

          // Конвертация snake_case → camelCase для EditorStore
          const block = {
            id: row.id as string,
            documentId: row.document_id as string,
            pageNumber: row.page_number as number,
            blockKind: row.block_kind as string,
            shapeType: row.shape_type as string,
            bboxJson: row.bbox_json,
            polygonJson: row.polygon_json,
            readingOrder: row.reading_order as number,
            geometryRev: row.geometry_rev as number,
            contentRev: row.content_rev as number,
            manualLock: row.manual_lock as boolean,
            routeSourceId: row.route_source_id as string | null,
            routeModelName: row.route_model_name as string | null,
            promptTemplateId: row.prompt_template_id as string | null,
            currentText: row.current_text as string | null,
            currentStructuredJson: row.current_structured_json,
            currentRenderHtml: row.current_render_html as string | null,
            currentStatus: row.current_status as string,
            currentAttemptId: row.current_attempt_id as string | null,
            lastRecognitionSignature: row.last_recognition_signature as string | null,
            createdAt: row.created_at as string,
            updatedAt: row.updated_at as string,
            deletedAt: row.deleted_at as string | null,
          }

          updateBlockInStore(block as any)
        },
      )
      .subscribe()

    channelRef.current = channel

    return () => {
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current)
        channelRef.current = null
      }
    }
  }, [documentId, updateBlockInStore])

  // Подписка на recognition_runs для прогресса
  useEffect(() => {
    if (!activeRunId) {
      if (runChannelRef.current) {
        supabase.removeChannel(runChannelRef.current)
        runChannelRef.current = null
      }
      return
    }

    const channel = supabase
      .channel(`run:${activeRunId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'recognition_runs',
          filter: `id=eq.${activeRunId}`,
        },
        (payload) => {
          const row = payload.new as Record<string, unknown>
          if (!row) return

          // Обновить runProgress в store
          const state = useEditorStore.getState()
          if (state.runProgress) {
            const updated = {
              ...state.runProgress,
              status: row.status as string,
              processedBlocks: row.processed_blocks as number,
              recognizedBlocks: row.recognized_blocks as number,
              failedBlocks: row.failed_blocks as number,
              manualReviewBlocks: row.manual_review_blocks as number,
            }
            useEditorStore.setState({ runProgress: updated })

            // Если run завершён — сбросить activeRunId
            if (row.status === 'completed' || row.status === 'failed' || row.status === 'cancelled') {
              useEditorStore.setState({ activeRunId: null })
            }
          }
        },
      )
      .subscribe()

    runChannelRef.current = channel

    return () => {
      if (runChannelRef.current) {
        supabase.removeChannel(runChannelRef.current)
        runChannelRef.current = null
      }
    }
  }, [activeRunId])
}
