# 🖼️ Image Crop Tool & ZIP Cleaner

> 🇷🇺 **Русская версия** · 🇬🇧 **English version**

Простой и удобный веб-инструмент на **Streamlit** для пакетной обработки изображений и очистки ZIP-архивов.

## 🇷🇺 Русская версия

### ✨ Возможности

Приложение состоит из **двух вкладок**:

#### ✂️ Image Crop Tool

- 📁 Загрузка нескольких изображений одновременно
- ✂️ Автоматическая обрезка пустых полей
- 🎯 Ручная обрезка по четырём сторонам
- ⬜ Режим без обрезки
- 📐 Настройка размера квадратного холста
- ↔️ Настройка отступа
- 🖼️ Экспорт в PNG или JPG
- 🔲 Прозрачный фон для PNG
- 📦 Скачивание всех результатов одним ZIP-архивом
- 🗑️ Удаление отдельных файлов из списка
- 🌓 Светлая и тёмная тема
- 🧩 Поддержка AVIF при наличии `pillow-avif-plugin`

#### 📦 ZIP Cleaner

Инструмент для быстрой очистки ZIP-архивов с изображениями.

Обрабатываются только файлы, в имени которых есть **`_images_`**.

- ✅ Оставляет только основной файл с суффиксом `_images_1`
- 🗑️ Удаляет остальные файлы `_images_2`, `_images_3` и т. д.
- 🔄 Переименовывает первый файл в формат `{folder_name}_1.png`
- 🖼️ При необходимости конвертирует выбранное изображение в **PNG**
- 📦 Все обработанные изображения собираются в **один ZIP-архив**
- 📂 Не создаёт множество отдельных папок с результатами
- 🚫 Файлы без `_images_` не затрагиваются

Пример:

```text
product/
├── product_images_1.jpg   → product_1.png
├── product_images_2.jpg   → удаляется
├── product_images_3.webp  → удаляется
└── other_file.txt         → игнорируется
```

### 🔄 Логика ZIP Cleaner

1. Инструмент получает ZIP-архив.
2. Находит изображения с `_images_` в имени.
3. Определяет файл `_images_1` как основной.
4. Основной файл конвертируется в PNG и получает имя `{folder_name}_1.png`.
5. Остальные `_images_` удаляются.
6. Готовые PNG-файлы помещаются в новый ZIP-архив.
7. Архив становится доступен для скачивания прямо из браузера.

> **Важно:** `rembg` больше не используется и не требуется.

### 🚀 Запуск локально

```bash
git clone https://github.com/justsmokeadfly/image-crop-tool.git
cd image-crop-tool
pip install -r requirements.txt
streamlit run app.py
```

После запуска приложение откроется в браузере.

### 🧪 Тесты

Установка dev-зависимостей:

```bash
pip install -r requirements-dev.txt
```

Запуск тестов:

```bash
pytest -q
```

GitHub Actions автоматически проверяет проект после изменений.

### ☁️ Streamlit Community Cloud

Проект готов для запуска через **Streamlit Community Cloud**.

Параметры приложения:

- **Repository:** `justsmokeadfly/image-crop-tool`
- **Branch:** `main`
- **Main file:** `app.py`

Зависимости устанавливаются автоматически из `requirements.txt`.

### 🛠️ Технологии

- Python
- Streamlit
- Pillow
- pillow-avif-plugin
- pytest
- GitHub Actions

### 📄 Поддерживаемые форматы

**Image Crop Tool:** PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF и AVIF.

**ZIP Cleaner:** распространённые форматы изображений с автоматическим преобразованием выбранного файла в PNG.

---

## 🇬🇧 English version

### ✨ Features

The application contains **two tabs**:

#### ✂️ Image Crop Tool

- 📁 Upload multiple images at once
- ✂️ Automatic empty-area cropping
- 🎯 Manual cropping from four sides
- ⬜ No-crop mode
- 📐 Adjustable square canvas size
- ↔️ Adjustable padding
- 🖼️ Export to PNG or JPG
- 🔲 Transparent background for PNG
- 📦 Download all processed images as a single ZIP archive
- 🗑️ Remove individual files from the list
- 🌓 Light and dark themes
- 🧩 AVIF support when `pillow-avif-plugin` is installed

#### 📦 ZIP Cleaner

A fast tool for cleaning ZIP archives containing image variants.

Only files containing **`_images_`** in their filename are processed.

- ✅ Keeps only the main `_images_1` file
- 🗑️ Removes other `_images_2`, `_images_3`, etc.
- 🔄 Renames the first image to `{folder_name}_1.png`
- 🖼️ Converts the selected image to **PNG**
- 📦 Packs all processed PNG files into **one ZIP archive**
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

### 🔄 ZIP Cleaner workflow

1. Upload a ZIP archive.
2. Find image files containing `_images_`.
3. Detect the `_images_1` file as the primary image.
4. Convert the primary image to PNG and rename it to `{folder_name}_1.png`.
5. Remove all other `_images_` variants.
6. Pack the resulting PNG files into a new ZIP archive.
7. Download the cleaned archive directly from the browser.

> **Note:** `rembg` is no longer used or required.

### 🚀 Local installation

```bash
git clone https://github.com/justsmokeadfly/image-crop-tool.git
cd image-crop-tool
pip install -r requirements.txt
streamlit run app.py
```

The application will open in your browser.

### 🧪 Tests

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest -q
```

GitHub Actions automatically validates the project after changes.

### ☁️ Streamlit Community Cloud

The project is ready to run on **Streamlit Community Cloud**.

Application settings:

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

**ZIP Cleaner:** common image formats with automatic conversion of the selected image to PNG.

---

## 🔗 Repository

urlGitHub — justsmokeadfly/image-crop-toolhttps://github.com/justsmokeadfly/image-crop-tool
