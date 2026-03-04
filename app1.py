import streamlit as st
import requests
import folium
import plotly.graph_objects as go
import numpy as np
from datetime import datetime, timedelta
from streamlit_folium import st_folium
from geopy.geocoders import OpenCage
import math
import os

# --- PAGE SETUP ---
st.set_page_config(page_title="ArcticShield", layout="wide")
st.title("🛰️ ArcticShield – Permafrost Impact Viewer")
st.caption("Visualize permafrost degradation using NASA data & satellite imagery")

# --- SESSION STATE ---
if 'data' not in st.session_state:
    st.session_state.data = None

# --- CONSTANTS ---
TDD_THRESH = {'stable': 200, 'caution': 500, 'high': 800}
LAT_PERMAFROST_MIN = 60
LATENT_HEAT_FUSION = 334_000
WATER_DENSITY = 1000

# --- NASA DATA FETCH ---
@st.cache_data(ttl=3600)
def fetch_nasa_temperature(lat, lon, days=365):
    end = datetime.now()
    start = end - timedelta(days=days)
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        'parameters': 'T2M',
        'community': 'AG',
        'longitude': lon,
        'latitude': lat,
        'start': start.strftime('%Y%m%d'),
        'end': end.strftime('%Y%m%d'),
        'format': 'JSON'
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()['properties']['parameter']['T2M']
        temps = [v for v in data.values() if v != -999.0]
        return temps if len(temps) > 30 else None
    except:
        return None

@st.cache_data(ttl=3600)
def fetch_moisture(lat, lon):
    end = datetime.now()
    start = end - timedelta(days=30)
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        'parameters': 'GWETTOP',
        'community': 'AG',
        'longitude': lon,
        'latitude': lat,
        'start': start.strftime('%Y%m%d'),
        'end': end.strftime('%Y%m%d'),
        'format': 'JSON'
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()['properties']['parameter']['GWETTOP']
        mois = [v for v in data.values() if v != -999.0]
        return round(sum(mois)/len(mois), 2) if mois else 0.3
    except:
        return 0.3

# --- GEOCODING WITH OPENCAGE (cached) ---
@st.cache_data(ttl=86400)
def geocode_location(location_name):
    """Convert place name to (lat, lon) using OpenCage, with error handling."""
    # Try to get API key from Streamlit secrets
    try:
        api_key = st.secrets["OPENCAGE_API_KEY"]
    except (KeyError, FileNotFoundError):
        st.error("❌ OpenCage API key not found. Please add it to your Streamlit secrets.")
        st.info("To run locally, create a `.streamlit/secrets.toml` file with:\n\n```toml\nOPENCAGE_API_KEY = \"your-api-key-here\"\n```")
        st.stop()

    try:
        geolocator = OpenCage(api_key=api_key)
        location = geolocator.geocode(location_name)
        if location:
            return (location.latitude, location.longitude)
        else:
            return None
    except Exception as e:
        st.error(f"Geocoding error: {str(e)}")
        return None

# --- RISK CALCULATION ---
def compute_risk(temps, moisture):
    if not temps:
        return None, None, None, None, None
    tdd = sum(max(0, t) for t in temps)
    fdd = sum(max(0, -t) for t in temps)

    ice_frac = moisture * 0.8
    latent_heat = ice_frac * WATER_DENSITY * LATENT_HEAT_FUSION
    k = 1.5
    tdd_sec = tdd * 24 * 3600
    alt = math.sqrt((2 * k * tdd_sec) / latent_heat) if latent_heat > 0 else 0.0
    alt = round(alt, 2)

    raw_score = (tdd / TDD_THRESH['high']) * 100
    score = min(100, raw_score + moisture * 10)
    score = round(score)

    if tdd >= TDD_THRESH['high']:
        level = "CRITICAL"
        icon = "🔴"
        color = "#ff4444"
    elif tdd >= TDD_THRESH['caution']:
        level = "HIGH RISK"
        icon = "🟠"
        color = "#ffaa44"
    elif tdd >= TDD_THRESH['stable']:
        level = "CAUTION"
        icon = "🟡"
        color = "#ffdd44"
    else:
        level = "STABLE"
        icon = "🟢"
        color = "#44ff44"

    # Permafrost classification based on FDD
    if fdd > 5000:
        permafrost_type = "Continuous Permafrost"
    elif fdd > 3000:
        permafrost_type = "Discontinuous Permafrost"
    elif fdd > 1000:
        permafrost_type = "Sporadic Permafrost"
    else:
        permafrost_type = "No Permafrost"

    return score, level, tdd, fdd, alt, icon, color, permafrost_type

