import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
import html
import re
import matplotlib.pyplot as plt
import numpy as np
import requests
import io

st.set_page_config(page_title="Yerevan Parking Supply", page_icon="🅿️", layout="wide")

st.markdown("""
<style>
.kpi-card { background:#f7f8f9; border-radius:10px; padding:16px 20px; text-align:center; }
.kpi-number { font-size:2rem; font-weight:600; color:#1d9e75; line-height:1.1; margin-bottom:4px; }
.kpi-label { font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:0.1em; }
.section-title { font-size:0.7rem; font-weight:600; color:#888; text-transform:uppercase;
    letter-spacing:0.15em; margin-bottom:10px; padding-bottom:6px; border-bottom:1px solid #eee; }
</style>
""", unsafe_allow_html=True)

KML_URL = "https://raw.githubusercontent.com/Urbanoise/test1/main/Parking_Supply.kml"

@st.cache_data(ttl=3600)
def load_kml(url):
    response = requests.get(url)
    response.raise_for_status()
    tree = ET.parse(io.BytesIO(response.content))
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
        space    = re.search(r'Space[:\s]+(\d+)', desc_clean)
        method   = re.search(r'Method[:\s]+([^\<\n&]+)', desc_clean)
        signage  = re.search(r'Signage[:\s]+([^\<\n&]+)', desc_clean)
        location = re.search(r'Location[:\s]+([^\<\n&]+)', desc_clean)
        ls         = pm.find('.//kml:LineString/kml:coordinates', ns)
        poly_outer = pm.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
        pt         = pm.find('.//kml:Point/kml:coordinates', ns)
        lat, lon, coords = None, None, []
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
        rm = (method.group(1).strip().lower() if method else '')
        if rm in ('parallel','paralell'): rm='Parallel'
        elif rm=='90': rm='90°'
        elif rm=='45': rm='45°'
        elif rm in ('parallel or 45','parallel/45','parallel/90','45/90'): rm='Mixed'
        elif rm in ('any','aby'): rm='Any'
        else: rm=rm.title() if rm else 'Unknown'
        rs=(signage.group(1).strip().lower() if signage else '')
        rs='Yes' if rs.startswith('y') else 'No' if rs.startswith('n') else 'Unknown'
        rl=(location.group(1).strip().lower() if location else '')
        if 'pocket' in rl: rl='Pocket'
        elif 'set' in rl: rl='Set-back'
        elif 'on' in rl: rl='On-street'
        else: rl='Unknown'
        street=re.sub(r'\d+$','',name).strip()
        records.append({'name':name,'street':street,'spaces':int(space.group(1)) if space else 0,
            'method':rm,'signage':rs,'location':rl,'lat':lat,'lon':lon,'coords':coords,
            'has_line':ls is not None or poly_outer is not None})
    return pd.DataFrame(records)

try:
    df = load_kml(KML_URL)
except Exception as e:
    st.error(f"⚠️ Could not load KML: {e}")
    st.stop()

with st.sidebar:
    st.markdown("## 🅿️ Filters")
    sel_method = st.multiselect("Parking method", sorted(df['method'].unique()), default=sorted(df['method'].unique()))
    sel_loc    = st.multiselect("Location type",  sorted(df['location'].unique()), default=sorted(df['location'].unique()))
    sel_sign   = st.multiselect("Signage",        sorted(df['signage'].unique()), default=sorted(df['signage'].unique()))
    sel_spaces = st.slider("Min spaces per segment", int(df['spaces'].min()), int(df['spaces'].max()), int(df['spaces'].min()))
    st.markdown("---")
    st.caption(f"{len(df)} segments loaded")

mask = (df['method'].isin(sel_method) & df['location'].isin(sel_loc) &
        df['signage'].isin(sel_sign) & (df['spaces'] >= sel_spaces))
fdf = df[mask]

st.markdown("## 🅿️ Yerevan parking supply")
st.caption("On-street parking inventory · field survey data · Yerevan, Armenia")
st.markdown("---")

