from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import numpy as np
import math

app = FastAPI(
    title="JIAT Telemetry AI API", 
    description="API untuk menghitung Estimasi Pemulihan (Recovery) & Transmisivitas Theis",
    version="1.1.0"
)

# --- Mengizinkan Lintas Port (CORS) agar UI Web bisa Fetch API ini ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Struktur data payload JSON yang diharapkan dari Frontend/Dashboard dengan Theis params
class TelemetryData(BaseModel):
    data_points: List[float]
    static_tma: float
    discharge_m3_day: float # Parameter Q (Discharge)
    pump_duration_hours: float # Parameter t_p (waktu operasional pompa nyala)

def format_waktu(waktu_menit_total: float) -> str:
    total_menit = int(round(waktu_menit_total))
    if total_menit < 60:
        return f"{total_menit} Menit"
        
    menit = total_menit % 60
    total_jam = total_menit // 60
    
    if total_jam < 24:
        if menit == 0:
            return f"{total_jam} Jam"
        return f"{total_jam} Jam {menit} Menit"
    else:
        hari = total_jam // 24
        jam = total_jam % 24
        res = f"{hari} Hari"
        if jam > 0:
            res += f" {jam} Jam"
        if menit > 0:
            res += f" {menit} Menit"
        return res

@app.post("/api/m3/predict")
def predict_recovery(payload: TelemetryData):
    """
    Endpoint (M3 Updated): Menganalisis kurva berdasarkan Kruseman & De Ridder
    Menggunakan rumus Theis Recovery Equation: s' = (2.30 Q) / (4 pi T) * log10(t/t')
    """
    try:
        data = np.array(payload.data_points)
        static_tma = payload.static_tma
        Q = payload.discharge_m3_day
        tp_hours = payload.pump_duration_hours
        
        # 1. Mencari titik saat pompa mati (Drawdown Tertinggi)
        peak_idx = np.argmax(data)
        
        if peak_idx >= len(data) - 2:
            return {
                "status": "pending", 
                "message": "Menunggu setidaknya 2 jam data masuk pasca pompa mati untuk menganalisis Slope Theis."
            }
            
        # 2. Ambil 2 titik awal masa recovery untuk mencari turunan s' (residual drawdown) per siklus logaritma
        # Membaca titik t' (waktu pasca pompa mati) pada t'=1 dan t'=2 
        t_prime_1 = 1  
        t_1 = tp_hours + t_prime_1  # total waktu t
        s_prime_1 = data[peak_idx + 1] - static_tma
        
        t_prime_2 = 2  
        t_2 = tp_hours + t_prime_2 
        s_prime_2 = data[peak_idx + 2] - static_tma
        
        # Validasi hidrologi logis
        if s_prime_1 <= 0 or s_prime_2 <= 0:
            return {"status": "error", "message": "Anomali: TMA melewati batas statis."}
        if s_prime_2 >= s_prime_1:
            return {"status": "error", "message": "Anomali: Tidak terdeteksi pemulihan kurva air."}

        # 3. PERHITUNGAN TRANSIMISIVITAS (T) via Kemiringan Kurva Log Base 10
        # Slope = delta s' / log10_diff
        ratio_1 = t_1 / t_prime_1
        ratio_2 = t_2 / t_prime_2
        
        log_diff = math.log10(ratio_1) - math.log10(ratio_2)
        delta_s = s_prime_1 - s_prime_2
        
        if log_diff <= 0 or delta_s <= 0:
             return {"status": "error", "message": "Log/Drawdown tidak valid."}
             
        slope = delta_s / log_diff
        
        # T (m2/hari)
        transmissivity = (2.30 * Q) / (4 * math.pi * slope)
        
        # 4. PREDIKSI ESTIMASI SISA WAKTU RECOVERY PENUH
        # sisa_target_m = batas toleransi sebelum dianggap stabil/statis (10cm)
        sisa_target_m = 0.10
        
        if s_prime_2 <= sisa_target_m:
             return {"status": "completed", "message": "Air sudah mendekati atau pulih sepenuhnya."}

        # Mengembalikan rumus s' = slope * log10(tp/t' + 1)
        # target_log10_ratio = s_target / slope
        target_log_ratio = sisa_target_m / slope
        
        # Rasio Theis target: 10^(target_log_ratio) = (tp + t') / t'
        ratio_val = 10**target_log_ratio
        
        if ratio_val <= 1.01:
             waktu_prediksi_jam = 0
        else:
             t_prime_target = tp_hours / (ratio_val - 1)
             waktu_prediksi_jam = max(0, t_prime_target - t_prime_2) # Sisa jam
             
        menit = waktu_prediksi_jam * 60
        formatted_time = format_waktu(menit)
        
        return {
            "status": "success",
            "transmissivity_m2_day": round(transmissivity, 2),
            "recovery_time_formatted": formatted_time,
            "message": "Theis calculation successful."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_m3:app", host="localhost", port=8000, reload=True)
