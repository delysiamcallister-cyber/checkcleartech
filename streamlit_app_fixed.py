import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats
import numpy as np
import glob
import os

st.set_page_config(page_title="ClearCheck Dashboard", layout="wide")
st.title("ClearCheck Technician Approval Dashboard")

# Load ALL Excel files with detailed error handling
@st.cache_data
def load_all_excel_files():
    try:
        # Find all .xlsx files
        excel_files = glob.glob("*.xlsx")
        
        st.write(f"DEBUG: Found {len(excel_files)} Excel files")
        
        if not excel_files:
            st.error("❌ No Excel files found! Make sure these files are in the repo:")
            st.write("- Arnold_001.xlsx through Arnold_009.xlsx")
            st.write("- Mendez_001.xlsx through Mendez_005.xlsx")
            st.write("- Shawn_001.xlsx")
            return None
        
        st.write(f"📁 Files found: {', '.join(excel_files)}")
        
        # Load and combine all files
        dfs = []
        for file in excel_files:
            try:
                df_temp = pd.read_excel(file)
                dfs.append(df_temp)
                st.write(f"✅ Loaded {file} - {len(df_temp)} rows")
            except Exception as e:
                st.write(f"⚠️ Error loading {file}: {e}")
        
        if not dfs:
            st.error("No data could be loaded from Excel files")
            return None
        
        df = pd.concat(dfs, ignore_index=True)
        st.write(f"📊 Total rows combined: {len(df)}")
        
        # Check columns
        st.write(f"📋 Columns found: {list(df.columns)}")
        
        # Clean technician names from PROVIDER_APPROVING_NAME
        df['Technician'] = df['PROVIDER_APPROVING_NAME'].str.extract(r'(\w+)\s')[0].str.capitalize()
        
        # Convert APPROVAL_DATE to datetime
        df['APPROVAL_DATE'] = pd.to_datetime(df['APPROVAL_DATE'])
        
        # Extract time features
        df['date'] = df['APPROVAL_DATE'].dt.date
        df['weekday'] = df['APPROVAL_DATE'].dt.day_name()
        df['hour'] = df['APPROVAL_DATE'].dt.hour
        df['month'] = df['APPROVAL_DATE'].dt.month
        df['is_weekend'] = df['weekday'].isin(['Saturday', 'Sunday'])
        
        # Calculate gaps
        df_sorted = df.sort_values('APPROVAL_DATE')
        df_sorted['duration_sameday'] = df_sorted.groupby('Technician')['APPROVAL_DATE'].diff().dt.total_seconds()
        
        st.write(f"✅ Data loaded successfully!")
        st.write(f"Technicians: {sorted(df_sorted['Technician'].unique())}")
        
        return df_sorted
    
    except Exception as e:
        st.error(f"❌ Critical error loading data: {str(e)}")
        st.write("Please check that all Excel files are uploaded to GitHub")
        return None

# Load data
with st.spinner("Loading data..."):
    df = load_all_excel_files()

if df is None:
    st.stop()

# Remove debug messages after successful load
st.success("✅ Dashboard loaded successfully!")

techs = sorted(df['Technician'].unique())
day_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
review_thresholds = [0, 2, 5, 10, 30, 60]

# Sidebar
tech = st.sidebar.selectbox("Select Technician", techs)

# Get data for selected technician
t_df = df[df['Technician'] == tech].copy()
gaps_sameday = t_df['duration_sameday'].dropna()

# Daily aggregates
t_daily = t_df.groupby('date').size().reset_index(name='approvals_per_day')
t_daily['date'] = pd.to_datetime(t_daily['date'])

# Sidebar metrics
st.sidebar.markdown(f"### {tech}")
st.sidebar.metric("Total Approvals", len(t_df))
st.sidebar.metric("Active Days", t_df['date'].nunique())
if len(gaps_sameday) > 0:
    st.sidebar.metric("Avg Gap (sec)", f"{gaps_sameday.mean():.1f}")
    st.sidebar.metric("Median Gap (sec)", f"{gaps_sameday.median():.1f}")

