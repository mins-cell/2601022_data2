
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import date

st.set_page_config(page_title="월간 주민등록 인구 증감 대시보드", layout="wide")

DATA_DEFAULT_PATH = "processed_population_change_long.csv"

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    # Ensure canonical ordering
    df["measure"] = df["measure"].astype("category")
    df["sex"] = df["sex"].astype("category")
    return df

def fmt_int(x):
    if pd.isna(x):
        return "-"
    try:
        return f"{int(round(float(x))):,}"
    except:
        return str(x)

def fmt_signed_int(x):
    if pd.isna(x):
        return "-"
    try:
        xi = int(round(float(x)))
        sign = "+" if xi > 0 else ""
        return f"{sign}{xi:,}"
    except:
        return str(x)

st.title("📊 월간 주민등록 인구 증감 대시보드")
st.caption("데이터 기반: 전월/당월 인구수 및 인구증감(남/여/계). 행정구역 명칭 변경(전라북도 → 전북특별자치도)은 표준명으로 자동 통합.")

with st.sidebar:
    st.header("⚙️ 설정")
    uploaded = st.file_uploader("CSV 업로드(선택)", type=["csv"])
    if uploaded is not None:
        # If user uploads the original wide CSV, try to auto-convert
        raw = pd.read_csv(uploaded, encoding="cp949")
        st.success("업로드된 CSV를 읽었습니다. (원본 wide 형태일 수 있어요)")
        st.info("원본 wide CSV는 이 앱의 기본 포맷(long)과 달라서, 아래 'long 포맷으로 변환'을 눌러주세요.")
        if st.button("🔁 long 포맷으로 변환해서 사용하기"):
            import re
            def standardize_region(s: str) -> str:
                if pd.isna(s):
                    return s
                s = str(s).strip()
                if s.startswith("전라북도"):
                    s = s.replace("전라북도", "전북특별자치도", 1)
                return s

            raw["행정구역_표준"] = raw["행정구역"].map(standardize_region)
            value_cols = [c for c in raw.columns if c not in ["행정구역","행정구역_표준"]]
            pattern = re.compile(r"^(?P<ym>\d{4})년(?P<m>\d{1,2})월_(?P<measure>전월인구수|당월인구수|인구증감)_(?P<sex>남자인구수|여자인구수|계)$")
            meta = []
            for c in value_cols:
                m = pattern.match(c)
                if not m:
                    continue
                meta.append((c, int(m.group("ym")), int(m.group("m")), m.group("measure"), m.group("sex")))
            meta = pd.DataFrame(meta, columns=["col","year","month","measure","sex"])
            long = raw.melt(
                id_vars=["행정구역","행정구역_표준"],
                value_vars=meta["col"].tolist(),
                var_name="col",
                value_name="value_raw"
            ).merge(meta, on="col", how="left")

            def to_num(x):
                if pd.isna(x): 
                    return np.nan
                s = str(x).strip().replace(",","")
                if s == "":
                    return np.nan
                try:
                    return float(s)
                except:
                    return np.nan

            long["value"] = long["value_raw"].map(to_num).astype("float")
            long["date"] = pd.to_datetime(long["year"].astype(str) + "-" + long["month"].astype(str).str.zfill(2) + "-01")
            tidy = long[["행정구역_표준","date","measure","sex","value"]].copy()
            df = tidy.groupby(["행정구역_표준","date","measure","sex"], as_index=False)["value"].max()
        else:
            st.stop()
    else:
        df = load_data(DATA_DEFAULT_PATH)

    # Filters
    measures = ["당월인구수", "인구증감", "전월인구수"]
    measure = st.selectbox("지표", measures, index=0)

    sexes = ["계", "남자인구수", "여자인구수"]
    sex = st.selectbox("성별", sexes, index=0)

    regions = sorted(df["행정구역_표준"].dropna().unique().tolist())
    region = st.selectbox("행정구역", ["전국(합계)"] + regions, index=0)

    min_d = df["date"].min().date()
    max_d = df["date"].max().date()
    start_d, end_d = st.slider(
        "기간",
        min_value=min_d,
        max_value=max_d,
        value=(min_d, max_d),
        format="YYYY-MM"
    )

    target_month = st.selectbox(
        "랭킹/비교 기준 월",
        options=sorted(df["date"].dt.to_period("M").astype(str).unique().tolist()),
        index=len(sorted(df["date"].dt.to_period("M").astype(str).unique())) - 1
    )

