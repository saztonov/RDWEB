# LM Studio Server

Отдельный GPU-сервер для локальных LLM моделей, используемых в OCR pipeline.

## Требования

- GPU с 8+ GB VRAM (рекомендуется NVIDIA RTX 3080 / 4070 и выше)
- LM Studio установлен и настроен
- Сетевой доступ от backend-сервера

## Установка

1. Скачать LM Studio: https://lmstudio.ai
2. Загрузить нужные модели для OCR задач
3. Запустить сервер в LM Studio (Developer → Start Server)
4. По умолчанию слушает на порту `1234`

## Подключение к backend

На backend-сервере задать переменную:

```bash
CHANDRA_BASE_URL=http://<lmstudio-host>:1234
```

Где `<lmstudio-host>` — IP или hostname GPU-сервера.

### Через ngrok (если нет прямого доступа)

```bash
ngrok http 1234
```

Использовать полученный URL как `CHANDRA_BASE_URL`.

## Проверка здоровья

```bash
curl http://<lmstudio-host>:1234/v1/models
```

Должен вернуть JSON со списком загруженных моделей.

## Управление памятью

- LM Studio автоматически загружает модель при первом запросе
- Backend поддерживает паттерн auto-unload: если модель не используется 30+ секунд, она может быть выгружена
- Рекомендуется мониторить VRAM через `nvidia-smi`

## Безопасность

- LM Studio **не** должен быть доступен из интернета напрямую
- Используйте VPN / private network между backend и LM Studio
- Если используется ngrok — ограничьте доступ через ngrok auth
