"""
api_dummy.py — JIAT Aquifer Recovery Simulation API (Dummy / GET Version)
=========================================================================
Simulasi endpoint GET untuk estimasi real-time pemulihan akuifer.
Berdasarkan logika deteksi fase dari note_rnd3.ipynb:
  - Merah  (#ef4444) : Fase Discharging (Pompa Aktif / Surut)
  - Kuning (#facc15) : Fase Recovery    (Sumur Memulih / Naik)
  - Abu-abu(#94a3b8) : Fase Stabil      (Idle / Istirahat)

Model prediksi recovery menggunakan exponential fitting:
  h(t) = h_max * (1 - exp(-t / tau))
  Estimasi recovery 95% selesai pada t = 3 * tau jam

Jalankan:
  uvicorn api_dummy:app --host localhost --port 8001 --reload
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import math
import random
from datetime import datetime, timedelta
from typing import Optional

# ==============================================================================
# INISIALISASI APP
# ==============================================================================
app = FastAPI(
    title="JIAT Aquifer Recovery — Dummy GET API",
    description=(
        "Simulasi endpoint GET real-time untuk estimasi pemulihan akuifer JIAT. "
        "Menggunakan model eksponensial Theis Recovery + deteksi fase (Pumping/Recovery/Stabil). "
        "Semua data adalah SIMULASI — tidak terhubung ke sensor asli."
    ),
    version="0.1.0-dummy",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ==============================================================================
# KONSTANTA SIMULASI AKUIFER (representasi Pos AWLR JIAT Pondok Kahuru)
# ==============================================================================
STATIC_TMA_M        = 3.50   # Kedalaman statis sebelum pompa (meter dari permukaan)
MAX_DRAWDOWN_M      = 5.80   # Kedalaman tertinggi saat pompa aktif penuh (meter)
THRESHOLD_STABLE    = 0.003  # Threshold delta untuk deteksi fase (meter/jam)
THRESHOLD_RECOVERY  = 0.10   # Jarak dari static_tma agar dianggap "pulih" (meter)
TAU_DEFAULT_JAM     = 6.0    # Time-constant eksponensial default (jam) — dari kalibrasi historis


# ==============================================================================
# UTILITY: Format Waktu
# ==============================================================================
def format_waktu(menit_total: float) -> str:
    total_menit = int(round(menit_total))
    if total_menit < 60:
        return f"{total_menit} Menit"
    menit  = total_menit % 60
    total_jam = total_menit // 60
    if total_jam < 24:
        return f"{total_jam} Jam {menit} Menit" if menit > 0 else f"{total_jam} Jam"
    hari = total_jam // 24
    jam  = total_jam % 24
    hasil = f"{hari} Hari"
    if jam  > 0: hasil += f" {jam} Jam"
    if menit > 0: hasil += f" {menit} Menit"
    return hasil


# ==============================================================================
# UTILITY: Deteksi Fase Berdasarkan Delta (sesuai logika notebook)
# ==============================================================================
def deteksi_fase(delta: float) -> dict:
    if delta < -THRESHOLD_STABLE:
        return {"fase": "DISCHARGING", "warna": "#ef4444", "label": "Pompa Aktif / Surut"}
    elif delta > THRESHOLD_STABLE:
        return {"fase": "RECOVERY",    "warna": "#facc15", "label": "Sumur Memulih / Naik"}
    else:
        return {"fase": "STABIL",      "warna": "#94a3b8", "label": "Idle / Istirahat"}


# ==============================================================================
# UTILITY: Estimasi Waktu Recovery (Model Eksponensial)
# ==============================================================================
def estimasi_recovery_jam(tma_saat_ini: float, tau: float = TAU_DEFAULT_JAM) -> dict:
    """
    Menghitung sisa waktu recovery aquifer dari posisi TMA saat ini.
    
    Args:
        tma_saat_ini : Kedalaman TMA saat ini (meter). Makin besar = makin dalam = belum pulih.
        tau          : Time constant aquifer (jam). Default dari kalibrasi historis.

    Returns:
        dict berisi persen recovery, ETA dalam jam, dan format string.
    """
    sisa_drawdown = tma_saat_ini - STATIC_TMA_M

    if sisa_drawdown <= THRESHOLD_RECOVERY:
        return {
            "persen_recovery": 100.0,
            "sisa_drawdown_m": round(sisa_drawdown, 4),
            "eta_jam": 0.0,
            "eta_formatted": "Sudah Pulih",
            "status": "completed"
        }

    # Balik rumus eksponensial: t = -tau * ln(1 - h/h_max_dd)
    max_dd = MAX_DRAWDOWN_M - STATIC_TMA_M  # drawdown maksimum (meter)
    fraksi_tersisa = sisa_drawdown / max_dd

    if fraksi_tersisa >= 1.0:
        fraksi_tersisa = 0.999  # Guard agar tidak log(0)

    # t = -tau * ln(fraksi_tersisa)
    eta_jam = -tau * math.log(fraksi_tersisa)
    persen  = round((1 - fraksi_tersisa) * 100, 1)

    return {
        "persen_recovery": persen,
        "sisa_drawdown_m": round(sisa_drawdown, 4),
        "eta_jam": round(eta_jam, 2),
        "eta_formatted": format_waktu(eta_jam * 60),
        "status": "recovering"
    }


# ==============================================================================
# SIMULASI STATUS SENSOR (Dummy — meniru siklus harian pompa)
# ==============================================================================
def simulasi_tma_sekarang() -> dict:
    """
    Simulasikan posisi TMA saat ini berdasarkan siklus jam harian.
    Pompa aktif: 06:00–10:00, 13:00–15:00 (contoh siklus JIAT umum).
    """
    jam_sekarang = datetime.now().hour + datetime.now().minute / 60

    # Tentukan apakah pompa sedang aktif
    pompa_aktif = (6.0 <= jam_sekarang < 10.0) or (13.0 <= jam_sekarang < 15.0)

    if pompa_aktif:
        # Simulasikan drawdown progresif dalam sesi pompa
        progress = min((jam_sekarang % 4) / 4, 1.0)
        tma = STATIC_TMA_M + (MAX_DRAWDOWN_M - STATIC_TMA_M) * progress
        delta = -(MAX_DRAWDOWN_M - STATIC_TMA_M) / 4 / 60  # per jam
    else:
        # Simulasikan recovery eksponensial setelah pompa mati
        # Cari berapa jam sejak pompa terakhir mati
        if jam_sekarang < 6.0:
            jam_sejak_mati = jam_sekarang  # sisa malam
        elif 10.0 <= jam_sekarang < 13.0:
            jam_sejak_mati = jam_sekarang - 10.0
        else:
            jam_sejak_mati = jam_sekarang - 15.0

        max_dd = MAX_DRAWDOWN_M - STATIC_TMA_M
        recovery_fraksi = 1 - math.exp(-jam_sejak_mati / TAU_DEFAULT_JAM)
        tma = MAX_DRAWDOWN_M - max_dd * recovery_fraksi
        delta = max_dd / TAU_DEFAULT_JAM * math.exp(-jam_sejak_mati / TAU_DEFAULT_JAM)

    # Tambah noise sensor kecil (±0.001 m)
    tma += random.uniform(-0.001, 0.001)

    return {
        "tma_meter": round(tma, 4),
        "delta_per_jam": round(delta, 5),
        "pompa_aktif": pompa_aktif,
    }


# ==============================================================================
# ENDPOINTS GET
# ==============================================================================

@app.get("/", tags=["Info"])
def root():
    """Cek status API."""
    return {
        "api": "JIAT Aquifer Recovery Dummy API",
        "versi": "0.1.0-dummy",
        "waktu_server": datetime.now().isoformat(),
        "endpoints": [
            "GET /status          — Status TMA & fase saat ini",
            "GET /recovery        — Estimasi ETA recovery aquifer",
            "GET /simulasi/siklus — Simulasi satu siklus 24 jam (data per jam)",
            "GET /fase            — Deteksi fase dari nilai delta TMA manual",
        ]
    }


@app.get("/status", tags=["Real-Time"])
def get_status():
    """
    Ambil status TMA dan fase aquifer saat ini (simulasi real-time).

    Returns posisi TMA, delta perubahan, fase aktif (Pumping/Recovery/Stabil),
    dan warna indikator sesuai notebook note_rnd3.ipynb.
    """
    sensor = simulasi_tma_sekarang()
    fase   = deteksi_fase(sensor["delta_per_jam"])

    return {
        "timestamp": datetime.now().isoformat(),
        "tma_meter": sensor["tma_meter"],
        "delta_per_jam": sensor["delta_per_jam"],
        "pompa_aktif": sensor["pompa_aktif"],
        "fase": fase["fase"],
        "warna_indikator": fase["warna"],
        "label_fase": fase["label"],
        "static_tma_referensi": STATIC_TMA_M,
        "max_drawdown_referensi": MAX_DRAWDOWN_M,
    }


@app.get("/recovery", tags=["Estimasi Recovery"])
def get_recovery(
    tma: Optional[float] = Query(
        default=None,
        description="Kedalaman TMA saat ini (meter). Jika tidak diisi, pakai nilai simulasi.",
        ge=0.0,
        le=20.0
    ),
    tau: float = Query(
        default=TAU_DEFAULT_JAM,
        description=f"Time constant aquifer (jam). Default: {TAU_DEFAULT_JAM} jam dari kalibrasi historis.",
        gt=0.0,
        le=72.0
    )
):
    """
    Estimasi waktu recovery aquifer dari posisi TMA yang diberikan.

    - **tma**: Kedalaman TMA saat ini dalam meter (opsional — jika kosong, pakai simulasi sensor)
    - **tau**: Time-constant eksponensial (jam) dari kalibrasi historis
    
    Formula:  `h(t) = h_max * (1 - exp(-t / tau))`  
    Recovery 95% terjadi pada `t ≈ 3 * tau` jam.
    """
    if tma is None:
        sensor = simulasi_tma_sekarang()
        tma    = sensor["tma_meter"]
        sumber = "simulasi-sensor"
    else:
        sumber = "manual-input"

    fase   = deteksi_fase(simulasi_tma_sekarang()["delta_per_jam"])
    result = estimasi_recovery_jam(tma, tau)

    return {
        "timestamp": datetime.now().isoformat(),
        "sumber_tma": sumber,
        "tma_input_meter": round(tma, 4),
        "tau_jam": tau,
        "fase_saat_ini": fase["fase"],
        **result,
        "catatan": (
            "Recovery dihitung dari static TMA referensi. "
            "ETA valid hanya selama fase RECOVERY aktif."
        )
    }


@app.get("/simulasi/siklus", tags=["Simulasi"])
def get_simulasi_siklus_harian(
    tau: float = Query(
        default=TAU_DEFAULT_JAM,
        description="Time constant aquifer (jam).",
        gt=0.0
    ),
    resolusi_menit: int = Query(
        default=60,
        description="Resolusi data simulasi dalam menit (30 atau 60).",
        ge=15,
        le=120
    )
):
    """
    Generate satu siklus 24 jam data TMA simulasi (per jam atau per 30 menit).

    Berguna untuk memvalidasi model recovery sebelum disambungkan ke data sensor asli.
    Menghasilkan array time-series lengkap dengan fase, delta, dan estimasi recovery per titik.
    """
    data_siklus = []
    base_time   = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    langkah     = resolusi_menit / 60  # dalam jam

    jam = 0.0
    while jam < 24.0:
        pompa_aktif = (6.0 <= jam < 10.0) or (13.0 <= jam < 15.0)

        if pompa_aktif:
            progress = min((jam % 4) / 4, 1.0)
            tma = STATIC_TMA_M + (MAX_DRAWDOWN_M - STATIC_TMA_M) * progress
            delta = -(MAX_DRAWDOWN_M - STATIC_TMA_M) / 4
        else:
            if jam < 6.0:
                t_off = jam
            elif 10.0 <= jam < 13.0:
                t_off = jam - 10.0
            else:
                t_off = jam - 15.0

            max_dd = MAX_DRAWDOWN_M - STATIC_TMA_M
            rf = 1 - math.exp(-t_off / tau)
            tma = MAX_DRAWDOWN_M - max_dd * rf
            delta = max_dd / tau * math.exp(-t_off / tau)

        tma += random.uniform(-0.001, 0.001)
        fase = deteksi_fase(delta)
        eta  = estimasi_recovery_jam(tma, tau)

        data_siklus.append({
            "jam_ke": round(jam, 2),
            "timestamp": (base_time + timedelta(hours=jam)).strftime("%H:%M"),
            "tma_meter": round(tma, 4),
            "delta": round(delta, 5),
            "pompa_aktif": pompa_aktif,
            "fase": fase["fase"],
            "warna": fase["warna"],
            "persen_recovery": eta["persen_recovery"],
            "eta_formatted": eta["eta_formatted"],
        })

        jam += langkah

    return {
        "tanggal_simulasi": base_time.strftime("%Y-%m-%d"),
        "tau_jam": tau,
        "resolusi_menit": resolusi_menit,
        "static_tma": STATIC_TMA_M,
        "max_drawdown": MAX_DRAWDOWN_M,
        "total_titik": len(data_siklus),
        "data": data_siklus,
    }


@app.get("/fase", tags=["Utilitas"])
def get_fase_manual(
    delta: float = Query(
        ...,
        description="Nilai selisih delta TMA per jam (meter/jam). Negatif = menyusut, Positif = memulih."
    )
):
    """
    Klasifikasikan fase aquifer dari nilai delta TMA secara manual.

    - **delta < -0.003** → Fase DISCHARGING (merah) — pompa aktif
    - **delta >  0.003** → Fase RECOVERY (kuning) — sumur memulih
    - **-0.003 ≤ delta ≤ 0.003** → Fase STABIL (abu-abu) — idle
    
    Threshold sesuai `note_rnd3.ipynb`.
    """
    fase = deteksi_fase(delta)
    return {
        "delta_input": delta,
        "threshold_pumping": f"< -{THRESHOLD_STABLE}",
        "threshold_recovery": f"> {THRESHOLD_STABLE}",
        **fase
    }


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_dummy:app", host="localhost", port=8001, reload=True)