# Apply filters
mask = (
    (df["measure"] == measure) &
    (df["sex"] == sex) &
    (df["date"].dt.date >= start_d) &
    (df["date"].dt.date <= end_d)
)
dff = df.loc[mask].copy()

# Build national total if needed
if region == "전국(합계)":
    ts = dff.groupby("date", as_index=False)["value"].sum()
else:
    ts = dff[dff["행정구역_표준"] == region][["date","value"]].sort_values("date")

# KPI cards
latest = ts.sort_values("date").tail(1)
prev = ts.sort_values("date").tail(2).head(1)

latest_value = latest["value"].iloc[0] if len(latest) else np.nan
prev_value = prev["value"].iloc[0] if len(prev) else np.nan

col1, col2, col3, col4 = st.columns(4)
col1.metric("선택 지표", measure)
col2.metric("성별", sex)
col3.metric("최신 값", fmt_int(latest_value))
if measure in ["당월인구수","전월인구수"]:
    delta = latest_value - prev_value if (not pd.isna(latest_value) and not pd.isna(prev_value)) else np.nan
    col4.metric("전월 대비 변화", fmt_signed_int(delta))
else:
    col4.metric("—", "—")

# Trend chart
st.subheader("📈 추세")
chart_df = ts.copy()
chart_df["월"] = chart_df["date"].dt.to_period("M").astype(str)

line = (
    alt.Chart(chart_df)
    .mark_line()
    .encode(
        x=alt.X("date:T", title="월"),
        y=alt.Y("value:Q", title="값"),
        tooltip=[alt.Tooltip("월:N"), alt.Tooltip("value:Q", format=",.0f")]
    )
    .properties(height=320)
)
st.altair_chart(line, use_container_width=True)

# Rankings (only makes sense for 인구증감 / 당월인구수)
st.subheader("🏆 지역 랭킹")
rank_month = pd.Period(target_month, freq="M").to_timestamp()

rank_base = df[(df["measure"] == "인구증감") & (df["sex"] == sex) & (df["date"] == rank_month)].copy()
if rank_base.empty:
    st.info("선택한 월에 랭킹 데이터를 만들 수 없습니다(해당 월이 데이터 범위 밖이거나 결측일 수 있어요).")
else:
    inc = rank_base.sort_values("value", ascending=False).head(10)[["행정구역_표준","value"]]
    dec = rank_base.sort_values("value", ascending=True).head(10)[["행정구역_표준","value"]]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**증가 Top 10 (인구증감)**")
        inc_show = inc.copy()
        inc_show["인구증감"] = inc_show["value"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
        st.dataframe(inc_show[["행정구역_표준","인구증감"]], use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**감소 Top 10 (인구증감)**")
        dec_show = dec.copy()
        dec_show["인구증감"] = dec_show["value"].map(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
        st.dataframe(dec_show[["행정구역_표준","인구증감"]], use_container_width=True, hide_index=True)

# Data quality section
with st.expander("🧼 데이터 품질(결측치/명칭통합) 보기"):
    st.write("이 데이터는 일부 행정구역이 명칭 변경으로 인해 특정 기간 값이 비어 있습니다(예: 전라북도 → 전북특별자치도).")
    # Missingness quick view (by date) for selected measure/sex
    q = df[(df["measure"] == measure) & (df["sex"] == sex)].copy()
    miss = q.groupby("date")["value"].apply(lambda s: s.isna().mean()).reset_index(name="missing_rate")
    miss["월"] = miss["date"].dt.to_period("M").astype(str)
    miss_chart = (
        alt.Chart(miss)
        .mark_bar()
        .encode(
            x=alt.X("date:T", title="월"),
            y=alt.Y("missing_rate:Q", title="결측 비율", axis=alt.Axis(format="%")),
            tooltip=[alt.Tooltip("월:N"), alt.Tooltip("missing_rate:Q", format=".1%")]
        )
        .properties(height=200)
    )
    st.altair_chart(miss_chart, use_container_width=True)

st.caption("Tip: '인구증감(계)'를 기본으로 보고, 성별로 전환하면 변화의 원인을 더 잘 볼 수 있어요.")
