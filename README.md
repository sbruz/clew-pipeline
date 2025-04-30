

# Clew Book Content Pipeline

Этот проект — Python-пайплайн для автоматизированной подготовки книг для приложения **Clew**.

Он выполняет:
- 💬 форматирование и очистку текста (OpenAI)
- ✂️ разбивку на абзацы
- 🧱 структурирование по главам
- 🧒 упрощение текста до уровня B1
- 🌍 перевод по предложениям
- 🧠 лексический разбор слов и переводов
- 🎧 озвучку оригинального и упрощённого текста (ElevenLabs)
- 📦 экспорт в `.json` и `.mp3`

---

## 📁 Структура проекта

clew/
├── main.py                  # Точка входа
├── preprocess.py            # Все этапы форматирования, перевода, озвучки
├── schemas/                 # Структуры данных (Pydantic)
│   └── translation_schema.py
├── utils/                   # Клиенты supabase, tools
├── export/                  # Финальные .json и .mp3 файлы
├── .env                     # API-ключи (в .gitignore)
├── config.yaml              # Конфигурация пайплайна
└── requirements.txt

---

## Использование

Создайте .env файл:
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://...
SUPABASE_KEY=...
ELEVENLABS_API_KEY=...

Установите зависимости:
pip install -r requirements.txt

Запуск:
main.py

Настройки указываются в `config.yaml`
Включайте/отключайте шаги обработки

## Результаты
export/book_<id>.json — итоговый JSON
export/voice_book_<id>/ — аудиофайлы и тайминги
