"""India Air Quality Analytics Dashboard (2015-2020)

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_prep import (AQI_BUCKETS, AQI_COLORS, POLLUTANTS, UNITS,
                       interpolate_gaps, load_data, missing_summary)

st.set_page_config(page_title="India Air Quality Dashboard", layout="wide")

# Fixed categorical order; a city keeps its colour for the whole session.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
MAX_CITIES = len(SERIES_COLORS)
DEFAULT_CITIES = ["Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad"]
PLOT_LAYOUT = dict(template="plotly_white", margin=dict(l=10, r=10, t=40, b=10),
                   font=dict(size=13), hovermode="x unified",
                   legend=dict(orientation="h", y=-0.15))


@st.cache_data
def get_data() -> pd.DataFrame:
    return load_data()


def city_colors(selected):
    """Give each city a stable colour slot; new cities take the first free slot."""
    cmap = st.session_state.setdefault("city_colors", {})
    for c in list(cmap):
        if c not in selected:
            del cmap[c]
    used = set(cmap.values())
    for c in selected:
        if c not in cmap:
            free = next(col for col in SERIES_COLORS if col not in used)
            cmap[c] = free
            used.add(free)
    return dict(cmap)


df_raw = get_data()
all_cities = sorted(df_raw["City"].unique())
df_all = df_raw

# ---------------------------------------------------------------- Sidebar
st.sidebar.header("Filters")
cities = st.sidebar.multiselect(
    f"Cities (up to {MAX_CITIES})", all_cities,
    default=[c for c in DEFAULT_CITIES if c in all_cities],
    max_selections=MAX_CITIES)

dmin, dmax = df_all["Date"].min().date(), df_all["Date"].max().date()
date_range = st.sidebar.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
pollutant = st.sidebar.selectbox("Pollutant", POLLUTANTS, index=0)
freq_label = st.sidebar.radio("Time resolution", ["Daily", "Weekly", "Monthly"], index=2,
                              horizontal=True)
fill_gaps = st.sidebar.checkbox("Interpolate short gaps (up to 7 days)", value=False)
cap_aqi = st.sidebar.checkbox("Cap AQI at 500 (CPCB scale maximum)", value=True,
                              help="543 readings exceed 500, mostly Ahmedabad; the "
                                   "official scale ends at 500.")

st.sidebar.markdown("---")
st.sidebar.caption("Data: CPCB city-level daily readings, 2015-2020 "
                   "(Kaggle: Air Quality Data in India, Vopani).")

if not cities:
    st.warning("Select at least one city in the sidebar.")
    st.stop()
if not isinstance(date_range, (list, tuple)) or len(date_range) != 2:
    st.info("Pick an end date to complete the date range.")
    st.stop()

if cap_aqi:
    df_all = df_raw.assign(AQI=df_raw["AQI"].clip(upper=500))

start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
in_range = df_all[(df_all["Date"] >= start) & (df_all["Date"] <= end)]
df = in_range[in_range["City"].isin(cities)]
if fill_gaps:
    df = interpolate_gaps(df, POLLUTANTS + ["AQI"])
colors = city_colors(cities)
FREQ = {"Daily": "D", "Weekly": "W", "Monthly": "MS"}[freq_label]

# ---------------------------------------------------------------- Header + KPIs
st.title("India Air Quality Analytics Dashboard")
st.caption(f"{len(cities)} cities  |  {start:%d %b %Y} to {end:%d %b %Y}  |  "
           f"{len(df):,} city-day records")

aqi = df.dropna(subset=["AQI"])
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Average AQI", f"{aqi['AQI'].mean():.0f}" if len(aqi) else "n/a")
if len(aqi):
    peak = aqi.loc[aqi["AQI"].idxmax()]
    k2.metric("Peak AQI", f"{peak['AQI']:.0f}", f"{peak['City']}, {peak['Date']:%d %b %Y}",
              delta_color="off", delta_arrow="off")
    poor_share = aqi["AQI_Bucket"].isin(["Poor", "Very Poor", "Severe"]).mean() * 100
    k3.metric("Days Poor or worse", f"{poor_share:.1f}%")
    city_mean = aqi.groupby("City")["AQI"].mean().sort_values()
    k4.metric("Cleanest city", city_mean.index[0], f"avg AQI {city_mean.iloc[0]:.0f}",
              delta_color="off", delta_arrow="off")
    k5.metric("Most polluted city", city_mean.index[-1], f"avg AQI {city_mean.iloc[-1]:.0f}",
              delta_color="off", delta_arrow="off")

tabs = st.tabs(["Trends", "City Ranking", "Pollutants", "Seasonality",
                "AQI Categories", "COVID Lockdown", "Correlation", "Data"])


def resample_city(frame: pd.DataFrame, col: str) -> pd.DataFrame:
    return (frame.set_index("Date").groupby("City")[col]
                 .resample(FREQ).mean().reset_index())


# ---------------------------------------------------------------- 1. Trends
with tabs[0]:
    st.subheader(f"AQI over time ({freq_label.lower()} average)")
    ts = resample_city(df, "AQI")
    fig = px.line(ts, x="Date", y="AQI", color="City", color_discrete_map=colors,
                  category_orders={"City": cities})
    fig.update_traces(line=dict(width=2), connectgaps=False)
    for name in ["Moderate", "Poor", "Very Poor"]:
        lo = {"Moderate": 100, "Poor": 200, "Very Poor": 300}[name]
        fig.add_hline(y=lo, line=dict(color="#9a9a9a", width=1, dash="dot"),
                      annotation_text=f"{name} >{lo}", annotation_position="top right",
                      annotation_font=dict(size=11, color="#666"))
    fig.update_layout(**PLOT_LAYOUT, yaxis_title="AQI", xaxis_title=None, height=460)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Year-on-year average AQI")
    yearly = df.groupby(["Year", "City"], as_index=False)["AQI"].mean()
    fig = px.bar(yearly, x="Year", y="AQI", color="City", barmode="group",
                 color_discrete_map=colors, category_orders={"City": cities})
    fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, bargap=0.2,
                      bargroupgap=0.05, yaxis_title="Average AQI", height=400)
    fig.update_traces(marker_line_width=0)
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- 2. City ranking
with tabs[1]:
    st.subheader("Average AQI for all 26 cities in the selected period")
    rank = (in_range.groupby("City")["AQI"].agg(["mean", "count"]).dropna()
                    .sort_values("mean").reset_index())
    rank["Selected"] = rank["City"].isin(cities).map({True: "Selected", False: "Other"})
    fig = px.bar(rank, x="mean", y="City", orientation="h", color="Selected",
                 color_discrete_map={"Selected": "#2a78d6", "Other": "#c9c8c2"},
                 hover_data={"count": True, "mean": ":.0f"},
                 category_orders={"City": rank["City"].tolist()[::-1]},
                 labels={"mean": "Average AQI", "count": "Days with AQI"})
    fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"},
                      height=680, yaxis_title=None, legend_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption("Cities with very few AQI readings in the chosen period may not be "
               "representative; hover a bar to see the number of days.")

# ---------------------------------------------------------------- 3. Pollutants
with tabs[2]:
    st.subheader(f"{pollutant} over time ({UNITS[pollutant]})")
    ts = resample_city(df, pollutant)
    fig = px.line(ts, x="Date", y=pollutant, color="City", color_discrete_map=colors,
                  category_orders={"City": cities})
    fig.update_traces(line=dict(width=2))
    fig.update_layout(**PLOT_LAYOUT, yaxis_title=f"{pollutant} ({UNITS[pollutant]})",
                      xaxis_title=None, height=420)
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"Distribution of daily {pollutant}")
        fig = px.box(df.dropna(subset=[pollutant]), x="City", y=pollutant, color="City",
                     color_discrete_map=colors, category_orders={"City": cities},
                     points=False)
        fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, showlegend=False,
                          height=420, xaxis_title=None,
                          yaxis_title=f"{pollutant} ({UNITS[pollutant]})")
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Average pollutant profile")
        main = ["PM2.5", "PM10", "NO2", "SO2", "O3", "NH3"]
        prof = df.groupby("City")[main].mean().reindex(cities).reset_index()
        prof = prof.melt(id_vars="City", var_name="Pollutant", value_name="Average")
        fig = px.bar(prof, x="Pollutant", y="Average", color="City", barmode="group",
                     color_discrete_map=colors, category_orders={"City": cities})
        fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, height=420,
                          yaxis_title="Average concentration (µg/m³)", xaxis_title=None)
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- 4. Seasonality
with tabs[3]:
    focus = st.selectbox("City for the heatmap", cities, key="season_city")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader(f"Monthly average AQI in {focus}")
        hm = (df[df["City"] == focus].groupby(["Year", "Month"])["AQI"].mean()
                .unstack("Month").reindex(columns=range(1, 13)))
        fig = go.Figure(go.Heatmap(
            z=hm.values, x=[pd.Timestamp(2000, m, 1).strftime("%b") for m in hm.columns],
            y=hm.index.astype(str),
            colorscale=[[0, "#cde2fb"], [0.5, "#3987e5"], [1, "#0d366b"]],
            colorbar=dict(title="AQI"), xgap=2, ygap=2,
            hovertemplate="%{x} %{y}<br>AQI %{z:.0f}<extra></extra>"))
        fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, height=380,
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Average AQI by season")
        order = ["Winter", "Summer", "Monsoon", "Post-monsoon"]
        sea = df.groupby(["Season", "City"], as_index=False)["AQI"].mean()
        fig = px.bar(sea, x="Season", y="AQI", color="City", barmode="group",
                     color_discrete_map=colors,
                     category_orders={"Season": order, "City": cities})
        fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, height=380,
                          xaxis_title=None, yaxis_title="Average AQI")
        st.plotly_chart(fig, width="stretch")
    st.caption("Winter: Dec-Feb, Summer: Mar-May, Monsoon: Jun-Sep, Post-monsoon: Oct-Nov.")

# ---------------------------------------------------------------- 5. AQI categories
with tabs[4]:
    st.subheader("Share of days in each CPCB AQI category")
    cat = (df.dropna(subset=["AQI_Bucket"]).groupby(["City", "AQI_Bucket"]).size()
             .rename("Days").reset_index())
    cat["Share %"] = cat["Days"] / cat.groupby("City")["Days"].transform("sum") * 100
    fig = px.bar(cat, x="Share %", y="City", color="AQI_Bucket", orientation="h",
                 color_discrete_map=AQI_COLORS,
                 category_orders={"AQI_Bucket": AQI_BUCKETS, "City": cities[::-1]},
                 hover_data={"Days": True, "Share %": ":.1f"})
    fig.update_traces(marker_line=dict(color="white", width=2))
    fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, barmode="stack",
                      height=120 + 60 * len(cities), xaxis_title="% of days",
                      yaxis_title=None, legend_title=None)
    st.plotly_chart(fig, width="stretch")
    st.markdown("CPCB scale: Good 0-50, Satisfactory 51-100, Moderate 101-200, "
                "Poor 201-300, Very Poor 301-400, Severe 401-500.")

# ---------------------------------------------------------------- 6. COVID lockdown
with tabs[5]:
    st.subheader("Effect of the 2020 national lockdown (25 Mar - 31 May)")
    st.caption("Compares the lockdown window in 2020 with the same dates in 2019. "
               "Uses all data, independent of the date filter.")
    base = df_all[df_all["City"].isin(cities)]
    md = base["Date"].dt.strftime("%m-%d")
    window = (md >= "03-25") & (md <= "05-31")
    comp_cols = ["AQI", "PM2.5", "PM10", "NO2", "CO", "SO2", "O3"]
    y19 = base[window & (base["Year"] == 2019)].groupby("City")[comp_cols].mean()
    y20 = base[window & (base["Year"] == 2020)].groupby("City")[comp_cols].mean()
    change = ((y20 - y19) / y19 * 100).reindex(cities).round(1)
    metric = st.radio("Measure", comp_cols, horizontal=True, key="covid_metric")
    ch = change[metric].dropna().reset_index()
    ch.columns = ["City", "Change %"]
    ch["Direction"] = ch["Change %"].map(lambda v: "Decrease" if v < 0 else "Increase")
    fig = px.bar(ch, x="City", y="Change %", color="Direction",
                 color_discrete_map={"Decrease": "#2a78d6", "Increase": "#eb6834"},
                 text=ch["Change %"].map(lambda v: f"{v:+.0f}%"))
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.add_hline(y=0, line=dict(color="#666", width=1))
    fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, height=420,
                      yaxis_title=f"% change in {metric}, 2020 vs 2019",
                      xaxis_title=None, legend_title=None)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(change.rename(columns=lambda c: f"{c} %"), width="stretch")

# ---------------------------------------------------------------- 7. Correlation
with tabs[6]:
    st.subheader("Correlation between pollutants and AQI (Pearson)")
    corr = df[POLLUTANTS + ["AQI"]].corr().round(2)
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1,
        colorscale=[[0, "#eb6834"], [0.5, "#f2f1ed"], [1, "#2a78d6"]],
        text=corr.values, texttemplate="%{text:.2f}", xgap=2, ygap=2,
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>"))
    fig.update_layout(**{**PLOT_LAYOUT, "hovermode": "closest"}, height=560,
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")
    top = corr["AQI"].drop("AQI").sort_values(ascending=False)
    st.markdown("**Strongest drivers of AQI in this selection:** " +
                ", ".join(f"{k} ({v:.2f})" for k, v in top.head(3).items()))

# ---------------------------------------------------------------- 8. Data
with tabs[7]:
    st.subheader("Filtered records")
    show = df[["City", "Date", "AQI", "AQI_Bucket"] + POLLUTANTS]
    st.dataframe(show, width="stretch", height=380, hide_index=True)
    st.download_button("Download filtered data (CSV)", show.to_csv(index=False),
                       file_name="aqi_filtered.csv", mime="text/csv")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Missing values")
        st.dataframe(missing_summary(df), width="stretch")
    with c2:
        st.subheader("Summary statistics")
        st.dataframe(df[["AQI"] + POLLUTANTS].describe().T.round(1), width="stretch")
