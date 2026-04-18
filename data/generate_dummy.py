import csv
import math
import random
from datetime import datetime, timedelta

# ==============================================================================
# KONFIGURASI DUMMY DATA
# ==============================================================================
START_DATE = "2026-05-01 00:00:00"
DAYS = 30 # Berapa hari durasi data yang mau di-generate
OUTPUT_PATH = r"D:\RnD_JIAT\data\Dummy_AWLR_1-4_Cycles.csv"

# Parameter Hidrologi Mock
STATIC_TMA_M = 18.10   # Elevasi statis air tinggi (kondisi full)
MAX_DRAWDOWN_M = 1.20  # Maksimal penurunan elevasi saat dipompa
TAU_HOURS = 5.0        # Konstanta Theis recovery

def generate_dummy_data():
    current_time = datetime.strptime(START_DATE, "%Y-%m-%d %H:%M:%S")
    end_time = current_time + timedelta(days=DAYS)
    
    data = []
    headers = ["Waktu", "Rerata Muka Air Tanah", "Minimal", "Maksimal"]
    
    tma_current = STATIC_TMA_M
    pump_end_time = None
    
    print(f"🔄 Membuat data {DAYS} hari dengan 1-4 siklus acak harian...")
    
    pump_schedules = []
    
    while current_time < end_time:
        # Mulai hari baru: Tentukan jadwal pompa acak untuk hari ini
        if current_time.hour == 0:
            num_cycles = random.randint(1, 4)
            pump_schedules = []
            available_hours = list(range(4, 21)) # Pompa antara jam 04:00 sampai 21:00
            random.shuffle(available_hours)
            
            for _ in range(num_cycles):
                if not available_hours: break
                start_h = available_hours.pop()
                dur_h = random.randint(2, 6) # durasi pompa 2-6 jam
                
                # Buang jam yang tertimpa durasi agar tidak beririsan
                for h in range(start_h, start_h + dur_h + 2):
                    if h in available_hours:
                        available_hours.remove(h)
                        
                pump_schedules.append({
                    "start": start_h,
                    "end": start_h + dur_h
                })
        
        # Cek status pompa di jam ini
        jam = current_time.hour
        is_pumping = False
        active_schedule = None
        for sch in pump_schedules:
            if sch['start'] <= jam < sch['end']:
                is_pumping = True
                active_schedule = sch
                break
                
        # Hitung TMA berdasarkan fase
        if is_pumping:
            # POMPA NYALA -> TMA TURUN
            jam_berjalan = jam - active_schedule['start'] + 1
            progress = min(jam_berjalan / (active_schedule['end'] - active_schedule['start']), 1.0)
            
            target_drop = random.uniform(MAX_DRAWDOWN_M * 0.7, MAX_DRAWDOWN_M)
            tma_current = STATIC_TMA_M - (target_drop * progress)
            
            # Hitung kapan pompa mati
            pump_end_time = current_time.replace(hour=0) + timedelta(hours=active_schedule['end'])
            
        else:
            # POMPA MATI -> TMA RECOVERY NAIK
            if pump_end_time and current_time >= pump_end_time:
                jam_sejak_mati = (current_time - pump_end_time).total_seconds() / 3600
                if jam_sejak_mati >= 0:
                    sisa_drawdown = STATIC_TMA_M - tma_current
                    if sisa_drawdown > 0:
                        rf = 1 - math.exp(-1 / TAU_HOURS) 
                        tma_current = tma_current + (sisa_drawdown * rf)
            else:
                tma_current = min(tma_current + 0.01, STATIC_TMA_M)

        if tma_current > STATIC_TMA_M: tma_current = STATIC_TMA_M
        
        noise = random.uniform(-0.015, 0.015)
        tma_final = tma_current + noise
        
        data.append({
            "Waktu": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Rerata Muka Air Tanah": round(tma_final, 3),
            "Minimal": round(tma_final - random.uniform(0.01, 0.03), 2),
            "Maksimal": round(tma_final + random.uniform(0.01, 0.03), 2)
        })
        
        current_time += timedelta(hours=1)
        
    with open(OUTPUT_PATH, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)
        
    print(f"✅ Selesai! Data dummy tersimpan di: {OUTPUT_PATH}")
    print("Contoh 5 Data Teratas:")
    for row in data[:5]:
        print(row)

if __name__ == "__main__":
    generate_dummy_data()
