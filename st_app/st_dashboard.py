import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# Set Streamlit page config
st.set_page_config(
    page_title="JIAT Hydrological Dashboard",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium dark mode aesthetics
st.markdown("""
<style>
    /* Styling for the main app background and fonts */
    .stApp {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        backdrop-filter: blur(10px);
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-5px);
    }
    .metric-title {
        color: #94a3b8;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #38bdf8;
        font-size: 2rem;
        font-weight: 700;
    }
    h1, h2, h3 {
        color: #f8fafc;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_and_process_data(file_path):
    """
    Pipeline to load hydrological data and categorize Discharge/Charge states.
    """
    df = pd.read_csv(file_path)
    df['Waktu'] = pd.to_datetime(df['Waktu'])
    df = df.sort_values('Waktu').reset_index(drop=True)
    
    # 1. Hitung Delta (Perubahan Muka Air Tanah)
    df['delta'] = df['Rerata Muka Air Tanah'].diff()
    
    # 2. Definisikan Threshold (Bisa disesuaikan untuk mengabaikan noise sensor)
    threshold = 0.005 # 5mm threshold
    
    # 3. Klasifikasi Status Pompa/Aquifer
    conditions = [
        df['delta'] > threshold,   # Kedalaman bertambah -> Pompa menyedot (Discharge)
        df['delta'] < -threshold   # Kedalaman berkurang -> Aquifer pulih (Charge)
    ]
    choices = ['Discharge (Pumping)', 'Charge (Recovery)']
    
    df['Status'] = np.select(conditions, choices, default='Static / Steady')
    
    # 4. Kalkulasi Kolom Air Fisik (Opsional: Normalisasi berdasarkan Kedalaman Sumur)
    # Asumsi kedalaman sensor konstan jika ingin divisualisasikan terbalik
    
    return df

# Main Title
st.title("💧 JIAT Hydrological State Analysis Pipeline")
st.markdown("Dashboard ini menganalisis siklus *Discharge* (Pemompaan) dan *Charge* (Recovery Aquifer) secara dinamis.")

try:
    # File uploader for the dataset
    uploaded_file = st.file_uploader("Upload Data CSV (Pos AWLR)", type=["csv"])
    
    if uploaded_file is None:
        st.info("👋 Silakan upload file CSV Hydrological Data untuk memulai analisis pipeline.")
        st.stop()
        
    data = load_and_process_data(uploaded_file)
    
    # Kpi Cards
    col1, col2, col3 = st.columns(3)
    with col1:
        total_discharge = len(data[data['Status'] == 'Discharge (Pumping)'])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Total Jam Discharge (Pompa Aktif)</div>
            <div class="metric-value" style="color: #ef4444;">{total_discharge} Jam</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        total_charge = len(data[data['Status'] == 'Charge (Recovery)'])
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Total Jam Charge (Aquifer Pulih)</div>
            <div class="metric-value" style="color: #10b981;">{total_charge} Jam</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        avg_level = round(data['Rerata Muka Air Tanah'].mean(), 2)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">Rerata Muka Air Tanah (m)</div>
            <div class="metric-value">{avg_level}</div>
        </div>
        """, unsafe_allow_html=True)

    # Plotly Visualization
    st.subheader("Visualisasi Dinamika Aquifer")
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Warna berdasarkan status agar terlihat lebih jelas transisinya
    color_map = {
        'Discharge (Pumping)': 'rgba(239, 68, 68, 0.8)',   # Red for pumping
        'Charge (Recovery)': 'rgba(16, 185, 129, 0.8)',    # Green for recovery
        'Static / Steady': 'rgba(148, 163, 184, 0.5)'      # Grey for static
    }
    
    # Kita buat scatter plot per kategori untuk legend yang rapi
    for status in ['Charge (Recovery)', 'Discharge (Pumping)', 'Static / Steady']:
        df_sub = data[data['Status'] == status]
        fig.add_trace(
            go.Scatter(
                x=df_sub['Waktu'], 
                y=df_sub['Rerata Muka Air Tanah'],
                mode='markers',
                marker=dict(size=6, color=color_map[status]),
                name=status
            ),
            secondary_y=False
        )
        
    # Tambahkan line trend menyambung seluruh data
    fig.add_trace(
        go.Scatter(
            x=data['Waktu'],
            y=data['Rerata Muka Air Tanah'],
            mode='lines',
            line=dict(color='rgba(255,255,255,0.2)', width=1),
            showlegend=False,
            hoverinfo='skip'
        ),
        secondary_y=False
    )

    # Layout premium aesthetics
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#f8fafc', family='Inter'),
        xaxis=dict(
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', 
            title="Waktu (Jam)"
        ),
        yaxis=dict(
            showgrid=True, gridcolor='rgba(255,255,255,0.1)', 
            title="Muka Air Tanah (meter)",
            autorange="reversed" # Reversed axis: Dalam ke bawah terlihat (semakin besar angka, level air semakin turun)
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
        margin=dict(l=20, r=20, t=50, b=20),
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Data Table View
    st.subheader("Data Pipeline Output")
    st.dataframe(
        data[['Waktu', 'Rerata Muka Air Tanah', 'delta', 'Status']].style.applymap(
            lambda x: 'background-color: rgba(239, 68, 68, 0.2); color: #fca5a5' if x == 'Discharge (Pumping)' else 
                      ('background-color: rgba(16, 185, 129, 0.2); color: #6ee7b7' if x == 'Charge (Recovery)' else ''),
            subset=['Status']
        ),
        use_container_width=True,
        hide_index=True
    )

except Exception as e:
    st.error(f"Gagal memuat atau memproses data: {e}")