# --- HORIZONTAL GAUGE ---
def horizontal_risk_gauge(score, level_color):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[100], y=[""], orientation='h',
        marker=dict(color='lightgray', opacity=0.3),
        width=[0.3], showlegend=False, hoverinfo='skip'
    ))
    fig.add_trace(go.Bar(
        x=[score], y=[""], orientation='h',
        marker=dict(color=level_color),
        width=[0.3],
        text=[f"<b>{score}%</b>"],
        textposition='inside',
        insidetextanchor='middle',
        textfont=dict(color='white', size=14, weight='bold'),
        showlegend=False, hoverinfo='skip'
    ))
    for thresh in [30, 50, 70]:
        fig.add_vline(x=thresh, line_width=1, line_dash="dash", line_color="gray", opacity=0.6)
    annotations = [
        dict(x=15, y=-0.4, text="STABLE", showarrow=False, font=dict(size=11, color="green")),
        dict(x=40, y=-0.4, text="CAUTION", showarrow=False, font=dict(size=11, color="orange")),
        dict(x=60, y=-0.4, text="HIGH", showarrow=False, font=dict(size=11, color="darkorange")),
        dict(x=85, y=-0.4, text="CRITICAL", showarrow=False, font=dict(size=11, color="red"))
    ]
    fig.update_layout(
        xaxis=dict(range=[0,100], title="Risk Score (%)", tickvals=[0,20,40,60,80,100]),
        yaxis=dict(showticklabels=False, showgrid=False),
        height=140,
        margin=dict(l=10, r=10, t=10, b=50),
        annotations=annotations,
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

# --- UI ---
with st.form("search_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        location = st.text_input("Enter Arctic location", "Batagaika Crater, Russia")
    with col2:
        submitted = st.form_submit_button("Analyze", use_container_width=True, type="primary")

if submitted:
    with st.spinner("🌍 Geocoding and fetching NASA data..."):
        # Geocode using OpenCage (cached)
        coords = geocode_location(location)
        if coords is None:
            # Error already shown in geocode_location
            st.stop()
        lat, lon = coords

        if abs(lat) < LAT_PERMAFROST_MIN:
            st.warning(f"📍 {location} is at {abs(lat):.1f}°{'N' if lat>0 else 'S'} – outside the Arctic permafrost zone.")
            st.info("This location has **no permafrost**.")
            st.session_state.data = None
        else:
            temps = fetch_nasa_temperature(lat, lon)
            mois = fetch_moisture(lat, lon)
            if not temps:
                st.error("❌ Could not retrieve temperature data from NASA. Please try again later.")
                st.stop()
            score, level, tdd, fdd, alt, icon, color, ptype = compute_risk(temps, mois)
            st.session_state.data = {
                'name': location,
                'lat': lat, 'lon': lon,
                'score': score, 'level': level, 'icon': icon,
                'tdd': tdd, 'fdd': fdd,
                'alt': alt, 'moisture': mois,
                'color': color,
                'permafrost_type': ptype
            }

if st.session_state.data:
    d = st.session_state.data
    st.success(f"📍 **{d['name']}** – {abs(d['lat']):.1f}°N, {abs(d['lon']):.1f}°E")

    # --- METRICS ROW ---
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Thawing Degree Days", f"{d['tdd']:.0f} °C·day")
    with col_b:
        st.metric("Freezing Degree Days", f"{d['fdd']:.0f} °C·day")
    with col_c:
        st.metric("Active Layer Thickness", f"{d['alt']} m")
    with col_d:
        st.metric("Soil Moisture", f"{d['moisture']*100:.0f}%")

    # --- GAUGE ---
    st.markdown("---")
    st.subheader("📊 Thaw Risk Gauge")
    gauge_col1, gauge_col2, gauge_col3 = st.columns([1, 6, 1])
    with gauge_col2:
        st.plotly_chart(horizontal_risk_gauge(d['score'], d['color']), use_container_width=True)
    st.markdown("---")

    # --- PERMAFROST IMPACT VISUALIZATION (SATELLITE IMAGE) ---
    st.subheader("🛰️ Permafrost Impact – Satellite Imagery")
    st.caption("The image below shows the current surface expression of permafrost. Look for thermokarst lakes, thaw slumps, or ice wedge polygons.")

    # Create a map with a larger size and annotations
    m = folium.Map(location=[d['lat'], d['lon']], zoom_start=12,
                   tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                   attr='Google Satellite')

    # Add a marker with risk info
    marker_color = ('red' if d['level'] == 'CRITICAL' else
                    'orange' if d['level'] == 'HIGH RISK' else
                    'yellow' if d['level'] == 'CAUTION' else 'green')
    folium.Marker(
        [d['lat'], d['lon']],
        popup=f"<b>{d['name']}</b><br>Risk: {d['level']}",
        icon=folium.Icon(color=marker_color)
    ).add_to(m)

    # For known thaw features, add a circle to highlight crater extent (e.g., Batagaika)
    if "batagaika" in d['name'].lower():
        folium.Circle(
            radius=800,
            location=[d['lat'], d['lon']],
            popup='Batagaika Crater extent',
            color='red',
            fill=True,
            opacity=0.3
        ).add_to(m)
        st.info("🔴 Red circle outlines the Batagaika Crater – a massive permafrost thaw feature.")

    # Display the map prominently
    st_folium(m, width='100%', height=500)

    # Additional explanatory text
    with st.expander("🔍 What to look for in the image"):
        st.markdown("""
        - **Thermokarst lakes**: Irregular-shaped water bodies formed by ground ice melt.
        - **Thaw slumps**: Horseshoe-shaped scars on slopes where ice-rich permafrost has collapsed.
        - **Ice wedge polygons**: Polygonal patterns on the ground surface caused by ice wedges.
        - **Retrogressive thaw slumps**: Actively eroding cliffs of exposed ice.
        """)

    # --- ADDITIONAL INFO (optional) ---
    col_left, col_right = st.columns(2)
    with col_left:
        st.metric("Permafrost type", d['permafrost_type'])
    with col_right:
        if d['tdd'] > 800:
            thaw = "🔴 Extreme"
        elif d['tdd'] > 500:
            thaw = "🟠 High"
        elif d['tdd'] > 200:
            thaw = "🟡 Moderate"
        else:
            thaw = "🟢 Low"
        st.metric("Thaw potential", thaw)

    # --- SCIENTIFIC EXPANDER ---
    with st.expander("🔬 Scientific explanation"):
        st.markdown(f"""
        - **Thawing Degree Days (TDD)** = sum of daily mean temperatures above 0 °C over the last year.  
          Current TDD: {d['tdd']:.0f}
        - **Freezing Degree Days (FDD)** = sum of daily mean temperatures below 0 °C.  
          Current FDD: {d['fdd']:.0f}
        - **Active layer thickness (ALT)** estimated via Stefan equation: {d['alt']} m.
        - **Risk thresholds** (IPA):
            - <200 TDD → STABLE
            - 200–500 → CAUTION
            - 500–800 → HIGH RISK
            - >800 → CRITICAL
        - **Permafrost type** based on FDD: {d['permafrost_type']}
        """)

    if st.button("🔄 New Search"):
        st.session_state.data = None
        st.rerun()