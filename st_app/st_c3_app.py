import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import math

# =========================================================
# KONFIGURASI STREAMLIT
# =========================================================
st.set_page_config(page_title="Monitoring Hidrologi Sumur (C3)", layout="wide", initial_sidebar_state="expanded")

# Sesuai komentar: sidebar kosongan
st.sidebar.title("Navigasi")
st.sidebar.empty() 

# =========================================================
# 1. LOAD DAN FILTER DATA MENGGUNAKAN ST.CACHE
# =========================================================
@st.cache_data
def load_data():
    data_filepath = r"D:\RnD_JIAT\data\Pos_AWLR_JIAT_Pondok_Kahuru.csv"
    df_c3 = pd.read_csv(data_filepath)
    df_c3["waktu"] = pd.to_datetime(df_c3["waktu"])
    df_c3 = df_c3.set_index("waktu")

    # Ambil data spesifik tanggal 2026-04-10
    try:
        df_day = df_c3.loc['2026-04-10'].copy()
    except KeyError:
        # Jika tidak ada, fallback ke tanggal pertama di dataset
        fallback_date = df_c3.index[0].strftime('%Y-%m-%d')
        df_day = df_c3.loc[fallback_date].copy()
    return df_day

df_day = load_data()

if df_day.empty:
    st.error("Data tidak ditemukan atau error loading.")
    st.stop()

# Cari nama aktual kolom Muka Air Tanah 
col_mat = 'Muka_Air_Tanah_mean' if 'Muka_Air_Tanah_mean' in df_day.columns else df_day.columns[0]

# =========================================================
# 2. INFORMASI TAMBAHAN & KONSTANTA TANGKI SUMUR
# =========================================================
kedalaman_sumur = 70.0    # meter
kedalaman_sensor = 60.0   # meter
diameter_inch = 8.0       # inch

# Menghitung Luas Penampang Sumur
diameter_m = diameter_inch * 0.0254    # konversi inch ke meter
radius_m = diameter_m / 2
luas_penampang = math.pi * (radius_m ** 2)

# =========================================================
# 3. PENAMBAHAN FITUR: DAT & VOLUME TABUNG
# =========================================================
# Data Air Tanah (DAT) adalah jarak air murni dari dasar sumur
df_day['DAT'] = kedalaman_sumur - df_day[col_mat]
df_day['Volume_Tabung_m3'] = df_day['DAT'] * luas_penampang

# =========================================================
# 4. PENAMBAHAN STATUS POMPA (DUMMY SENSOR)
# =========================================================
df_day['status_pompa'] = 0

# 1st Pump: Start jam 4 pagi -> Selesai jam 8 pagi
pump1_mask = (df_day.index.hour >= 4) & (df_day.index.hour < 8)
df_day.loc[pump1_mask, 'status_pompa'] = 1

# 2nd Pump: Start jam 3 sore -> Selesai jam 6 sore (15:00 - 18:00)
pump2_mask = (df_day.index.hour >= 15) & (df_day.index.hour < 18)
df_day.loc[pump2_mask, 'status_pompa'] = 1

# =========================================================
# 5. EKSTRAKSI INSIGHT (START PUMP & RECOVERY)
# =========================================================
target_date_str = str(df_day.index[0].date())

def get_closest_val(target_time, col):
    """Fungsi pembantu untuk mengambil data terdekat di waktu spesifik"""
    target_dt = pd.to_datetime(f'{target_date_str} {target_time}')
    
    if target_dt in df_day.index:
        res = df_day.loc[target_dt, col]
        return res.iloc[0] if isinstance(res, pd.Series) else res
    
    idx = df_day.index.get_indexer([target_dt], method='nearest')[0]
    return df_day[col].iloc[idx]

# Ambil poin-poin waktu kritis
mat_start = get_closest_val('04:00:00', col_mat)
dat_start = get_closest_val('04:00:00', 'DAT')
vol_start = get_closest_val('04:00:00', 'Volume_Tabung_m3')

