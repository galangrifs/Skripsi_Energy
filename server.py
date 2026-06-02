"""
============================================================
  WEB SERVER DASHBOARD - MONITORING ENERGI LISTRIK
  Framework : Flask (Python)
  Database  : SQLite (lokal, tidak perlu install terpisah)
  Fungsi    : Terima data ESP32, simpan ke DB, tampilkan dashboard
  Author    : Galang Rif Setiady (Skripsi UNPAM 2026)
============================================================

CARA MENJALANKAN:
  1. Install dependencies:
     pip install flask flask-cors

  2. Jalankan server:
     python server.py

  3. Buka browser: http://localhost:5000
  4. Ganti SERVER_URL di ESP32 dengan IP komputer ini
     (cari IP dengan: ipconfig / ifconfig)
============================================================
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import csv
import io
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Railway: simpan di /data agar tidak hilang saat restart
# Lokal: otomatis fallback ke folder project
import os
DATA_DIR = "/data" if os.path.exists("/data") else "."
DB_PATH  = os.path.join(DATA_DIR, "energy_data.db")

# ============================================================
#  INISIALISASI DATABASE
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS energy_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            voltage   REAL,
            current   REAL,
            power     REAL,
            energy    REAL,
            frequency REAL,
            pf        REAL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] Database siap:", os.path.abspath(DB_PATH))

# ============================================================
#  API: TERIMA DATA DARI ESP32
# ============================================================
@app.route("/api/data", methods=["POST"])
def receive_data():
    try:
        data = request.get_json(force=True)

        # Validasi field yang wajib ada
        required = ["timestamp", "voltage", "current", "power", "energy"]
        for field in required:
            if field not in data:
                return jsonify({"status": "error", "message": f"Field '{field}' tidak ada"}), 400

        # Simpan ke database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO energy_log (timestamp, voltage, current, power, energy, frequency, pf)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["timestamp"],
            data.get("voltage", 0),
            data.get("current", 0),
            data.get("power", 0),
            data.get("energy", 0),
            data.get("frequency", 50.0),
            data.get("pf", 1.0)
        ))
        conn.commit()
        conn.close()

        print(f"[DATA] {data['timestamp']} | "
              f"{data['voltage']}V | {data['current']}A | "
              f"{data['power']}W | {data['energy']}kWh")

        return jsonify({"status": "ok", "message": "Data tersimpan"}), 201

    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================
#  API: AMBIL DATA TERBARU (untuk grafik real-time)
# ============================================================
@app.route("/api/latest", methods=["GET"])
def get_latest():
    limit = request.args.get("limit", 100, type=int)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM energy_log
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    rows.reverse()  # urutkan dari yang lama ke baru
    return jsonify(rows)

# ============================================================
#  API: STATISTIK RINGKASAN
# ============================================================
@app.route("/api/stats", methods=["GET"])
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT
            COUNT(*)        as total_records,
            AVG(voltage)    as avg_voltage,
            AVG(current)    as avg_current,
            AVG(power)      as avg_power,
            MAX(power)      as max_power,
            MIN(power)      as min_power,
            MAX(energy)     as total_energy
        FROM energy_log
    """)
    row = c.fetchone()
    conn.close()

    return jsonify({
        "total_records": row[0],
        "avg_voltage":   round(row[1] or 0, 2),
        "avg_current":   round(row[2] or 0, 3),
        "avg_power":     round(row[3] or 0, 2),
        "max_power":     round(row[4] or 0, 2),
        "min_power":     round(row[5] or 0, 2),
        "total_energy":  round(row[6] or 0, 4),
    })

# ============================================================
#  EXPORT CSV (untuk dataset training LSTM)
# ============================================================
@app.route("/export/csv", methods=["GET"])
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, voltage, current, power, energy, frequency, pf FROM energy_log ORDER BY id")
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "voltage", "current", "power", "energy", "frequency", "pf"])
    writer.writerows(rows)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=energy_data.csv"}
    )