k1,k2,k3,k4,k5 = st.columns(5)
for col, val, label in [
    (k1, f"{fdf['spaces'].sum():,}", "Total spaces"),
    (k2, f"{len(fdf):,}", "Segments"),
    (k3, f"{fdf['street'].nunique():,}", "Streets"),
    (k4, f"{fdf[fdf['signage']=='Yes']['spaces'].sum():,}", "Signed spaces"),
    (k5, f"{round(fdf['spaces'].mean(),1)}", "Avg / segment"),
]:
    with col:
        st.markdown(f"<div class='kpi-card'><div class='kpi-number'>{val}</div>"
                    f"<div class='kpi-label'>{label}</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

METHOD_COLORS = {'Parallel':'#1d9e75','90°':'#E24B4A','45°':'#EF9F27',
                 'Mixed':'#7F77DD','Any':'#378ADD','Unknown':'#aaaaaa'}

map_col, chart_col = st.columns([3, 2])

with map_col:
    st.markdown("<div class='section-title'>📍 Spatial distribution</div>", unsafe_allow_html=True)
    m = folium.Map(location=[fdf['lat'].mean(), fdf['lon'].mean()], zoom_start=13, tiles='CartoDB positron')
    for _, row in fdf.iterrows():
        color = METHOD_COLORS.get(row['method'], '#aaa')
        tip = f"{row['name']} | {row['spaces']} spaces | {row['method']} | {row['location']}"
        if row['has_line'] and len(row['coords']) > 1:
            folium.PolyLine(row['coords'], color=color, weight=3+min(row['spaces']/30,5),
                            opacity=0.8, tooltip=tip).add_to(m)
        else:
            folium.CircleMarker([row['lat'],row['lon']], radius=6, color=color,
                                fill=True, fill_opacity=0.9, tooltip=tip).add_to(m)
    legend_html = "<div style='position:fixed;bottom:20px;left:20px;background:white;border:1px solid #ddd;border-radius:8px;padding:10px 14px;z-index:9999;font-size:12px;color:#444;'><strong>Method</strong><br>"
    for method, color in METHOD_COLORS.items():
        legend_html += f"<span style='color:{color}'>■</span> {method}<br>"
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))
    st_folium(m, width=None, height=500, returned_objects=[])

with chart_col:
    st.markdown("<div class='section-title'>Spaces by method</div>", unsafe_allow_html=True)
    method_spaces = fdf.groupby('method')['spaces'].sum().sort_values(ascending=False)
    colors = [METHOD_COLORS.get(m,'#aaa') for m in method_spaces.index]
    fig1, ax1 = plt.subplots(figsize=(4.5,3), facecolor='white')
    ax1.set_facecolor('white')
    ax1.pie(method_spaces.values, labels=method_spaces.index, autopct='%1.0f%%', colors=colors,
            startangle=140, wedgeprops=dict(width=0.55,edgecolor='white'),
            textprops=dict(color='#555',fontsize=9))
    plt.tight_layout(); st.pyplot(fig1); plt.close()

    st.markdown("<div class='section-title'>Spaces by location type</div>", unsafe_allow_html=True)
    loc_data = fdf.groupby('location')['spaces'].sum().sort_values()
    loc_colors = ['#1d9e75','#378ADD','#EF9F27','#aaaaaa'][:len(loc_data)]
    fig2, ax2 = plt.subplots(figsize=(4.5,2), facecolor='white')
    ax2.set_facecolor('white')
    bars = ax2.barh(loc_data.index, loc_data.values, color=loc_colors, height=0.5)
    for bar, val in zip(bars, loc_data.values):
        ax2.text(val+20, bar.get_y()+bar.get_height()/2, f'{val:,}', va='center', color='#666', fontsize=9)
    ax2.set_xlabel('Total spaces', color='#888', fontsize=9)
    ax2.tick_params(colors='#666', labelsize=9)
    for spine in ax2.spines.values(): spine.set_edgecolor('#eee')
    plt.tight_layout(); st.pyplot(fig2); plt.close()

left, right = st.columns(2)

with left:
    st.markdown("<div class='section-title'>📋 Signage coverage</div>", unsafe_allow_html=True)
    sign_data = fdf.groupby('signage')['spaces'].sum()
    sc = [{'Yes':'#1d9e75','No':'#E24B4A','Unknown':'#aaaaaa'}.get(s,'#aaa') for s in sign_data.index]
    fig3, ax3 = plt.subplots(figsize=(5,2.6), facecolor='white')
    ax3.set_facecolor('white')
    ax3.bar(sign_data.index, sign_data.values, color=sc, width=0.45)
    for i,(idx,val) in enumerate(sign_data.items()):
        ax3.text(i, val+40, f'{val:,}', ha='center', color='#666', fontsize=10)
    ax3.set_ylabel('Spaces', color='#888', fontsize=9)
    ax3.tick_params(colors='#666')
    for spine in ax3.spines.values(): spine.set_edgecolor('#eee')
    plt.tight_layout(); st.pyplot(fig3); plt.close()

with right:
    st.markdown("<div class='section-title'>🏆 Top 15 streets by spaces</div>", unsafe_allow_html=True)
    top_streets = fdf.groupby('street')['spaces'].sum().sort_values(ascending=False).head(15)
    fig4, ax4 = plt.subplots(figsize=(5,4.2), facecolor='white')
    ax4.set_facecolor('white')
    y_pos = np.arange(len(top_streets))
    ax4.barh(y_pos, top_streets.values[::-1], color='#1d9e75', height=0.6, alpha=0.85)
    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(top_streets.index[::-1], fontsize=8, color='#555')
    ax4.set_xlabel('Total spaces', color='#888', fontsize=9)
    ax4.tick_params(axis='x', colors='#888', labelsize=8)
    for spine in ax4.spines.values(): spine.set_edgecolor('#eee')
    plt.tight_layout(); st.pyplot(fig4); plt.close()

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>📊 Segment data</div>", unsafe_allow_html=True)
show_df = fdf[['name','street','spaces','method','location','signage']].sort_values('spaces', ascending=False)
st.dataframe(show_df, use_container_width=True, height=280)
st.caption("Yerevan Parking Supply Survey · Transportation Planning")
