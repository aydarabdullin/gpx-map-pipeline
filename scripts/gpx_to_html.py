#!/usr/bin/env python3
#https://github.com/aydarabdullin/gpx-map-pipeline.git
"""
gpx_to_html.py — конвертер GPX-трека в автономную HTML-страницу с картой.

Использование:
    python gpx_to_html.py <входной.gpx> <выходной.html>

Пример:
    python gpx_to_html.py data/track.gpx output/index.html

Зависимости: только стандартная библиотека Python (xml, math, json, sys, pathlib).
"""

import sys
import math
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone


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
      - интерактивной картой Leaflet (3 подложки на выбор)
      - треком с градиентом по высоте
      - маркерами старта и финиша
      - графиком профиля высот (Chart.js)
      - синхронизацией: наведение на график → маркер на карте
      - панелью статистики
    """
    # Подготовка данных для JS
    latlngs_js  = json.dumps([[p["lat"], p["lon"]] for p in points], separators=(",", ":"))
    eles_js     = json.dumps([p["ele"] for p in points],             separators=(",", ":"))
    dist_km_js  = json.dumps(stats["cum_dist_km"],                   separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{track_name}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0f4f8;
      color: #1a202c;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    /* ── Шапка ── */
    header {{
      background: linear-gradient(135deg, #1e4d8c 0%, #2b6cb0 100%);
      color: #fff;
      padding: 13px 22px;
      display: flex;
      align-items: center;
      gap: 13px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      flex-shrink: 0;
    }}
    header svg {{ flex-shrink: 0; }}
    header h1 {{ font-size: 1.2rem; font-weight: 700; }}
    header p  {{ font-size: 0.77rem; opacity: 0.82; margin-top: 2px; }}

    /* ── Статистика ── */
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 18px;
      background: #fff;
      border-bottom: 1px solid #e2e8f0;
      flex-shrink: 0;
    }}
    .stat {{
      flex: 1 1 90px;
      background: #f7fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 7px 12px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    .stat-value {{ font-size: 1.1rem; font-weight: 700; color: #2b6cb0; }}
    .stat-label {{ font-size: 0.65rem; color: #718096; text-transform: uppercase;
                   letter-spacing: 0.05em; margin-top: 2px; white-space: nowrap; }}

    /* ── Основная область ── */
    .main {{ display: flex; flex-direction: column; flex: 1 1 auto; overflow: hidden; }}

    #map {{ flex: 1 1 auto; z-index: 0; }}

    /* ── График высот ── */
    .elev-panel {{
      flex: 0 0 180px;
      background: #fff;
      border-top: 1px solid #e2e8f0;
      padding: 10px 16px 8px;
      display: flex;
      flex-direction: column;
    }}
    .elev-panel h2 {{
      font-size: 0.7rem; font-weight: 600; color: #4a5568;
      text-transform: uppercase; letter-spacing: 0.06em;
      margin-bottom: 6px; flex-shrink: 0;
    }}
    .elev-wrap {{ position: relative; flex: 1 1 auto; }}
    #elevChart {{ width: 100% !important; height: 100% !important; }}

    /* ── Переключатель слоёв ── */
    #layerCtrl {{
      position: absolute; top: 12px; right: 12px; z-index: 900;
      background: rgba(255,255,255,0.96); border-radius: 8px;
      padding: 8px 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.14);
      font-size: 0.78rem;
    }}
    #layerCtrl strong {{ display: block; color: #4a5568; margin-bottom: 5px; font-size: 0.75rem; }}
    #layerCtrl label  {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 3px; }}
    #layerCtrl input  {{ accent-color: #2b6cb0; }}

    /* ── Всплывашки Leaflet ── */
    .leaflet-popup-content-wrapper {{ border-radius: 10px; font-size: 0.82rem; }}
    .popup b {{ color: #2b6cb0; }}
  </style>
</head>
<body>

<header>
  <svg width="38" height="38" viewBox="0 0 38 38" fill="none">
    <circle cx="19" cy="19" r="19" fill="rgba(255,255,255,0.15)"/>
    <path d="M19 9C14 9 10 13 10 18C10 24 19 32 19 32C19 32 28 24 28 18C28 13 24 9 19 9Z"
          fill="#fff" opacity="0.9"/>
    <circle cx="19" cy="18" r="4.5" fill="#2b6cb0"/>
  </svg>
  <div>
    <h1>{track_name}</h1>
    <p>{stats["date_str"]} &nbsp;·&nbsp; {stats["point_count"]} точек GPS</p>
  </div>
</header>

<div class="stats">
  <div class="stat">
    <span class="stat-value">{stats["total_dist_km"]:.2f} км</span>
    <span class="stat-label">Расстояние</span>
  </div>
  <div class="stat">
    <span class="stat-value">{stats["duration_str"]}</span>
    <span class="stat-label">Длительность</span>
  </div>
  <div class="stat">
    <span class="stat-value">{stats["avg_speed_kmh"]:.1f} км/ч</span>
    <span class="stat-label">Ср. скорость</span>
  </div>
  <div class="stat">
    <span class="stat-value">{stats["ele_max"]:.0f} м</span>
    <span class="stat-label">Макс. высота</span>
  </div>
  <div class="stat">
    <span class="stat-value">{stats["ele_min"]:.0f} м</span>
    <span class="stat-label">Мин. высота</span>
  </div>
  <div class="stat">
    <span class="stat-value">+{stats["ascent"]:.0f} м</span>
    <span class="stat-label">Набор высоты</span>
  </div>
  <div class="stat">
    <span class="stat-value">−{stats["descent"]:.0f} м</span>
    <span class="stat-label">Сброс высоты</span>
  </div>
  <div class="stat">
    <span class="stat-value">{stats["point_count"]}</span>
    <span class="stat-label">Точек трека</span>
  </div>
</div>

<div class="main">
  <div style="position:relative; flex:1 1 auto; min-height:0;">
    <div id="map" style="height:100%;"></div>
    <div id="layerCtrl">
      <strong>Подложка карты</strong>
      <label><input type="radio" name="layer" value="osm"  checked> OpenStreetMap</label>
      <label><input type="radio" name="layer" value="sat"> Спутник (Esri)</label>
      <label><input type="radio" name="layer" value="topo"> Рельеф (CartoDB)</label>
    </div>
  </div>
  <div class="elev-panel">
    <h2>Профиль высот — наведите курсор для позиции на карте</h2>
    <div class="elev-wrap">
      <canvas id="elevChart"></canvas>
    </div>
  </div>
</div>

<script>
// ── Данные трека (встроены скриптом, внешних файлов не нужно) ─────────────
const LATLNGS = {latlngs_js};
const ELES    = {eles_js};
const DIST_KM = {dist_km_js};

const ELE_MIN = Math.min(...ELES);
const ELE_MAX = Math.max(...ELES);

// ── Карта ─────────────────────────────────────────────────────────────────
const centerLat = LATLNGS.reduce((s,p) => s+p[0], 0) / LATLNGS.length;
const centerLon = LATLNGS.reduce((s,p) => s+p[1], 0) / LATLNGS.length;

const map = L.map('map').setView([centerLat, centerLon], 14);

// Три подложки на выбор
const LAYERS = {{
  osm:  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
          attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
          maxZoom: 19
        }}),
  sat:  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
          attribution: '© Esri',
          maxZoom: 19
        }}),
  topo: L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
          attribution: '© CartoDB',
          maxZoom: 19
        }})
}};
LAYERS.osm.addTo(map);

document.querySelectorAll('input[name="layer"]').forEach(radio => {{
  radio.addEventListener('change', () => {{
    Object.values(LAYERS).forEach(l => map.removeLayer(l));
    LAYERS[radio.value].addTo(map);
  }});
}});

// ── Трек с градиентом цвета по высоте ─────────────────────────────────────
function eleColor(ele) {{
  // зелёный (низко) → жёлтый → красный (высоко)
  const t = Math.max(0, Math.min(1, (ele - ELE_MIN) / (ELE_MAX - ELE_MIN || 1)));
  const r = Math.round(30  + t * 210);
  const g = Math.round(180 - t * 140);
  const b = Math.round(60  - t * 40);
  return `rgb(${{r}},${{g}},${{b}})`;
}}

for (let i = 1; i < LATLNGS.length; i++) {{
  L.polyline([LATLNGS[i-1], LATLNGS[i]], {{
    color:   eleColor(ELES[i]),
    weight:  5,
    opacity: 0.92,
    lineCap: 'round',
    lineJoin: 'round'
  }}).addTo(map);
}}

// Тонкая обводка для читаемости на тёмных подложках
L.polyline(LATLNGS, {{
  color: 'rgba(0,0,0,0.15)', weight: 7, opacity: 1, lineCap: 'round'
}}).addTo(map);

// ── Маркеры старта / финиша ────────────────────────────────────────────────
function circleIcon(color) {{
  return L.divIcon({{
    className: '',
    html: `<div style="width:16px;height:16px;border-radius:50%;
                background:${{color}};border:3px solid #fff;
                box-shadow:0 1px 5px rgba(0,0,0,.4)"></div>`,
    iconAnchor: [8, 8]
  }});
}}

L.marker(LATLNGS[0], {{icon: circleIcon('#22c55e')}}).addTo(map)
  .bindPopup(`<div class="popup"><b>Старт</b><br>
    Высота: ${{ELES[0]}} м<br>
    Пройдено: 0.00 км</div>`);

L.marker(LATLNGS[LATLNGS.length-1], {{icon: circleIcon('#ef4444')}}).addTo(map)
  .bindPopup(`<div class="popup"><b>Финиш</b><br>
    Высота: ${{ELES[ELES.length-1]}} м<br>
    Пройдено: ${{DIST_KM[DIST_KM.length-1].toFixed(2)}} км</div>`);

map.fitBounds(L.polyline(LATLNGS).getBounds(), {{padding: [28, 28]}});

// ── Скользящий маркер (синхронизация карта ↔ график) ─────────────────────
const sliderMarker = L.marker(LATLNGS[0], {{
  icon: L.divIcon({{
    className: '',
    html: `<div style="width:13px;height:13px;border-radius:50%;
                background:#2b6cb0;border:2px solid #fff;
                box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
    iconAnchor: [6.5, 6.5]
  }}),
  interactive: false,
  zIndexOffset: 1000
}}).addTo(map);
sliderMarker.setOpacity(0);

// ── График профиля высот ──────────────────────────────────────────────────
const ctx = document.getElementById('elevChart').getContext('2d');

const gradient = ctx.createLinearGradient(0, 0, 0, 160);
gradient.addColorStop(0,   'rgba(43,108,176,0.35)');
gradient.addColorStop(0.6, 'rgba(43,108,176,0.12)');
gradient.addColorStop(1,   'rgba(43,108,176,0.02)');

new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: DIST_KM,
    datasets: [{{
      data: ELES,
      borderColor: '#2b6cb0',
      borderWidth: 2,
      backgroundColor: gradient,
      fill: true,
      pointRadius: 0,
      tension: 0.35
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          title: items => parseFloat(items[0].label).toFixed(2) + ' км',
          label: items => 'Высота: ' + items.raw + ' м'
        }}
      }}
    }},
    scales: {{
      x: {{
        ticks: {{
          maxTicksLimit: 9,
          callback: (v) => DIST_KM[v] !== undefined
            ? Number(DIST_KM[v]).toFixed(1) + ' км' : ''
        }},
        grid: {{ color: '#edf2f7' }}
      }},
      y: {{
        ticks: {{ callback: v => v + ' м', maxTicksLimit: 5 }},
        grid: {{ color: '#edf2f7' }}
      }}
    }},
    // При наведении — двигаем маркер на карте
    onHover: (event, elements) => {{
      if (elements.length) {{
        const idx = elements[0].index;
        sliderMarker.setLatLng(LATLNGS[idx]);
        sliderMarker.setOpacity(1);
      }} else {{
        sliderMarker.setOpacity(0);
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"✓ HTML сохранён: {out_path}")
    print(f"  Точек:      {stats['point_count']}")
    print(f"  Дистанция:  {stats['total_dist_km']:.2f} км")
    print(f"  Длительность: {stats['duration_str']}")
    print(f"  Высоты:     {stats['ele_min']:.0f}–{stats['ele_max']:.0f} м")


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

    print(f"Обработка: {gpx_path}")
    track  = parse_gpx(gpx_path)
    stats  = calc_stats(track["points"])
    render_html(track["name"], track["points"], stats, out_path)


if __name__ == "__main__":
    main()
