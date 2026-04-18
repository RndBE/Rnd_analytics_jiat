import json
import requests
import pandas as pd

def fetch_data_by_logger(id_logger, start_date, end_date):
    """
    Fungsi fetch API dari jiat_info.json, mengubah nilai Muka Air Tanah per Kolom
    dan menstrukturisasi ulang (Rename & Pilih Kolom Tertentu).
    """
    json_filepath = "d:/RnD_JIAT/data/jiat_info.json"

    # 1. Baca konfigurasi JSON
    with open(json_filepath, 'r') as file:
        print("✅ Ambil Informasi dari jiat_info.json ")
        jiat_data = json.load(file)

    # 2. Cari id_parameter, Kedalaman Sumur, dan nama Pos berdasarkan id_logger
    id_parameter = None
    kedalaman_sumur = None
    pos_name = None
    
    for nama_pos, metadata in jiat_data.items():
        if str(metadata.get("id_logger")) == str(id_logger):
            id_parameter = metadata.get("id_parameter")
            kedalaman_sumur = metadata.get("Kedalaman Sumur") 
            pos_name = nama_pos
            break
            
    if id_parameter is None:
        print(f"❌ Error: Logger ID '{id_logger}' tidak ditemukan di jiat_info.json")
        return pd.DataFrame()

    print(f"🚀 Memproses {pos_name} | Logger: {id_logger} | Sumur: {kedalaman_sumur}m")

    # 3. Request API 
    url = f"https://mini-stesy.beacontelemetry.com/api/v1/loggers/{id_logger}/hourly-range"
    params = {
        "parameter_id": id_parameter,
        "start_date": start_date,
        "end_date": end_date
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        
        # Parse JSON ke dict bawaan Python
        data_api = response.json() 
        
        # 4. Ambil isi sub-array-nya langsung dari dict
        all_data = data_api.get("data", [])
            
        if not all_data:
             print("⚠️ Data kosong pada API untuk interval waktu ini.")
             return pd.DataFrame()
        
        # 5. Konversi Object menjadi DataFrame
        df = pd.DataFrame(all_data) 
        
        # Pastikan tipe/format kolom waktu rapi
        df['waktu'] = pd.to_datetime(df['waktu'])
        df = df.sort_values('waktu').reset_index(drop=True)
        
        # Kalkulasi Fisik ke Data Air Tanah
        df['Kedalaman Sumur'] = kedalaman_sumur
        df['Data_Air_Tanah'] = df['Kedalaman Sumur'] - df['nilai']
        
        # ------------------------------------------------------------
        # 6. MENGATUR STRUKTUR & RENAME KOLOM SECARA SPESIFIK
        # ------------------------------------------------------------
        # (A) Hanya menyisakan list kolom yang Anda minta:
        list_col = ["waktu", "nilai", "Kedalaman Sumur", "Data_Air_Tanah"]
        
        # Ekstrak dataframe tersebut (gunakan copy() agar modifikasi di memori baru aman)
        df_bersih = df[list_col].copy()
        
        # (B) Rename nama "nilai" dan "Kedalaman Sumur"
        df_bersih = df_bersih.rename(columns={
            "nilai": "Muka_Air_Tanah_mean",
            "Kedalaman Sumur": "Kedalaman_Sumur"
        })
        
        print(f"✅ Berhasil menarik & menyaring {len(df_bersih)} baris data.")
        return df_bersih
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal melakukan request API: {e}")
        return pd.DataFrame()