# VOLUME & TIMING
st.header("📊 Volume & Timing")
col1, col2, col3 = st.columns(3)

with col1:
    fig_daily = px.line(t_daily.sort_values('date'), x='date', y='approvals_per_day',
                         markers=True, title='Approvals per day')
    if len(t_daily) > 0:
        fig_daily.add_hline(y=t_daily['approvals_per_day'].mean(), line_dash='dash', line_color='green')
    st.plotly_chart(fig_daily, use_container_width=True)

with col2:
    wk = t_df['weekday'].value_counts(normalize=True).reindex(day_order).fillna(0) * 100
    fig_weekday = px.bar(x=wk.index, y=wk.values, title='Approvals by weekday',
                          labels={'x': 'weekday', 'y': '% of approvals'})
    st.plotly_chart(fig_weekday, use_container_width=True)

with col3:
    off_hours = (~t_df['hour'].between(7, 18)).mean() * 100
    weekend = t_df['is_weekend'].mean() * 100
    fig_offhours = go.Figure(go.Bar(x=['Outside 7am-7pm', 'Weekend'], y=[off_hours, weekend]))
    fig_offhours.update_layout(title='Off-hours and weekend activity (%)', yaxis_title='% of approvals')
    st.plotly_chart(fig_offhours, use_container_width=True)

# GAP ANALYSIS
st.header("⏱️ Gap Analysis")

if len(gaps_sameday) > 0:
    col1, col2, col3 = st.columns(3)

    with col1:
        fast_row = {f'{t}s or less (%)': round((gaps_sameday <= t).mean() * 100, 2) for t in review_thresholds}
        fig_fast = px.bar(x=list(fast_row.keys()), y=list(fast_row.values()), title='Fast-approval thresholds',
                           labels={'x': 'threshold', 'y': '% of approvals'})
        st.plotly_chart(fig_fast, use_container_width=True)

    with col2:
        short_gaps = gaps_sameday[gaps_sameday <= 300]
        if len(short_gaps) > 0:
            fig_hist = px.histogram(short_gaps, nbins=60, title='Short gaps (<=300s)',
                                     labels={'value': 'seconds'})
            fig_hist.add_vline(x=gaps_sameday.median(), line_dash='dash', line_color='red')
            st.plotly_chart(fig_hist, use_container_width=True)

    with col3:
        fig_box = go.Figure()
        for tc in techs:
            g = df.loc[df['Technician'] == tc, 'duration_sameday'].dropna().clip(upper=600)
            fig_box.add_trace(go.Box(y=g, name=tc, marker_color='crimson' if tc == tech else 'lightgray'))
        fig_box.update_layout(title='Same-day gap by technician (capped at 600s)', height=400)
        st.plotly_chart(fig_box, use_container_width=True)

    # Statistics table
    skew_df = pd.DataFrame([{
        'skewness': round(gaps_sameday.skew(), 2) if len(gaps_sameday) > 2 else None,
        'mean_seconds': round(gaps_sameday.mean(), 2),
        'median_seconds': round(gaps_sameday.median(), 2),
        'std_dev': round(gaps_sameday.std(), 2)
    }])
    st.subheader("Gap Statistics")
    st.dataframe(skew_df, use_container_width=True)

# TECHNICIAN COMPARISON
st.header("🔍 Technician Comparison")
comparison_data = []
for tc in techs:
    tc_df = df[df['Technician'] == tc]
    tc_gaps = tc_df['duration_sameday'].dropna()
    comparison_data.append({
        'Technician': tc,
        'Total Approvals': len(tc_df),
        'Active Days': tc_df['date'].nunique(),
        'Mean Gap (min)': round(tc_gaps.mean()/60, 2) if len(tc_gaps) > 0 else 0,
        'Median Gap (min)': round(tc_gaps.median()/60, 2) if len(tc_gaps) > 0 else 0,
        'Avg per Day': round(len(tc_df) / tc_df['date'].nunique(), 1) if tc_df['date'].nunique() > 0 else 0
    })

comparison_df = pd.DataFrame(comparison_data)
st.dataframe(comparison_df, use_container_width=True)
