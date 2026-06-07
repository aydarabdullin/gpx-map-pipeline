# GPX Map Pipeline

Автоматический пайплайн: загрузи `.gpx`-файл → получи интерактивную HTML-карту на GitHub Pages.

## Как использовать

1. Положи `.gpx`-файл в папку `data/`:
   ```bash
   cp твой_маршрут.gpx data/track.gpx
   git add data/track.gpx
   git commit -m "Добавлен маршрут"
   git push
   ```

2. GitHub Actions автоматически запустит пайплайн (~1–2 минуты).

3. Готовая карта появится по адресу:
   ```
   https://<твой-логин>.github.io/<название-репозитория>/
   ```

## Что генерируется

- Интерактивная карта Leaflet с тремя подложками (OSM, спутник, рельеф)
- Трек с градиентом цвета по высоте
- Маркеры старта и финиша
- График профиля высот (синхронизирован с картой)
- Панель статистики: дистанция, время, скорость, высоты, набор/сброс

## Структура проекта

```
gpx-map-pipeline/
├── .github/
│   └── workflows/
│       └── process_gpx.yml   ← пайплайн GitHub Actions
├── data/
│   └── track.gpx             ← сюда кладёшь свой GPX-файл
├── output/
│   └── index.html            ← сюда пайплайн кладёт результат
├── scripts/
│   └── gpx_to_html.py        ← скрипт обработки (стандартная библиотека Python)
└── README.md
```

## Запуск локально

```bash
python scripts/gpx_to_html.py data/track.gpx output/index.html
# Затем открыть output/index.html в браузере
```

## Настройка GitHub Pages

В настройках репозитория:
`Settings → Pages → Source → GitHub Actions`