# ============================================================
#  DASHBOARD HTML (tampilan web sederhana)
# ============================================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitoring Energi Listrik - Skripsi Galang</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
  header { background: #1e3a5f; padding: 20px 30px; }
  header h1 { font-size: 1.4rem; color: #60a5fa; }
  header p  { font-size: 0.85rem; color: #94a3b8; margin-top: 4px; }
  .container { padding: 24px 30px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border-left: 4px solid #3b82f6; }
  .card .label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }
  .card .value { font-size: 1.8rem; font-weight: 700; color: #f1f5f9; margin-top: 6px; }
  .card .unit  { font-size: 0.8rem; color: #60a5fa; }
  .card.green  { border-left-color: #22c55e; }
  .card.yellow { border-left-color: #f59e0b; }
  .card.red    { border-left-color: #ef4444; }
  .card.purple { border-left-color: #a78bfa; }
  .chart-wrap { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .chart-wrap h2 { font-size: 1rem; color: #94a3b8; margin-bottom: 16px; }
  .actions { display: flex; gap: 12px; margin-bottom: 20px; }
  .btn { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-size: 0.9rem; font-weight: 600; }
  .btn-primary { background: #3b82f6; color: white; }
  .btn-green   { background: #22c55e; color: white; }
  .btn:hover   { opacity: 0.85; }
  .status { font-size: 0.8rem; color: #94a3b8; margin-top: 8px; }
  #statusDot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e; margin-right: 6px; }
</style>
</head>
<body>
<header>
  <h1>⚡ Monitoring Energi Listrik Rumah Tangga</h1>
  <p>Skripsi: Galang Rif Setiady &nbsp;|&nbsp; UNPAM 2026 &nbsp;|&nbsp; ESP32 + PZEM-004T + LSTM</p>
</header>

<div class="container">
  <!-- Status & Actions -->
  <div class="actions">
    <button class="btn btn-primary" onclick="fetchData()">🔄 Refresh</button>
    <a href="/export/csv"><button class="btn btn-green">📥 Export CSV</button></a>
  </div>
  <p class="status"><span id="statusDot"></span><span id="statusText">Memuat data...</span></p>

  <!-- Kartu Parameter -->
  <div class="cards" style="margin-top:16px;">
    <div class="card">
      <div class="label">Tegangan</div>
      <div class="value" id="voltage">--</div>
      <div class="unit">Volt</div>
    </div>
    <div class="card green">
      <div class="label">Arus</div>
      <div class="value" id="current">--</div>
      <div class="unit">Ampere</div>
    </div>
    <div class="card yellow">
      <div class="label">Daya Aktif</div>
      <div class="value" id="power">--</div>
      <div class="unit">Watt</div>
    </div>
    <div class="card red">
      <div class="label">Energi</div>
      <div class="value" id="energy">--</div>
      <div class="unit">kWh</div>
    </div>
    <div class="card purple">
      <div class="label">Total Data</div>
      <div class="value" id="totalRecords">--</div>
      <div class="unit">records</div>
    </div>
  </div>

  <!-- Grafik Daya -->
  <div class="chart-wrap">
    <h2>📊 Grafik Daya Aktif (Watt) - Real-time</h2>
    <canvas id="powerChart" height="100"></canvas>
  </div>

  <!-- Grafik Tegangan -->
  <div class="chart-wrap">
    <h2>📈 Grafik Tegangan (Volt)</h2>
    <canvas id="voltageChart" height="80"></canvas>
  </div>
</div>

<script>
let powerChart, voltageChart;

function initCharts() {
  const commonOptions = {
    responsive: true,
    animation: false,
    scales: {
      x: { ticks: { color: '#64748b', maxTicksLimit: 10 }, grid: { color: '#1e293b' } },
      y: { ticks: { color: '#64748b' }, grid: { color: '#334155' } }
    },
    plugins: { legend: { labels: { color: '#94a3b8' } } }
  };

  powerChart = new Chart(document.getElementById('powerChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [{ label: 'Daya (W)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { ...commonOptions }
  });

  voltageChart = new Chart(document.getElementById('voltageChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [{ label: 'Tegangan (V)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { ...commonOptions }
  });
}

async function fetchData() {
  try {
    // Ambil data terbaru
    const res   = await fetch('/api/latest?limit=100');
    const rows  = await res.json();
    const stats = await (await fetch('/api/stats')).json();

    if (rows.length === 0) {
      document.getElementById('statusText').textContent = 'Belum ada data. Tunggu data dari ESP32...';
      return;
    }

    // Update kartu
    const last = rows[rows.length - 1];
    document.getElementById('voltage').textContent      = last.voltage?.toFixed(1) ?? '--';
    document.getElementById('current').textContent      = last.current?.toFixed(3) ?? '--';
    document.getElementById('power').textContent        = last.power?.toFixed(1) ?? '--';
    document.getElementById('energy').textContent       = last.energy?.toFixed(4) ?? '--';
    document.getElementById('totalRecords').textContent = stats.total_records ?? '--';

    // Update status
    document.getElementById('statusText').textContent =
      `Data terakhir: ${last.timestamp} | Total: ${stats.total_records} records`;

    // Update grafik
    const labels  = rows.map(r => r.timestamp.substring(11, 16)); // HH:MM
    const powers   = rows.map(r => r.power);
    const voltages = rows.map(r => r.voltage);

    powerChart.data.labels            = labels;
    powerChart.data.datasets[0].data  = powers;
    powerChart.update();

    voltageChart.data.labels           = labels;
    voltageChart.data.datasets[0].data = voltages;
    voltageChart.update();

  } catch (e) {
    document.getElementById('statusText').textContent = 'Error mengambil data: ' + e.message;
    document.getElementById('statusDot').style.background = '#ef4444';
  }
}

// Init
initCharts();
fetchData();
// Auto-refresh setiap 30 detik
setInterval(fetchData, 30000);
</script>
</body>
</html>
"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    init_db()
    print("\n============================================")
    print("  Web Server Dashboard - Monitoring Energi")
    print("============================================")
    print(f"  Dashboard : http://localhost:5000")
    print(f"  API Data  : http://localhost:5000/api/data  (POST)")
    print(f"  Export CSV: http://localhost:5000/export/csv")
    print("  Tekan Ctrl+C untuk berhenti")
    print("============================================\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
