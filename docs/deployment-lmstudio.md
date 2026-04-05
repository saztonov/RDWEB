# Deployment: LM Studio (GPU Server)

Руководство по установке, настройке и интеграции LM Studio как локального OCR-провайдера.

---

## 1. Installation

### Системные требования

| Компонент | Минимум                  | Рекомендация              |
|-----------|--------------------------|---------------------------|
| GPU       | 8 GB VRAM               | NVIDIA RTX 3080 / 4070+  |
| CUDA      | 535+ (Linux), 537+ (Windows) | Последняя stable версия |
| RAM       | 16 GB                    | 32 GB                     |
| Диск      | 20 GB свободного места   | SSD, 50+ GB              |
| ОС        | Windows 10/11, Linux, macOS | --                      |

### Установка

1. Скачайте LM Studio: https://lmstudio.ai
2. Установите приложение
3. Убедитесь, что NVIDIA драйверы обновлены (для GPU-ускорения)

Проверка CUDA:

```bash
nvidia-smi
```

Вывод должен показывать GPU с достаточным объемом VRAM и версию CUDA Driver.

---

## 2. Model Download

LM Studio используется для двух типов задач в OCR pipeline:

### Vision-модели (image, stamp)

Для распознавания изображений и печатей нужны vision-модели с поддержкой image input:

- **Qwen2-VL** (7B/14B) -- рекомендуется для stamp и image блоков
- **LLaVA** (7B/13B) -- альтернатива

### Text-модели

Для обработки текстовых блоков (text block kind):

- Любая instruction-tuned модель с поддержкой русского языка

### Подбор модели по VRAM

| VRAM   | Максимальный размер модели | Пример                     |
|--------|---------------------------|----------------------------|
| 8 GB   | 7B (Q4_K_M)              | Qwen2-VL-7B-Q4_K_M        |
| 12 GB  | 7B (Q8) или 13B (Q4)     | LLaVA-13B-Q4_K_M          |
| 16 GB  | 14B (Q5-Q8)              | Qwen2-VL-14B-Q5_K_M       |
| 24 GB  | 14B (Q8) или 70B (Q4)    | --                         |

### Context length

Для OCR задач достаточно context length 4096-8192 токенов.
Увеличение context length потребляет дополнительную VRAM.

В LM Studio настройте context length в параметрах модели (Developer tab).

---

## 3. API Endpoint

### Запуск сервера

1. Откройте LM Studio
2. Перейдите в раздел **Developer**
3. Загрузите нужную модель
4. Нажмите **Start Server**

По умолчанию сервер слушает на порту `1234`.

### OpenAI-compatible API

LM Studio предоставляет API, совместимый с OpenAI:

| Endpoint                 | Описание                    |
|--------------------------|-----------------------------|
| `GET /v1/models`         | Список загруженных моделей  |
| `POST /v1/chat/completions` | Chat completion запрос   |

Проверка работоспособности:

```bash
curl http://localhost:1234/v1/models
```

### Host binding

По умолчанию LM Studio слушает на `localhost`. Для доступа с других машин:

1. В Developer tab включите опцию **Serve on Local Network**
2. Или вручную задайте host `0.0.0.0`
3. Сервер станет доступен по IP машины: `http://<machine-ip>:1234`

---

## 4. Network Configuration

### Вариант 1: Локальная сеть (local)

Если backend и LM Studio в одной сети:

```bash
CHANDRA_BASE_URL=http://192.168.1.100:1234
```

Замените `192.168.1.100` на IP GPU-машины.

### Вариант 2: Ngrok tunnel (remote_ngrok)

Если прямого сетевого доступа нет:

```bash
# На GPU-машине
ngrok http 1234
```

Ngrok выдаст URL вида `https://xxxx.ngrok-free.app`. Используйте его:

```bash
CHANDRA_BASE_URL=https://xxxx.ngrok-free.app
```

Для стабильного subdomain (платная подписка ngrok):

```bash
ngrok http 1234 --domain=your-subdomain.ngrok-free.app
```

### Вариант 3: VPN / private network (private_url)

Для production рекомендуется VPN-соединение между серверами:

- **WireGuard** -- минимальный overhead, простая настройка
- **Tailscale** -- WireGuard-based, zero-config mesh VPN

```bash
# Пример с Tailscale
CHANDRA_BASE_URL=http://gpu-server.tailnet-name.ts.net:1234
```

### Сравнение вариантов

| Вариант      | Задержка  | Надёжность | Безопасность | Стоимость    |
|-------------|-----------|------------|--------------|-------------|
| Local       | Минимум   | Высокая    | Высокая      | Бесплатно   |
| Ngrok       | +50-100ms | Средняя    | Средняя      | Free / $8/мес |
| VPN         | +5-10ms   | Высокая    | Высокая      | Бесплатно   |

---

## 5. Integration с Backend

### Таблица ocr_sources

LM Studio регистрируется в базе данных через таблицу `ocr_sources`:

| Поле              | Описание                                     |
|-------------------|----------------------------------------------|
| `source_type`     | `lmstudio`                                   |
| `name`            | Отображаемое имя                              |
| `base_url`        | URL сервера (например, `http://localhost:1234/v1`) |
| `deployment_mode` | `docker`, `remote_ngrok` или `private_url`   |
| `is_enabled`      | Активен ли source                            |
| `concurrency_limit` | Максимум параллельных запросов             |
| `timeout_sec`     | Таймаут на один запрос (секунды)             |
| `health_status`   | `healthy`, `unhealthy`, `unknown`            |
| `credentials_json`| JSON с auth данными (для ngrok и т.д.)       |

