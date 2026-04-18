from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime
import os
import numpy as np
import pandas as pd

app = FastAPI(title="API Muka Air Tanah", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
DATA_CSV = Path(os.getenv("MA_CSV_PATH", BASE_DIR / "Pos_AWLR_JIAT_Curug_Agung.csv"))

KEDALAMAN_SUMUR = 100.0 # 18789█
DIAMETER_SUMUR = 0.25
KEDALAMAN_SENSOR = 55.0
KEDALAMAN_POMPA = 40.0
DEBIT_LPS = 10.0
T_DISCHARGE_JAM = 6
MAT_AWAL = 7.5
S_MAX_DUMMY = 1.5
K_D = 0.5
K_R = 0.3

def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "waktu" not in df.columns:
        raise ValueError("Kolom 'waktu' tidak ditemukan")
    df["waktu"] = pd.to_datetime(df["waktu"], errors="coerce")
    df = df.dropna(subset=["waktu"]).sort_values("waktu").reset_index(drop=True)

    if "Muka_Air_Tanah_mean" not in df.columns:
        for c in ["Muka_Air_Tanah", "Muka Air Tanah", "muka_air_tanah"]:
            if c in df.columns:
                df["Muka_Air_Tanah_mean"] = pd.to_numeric(df[c], errors="coerce")
                break

    if "Kedalaman_Sumur" not in df.columns:
        df["Kedalaman_Sumur"] = KEDALAMAN_SUMUR

    if "Data_Air_Tanah" not in df.columns:
        df["Data_Air_Tanah"] = pd.to_numeric(df["Kedalaman_Sumur"], errors="coerce") - pd.to_numeric(df["Muka_Air_Tanah_mean"], errors="coerce")

    df["Muka_Air_Tanah_mean"] = pd.to_numeric(df["Muka_Air_Tanah_mean"], errors="coerce")
    df["Kedalaman_Sumur"] = pd.to_numeric(df["Kedalaman_Sumur"], errors="coerce").fillna(KEDALAMAN_SUMUR)
    df["Data_Air_Tanah"] = pd.to_numeric(df["Data_Air_Tanah"], errors="coerce")
    df["Kategori_Data"] = df.get("Kategori_Data", "Aktual Historis")
    df = df.dropna(subset=["Muka_Air_Tanah_mean"])
    return df

def load_real_data() -> pd.DataFrame:
    if DATA_CSV.exists():
        df = pd.read_csv(DATA_CSV)
        df = ensure_columns(df)
        df["Kategori_Data"] = "Aktual Historis"
        return df

    waktu = pd.date_range(end=pd.Timestamp.now().floor("h") - pd.Timedelta(hours=1), periods=72, freq="h")
    mat = 7.2 + 0.15 * np.sin(np.linspace(0, 8 * np.pi, len(waktu))) + np.linspace(0, 0.2, len(waktu))
    df = pd.DataFrame({
        "waktu": waktu,
        "Muka_Air_Tanah_mean": mat,
        "Kedalaman_Sumur": KEDALAMAN_SUMUR
    })
    df["Data_Air_Tanah"] = df["Kedalaman_Sumur"] - df["Muka_Air_Tanah_mean"]
    df["Kategori_Data"] = "Aktual Historis"
    return df

def hitung_penurunan_dummy(t_jam: int) -> float:
    if t_jam <= T_DISCHARGE_JAM:
        return S_MAX_DUMMY * (1 - np.exp(-K_D * t_jam))
    s_end = S_MAX_DUMMY * (1 - np.exp(-K_D * T_DISCHARGE_JAM))
    return s_end * np.exp(-K_R * (t_jam - T_DISCHARGE_JAM))

def generate_dummy_data(target_date: str | None = None) -> pd.DataFrame:
    if target_date:
        start_date = pd.to_datetime(target_date).normalize()
    else:
        start_date = pd.Timestamp.now().normalize()

    waktu_dummy = pd.date_range(start=start_date, end=start_date + pd.Timedelta(hours=23), freq="h")
    jam_indeks = np.arange(len(waktu_dummy))
    mat_dummy = np.array([MAT_AWAL + hitung_penurunan_dummy(int(t)) for t in jam_indeks])

    df_dummy = pd.DataFrame({
        "waktu": waktu_dummy,
        "Muka_Air_Tanah_mean": mat_dummy,
        "Kedalaman_Sumur": KEDALAMAN_SUMUR
    })
    df_dummy["Data_Air_Tanah"] = df_dummy["Kedalaman_Sumur"] - df_dummy["Muka_Air_Tanah_mean"]
    df_dummy["Kategori_Data"] = ["Dummy Discharge" if t <= T_DISCHARGE_JAM else "Dummy Recovery" for t in jam_indeks]
    return df_dummy

def build_merged_dataframe(target_date: str | None = None) -> pd.DataFrame:
    df_real = load_real_data()
    df_dummy = generate_dummy_data(target_date)
    df = pd.concat([df_real, df_dummy], ignore_index=True)
    df = df.sort_values("waktu").reset_index(drop=True)
    return df

def hitung_waktu_t_persen(df_rec_phase: pd.DataFrame, waktu_h_min: pd.Timestamp, persentase: float) -> float | None:
    kondisi = df_rec_phase["Recovery_Pcnt"] >= persentase
    if kondisi.any():
        data_match = df_rec_phase[kondisi].iloc[0]
        waktu_tempuh = data_match["waktu"] - waktu_h_min
        return round(waktu_tempuh.total_seconds() / 3600, 3)
    return None

def analyze_recovery(df_gabungan: pd.DataFrame, event_date: str | None = None) -> dict:
    if event_date:
        tanggal = pd.to_datetime(event_date).date()
    else:
        tanggal = df_gabungan["waktu"].max().date()

    df_event = df_gabungan[df_gabungan["waktu"].dt.date == tanggal].copy().reset_index(drop=True)
    if df_event.empty:
        return {
            "tanggal_event": str(tanggal),
            "status": "DATA_TIDAK_ADA"
        }

    h_baseline = float(df_event["Muka_Air_Tanah_mean"].iloc[0])
    h_min = float(df_event["Muka_Air_Tanah_mean"].max())
    idx_h_min = int(df_event["Muka_Air_Tanah_mean"].idxmax())
    waktu_h_min = pd.to_datetime(df_event.loc[idx_h_min, "waktu"])
    s_max = float(h_min - h_baseline)

    df_rec_phase = df_event[df_event["waktu"] >= waktu_h_min].copy()
    if s_max == 0:
        df_rec_phase["Recovery_Pcnt"] = 100.0
    else:
        df_rec_phase["Recovery_Pcnt"] = ((h_min - df_rec_phase["Muka_Air_Tanah_mean"]) / s_max) * 100

    t_50 = hitung_waktu_t_persen(df_rec_phase, waktu_h_min, 50)
    t_80 = hitung_waktu_t_persen(df_rec_phase, waktu_h_min, 80)
    t_90 = hitung_waktu_t_persen(df_rec_phase, waktu_h_min, 90)

    h_akhir = float(df_rec_phase["Muka_Air_Tanah_mean"].iloc[-1])
    residual_drawdown = float(h_akhir - h_baseline)

    status = "NORMAL (Pemulihan Cepat)"
    if t_90 is None:
        status = "TERTEKAN (Sistem lambat, tak mencapai 90% dalam harian)"
    elif residual_drawdown > 0.5:
        status = "WASPADA (Residual drawdown tinggi, ada indikasi eksploitasi)"

    return {
        "tanggal_event": str(tanggal),
        "h_baseline": round(h_baseline, 3),
        "h_min": round(h_min, 3),
        "waktu_h_min": waktu_h_min.strftime("%Y-%m-%d %H:%M:%S"),
        "s_max": round(s_max, 3),
        "t_50_jam": t_50,
        "t_80_jam": t_80,
        "t_90_jam": t_90,
        "h_akhir": round(h_akhir, 3),
        "residual_drawdown": round(residual_drawdown, 3),
        "status": status
    }

def build_chart_series(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, row in df.iterrows():
        out.append({
            "waktu": pd.to_datetime(row["waktu"]).strftime("%Y-%m-%d %H:%M:%S"),
            "Muka_Air_Tanah_mean": None if pd.isna(row["Muka_Air_Tanah_mean"]) else round(float(row["Muka_Air_Tanah_mean"]), 3),
            "Data_Air_Tanah": None if pd.isna(row["Data_Air_Tanah"]) else round(float(row["Data_Air_Tanah"]), 3),
            "Kedalaman_Sumur": None if pd.isna(row["Kedalaman_Sumur"]) else round(float(row["Kedalaman_Sumur"]), 3),
            "Kategori_Data": row["Kategori_Data"]
        })
    return out

@app.get("/")
def root():
    return {"message": "API Muka Air Tanah aktif"}

@app.get("/api/ma/dashboard")
def get_dashboard(
    target_date: str | None = Query(default=None),
    event_date: str | None = Query(default=None),
    last_n_hours: int = Query(default=240, ge=24, le=5000)
):
    df = build_merged_dataframe(target_date=target_date)
    df = df.sort_values("waktu").reset_index(drop=True)

    if last_n_hours:
        batas = df["waktu"].max() - pd.Timedelta(hours=last_n_hours - 1)
        df_chart = df[df["waktu"] >= batas].copy()
    else:
        df_chart = df.copy()

    analysis = analyze_recovery(df, event_date=event_date if event_date else target_date)

    latest = df.iloc[-1]
    pemakaian_hari = round(DEBIT_LPS * 3600 * T_DISCHARGE_JAM / 1000, 3)
    pemakaian_minggu = round(pemakaian_hari * 7, 3)
    pemakaian_bulan = round(pemakaian_hari * 30, 3)
    pemakaian_tahun = round(pemakaian_hari * 365, 3)

    payload = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "refresh_interval_ms": 3600000,
            "data_csv": str(DATA_CSV),
            "target_date": target_date,
            "event_date": event_date if event_date else target_date,
            "last_n_hours": last_n_hours
        },
        "summary": {
            "lokasi": "Pos AWLR JIAT Curug Agung",
            "data_air_tanah": round(float(latest["Data_Air_Tanah"]), 3),
            "muka_air_tanah": round(float(latest["Muka_Air_Tanah_mean"]), 3),
            "kedalaman_sumur": round(float(latest["Kedalaman_Sumur"]), 3),
            "kedalaman_sensor": KEDALAMAN_SENSOR,
            "diameter_sumur": DIAMETER_SUMUR,
            "kedalaman_pompa": KEDALAMAN_POMPA,
            "debit_lps": DEBIT_LPS,
            "pemakaian_hari_m3": pemakaian_hari,
            "pemakaian_minggu_m3": pemakaian_minggu,
            "pemakaian_bulan_m3": pemakaian_bulan,
            "pemakaian_tahun_m3": pemakaian_tahun,
            "kategori_data_terakhir": latest["Kategori_Data"]
        },
        "analysis": analysis,
        "chart_data": build_chart_series(df_chart)
    }
    return JSONResponse(payload)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_mat:app", host="localhost", port=8001, reload=True)