mat_end1 = get_closest_val('08:00:00', col_mat)
dat_end1 = get_closest_val('08:00:00', 'DAT')
vol_end1 = get_closest_val('08:00:00', 'Volume_Tabung_m3')

mat_recov = get_closest_val('15:00:00', col_mat)
dat_recov = get_closest_val('15:00:00', 'DAT')
vol_recov = get_closest_val('15:00:00', 'Volume_Tabung_m3')

# DISCHARGE INSIGHT
durasi_discharge1 = 4 # 04:00 - 08:00 (dalam jam)
vol_eksploitasi1 = vol_start - vol_end1

# Ambil data pump 2
vol_start2 = get_closest_val('15:00:00', 'Volume_Tabung_m3')
vol_end2 = get_closest_val('18:00:00', 'Volume_Tabung_m3')
durasi_discharge2 = 3 # 15:00 - 18:00
vol_eksploitasi2 = vol_start2 - vol_end2

total_durasi_discharge = durasi_discharge1 + durasi_discharge2
rata_durasi_discharge = total_durasi_discharge / 2
total_vol_eksploitasi = vol_eksploitasi1 + vol_eksploitasi2
total_vol_liter = total_vol_eksploitasi * 1000

rate_ekstraksi_m3_jam = total_vol_eksploitasi / total_durasi_discharge if total_durasi_discharge > 0 else 0
rate_ekstraksi_liter_menit = (rate_ekstraksi_m3_jam * 1000) / 60

# RECOVERY INSIGHT
durasi_recovery = 7 # 08:00 - 15:00 (dalam jam)

# Catatan: Muka Air Tanah (mAT) adalah kedalaman dari permukaan
kenaikan_mat_total = mat_end1 - mat_recov
kenaikan_vol_total = vol_recov - vol_end1

mat_per_jam = kenaikan_mat_total / durasi_recovery
vol_per_jam = kenaikan_vol_total / durasi_recovery

# Evaluasi 100% Recovery
if mat_recov <= mat_start:
    recovery_status = "100% (Terisi Penuh)"
else:
    if (mat_end1 - mat_start) == 0:
        recovery_status = "0.00% (Data awal dan akhir identik / kurang valid)"
    else:
        persentase_recov = (mat_end1 - mat_recov) / (mat_end1 - mat_start) * 100
        recovery_status = f"{persentase_recov:.2f}% (Belum Kembali Penuh)"

# =========================================================
# TAMPILAN INFORMASI DI WEBSITE ATAS (STREAMLIT UI)
# =========================================================
st.title("Monitoring Hidrologi Sumur (Pos C3)")
st.markdown("Berikut adalah hasil analisis eksploitasi dan recovery harian berdasarkan data air tanah (DAT) dan muka air tanah (mAT).")

# Row 1 - KPI Metrics
col1, col2, col3 = st.columns(3)

with col1:
    st.info("**Pengambilan Air Tanah**")
    st.metric("Akumulasi Durasi Pengambilan", f"{total_durasi_discharge} Jam", f"Rata-rata: {rata_durasi_discharge:.1f} Jam/Siklus", delta_color="off")
    st.metric("Pengambilan Air Tanah (Liter)", f"{total_vol_liter:,.0f} L", "Total dalam 1 hari", delta_color="off")
    st.metric("Laju Ekstraksi Pompa", f"{rate_ekstraksi_liter_menit:.0f} L/mnt", f"-{rate_ekstraksi_m3_jam:.2f} m³/jam (Discharge)", delta_color="inverse")

with col2:
    st.success("**Pemulihan Air Tanah**")
    st.metric("Durasi Pemulihan Air Tanah", f"{durasi_recovery} Jam", "08:00 - 15:00", delta_color="off")
    st.metric("Kenaikan Volume per Jam", f"+{vol_per_jam:.3f} m³/jam")
    st.metric("Kenaikan Elevasi (mAT)", f"+{mat_per_jam:.3f} m/jam")

