# Deployment: Web (Frontend)

Руководство по сборке, деплою и настройке React SPA для OCR Web MVP.

---

## 1. Build Configuration

| Параметр      | Значение                          |
|---------------|-----------------------------------|
| Framework     | React 18 + TypeScript             |
| Bundler       | Vite                              |
| UI-библиотека | Ant Design                        |
| Dev-порт      | 3000                              |

### Сборка

```bash
cd apps/web
npx vite build
```

Результат: директория `dist/` с готовой статикой.

### Dev-режим

```bash
cd apps/web
npx vite
```

Vite dev server запускается на `http://localhost:3000`.
Proxy настроен в `apps/web/vite.config.ts`:

- `/api` -> `http://localhost:8000` (FastAPI backend)
- SSE-ответы (`text/event-stream`) отдаются без буферизации

---

## 2. Environment Variables

Переменные задаются на этапе сборки (prefix `VITE_`).

| Переменная              | Описание                  | Пример                                       |
|-------------------------|---------------------------|-----------------------------------------------|
| `VITE_SUPABASE_URL`     | Публичный URL Supabase    | `https://xxx.supabase.co`                     |
| `VITE_SUPABASE_ANON_KEY`| Публичный anon key        | `eyJhbGciOi...`                               |

**Правило безопасности:** frontend НЕ содержит секретов. Все service role keys, API keys провайдеров и R2 credentials находятся только на backend.

Создайте файл `apps/web/.env` для локальной разработки:

```bash
VITE_SUPABASE_URL=http://localhost:54321
VITE_SUPABASE_ANON_KEY=<anon_key из supabase start>
```

---

## 3. Static Hosting

### Nginx (production)

Docker Compose конфигурация: `infra/web/docker-compose.yml`

```yaml
services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ../../apps/web/dist:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    environment:
      - BACKEND_URL=${BACKEND_URL:-http://backend-server:8000}
    mem_limit: 128m
```

Nginx конфигурация (`infra/web/nginx.conf`) обеспечивает:

**SPA fallback** -- все маршруты отдают `index.html`:

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

**API proxy** -- запросы `/api/` проксируются на backend:

```nginx
location /api/ {
    proxy_pass http://backend-server:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Кеширование статики** -- js, css, шрифты, изображения:

```nginx
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

**SSE** -- для event-stream ответов добавьте в блок `/api/`:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
```

### Альтернативные варианты

**Caddy** -- автоматический HTTPS через Let's Encrypt:

```
example.com {
    root * /srv/dist
    file_server
    try_files {path} /index.html
    reverse_proxy /api/* backend-server:8000
}
```

**Vercel** -- для быстрого прототипирования. Настройки rewrites в `vercel.json`:

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://backend.example.com/api/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

---

## 4. Supabase Auth

Frontend использует `@supabase/supabase-js` с публичным anon key.

### Инициализация

```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)
```

### Хранение токена

JWT сохраняется в `localStorage` под ключом `sb-<project_ref>-auth-token`.
Supabase JS SDK управляет refresh автоматически.

### Проверка прав администратора

Административные функции доступны при наличии флага в `app_metadata`:

```typescript
const { data: { user } } = await supabase.auth.getUser()
const isAdmin = user?.app_metadata?.is_admin === true
```

### SSE-авторизация

Server-Sent Events не поддерживают заголовки авторизации в `EventSource`.
Токен передается через query parameter:

```typescript
const token = (await supabase.auth.getSession()).data.session?.access_token
const evtSource = new EventSource(`/api/ocr/stream?token=${token}`)
```

---

## 5. CORS

### Production (через nginx proxy)

Когда frontend и API обслуживаются через один nginx -- CORS не нужен.
Браузер видит same-origin запросы.

### Dev-режим (Vite proxy)

Vite dev server проксирует `/api` на backend -- CORS не нужен на клиенте.

### Прямое подключение к backend

Если frontend обращается к backend напрямую (без proxy), на backend настроен
`CORSMiddleware`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

В production добавьте домен frontend в `allow_origins`.

---

## 6. Production Checklist

- [ ] `npx vite build` завершается без ошибок
- [ ] `VITE_SUPABASE_URL` и `VITE_SUPABASE_ANON_KEY` указывают на production Supabase
- [ ] Nginx конфигурация: SPA fallback, API proxy, кеширование статики
- [ ] SSE proxy: `proxy_buffering off` в блоке `/api/`
- [ ] HTTPS termination настроен (certbot, Cloudflare, или аналог)
- [ ] `dist/` не содержит `.env` файлов и source maps (если не нужны)
- [ ] Gzip/Brotli сжатие включено в nginx
- [ ] Content-Security-Policy заголовок настроен
- [ ] `X-Frame-Options: DENY` для защиты от clickjacking
- [ ] Мониторинг доступности nginx (healthcheck на port 80)
- [ ] Логирование nginx: access log + error log с ротацией
