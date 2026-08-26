# 🖼️ Image Crop Tool & ZIP Cleaner

> 🇷🇺 Русская версия · 🇬🇧 English version

Веб-инструмент на **Streamlit** для пакетной обработки изображений и очистки ZIP-архивов.

**Версия: 2.4**

## 🚀 Онлайн

Приложение рассчитано на запуск через **Streamlit Community Cloud**.

> 💡 Если у вас уже есть опубликованный Streamlit URL, добавьте его сюда как основной Demo для пользователей.

## 🇷🇺 Возможности

### ✂️ Обрезка изображений

- 📁 Загрузка нескольких изображений одновременно
- 🗑️ Кнопка **«Очистить загруженные изображения»** — можно одним нажатием удалить текущий набор и выбрать новый
- ✂️ Автоматическая обрезка пустых полей
- 🎯 Ручная обрезка по четырём сторонам
- ⬜ Режим без обрезки
- 📐 Квадратный холст 1200×1200 или 1000×1000 px
- ↔️ Настройка отступа
- 🖼️ Экспорт в PNG или JPG
- 🔲 Прозрачный фон для PNG
- 📦 Несколько результатов скачиваются одним ZIP
- 🌓 Светлая и тёмная тема
- 🧩 AVIF при установленном `pillow-avif-plugin`

### 📦 ZIP Cleaner

- ✅ Оставляет основной `_images_1`
- 🗑️ Удаляет остальные `_images_2`, `_images_3` и т. д.
- 🔄 Переименовывает основной файл в `{folder_name}_1.png`
- 🖼️ Конвертирует основной файл в PNG
- 📦 Собирает результат в один ZIP
- 🚫 Файлы без `_images_` не затрагиваются
- 🔢 Максимум **30 файлов** в исходном ZIP
- 💾 Максимум **100 МБ** на исходный ZIP

## 🛡️ Ограничения и защита

### Изображения

- максимум **30 изображений** за один запуск;
- максимум **50 МБ на один файл**;
- максимум **100 МБ суммарно**;
- максимум **5000×5000 px**;
- результаты предыдущей загрузки автоматически сбрасываются при изменении входных файлов;
- для входных файлов используется SHA-256 отпечаток содержимого.

### ZIP Cleaner

- максимум **100 МБ** исходного ZIP;
- максимум **30 файлов** в архиве;
- защита от небезопасных путей при обработке ZIP;
- результат предыдущего архива автоматически сбрасывается при загрузке нового;
- скачиваемый ZIP получает уникальное имя.

### 🎲 Имена ZIP

Каждый скачиваемый архив получает имя с датой, временем и случайным идентификатором, например:

```text
processed_images_20260824_151530_a1b2c3d4.zip
cleaned_images_20260824_151545_f8e7d6c5.zip
```

## 🔄 Защита от старых результатов

При изменении загруженных файлов предыдущий результат удаляется из `session_state`. Это не позволяет случайно скачать результат от предыдущей операции.

## 🧪 Тесты

```bash
pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions автоматически запускает синтаксическую проверку активных модулей и тесты после изменений.

## 🚀 Запуск локально

```bash
git clone https://github.com/justsmokeadfly/image-crop-tool.git
cd image-crop-tool
pip install -r requirements.txt
streamlit run app.py
```

## ☁️ Streamlit Community Cloud

- **Repository:** `justsmokeadfly/image-crop-tool`
- **Branch:** `main`
- **Main file:** `app.py`

Зависимости устанавливаются из `requirements.txt`.

Для личного использования рекомендуется сделать приложение **Private** в настройках Streamlit Community Cloud и разрешить просмотр только своему аккаунту.

## 🛠️ Технологии

- Python
- Streamlit
- Pillow
- pillow-avif-plugin
- pytest
- GitHub Actions

## 📄 Поддерживаемые форматы

**Image Crop Tool:** PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF и AVIF.

**ZIP Cleaner:** изображения с автоматическим преобразованием основного `_images_1` в PNG.

---

## 🇬🇧 English

### ✂️ Image Crop Tool

- Batch image upload
- **Clear uploaded images** button
- Automatic empty-area cropping
- Manual cropping
- No-crop mode
- Adjustable square canvas and padding
- PNG/JPG export
- Transparent PNG background
- ZIP download for multiple results
- Light/dark theme
- AVIF support when the plugin is installed

### 📦 ZIP Cleaner

- Keeps `_images_1`
- Removes other `_images_2`, `_images_3`, etc.
- Converts the primary image to PNG
- Renames it to `{folder_name}_1.png`
- Maximum 30 files per input ZIP
- Maximum 100 MB input ZIP
- Unique output ZIP names

### 🛡️ Security limits

- Maximum 30 uploaded images
- Maximum 50 MB per image
- Maximum 100 MB total image upload
- Maximum 5000×5000 pixels
- Maximum 30 files per ZIP
- Maximum 100 MB ZIP
- SHA-256 input fingerprints
- Previous results are cleared when inputs change

## 🔗 Repository

GitHub: https://github.com/justsmokeadfly/image-crop-tool