### Seed-данные

В `supabase/seed.sql` предустановлены два варианта source:

**LM Studio Local** (`docker`):

```sql
INSERT INTO ocr_sources (source_type, name, base_url, deployment_mode, is_enabled, concurrency_limit, timeout_sec)
VALUES ('lmstudio', 'LM Studio Local', 'http://localhost:1234/v1', 'docker', true, 2, 180);
```

**LM Studio Ngrok** (`remote_ngrok`):

```sql
INSERT INTO ocr_sources (source_type, name, base_url, deployment_mode, is_enabled, concurrency_limit, timeout_sec, credentials_json)
VALUES ('lmstudio', 'LM Studio Ngrok', 'https://example.ngrok-free.app/v1', 'remote_ngrok', false, 2, 240,
        '{"auth_user": "user", "auth_pass": "pass"}');
```

Ngrok source по умолчанию отключен (`is_enabled: false`). Включите его через Admin panel после настройки tunnel.

### SourceRegistry

При startup backend загружает все source из `ocr_sources` в `SourceRegistry`:

```
app.state.source_registry = SourceRegistry()
await registry.load_from_db()
```

SourceRegistry предоставляет провайдеры для OCR worker. При изменении записей в таблице необходимо перезапустить backend или вызвать reload через Admin panel.

---

## 6. Health Monitoring

### Автоматический мониторинг

Celery beat запускает probe каждую минуту:

1. Отправляет `GET /v1/models` на каждый активный LM Studio source
2. Обновляет поле `health_status` в таблице `ocr_sources`:
   - `healthy` -- ответ 200, модели загружены
   - `unhealthy` -- timeout, ошибка соединения, пустой список моделей
   - `unknown` -- проверка ещё не проводилась

### Admin panel

Страница **Sources** в admin panel отображает:

- Статус каждого source (healthy / unhealthy / unknown)
- Последнее время проверки
- Количество загруженных моделей
- Текущая нагрузка (active requests / concurrency_limit)

### GPU monitoring

На GPU-машине:

```bash
# Однократная проверка
nvidia-smi

# Непрерывный мониторинг (обновление каждые 2 секунды)
watch -n 2 nvidia-smi

# Только VRAM
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

Следите за:

- **GPU Utilization** -- должен расти при обработке запросов
- **Memory Usage** -- не должен приближаться к 100% (OOM crash)
- **Temperature** -- не выше 85C при длительной нагрузке

---

## 7. Troubleshooting

### Сервер не отвечает

**Симптомы:** `GET /v1/models` возвращает connection refused или timeout.

Проверки:
1. LM Studio запущен и сервер стартован (Developer -> Start Server)
2. Порт 1234 открыт: `telnet <ip> 1234` или `curl http://<ip>:1234/v1/models`
3. Firewall не блокирует порт (Windows Defender, iptables)
4. Если используется Docker -- проверьте, что host binding `0.0.0.0`, а не `127.0.0.1`

### Cold start (первый запрос медленный)

**Симптомы:** первый запрос занимает 30-60 секунд, последующие быстрее.

Причина: LM Studio загружает модель в VRAM при первом обращении.

Решение:
- Увеличьте `timeout_sec` в `ocr_sources` до 180-240 секунд
- Отправьте разогревающий запрос после старта сервера:

```bash
curl -X POST http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "loaded-model-name", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}'
```

- В LM Studio включите опцию **Keep model in memory** (если доступна)

### VRAM overflow

**Симптомы:** LM Studio вылетает, ошибка CUDA OOM, GPU зависает.

Решение:
1. Используйте модель меньшего размера или более агрессивную квантизацию (Q4 вместо Q8)
2. Уменьшите context length (4096 достаточно для большинства OCR задач)
3. Уменьшите `concurrency_limit` в `ocr_sources` до 1
4. Закройте другие приложения, использующие GPU
5. Перезапустите LM Studio для очистки VRAM

Проверка свободной VRAM:

```bash
nvidia-smi --query-gpu=memory.free --format=csv,noheader
```

### Ngrok disconnect

**Симптомы:** backend теряет связь с LM Studio через ngrok.

Причины и решения:
- **Free tier timeout** -- бесплатный ngrok разрывает соединение через ~2 часа. Перезапустите `ngrok http 1234`. Для стабильности используйте платный план.
- **URL изменился** -- при перезапуске ngrok URL меняется. Обновите `base_url` в таблице `ocr_sources` и перезапустите backend (или reload через Admin panel).
- **Rate limiting** -- ngrok free имеет ограничение на количество соединений. Уменьшите `concurrency_limit` до 1.

Рекомендация: для production используйте VPN (WireGuard / Tailscale) вместо ngrok.

### Модель выдает плохие результаты

Проверки:
1. Убедитесь, что загружена vision-модель для image/stamp блоков
2. Проверьте prompt templates в таблице `prompt_templates` -- они должны соответствовать модели
3. Попробуйте модель напрямую через LM Studio UI с тем же prompt
4. Для русскоязычных документов используйте модели с поддержкой русского языка
