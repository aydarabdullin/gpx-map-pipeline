#!/usr/bin/env python3
"""
gpx_to_html.py — конвертер GPX-трека в автономную HTML-страницу с картой.

Использование:
    python gpx_to_html.py <входной.gpx> <выходной.html>

Пример:
    python gpx_to_html.py data/track.gpx output/index.html

Зависимости: только стандартная библиотека Python (xml, math, json, sys, pathlib).
"""

import sys
import os
import math
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ
#
# Токен MapBox читается из переменной окружения MAPBOX_TOKEN.
# Никогда не вписывайте токен прямо в этот файл — он попадёт в публичный репо.
#
# Локальная разработка (VS Code):
#   export MAPBOX_TOKEN="pk.eyJ1Ijoiваш_токен..."   # macOS/Linux
#   $env:MAPBOX_TOKEN="pk.eyJ1Ijoiваш_токен..."     # Windows PowerShell
#
# GitHub Actions:
#   Settings → Secrets and variables → Actions → New repository secret
#   Name: MAPBOX_TOKEN  /  Value: pk.eyJ1Ijoiваш_токен...
# ─────────────────────────────────────────────────────────────────────────────
MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")
MAPBOX_STYLE = "mapbox/light-v11"  # стиль карты


# ─────────────────────────────────────────────────────────────────────────────
# 1. ПАРСИНГ GPX
# ─────────────────────────────────────────────────────────────────────────────

def parse_gpx(gpx_path: Path) -> dict:
    """
    Читает GPX-файл и возвращает словарь с:
      - name:   название трека
      - points: список точек [{lat, lon, ele, time}, ...]
    """
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    # GPX использует пространство имён
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}

    # Название трека (берём из <trk><name> или из имени файла)
    name_el = root.find(".//gpx:trk/gpx:name", ns)
    track_name = name_el.text.strip() if name_el is not None else gpx_path.stem

    # Собираем все точки из всех сегментов
    points = []
    for trkpt in root.findall(".//gpx:trkpt", ns):
        lat = float(trkpt.get("lat"))
        lon = float(trkpt.get("lon"))

        ele_el  = trkpt.find("gpx:ele",  ns)
        time_el = trkpt.find("gpx:time", ns)

        ele  = float(ele_el.text)  if ele_el  is not None else 0.0
        time = time_el.text        if time_el is not None else None

        points.append({"lat": lat, "lon": lon, "ele": ele, "time": time})

    if not points:
        raise ValueError(f"В файле {gpx_path} не найдено ни одной точки трека.")

    return {"name": track_name, "points": points}


# ─────────────────────────────────────────────────────────────────────────────
# 2. ВЫЧИСЛЕНИЕ СТАТИСТИКИ
# ─────────────────────────────────────────────────────────────────────────────

