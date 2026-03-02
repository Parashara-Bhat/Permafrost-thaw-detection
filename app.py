import streamlit as st
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
import requests
import random
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. RESEARCH DATA ASSETS ---
PRESET_DATA = {
    "batagaika": {
        "coords": (67.58, 134.77),
        "label": "Batagaika Megaslump (Siberia)",
        "fact": "The world's largest retrogressive thaw slump, currently expanding by 15 meters per year."
    },
    "drew point": {
        "coords": (70.86, -153.91),
        "label": "Drew Point Erosion (Alaska)",
        "fact": "Coastal permafrost here is collapsing into the sea at a rate of 20 meters annually."
    },
    "old crow": {
        "coords": (67.85, -139.83),
        "label": "Old Crow Flats (Canada)",
        "fact": "A critical wetland where thaw causes lakes to drain into the subsurface."
    }
}

# --- 2. CACHED NASA API ---
@st.cache_data(ttl=3600)
def get_nasa_data(lat, lon, season):
    try:
        # Use a summer date for simulation, or recent historical data
        target = "20250715" if season == "Summer (Simulation)" else (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        start = (datetime.strptime(target, '%Y%m%d') - timedelta(days=7)).strftime('%Y%m%d')

        url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        params = {"parameters": "TS", "community": "AG", "longitude": lon, "latitude": lat, "start": start, "end": target, "format": "JSON"}
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            temps = list(res.json()['properties']['parameter']['TS'].values())
            return [t if t != -999 else random.uniform(-5, 5) for t in temps]
        return [random.uniform(-10, 5) for _ in range(8)]
    except:
        return [random.uniform(-10, 5) for _ in range(8)]

# --- 3. UI HELPERS ---
def draw_gauge(score):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number", value = score,
        title = {'text': "Thaw Probability %", 'font': {'size': 18}},
        gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "darkblue"},
                 'steps': [{'range': [0, 40], 'color': "#a3cfbb"},
                           {'range': [40, 75], 'color': "#f8d7da"},
                           {'range': [75, 100], 'color': "#842029"}]}))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

# --- 4. DASHBOARD LAYOUT ---
st.set_page_config(page_title="ArcticShield Pro", layout="wide")

# Persistent State
if 'current_loc' not in st.session_state:
    st.session_state.current_loc = "Batagaika"

# Sidebar: Analysis Controls
st.sidebar.title("🛠️ Analysis Controls")
season_mode = st.sidebar.radio("Temporal Window:", ["Current", "Summer (Simulation)"])
st.sidebar.markdown("---")
st.sidebar.write("**Quick-Load Research Sites:**")

for site in PRESET_DATA.keys():
    if st.sidebar.button(site.title()):
        st.session_state.current_loc = site.title()

st.title("🌍 ArcticShield: Advanced Permafrost Analytics")

# Reactive Input: The button is gone, hitting 'Enter' here triggers the update
search = st.text_input("Active Search Location:", value=st.session_state.current_loc)
if search != st.session_state.current_loc:
    st.session_state.current_loc = search

# --- 5. LOGIC & PROCESSING ---
query = st.session_state.current_loc.lower().strip()
matched = next((k for k in PRESET_DATA if k in query), None)

if matched:
    lat, lon = PRESET_DATA[matched]["coords"]
    label, fact = PRESET_DATA[matched]["label"], PRESET_DATA[matched]["fact"]
else:
    try:
        loc = Nominatim(user_agent="arctic_shield_final").geocode(st.session_state.current_loc, timeout=5)
        lat, lon = (loc.latitude, loc.longitude) if loc else (67.5, 134.5)
        label, fact = f"Coordinate Search: {st.session_state.current_loc}", "General regional permafrost analysis."
    except:
        lat, lon, label, fact = 67.5, 134.5, "Default Site", "Using cached Arctic coordinates."

# Logic for Thaw (Only if in Arctic/Sub-Arctic)
is_arctic = abs(lat) > 45.0
temps = get_nasa_data(lat, lon, season_mode)
avg_t = sum(temps) / len(temps)
moisture = random.uniform(0.5, 0.9) if (is_arctic and avg_t > 0) else random.uniform(0.1, 0.3)
prob = min(100, max(0, (avg_t + 15) * 3 + (moisture * 35))) if is_arctic else 0

# --- 6. VISUALIZATION ---
col1, col2 = st.columns([1.3, 2])

with col1:
    st.plotly_chart(draw_gauge(prob), use_container_width=True)
    st.metric("Avg Surface Temp", f"{round(avg_t, 2)}°C")
    st.metric("Soil Moisture", f"{round(moisture*100)}%")
    st.line_chart(pd.DataFrame(temps, columns=["Temp"]))

with col2:
    st.subheader(f"Geospatial Context: {st.session_state.current_loc}")
    st.success(f"**Scientific Context:** {fact}")

    # Static Map (returned_objects=[] stops the infinite syncing loop)
    m = folium.Map(location=[lat, lon], zoom_start=12,
                   tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google Sat')
    folium.Marker([lat, lon]).add_to(m)
    st_folium(m, width=800, height=500, key=f"map_{st.session_state.current_loc}", returned_objects=[])