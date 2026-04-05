/**
 * Singleton Supabase клиент для авторизации и Realtime.
 *
 * Используется в LoginPage, ProtectedRoute, useBlockRealtimeUpdates.
 * Токен сессии хранится Supabase SDK автоматически в localStorage
 * под ключом sb-<project-ref>-auth-token, который читает client.ts.
 */

import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.error('VITE_SUPABASE_URL и VITE_SUPABASE_ANON_KEY обязательны')
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    storageKey: 'sb-auth-token',
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
  realtime: {
    params: { eventsPerSecond: 10 },
  },
})