with col3:
    st.warning("**Recovery vs Initial (04:00)**")
    st.metric("mAT Awal (04:00)", f"{mat_start:.2f} m")
    st.metric("mAT Akhir (15:00)", f"{mat_recov:.2f} m")
    
    st.markdown("**Status Recovery Akhir:**")
    if "100%" in recovery_status:
        st.success(f"✅ {recovery_status}")
    else:
        st.error(f"⚠️ {recovery_status}")

st.markdown("---")

# =========================================================
# 6. VISUALISASI DENGAN PLOTLY
# =========================================================
# Hitung min dan max absolut batas Zoom
mat_min = df_day[col_mat].min()
mat_max = df_day[col_mat].max()
pad_mat = (mat_max - mat_min) * 0.1 if (mat_max - mat_min) > 0 else 0.5

dat_min = df_day['DAT'].min()
dat_max = df_day['DAT'].max()
pad_dat = (dat_max - dat_min) * 0.1 if (dat_max - dat_min) > 0 else 0.5

# PALET WARNA (LIGHT MODE PREMIUM)
color_mat  = "#F97316"   # Oranye tegas
color_dat  = "#0284C7"   # Biru profesional
color_pump = "#E11D48"   # Merah status mesin 
bg_color   = "#FFFFFF"   
grid_color = "#F3F4F6"   
text_color = "#374151"   
font_family = "Inter, Roboto, sans-serif"

fig = go.Figure()

# 1. Trace mAT di Sumbu Y Utama (Kiri -> SEKARANG KANAN)
fig.add_trace(
    go.Scatter(
        x=df_day.index, 
        y=df_day[col_mat], 
        name=f"mAT ({col_mat})", 
        mode='lines+markers', 
        line=dict(color=color_mat, width=2.5),
        marker=dict(size=7, color=bg_color, line=dict(width=2, color=color_mat)),
        yaxis="y2",
        hovertemplate="<b>Waktu:</b> %{x}<br><b>mAT:</b> %{y:.2f} m<extra></extra>"
    )
)

# 2. Trace DAT di Sumbu Y Kedua (Kanan -> SEKARANG KIRI)
fig.add_trace(
    go.Scatter(
        x=df_day.index, 
        y=df_day['DAT'], 
        name="DAT (Kolom Air)", 
        mode='lines', 
        line=dict(color=color_dat, width=2, dash='dashdot'), 
        yaxis="y1",
        hovertemplate="<b>DAT:</b> %{y:.2f} m<extra></extra>"
    )
)

# 3. Trace Status Pompa di Sumbu Y Ketiga (Kanan Luar)
fig.add_trace(
    go.Scatter(
        x=df_day.index, 
        y=df_day['status_pompa'], 
        name="Status Pompa", 
        mode='lines',
        fill='tozeroy', 
        line=dict(color=color_pump, width=1.5), 
        fillcolor='rgba(225, 29, 72, 0.08)',
        yaxis="y3",
        hoverinfo="skip"
    )
)

# ---------------------------------------------------------
# 7. INFO FLUKTUASI & PER TAMBAHAN RECOVERY (PLOTLY)
# ---------------------------------------------------------
# Informasi Tambahan Elevasi Tiap Jam saat Recovery (09:00 - 15:00)
for h in range(9, 16):
    t_curr = f"{h:02d}:00:00"
    t_prev = f"{h-1:02d}:00:00"
    
    mat_curr = get_closest_val(t_curr, col_mat)
    mat_prev = get_closest_val(t_prev, col_mat)
    dat_curr = get_closest_val(t_curr, 'DAT')
    dat_prev = get_closest_val(t_prev, 'DAT')
    
    diff_dat = dat_curr - dat_prev
    diff_mat = mat_curr - mat_prev
    
    sign_dat = "+" if diff_dat > 0 else ""
    sign_mat = "+" if diff_mat > 0 else ""
    text_anno = f"ΔDAT: {sign_dat}{diff_dat:.2f}m<br>ΔmAT: {sign_mat}{diff_mat:.2f}m"
    
    fig.add_annotation(
        x=pd.to_datetime(f"{target_date_str} {t_curr}"),
        y=dat_curr,
        yref="y2",
        text=text_anno,
        font=dict(size=9, color="#0284C7"),
        showarrow=True,
        arrowhead=1,
        arrowsize=1.5,
        arrowcolor="#0284C7",
        ax=0,
        ay=-45, 
        bgcolor="rgba(255, 255, 255, 0.9)",
        bordercolor="#0284C7",
        borderwidth=1,
        borderpad=3
    )

