import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
import html
import re
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Yerevan Parking Supply",
    page_icon="🅿️",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Mono', monospace !important; }

.main { background-color: #0d1117; }

.kpi-card {
    background: linear-gradient(135deg, #1a1f2e 0%, #0f1420 100%);
    border: 1px solid #2a3042;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    transition: transform 0.2s;
}
.kpi-card:hover { transform: translateY(-3px); }
.kpi-number {
    font-family: 'Space Mono', monospace;
    font-size: 2.4rem;
    font-weight: 700;
    color: #4ecdc4;
    line-height: 1;
    margin-bottom: 6px;
}
.kpi-label {
    font-size: 0.8rem;
    color: #6b7db3;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}

.section-title {
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem;
    color: #4ecdc4;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #2a3042;
}

.stSelectbox label, .stMultiSelect label { color: #9ba8c4 !important; font-size: 0.85rem; }
.stSidebar { background: #0a0e1a !important; }
</style>
""", unsafe_allow_html=True)

# ── KML Parsing ───────────────────────────────────────────────────────────────
@st.cache_data
def load_kml(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    placemarks = root.findall('.//kml:Placemark', ns)
    records = []

    for pm in placemarks:
        name_el = pm.find('kml:name', ns)
        desc_el = pm.find('kml:description', ns)
        name = name_el.text.strip() if name_el is not None else ''
        desc = desc_el.text if desc_el is not None else ''

        if not desc or 'Space' not in desc:
            continue

        desc_clean = html.unescape(desc)
        space  = re.search(r'Space[:\s]+(\d+)', desc_clean)
        method = re.search(r'Method[:\s]+([^\<\n&]+)', desc_clean)
        signage= re.search(r'Signage[:\s]+([^\<\n&]+)', desc_clean)
        location=re.search(r'Location[:\s]+([^\<\n&]+)', desc_clean)

        # Grab midpoint of LineString or polygon centroid
        ls = pm.find('.//kml:LineString/kml:coordinates', ns)
        poly_outer = pm.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
        pt = pm.find('.//kml:Point/kml:coordinates', ns)

        lat, lon = None, None
        if ls is not None:
            pts = [c.split(',') for c in ls.text.strip().split()]
            lons = [float(p[0]) for p in pts if len(p)>=2]
            lats = [float(p[1]) for p in pts if len(p)>=2]
            lat, lon = sum(lats)/len(lats), sum(lons)/len(lons)
            coords = [[float(p[1]), float(p[0])] for p in pts if len(p)>=2]
        elif poly_outer is not None:
            pts = [c.split(',') for c in poly_outer.text.strip().split()]
            lons = [float(p[0]) for p in pts if len(p)>=2]
            lats = [float(p[1]) for p in pts if len(p)>=2]
            lat, lon = sum(lats)/len(lats), sum(lons)/len(lons)
            coords = [[float(p[1]), float(p[0])] for p in pts if len(p)>=2]
        elif pt is not None:
            c = pt.text.strip().split(',')
            lon, lat = float(c[0]), float(c[1])
            coords = [[lat, lon]]
        else:
            continue

        # Normalise values
        raw_method = method.group(1).strip() if method else 'unknown'
        raw_method = raw_method.lower().strip()
        if raw_method in ('paralell', 'parallel'):
            raw_method = 'Parallel'
        elif raw_method == '90':
            raw_method = '90°'
        elif raw_method == '45':
            raw_method = '45°'
        elif raw_method in ('parallel or 45', 'parallel/45'):
            raw_method = 'Mixed 45'
        elif raw_method in ('parallel/90',):
            raw_method = 'Mixed 90'
        elif raw_method in ('45/90',):
            raw_method = 'Mixed 45/90'
        elif raw_method in ('any', 'aby'):
            raw_method = 'Any'
        else:
            raw_method = raw_method.title() if raw_method else 'Unknown'

        raw_signage = (signage.group(1).strip().lower() if signage else 'unknown')
        raw_signage = 'Yes' if raw_signage.startswith('y') else 'No' if raw_signage.startswith('n') else 'Unknown'

        raw_loc = (location.group(1).strip().lower() if location else 'unknown')
        if 'pocket' in raw_loc:
            raw_loc = 'Pocket'
        elif 'set' in raw_loc:
            raw_loc = 'Set-back'
        elif 'on' in raw_loc:
            raw_loc = 'On-street'
        else:
            raw_loc = 'Unknown'

        # Extract street name from placemark name (strip trailing digits)
        street = re.sub(r'\d+$', '', name).strip()

        records.append({
            'name': name,
            'street': street,
            'spaces': int(space.group(1)) if space else 0,
            'method': raw_method,
            'signage': raw_signage,
            'location': raw_loc,
            'lat': lat,
            'lon': lon,
            'coords': coords,
            'has_line': ls is not None or poly_outer is not None,
        })

    return pd.DataFrame(records)

# ── Load data ─────────────────────────────────────────────────────────────────
KML_PATH = "Parking_Supply.kml"

try:
    df = load_kml(KML_PATH)
except FileNotFoundError:
    st.error("⚠️ `Parking_Supply.kml` not found. Place it in the same folder as app.py.")
    st.stop()

# ── Sidebar Filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🅿️ Filters")

    methods = sorted(df['method'].unique())
    sel_method = st.multiselect("Parking Method", methods, default=methods)

    locations = sorted(df['location'].unique())
    sel_loc = st.multiselect("Location Type", locations, default=locations)

    signages = sorted(df['signage'].unique())
    sel_sign = st.multiselect("Signage", signages, default=signages)

    min_sp, max_sp = int(df['spaces'].min()), int(df['spaces'].max())
    sel_spaces = st.slider("Min spaces per segment", min_sp, max_sp, min_sp)

    st.markdown("---")
    st.markdown(f"*{len(df)} segments loaded*")

# Apply filters
mask = (
    df['method'].isin(sel_method) &
    df['location'].isin(sel_loc) &
    df['signage'].isin(sel_sign) &
    (df['spaces'] >= sel_spaces)
)
fdf = df[mask]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("# 🅿️ YEREVAN PARKING SUPPLY")
st.markdown(
    "<p style='color:#6b7db3;font-size:0.9rem;margin-top:-12px;margin-bottom:24px;'>"
    "On-street parking inventory · Field survey data · Yerevan, Armenia</p>",
    unsafe_allow_html=True
)

# ── KPI row ────────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
kpis = [
    (k1, f"{fdf['spaces'].sum():,}", "Total Spaces"),
    (k2, f"{len(fdf):,}", "Segments"),
    (k3, f"{fdf['street'].nunique():,}", "Streets"),
    (k4, f"{fdf[fdf['signage']=='Yes']['spaces'].sum():,}", "Signed Spaces"),
    (k5, f"{round(fdf['spaces'].mean(), 1)}", "Avg / Segment"),
]
for col, val, label in kpis:
    with col:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-number'>{val}</div>"
            f"<div class='kpi-label'>{label}</div></div>",
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# ── Map + Charts row ──────────────────────────────────────────────────────────
map_col, chart_col = st.columns([3, 2])

with map_col:
    st.markdown("<div class='section-title'>📍 Spatial Distribution</div>", unsafe_allow_html=True)

    # Color by method
    METHOD_COLORS = {
        'Parallel': '#4ecdc4',
        '90°':      '#ff6b6b',
        '45°':      '#ffd93d',
        'Mixed 45': '#c084fc',
        'Mixed 90': '#f97316',
        'Mixed 45/90': '#84cc16',
        'Any':      '#60a5fa',
        'Unknown':  '#6b7280',
    }

    m = folium.Map(
        location=[fdf['lat'].mean(), fdf['lon'].mean()],
        zoom_start=13,
        tiles='CartoDB dark_matter'
    )

    for _, row in fdf.iterrows():
        color = METHOD_COLORS.get(row['method'], '#888')
        tip = f"{row['name']} | {row['spaces']} spaces | {row['method']} | {row['location']}"
        if row['has_line'] and len(row['coords']) > 1:
            folium.PolyLine(
                row['coords'],
                color=color,
                weight=3 + min(row['spaces'] / 30, 5),
                opacity=0.85,
                tooltip=tip,
            ).add_to(m)
        else:
            folium.CircleMarker(
                [row['lat'], row['lon']],
                radius=6,
                color=color,
                fill=True,
                fill_opacity=0.9,
                tooltip=tip,
            ).add_to(m)

    # Legend
    legend_html = """
    <div style='position:fixed;bottom:30px;left:30px;background:#1a1f2e;border:1px solid #2a3042;
    border-radius:8px;padding:12px 16px;z-index:9999;font-family:monospace;font-size:12px;color:#9ba8c4;'>
    <b style='color:#4ecdc4'>METHOD</b><br>
    """
    for method, color in METHOD_COLORS.items():
        legend_html += f"<span style='color:{color}'>■</span> {method}<br>"
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=520, returned_objects=[])

with chart_col:
    # ── Donut: method breakdown ───────────────────────────────────────────
    st.markdown("<div class='section-title'>Spaces by Method</div>", unsafe_allow_html=True)

    method_spaces = fdf.groupby('method')['spaces'].sum().sort_values(ascending=False)
    fig1, ax1 = plt.subplots(figsize=(4.5, 3.5), facecolor='#0d1117')
    colors = [METHOD_COLORS.get(m, '#888') for m in method_spaces.index]
    wedges, texts, autotexts = ax1.pie(
        method_spaces.values,
        labels=method_spaces.index,
        autopct='%1.0f%%',
        colors=colors,
        startangle=140,
        wedgeprops=dict(width=0.55, edgecolor='#0d1117'),
        textprops=dict(color='#9ba8c4', fontsize=9),
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color('#ffffff')
    ax1.set_facecolor('#0d1117')
    plt.tight_layout()
    st.pyplot(fig1)
    plt.close()

    # ── Bar: location type ───────────────────────────────────────────────
    st.markdown("<div class='section-title'>Spaces by Location Type</div>", unsafe_allow_html=True)

    loc_data = fdf.groupby('location')['spaces'].sum().sort_values()
    fig2, ax2 = plt.subplots(figsize=(4.5, 2.2), facecolor='#0d1117')
    ax2.set_facecolor('#0d1117')
    bar_colors = ['#4ecdc4', '#ff6b6b', '#ffd93d', '#c084fc'][:len(loc_data)]
    bars = ax2.barh(loc_data.index, loc_data.values, color=bar_colors, height=0.55)
    for bar, val in zip(bars, loc_data.values):
        ax2.text(val + 30, bar.get_y() + bar.get_height()/2,
                 f'{val:,}', va='center', color='#9ba8c4', fontsize=9)
    ax2.set_xlabel('Total Spaces', color='#6b7db3', fontsize=9)
    ax2.tick_params(colors='#9ba8c4', labelsize=9)
    for spine in ax2.spines.values():
        spine.set_edgecolor('#2a3042')
    ax2.xaxis.set_tick_params(color='#2a3042')
    plt.tight_layout()
    st.pyplot(fig2)
    plt.close()

# ── Bottom row: signage + top streets ──────────────────────────────────────────
left, right = st.columns(2)

with left:
    st.markdown("<div class='section-title'>📋 Signage Coverage</div>", unsafe_allow_html=True)
    sign_data = fdf.groupby('signage')['spaces'].sum()
    fig3, ax3 = plt.subplots(figsize=(5, 2.6), facecolor='#0d1117')
    ax3.set_facecolor('#0d1117')
    sign_colors = {'Yes': '#4ecdc4', 'No': '#ff6b6b', 'Unknown': '#6b7280'}
    sc = [sign_colors.get(s, '#888') for s in sign_data.index]
    ax3.bar(sign_data.index, sign_data.values, color=sc, width=0.5)
    for i, (idx, val) in enumerate(sign_data.items()):
        ax3.text(i, val + 50, f'{val:,}', ha='center', color='#9ba8c4', fontsize=10)
    ax3.set_ylabel('Spaces', color='#6b7db3', fontsize=9)
    ax3.tick_params(colors='#9ba8c4')
    for spine in ax3.spines.values():
        spine.set_edgecolor('#2a3042')
    plt.tight_layout()
    st.pyplot(fig3)
    plt.close()

with right:
    st.markdown("<div class='section-title'>🏆 Top 15 Streets by Spaces</div>", unsafe_allow_html=True)
    top_streets = (
        fdf.groupby('street')['spaces'].sum()
        .sort_values(ascending=False)
        .head(15)
    )
    fig4, ax4 = plt.subplots(figsize=(5, 4.2), facecolor='#0d1117')
    ax4.set_facecolor('#0d1117')
    y_pos = np.arange(len(top_streets))
    gradient = plt.cm.cool(np.linspace(0.3, 0.9, len(top_streets)))
    ax4.barh(y_pos, top_streets.values[::-1], color=gradient, height=0.65)
    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(top_streets.index[::-1], fontsize=8, color='#9ba8c4')
    ax4.set_xlabel('Total Spaces', color='#6b7db3', fontsize=9)
    ax4.tick_params(axis='x', colors='#9ba8c4', labelsize=8)
    for spine in ax4.spines.values():
        spine.set_edgecolor('#2a3042')
    plt.tight_layout()
    st.pyplot(fig4)
    plt.close()

# ── Data table ────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📊 Segment Data Table</div>", unsafe_allow_html=True)
show_df = fdf[['name','street','spaces','method','location','signage']].sort_values('spaces', ascending=False)
st.dataframe(show_df, use_container_width=True, height=280)

st.markdown(
    "<p style='color:#2a3042;font-size:0.75rem;text-align:center;margin-top:20px;'>"
    "Yerevan Parking Supply Survey · Transportation Planning</p>",
    unsafe_allow_html=True
)