def haversine_m(p1: dict, p2: dict) -> float:
    """Расстояние между двумя точками (lat/lon) в метрах."""
    R = 6_371_000
    lat1, lon1 = math.radians(p1["lat"]), math.radians(p1["lon"])
    lat2, lon2 = math.radians(p2["lat"]), math.radians(p2["lon"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def calc_stats(points: list) -> dict:
    """
    Вычисляет статистику маршрута:
      - total_dist_m   — общая дистанция в метрах
      - cum_dist_km    — накопленная дистанция по точкам (список, км)
      - ele_min/max    — минимальная/максимальная высота
      - ascent/descent — суммарный набор/сброс высоты
      - duration_s     — длительность в секундах
      - avg_speed_kmh  — средняя скорость (км/ч)
      - center_lat/lon — центр трека
      - start_time     — время старта (строка)
      - end_time       — время финиша (строка)
    """
    # Накопленная дистанция
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + haversine_m(points[i - 1], points[i]))
    total_dist_m = cum[-1]

    # Высоты
    eles = [p["ele"] for p in points]
    ele_min = min(eles)
    ele_max = max(eles)

    # Набор/сброс высоты
    ascent  = 0.0
    descent = 0.0
    for i in range(1, len(eles)):
        diff = eles[i] - eles[i - 1]
        if diff > 0:
            ascent  += diff
        else:
            descent += abs(diff)

    # Длительность
    duration_s  = 0.0
    start_time  = points[0]["time"]
    end_time    = points[-1]["time"]
    if start_time and end_time:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        try:
            t0 = datetime.strptime(start_time, fmt).replace(tzinfo=timezone.utc)
            t1 = datetime.strptime(end_time,   fmt).replace(tzinfo=timezone.utc)
            duration_s = (t1 - t0).total_seconds()
        except ValueError:
            pass

    # Средняя скорость
    avg_speed_kmh = 0.0
    if duration_s > 0:
        avg_speed_kmh = (total_dist_m / 1000) / (duration_s / 3600)

    # Центр трека
    center_lat = sum(p["lat"] for p in points) / len(points)
    center_lon = sum(p["lon"] for p in points) / len(points)

    # Форматирование длительности
    h = int(duration_s // 3600)
    m = int((duration_s % 3600) // 60)
    duration_str = f"{h}ч {m}м" if h > 0 else f"{m}м"

    # Форматирование даты старта
    date_str = ""
    if start_time:
        try:
            dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
            months = ["января","февраля","марта","апреля","мая","июня",
                      "июля","августа","сентября","октября","ноября","декабря"]
            date_str = f"{dt.day} {months[dt.month-1]} {dt.year}"
        except ValueError:
            date_str = start_time[:10]

    return {
        "total_dist_m":  total_dist_m,
        "total_dist_km": total_dist_m / 1000,
        "cum_dist_km":   [round(d / 1000, 4) for d in cum],
        "ele_min":       ele_min,
        "ele_max":       ele_max,
        "ascent":        ascent,
        "descent":       descent,
        "duration_s":    duration_s,
        "duration_str":  duration_str,
        "avg_speed_kmh": avg_speed_kmh,
        "center_lat":    center_lat,
        "center_lon":    center_lon,
        "start_time":    start_time,
        "end_time":      end_time,
        "date_str":      date_str,
        "point_count":   len(points),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. ГЕНЕРАЦИЯ HTML
# ─────────────────────────────────────────────────────────────────────────────

def render_html(track_name: str, points: list, stats: dict, out_path: Path):
    """
    Генерирует автономный HTML-файл с:
      - интерактивной картой Leaflet на подложке MapBox Light
      - треком с градиентом по высоте
      - маркерами старта и финиша
      - графиком профиля высот (Chart.js)
      - синхронизацией: наведение на график → маркер на карте
      - панелью статистики
    """
    # Подготовка данных для JS
    latlngs_js = json.dumps([[p["lat"], p["lon"]] for p in points], separators=(",", ":"))
    eles_js    = json.dumps([p["ele"] for p in points],             separators=(",", ":"))
    dist_km_js = json.dumps(stats["cum_dist_km"],                   separators=(",", ":"))

    # Подставляем токен и стиль из конфига (строковая интерполяция Python,
    # не f-строка внутри HTML — используем .format() чтобы не конфликтовать
    # с фигурными скобками Leaflet/JS)
    mapbox_url = (
        "https://api.mapbox.com/styles/v1/"
        + MAPBOX_STYLE
        + "/tiles/{z}/{x}/{y}@2x?access_token="
        + MAPBOX_TOKEN
    )

    html = (
        "<!DOCTYPE html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '  <meta charset="UTF-8"/>\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>\n'
        f"  <title>{track_name}</title>\n"
        '  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>\n'
        '  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n'
        '  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>\n'
        "  <style>\n"
        "    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "    body {\n"
        '      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;\n'
        "      background: #f0f4f8;\n"
        "      color: #1a202c;\n"
        "      height: 100vh;\n"
        "      display: flex;\n"
        "      flex-direction: column;\n"
        "      overflow: hidden;\n"
        "    }\n"
        "    header {\n"
        "      background: linear-gradient(135deg, #1e4d8c 0%, #2b6cb0 100%);\n"
        "      color: #fff;\n"
        "      padding: 13px 22px;\n"
        "      display: flex;\n"
        "      align-items: center;\n"
        "      gap: 13px;\n"
        "      box-shadow: 0 2px 8px rgba(0,0,0,0.2);\n"
        "      flex-shrink: 0;\n"
        "    }\n"
        "    header svg { flex-shrink: 0; }\n"
        "    header h1 { font-size: 1.2rem; font-weight: 700; }\n"
        "    header p  { font-size: 0.77rem; opacity: 0.82; margin-top: 2px; }\n"
        "    .stats {\n"
        "      display: flex; flex-wrap: wrap; gap: 8px;\n"
        "      padding: 10px 18px;\n"
        "      background: #fff;\n"
        "      border-bottom: 1px solid #e2e8f0;\n"
        "      flex-shrink: 0;\n"
        "    }\n"
        "    .stat {\n"
        "      flex: 1 1 90px;\n"
        "      background: #f7fafc;\n"
        "      border: 1px solid #e2e8f0;\n"
        "      border-radius: 10px;\n"
        "      padding: 7px 12px;\n"
        "      display: flex; flex-direction: column; align-items: center;\n"
        "    }\n"
        "    .stat-value { font-size: 1.1rem; font-weight: 700; color: #2b6cb0; }\n"
        "    .stat-label { font-size: 0.65rem; color: #718096; text-transform: uppercase;\n"
        "                  letter-spacing: 0.05em; margin-top: 2px; white-space: nowrap; }\n"
        "    .main { display: flex; flex-direction: column; flex: 1 1 auto; overflow: hidden; }\n"
        "    #map  { flex: 1 1 auto; z-index: 0; }\n"
        "    .elev-panel {\n"
        "      flex: 0 0 180px;\n"
        "      background: #fff;\n"
        "      border-top: 1px solid #e2e8f0;\n"
        "      padding: 10px 16px 8px;\n"
        "      display: flex; flex-direction: column;\n"
        "    }\n"
        "    .elev-panel h2 {\n"
        "      font-size: 0.7rem; font-weight: 600; color: #4a5568;\n"
        "      text-transform: uppercase; letter-spacing: 0.06em;\n"
        "      margin-bottom: 6px; flex-shrink: 0;\n"
        "    }\n"
        "    .elev-wrap { position: relative; flex: 1 1 auto; }\n"
        "    #elevChart { width: 100% !important; height: 100% !important; }\n"
        "    .leaflet-popup-content-wrapper { border-radius: 10px; font-size: 0.82rem; }\n"
        "    .popup b { color: #2b6cb0; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "\n"
        "<header>\n"
        '  <svg width="38" height="38" viewBox="0 0 38 38" fill="none">\n'
        '    <circle cx="19" cy="19" r="19" fill="rgba(255,255,255,0.15)"/>\n'
        '    <path d="M19 9C14 9 10 13 10 18C10 24 19 32 19 32C19 32 28 24 28 18C28 13 24 9 19 9Z"\n'
        '          fill="#fff" opacity="0.9"/>\n'
        '    <circle cx="19" cy="18" r="4.5" fill="#2b6cb0"/>\n'
        "  </svg>\n"
        "  <div>\n"
        f"    <h1>{track_name}</h1>\n"
        f"    <p>{stats['date_str']} &nbsp;·&nbsp; {stats['point_count']} точек GPS</p>\n"
        "  </div>\n"
        "</header>\n"
        "\n"
        '<div class="stats">\n'
        f'  <div class="stat"><span class="stat-value">{stats["total_dist_km"]:.2f} км</span><span class="stat-label">Расстояние</span></div>\n'
        f'  <div class="stat"><span class="stat-value">{stats["duration_str"]}</span><span class="stat-label">Длительность</span></div>\n'
        f'  <div class="stat"><span class="stat-value">{stats["avg_speed_kmh"]:.1f} км/ч</span><span class="stat-label">Ср. скорость</span></div>\n'
        f'  <div class="stat"><span class="stat-value">{stats["ele_max"]:.0f} м</span><span class="stat-label">Макс. высота</span></div>\n'
        f'  <div class="stat"><span class="stat-value">{stats["ele_min"]:.0f} м</span><span class="stat-label">Мин. высота</span></div>\n'
        f'  <div class="stat"><span class="stat-value">+{stats["ascent"]:.0f} м</span><span class="stat-label">Набор высоты</span></div>\n'
        f'  <div class="stat"><span class="stat-value">−{stats["descent"]:.0f} м</span><span class="stat-label">Сброс высоты</span></div>\n'
        f'  <div class="stat"><span class="stat-value">{stats["point_count"]}</span><span class="stat-label">Точек трека</span></div>\n'
        "</div>\n"
        "\n"
        '<div class="main">\n'
        '  <div style="position:relative; flex:1 1 auto; min-height:0;">\n'
        '    <div id="map" style="height:100%;"></div>\n'
        "  </div>\n"
        '  <div class="elev-panel">\n'
        "    <h2>Профиль высот — наведите курсор для позиции на карте</h2>\n"
        '    <div class="elev-wrap"><canvas id="elevChart"></canvas></div>\n'
        "  </div>\n"
        "</div>\n"
        "\n"
        "<script>\n"
        "// ── Данные трека ─────────────────────────────────────────────────────────\n"
        f"const LATLNGS = {latlngs_js};\n"
        f"const ELES    = {eles_js};\n"
        f"const DIST_KM = {dist_km_js};\n"
        "\n"
        "const ELE_MIN = Math.min(...ELES);\n"
        "const ELE_MAX = Math.max(...ELES);\n"
        "\n"
        "// ── Карта на подложке MapBox Light ───────────────────────────────────────\n"
        "const centerLat = LATLNGS.reduce((s,p) => s+p[0], 0) / LATLNGS.length;\n"
        "const centerLon = LATLNGS.reduce((s,p) => s+p[1], 0) / LATLNGS.length;\n"
        "\n"
        "const map = L.map('map').setView([centerLat, centerLon], 14);\n"
        "\n"
        "L.tileLayer(\n"
        f"  '{mapbox_url}',\n"
        "  {\n"
        "    attribution: '© <a href=\"https://www.mapbox.com/about/maps/\">Mapbox</a> "
        "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>',\n"
        "    tileSize: 512,\n"
        "    zoomOffset: -1,\n"
        "    maxZoom: 22\n"
        "  }\n"
        ").addTo(map);\n"
        "\n"
        "// ── Трек с градиентом по высоте ──────────────────────────────────────────\n"
        "function eleColor(ele) {\n"
        "  // зелёный (низко) → жёлтый → красный (высоко)\n"
        "  const t = Math.max(0, Math.min(1, (ele - ELE_MIN) / (ELE_MAX - ELE_MIN || 1)));\n"
        "  const r = Math.round(30  + t * 210);\n"
        "  const g = Math.round(180 - t * 140);\n"
        "  const b = Math.round(60  - t * 40);\n"
        "  return `rgb(${r},${g},${b})`;\n"
        "}\n"
        "\n"
        "for (let i = 1; i < LATLNGS.length; i++) {\n"
        "  L.polyline([LATLNGS[i-1], LATLNGS[i]], {\n"
        "    color:    eleColor(ELES[i]),\n"
        "    weight:   5,\n"
        "    opacity:  0.92,\n"
        "    lineCap:  'round',\n"
        "    lineJoin: 'round'\n"
        "  }).addTo(map);\n"
        "}\n"
        "\n"
        "// Тонкая тёмная обводка для читаемости на светлой подложке\n"
        "L.polyline(LATLNGS, {\n"
        "  color: 'rgba(0,0,0,0.12)', weight: 7, opacity: 1, lineCap: 'round'\n"
        "}).addTo(map);\n"
        "\n"
        "// ── Маркеры старта / финиша ───────────────────────────────────────────────\n"
        "function circleIcon(color) {\n"
        "  return L.divIcon({\n"
        "    className: '',\n"
        "    html: `<div style=\"width:16px;height:16px;border-radius:50%;\n"
        "                background:${color};border:3px solid #fff;\n"
        "                box-shadow:0 1px 5px rgba(0,0,0,.4)\"></div>`,\n"
        "    iconAnchor: [8, 8]\n"
        "  });\n"
        "}\n"
        "\n"
        "L.marker(LATLNGS[0], {icon: circleIcon('#22c55e')}).addTo(map)\n"
        "  .bindPopup(`<div class=\"popup\"><b>Старт</b><br>\n"
        "    Высота: ${ELES[0]} м<br>Пройдено: 0.00 км</div>`);\n"
        "\n"
        "L.marker(LATLNGS[LATLNGS.length-1], {icon: circleIcon('#ef4444')}).addTo(map)\n"
        "  .bindPopup(`<div class=\"popup\"><b>Финиш</b><br>\n"
        "    Высота: ${ELES[ELES.length-1]} м<br>\n"
        "    Пройдено: ${DIST_KM[DIST_KM.length-1].toFixed(2)} км</div>`);\n"
        "\n"
        "map.fitBounds(L.polyline(LATLNGS).getBounds(), {padding: [28, 28]});\n"
        "\n"
        "// ── Скользящий маркер (синхронизация карта ↔ график) ─────────────────────\n"
        "const sliderMarker = L.marker(LATLNGS[0], {\n"
        "  icon: L.divIcon({\n"
        "    className: '',\n"
        "    html: `<div style=\"width:13px;height:13px;border-radius:50%;\n"
        "                background:#2b6cb0;border:2px solid #fff;\n"
        "                box-shadow:0 1px 4px rgba(0,0,0,.4)\"></div>`,\n"
        "    iconAnchor: [6.5, 6.5]\n"
        "  }),\n"
        "  interactive: false,\n"
        "  zIndexOffset: 1000\n"
        "}).addTo(map);\n"
        "sliderMarker.setOpacity(0);\n"
        "\n"
        "// ── График профиля высот ──────────────────────────────────────────────────\n"
        "const ctx = document.getElementById('elevChart').getContext('2d');\n"
        "const gradient = ctx.createLinearGradient(0, 0, 0, 160);\n"
        "gradient.addColorStop(0,   'rgba(43,108,176,0.35)');\n"
        "gradient.addColorStop(0.6, 'rgba(43,108,176,0.12)');\n"
        "gradient.addColorStop(1,   'rgba(43,108,176,0.02)');\n"
        "\n"
        "new Chart(ctx, {\n"
        "  type: 'line',\n"
        "  data: {\n"
        "    labels: DIST_KM,\n"
        "    datasets: [{\n"
        "      data: ELES,\n"
        "      borderColor: '#2b6cb0',\n"
        "      borderWidth: 2,\n"
        "      backgroundColor: gradient,\n"
        "      fill: true,\n"
        "      pointRadius: 0,\n"
        "      tension: 0.35\n"
        "    }]\n"
        "  },\n"
        "  options: {\n"
        "    responsive: true,\n"
        "    maintainAspectRatio: false,\n"
        "    animation: false,\n"
        "    interaction: { mode: 'index', intersect: false },\n"
        "    plugins: {\n"
        "      legend: { display: false },\n"
        "      tooltip: {\n"
        "        callbacks: {\n"
        "          title: items => parseFloat(items[0].label).toFixed(2) + ' км',\n"
        "          label: items => 'Высота: ' + items.raw + ' м'\n"
        "        }\n"
        "      }\n"
        "    },\n"
        "    scales: {\n"
        "      x: {\n"
        "        ticks: {\n"
        "          maxTicksLimit: 9,\n"
        "          callback: (v) => DIST_KM[v] !== undefined\n"
        "            ? Number(DIST_KM[v]).toFixed(1) + ' км' : ''\n"
        "        },\n"
        "        grid: { color: '#edf2f7' }\n"
        "      },\n"
        "      y: {\n"
        "        ticks: { callback: v => v + ' м', maxTicksLimit: 5 },\n"
        "        grid: { color: '#edf2f7' }\n"
        "      }\n"
        "    },\n"
        "    onHover: (event, elements) => {\n"
        "      if (elements.length) {\n"
        "        const idx = elements[0].index;\n"
        "        sliderMarker.setLatLng(LATLNGS[idx]);\n"
        "        sliderMarker.setOpacity(1);\n"
        "      } else {\n"
        "        sliderMarker.setOpacity(0);\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "});\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"✓ HTML сохранён: {out_path}")
    print(f"  Точек:        {stats['point_count']}")
    print(f"  Дистанция:    {stats['total_dist_km']:.2f} км")
    print(f"  Длительность: {stats['duration_str']}")
    print(f"  Высоты:       {stats['ele_min']:.0f}–{stats['ele_max']:.0f} м")


# ─────────────────────────────────────────────────────────────────────────────
# 4. ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 3:
        print("Использование: python gpx_to_html.py <входной.gpx> <выходной.html>")
        sys.exit(1)

    gpx_path = Path(sys.argv[1])
    out_path  = Path(sys.argv[2])

    if not gpx_path.exists():
        print(f"Ошибка: файл не найден — {gpx_path}")
        sys.exit(1)

    if gpx_path.suffix.lower() != ".gpx":
        print(f"Ошибка: ожидается .gpx файл, получен {gpx_path.suffix}")
        sys.exit(1)

    # Проверяем наличие токена
    if not MAPBOX_TOKEN:
        print("Ошибка: переменная окружения MAPBOX_TOKEN не задана.")
        print("")
        print("Локально (macOS/Linux):")
        print('  export MAPBOX_TOKEN="pk.eyJ1Ijoiваш_токен..."')
        print("")
        print("GitHub Actions:")
        print("  Settings → Secrets and variables → Actions → New repository secret")
        print("  Name: MAPBOX_TOKEN")
        sys.exit(1)

    print(f"Обработка: {gpx_path}")
    track  = parse_gpx(gpx_path)
    stats  = calc_stats(track["points"])
    render_html(track["name"], track["points"], stats, out_path)


if __name__ == "__main__":
    main()