# Shape V-Rect untuk Fenomena Fluktuasi Jam Malam (21:00 - 23:00)
fig.add_vrect(
    x0=pd.to_datetime(f"{target_date_str} 21:00:00"),
    x1=pd.to_datetime(f"{target_date_str} 23:00:00"),
    fillcolor="navy",
    opacity=0.1,
    layer="below",
    line_width=0,
    annotation_text="Fluktuasi Akibat<br>Tekanan Aquifer",
    annotation_position="top left",
    annotation_font_size=11,
    annotation_font_color="navy"
)

# Anotasi untuk Judul Sumbu Pompa (Kanan Atas)
fig.add_annotation(
    x=0.98,
    y=1.05,
    xref="paper",
    yref="paper",
    text="<b>Mesin<br>Pompa</b>",
    font=dict(color=color_pump, size=12),
    showarrow=False,
    xanchor="center",
    yanchor="bottom"
)

# KONFIGURASI LAYOUT 
fig.update_layout(
    title=dict(
        text="<b>Monitoring Hidrologi Eksploitasi & Elevasi Sumur</b>",
        font=dict(size=22, color="#111827", family=font_family),
        x=0.02, 
        y=0.95
    ),
    font=dict(family=font_family, color=text_color),
    paper_bgcolor=bg_color,
    plot_bgcolor=bg_color,
    
    xaxis=dict(
        title="<b>Waktu (Jam)</b>", 
        domain=[0, 0.92], 
        showgrid=True,
        gridcolor=grid_color,
        gridwidth=1.5,
        zeroline=False
    ),
    
    # yaxis (DAT) - KIRI
    yaxis=dict(
        title="<b>DAT (Data Air Tanah)</b>",  
        titlefont=dict(color=color_dat, size=13),
        tickfont=dict(color=color_dat),
        showgrid=True,
        gridcolor=grid_color,
        gridwidth=1.5,
        zeroline=False,
        range=[dat_min - pad_dat, dat_max + pad_dat] 
    ),
    
    # yaxis2 (mAT) - KANAN
    yaxis2=dict(
        title="<b>Elevasi mAT (meter)</b>", 
        titlefont=dict(color=color_mat, size=13),
        tickfont=dict(color=color_mat),
        overlaying="y",
        side="right",
        showgrid=False, 
        zeroline=False,
        range=[mat_max + pad_mat, mat_min - pad_mat] 
    ),

    # yaxis3 (Pompa) - KANAN LUAR EKSTRA
    yaxis3=dict(
        title="", # dikosongkan karena dipindah ke annotation agar di 'kanan atas'
        tickfont=dict(color=color_pump, size=11),
        overlaying="y",
        side="right",
        position=0.98,
        showgrid=False,
        zeroline=False,
        range=[0, 1.2],
        tickvals=[0, 1],
        ticktext=["OFF", "ON"] 
    ),

    hovermode="x unified",
    hoverlabel=dict(
        bgcolor=bg_color,
        font_size=13,
        font_family=font_family,
        font_color=text_color,
        bordercolor="#D1D5DB"
    ),
    
    legend=dict(
        orientation="h", 
        yanchor="bottom", 
        y=1.05, 
        xanchor="right", 
        x=0.92,
        bgcolor="rgba(255, 255, 255, 0.9)",
        bordercolor=grid_color,
        borderwidth=1,
        font=dict(size=12, color=text_color)
    ),
    margin=dict(l=60, r=60, t=90, b=50) 
)

# Tampilkan ke Streamlit display 
st.plotly_chart(fig, use_container_width=True)
