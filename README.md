# 🖼️ Image Crop Tool & ZIP Cleaner

> 🇷🇺 **Русская версия** · 🇬🇧 **English version**

Простой веб-инструмент на **Streamlit** для пакетной обработки изображений и очистки ZIP-архивов.

**Версия: 2.1**

## 🇷🇺 Русская версия

### ✨ Возможности

Приложение состоит из **двух вкладок**:

#### ✂️ Image Crop Tool

- 📁 Загрузка нескольких изображений одновременно
- ✂️ Автоматическая обрезка пустых полей
- 🎯 Ручная обрезка по четырём сторонам
- ⬜ Режим без обрезки
- 📐 Настройка квадратного холста
- ↔️ Настройка отступа
- 🖼️ Экспорт в PNG или JPG
- 🔲 Прозрачный фон для PNG
- 📦 Скачивание нескольких результатов одним ZIP-архивом
- 🌓 Светлая и тёмная тема
- 🧩 Поддержка AVIF при наличии `pillow-avif-plugin`

#### 📦 ZIP Cleaner

Быстрая очистка ZIP-архивов с изображениями.

Обрабатываются только файлы, содержащие **`_images_`** в имени.

- ✅ Оставляет только основной файл `_images_1`
- 🗑️ Удаляет остальные `_images_2`, `_images_3` и т. д.
- 🔄 Переименовывает основной файл в `{folder_name}_1.png`
- 🖼️ Конвертирует основной файл в PNG
- 📦 Собирает готовые PNG-файлы в один ZIP
- 📂 Не создаёт отдельные папки для результатов
- 🚫 Файлы без `_images_` не затрагиваются

Пример:

```text
product/
├── product_images_1.jpg   → product_1.png
├── product_images_2.jpg   → удаляется
├── product_images_3.webp  → удаляется
└── other_file.txt         → игнорируется
```

### 🛡️ Защита от старых результатов — v2.1

Приложение больше не позволяет случайно скачать результат от **предыдущей загрузки**.

Для каждой новой загрузки вычисляется **SHA-256 отпечаток содержимого** вместе с именем и размером файла.

Если пользователь загружает другой файл:

1. Старый результат автоматически удаляется из `session_state`.
2. Старая кнопка скачивания исчезает.
3. Результат появляется только после новой обработки.

Защита работает **для обеих вкладок**:

- ✂️ Image Crop Tool — старые обработанные изображения сбрасываются при изменении набора файлов.
- 📦 ZIP Cleaner — старый очищенный ZIP сбрасывается при изменении исходного архива.

Это предотвращает ситуацию, когда пользователь загрузил новый файл, но скачал результат предыдущей операции.

### 🔄 Логика ZIP Cleaner

1. Пользователь загружает ZIP.
2. Инструмент находит файлы с `_images_`.
3. Файл `_images_1` определяется как основной.
4. Основное изображение конвертируется в PNG.
5. Оно получает имя `{folder_name}_1.png`.
6. Остальные `_images_` удаляются.
7. PNG-файлы собираются в один ZIP.
8. Новый результат становится доступен для скачивания.
9. При загрузке другого ZIP предыдущий результат автоматически сбрасывается.

> **Важно:** `rembg` больше не используется и не требуется.

### 🚀 Запуск локально

```bash
git clone https://github.com/justsmokeadfly/image-crop-tool.git
cd image-crop-tool
pip install -r requirements.txt
streamlit run app.py
```

### 🧪 Тесты

```bash
pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions автоматически проверяет проект после изменений.

### ☁️ Streamlit Community Cloud

Проект готов для запуска через **Streamlit Community Cloud**.

- **Repository:** `justsmokeadfly/image-crop-tool`
- **Branch:** `main`
- **Main file:** `app.py`

Зависимости устанавливаются из `requirements.txt`.

### 🛠️ Технологии

- Python
- Streamlit
- Pillow
- pillow-avif-plugin
- pytest
- GitHub Actions

### 📄 Поддерживаемые форматы

**Image Crop Tool:** PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF и AVIF.

**ZIP Cleaner:** изображения с автоматическим преобразованием основного `_images_1` в PNG.

---

## 🇬🇧 English version

### ✨ Features

The application contains **two tabs**:

#### ✂️ Image Crop Tool

- 📁 Upload multiple images at once
- ✂️ Automatic empty-area cropping
- 🎯 Manual cropping from four sides
- ⬜ No-crop mode
- 📐 Adjustable square canvas
- ↔️ Adjustable padding
- 🖼️ Export to PNG or JPG
- 🔲 Transparent PNG background
- 📦 Download multiple results as a single ZIP archive
- 🌓 Light and dark themes
- 🧩 AVIF support when `pillow-avif-plugin` is installed

#### 📦 ZIP Cleaner

A fast tool for cleaning ZIP archives containing image variants.

Only files containing **`_images_`** in their filename are processed.

- ✅ Keeps only the main `_images_1` file
- 🗑️ Removes other `_images_2`, `_images_3`, etc.
- 🔄 Renames the primary image to `{folder_name}_1.png`
- 🖼️ Converts the primary image to PNG
- 📦 Packs all processed PNG files into one ZIP archive
- 📂 Does not create multiple output folders
- 🚫 Files without `_images_` are ignored

Example:

```text
product/
├── product_images_1.jpg   → product_1.png
├── product_images_2.jpg   → removed
├── product_images_3.webp  → removed
└── other_file.txt         → ignored
```

### 🛡️ Stale-result protection — v2.1

The application now prevents accidental downloads of results from a **previous upload**.

Each new upload gets a **SHA-256 content fingerprint**, combined with its filename and size.

When the uploaded input changes:

1. The previous result is automatically removed from `session_state`.
2. The old download button disappears.
3. A new download becomes available only after processing the new input.

The protection covers **both tabs**:

- ✂️ Image Crop Tool — previous processed images are cleared when the uploaded set changes.
- 📦 ZIP Cleaner — the previous cleaned ZIP is cleared when the source archive changes.

This prevents downloading an old result after uploading a new file.

### 🔄 ZIP Cleaner workflow

1. Upload a ZIP archive.
2. Find image files containing `_images_`.
3. Detect `_images_1` as the primary image.
4. Convert the primary image to PNG.
5. Rename it to `{folder_name}_1.png`.
6. Remove all other `_images_` variants.
7. Pack the resulting PNG files into one ZIP archive.
8. Make the new result available for download.
9. Automatically clear the previous result when another ZIP is uploaded.

> **Note:** `rembg` is no longer used or required.

### 🚀 Local installation

```bash
git clone https://github.com/justsmokeadfly/image-crop-tool.git
cd image-crop-tool
pip install -r requirements.txt
streamlit run app.py
```

### 🧪 Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions automatically validates the project after changes.

### ☁️ Streamlit Community Cloud

The project is ready for **Streamlit Community Cloud**.

- **Repository:** `justsmokeadfly/image-crop-tool`
- **Branch:** `main`
- **Main file:** `app.py`

Dependencies are installed automatically from `requirements.txt`.

### 🛠️ Technologies

- Python
- Streamlit
- Pillow
- pillow-avif-plugin
- pytest
- GitHub Actions

### 📄 Supported formats

**Image Crop Tool:** PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF and AVIF.

**ZIP Cleaner:** image formats with automatic conversion of the primary `_images_1` image to PNG.

---

## 🔗 Repository

urlGitHub — justsmokeadfly/image-crop-toolhttps://github.com/justsmokeadfly/image-crop-tool
