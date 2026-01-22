
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="월간 주민등록 인구 증감 대시보드 (Plotly + 버블지도)", layout="wide")

DATA_DEFAULT_PATH = "processed_population_change_long.csv"
CENTROIDS_DEFAULT_PATH = "korea_admin_centroids.csv"  # 사용자 제공(또는 직접 다운로드) 필요

@st.cache_data(show_spinner=False)
def load_long(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(show_spinner=False)
def load_centroids(path: str) -> pd.DataFrame:
    # 인코딩이 euc-kr/cp949일 수도 있어서 순차 시도
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            c = pd.read_csv(path, encoding=enc)
            break
        except Exception:
            c = None
    if c is None:
        raise ValueError("centroids csv를 읽지 못했습니다. 인코딩을 확인해주세요.")
    # 컬럼 표준화
    rename_map = {}
    for col in c.columns:
        if col.strip() in ["위도", "lat", "latitude", "LAT"]:
            rename_map[col] = "lat"
        if col.strip() in ["경도", "lon", "lng", "longitude", "LON", "LNG"]:
            rename_map[col] = "lon"
        if col.strip() in ["행정구역_표준", "행정구역", "지역", "name", "NAME"]:
            rename_map[col] = "region"
        if col.strip() in ["시도"]:
            rename_map[col] = "sido"
        if col.strip() in ["시군구"]:
            rename_map[col] = "sigungu"
    c = c.rename(columns=rename_map)

    # region 컬럼이 없으면 (시도+시군구)로 합성
    if "region" not in c.columns:
        if "sido" in c.columns and "sigungu" in c.columns:
            c["region"] = (c["sido"].fillna("").astype(str).str.strip() + " " +
                           c["sigungu"].fillna("").astype(str).str.strip()).str.strip()
        elif "sido" in c.columns:
            c["region"] = c["sido"].astype(str).str.strip()
        else:
            raise ValueError("centroids csv에 region(또는 시도/시군구) 컬럼이 필요합니다.")

    if "lat" not in c.columns or "lon" not in c.columns:
        raise ValueError("centroids csv에 lat(위도), lon(경도) 컬럼이 필요합니다.")

    c["region"] = c["region"].astype(str).str.strip()
    c["lat"] = pd.to_numeric(c["lat"], errors="coerce")
    c["lon"] = pd.to_numeric(c["lon"], errors="coerce")
    c = c.dropna(subset=["lat","lon"])
    return c[["region","lat","lon"]].drop_duplicates()

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

st.title("📊 월간 주민등록 인구 증감 대시보드 (Plotly + 버블지도)")
st.caption("라인/랭킹은 Plotly로, 지도는 ‘원형(버블) 크기’로 분포를 보여줍니다. 버블에 마우스를 올리면 수치가 뜹니다.")

with st.sidebar:
    st.header("⚙️ 데이터")
    uploaded_long = st.file_uploader("Long 포맷 CSV 업로드(선택)", type=["csv"], key="long")
    if uploaded_long is not None:
        df = pd.read_csv(uploaded_long)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            st.error("업로드 파일에 date 컬럼이 없습니다. processed_population_change_long.csv를 사용하세요.")
            st.stop()
    else:
        df = load_long(DATA_DEFAULT_PATH)

    st.divider()
    st.header("🗺️ 지도 좌표(중심점)")

    uploaded_cent = st.file_uploader("행정구역 중심좌표 CSV 업로드(필수: 지도 기능)", type=["csv"], key="cent")
    if uploaded_cent is not None:
        cent = load_centroids(uploaded_cent)
    else:
        # 같은 폴더에 기본 파일이 있으면 자동 로드
        if os.path.exists(CENTROIDS_DEFAULT_PATH):
            cent = load_centroids(CENTROIDS_DEFAULT_PATH)
        else:
            cent = None

    st.divider()
    st.header("📌 필터")
    measures = ["당월인구수", "인구증감", "전월인구수"]
    measure = st.selectbox("지표", measures, index=1)

    sexes = ["계", "남자인구수", "여자인구수"]
    sex = st.selectbox("성별", sexes, index=0)

    regions = sorted(df["행정구역_표준"].dropna().unique().tolist())
    region = st.selectbox("행정구역(추세용)", ["전국(합계)"] + regions, index=0)

    min_d = df["date"].min().date()
    max_d = df["date"].max().date()
    start_d, end_d = st.slider("기간(추세/랭킹)", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM")

    target_month = st.selectbox(
        "지도/랭킹 기준 월",
        options=sorted(df["date"].dt.to_period("M").astype(str).unique().tolist()),
        index=len(sorted(df["date"].dt.to_period("M").astype(str).unique())) - 1
    )

# ---- 탭 구성 ----
tab1, tab2, tab3 = st.tabs(["📈 추세", "🏆 랭킹", "🗺️ 버블지도(원형 크기)"])

# 공통 필터 적용
mask = (
    (df["measure"] == measure) &
    (df["sex"] == sex) &
    (df["date"].dt.date >= start_d) &
    (df["date"].dt.date <= end_d)
)
dff = df.loc[mask].copy()

# ---- 추세 ----
with tab1:
    if region == "전국(합계)":
        ts = dff.groupby("date", as_index=False)["value"].sum()
    else:
        ts = dff[dff["행정구역_표준"] == region][["date","value"]].sort_values("date")

    ts_sorted = ts.sort_values("date")
    latest_value = ts_sorted["value"].iloc[-1] if len(ts_sorted) else np.nan
    prev_value = ts_sorted["value"].iloc[-2] if len(ts_sorted) >= 2 else np.nan

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("지표", measure)
    c2.metric("성별", sex)
    c3.metric("최신 값", fmt_int(latest_value))
    if measure in ["당월인구수","전월인구수"]:
        delta = latest_value - prev_value if (not pd.isna(latest_value) and not pd.isna(prev_value)) else np.nan
        c4.metric("전월 대비", fmt_signed_int(delta))
    else:
        c4.metric("—", "—")

    fig = px.line(ts_sorted, x="date", y="value", markers=True, title=f"{region} · {measure} · {sex}")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10), xaxis_title="월", yaxis_title="값")
    fig.update_traces(hovertemplate="%{x|%Y-%m}<br>%{y:,.0f}<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

# ---- 랭킹 ----
with tab2:
    rank_month = pd.Period(target_month, freq="M").to_timestamp()
    rank_base = df[(df["measure"] == "인구증감") & (df["sex"] == sex) & (df["date"] == rank_month)].copy()

    if rank_base.empty:
        st.info("선택한 월에 랭킹 데이터를 만들 수 없습니다(해당 월이 데이터 범위 밖이거나 결측일 수 있어요).")
    else:
        inc = rank_base.sort_values("value", ascending=False).head(10)
        dec = rank_base.sort_values("value", ascending=True).head(10)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**증가 Top 10 (인구증감)**")
            fig_inc = px.bar(inc[::-1], x="value", y="행정구역_표준", orientation="h")
            fig_inc.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="인구증감", yaxis_title="")
            fig_inc.update_traces(hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>")
            st.plotly_chart(fig_inc, use_container_width=True)

        with c2:
            st.markdown("**감소 Top 10 (인구증감)**")
            fig_dec = px.bar(dec, x="value", y="행정구역_표준", orientation="h")
            fig_dec.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="인구증감", yaxis_title="")
            fig_dec.update_traces(hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>")
            st.plotly_chart(fig_dec, use_container_width=True)

# ---- 버블지도 ----
with tab3:
    st.subheader("🗺️ 버블지도: 원형 크기 = 규모, 마우스오버 = 상세 수치")

    if cent is None:
        st.warning("지도 기능을 쓰려면 '행정구역 중심좌표 CSV'가 필요합니다.")
        st.markdown(
            """
**필요 컬럼(최소)**  
- `region`(또는 `행정구역_표준` / `행정구역` / `지역` / `시도`+`시군구`)  
- `lat`(위도), `lon`(경도)

**추천 데이터 소스 예시**  
- GitHub에 ‘행정구역 중심점(위/경도) CSV’를 제공하는 공개 저장소(예: cubensys/Korea_District) citeturn1view0  
- 전국 행정구역 중심좌표 CSV를 공유한 글(예: 티스토리 ‘전국 중심 좌표데이터.csv’) citeturn9view0

다운로드한 뒤 파일명을 `korea_admin_centroids.csv`로 저장해서 앱과 같은 폴더에 두거나, 사이드바에서 업로드해 주세요.
            """
        )
        st.stop()

    map_month = pd.Period(target_month, freq="M").to_timestamp()
    map_base = df[(df["date"] == map_month) & (df["measure"] == measure) & (df["sex"] == sex)].copy()

    if map_base.empty:
        st.info("선택한 월에 지도 데이터를 만들 수 없습니다.")
        st.stop()

    # 지역명 정리(centroids와 매칭)
    map_base["region"] = map_base["행정구역_표준"].astype(str).str.strip()

    m = map_base.merge(cent, on="region", how="inner")

    # 매칭이 너무 적으면 안내
    match_rate = len(m) / max(len(map_base), 1)
    if match_rate < 0.6:
        st.warning(f"좌표 매칭률이 낮습니다: {match_rate:.0%}. (지역명 표기가 다를 수 있어요)")

    # 버블 크기(절대값) + 색상(부호)
    m["abs_value"] = m["value"].abs()
    # size가 0이면 점이 안보여서 최소값 부여
    m["abs_value"] = m["abs_value"].fillna(0.0)
    m.loc[m["abs_value"] == 0, "abs_value"] = 1.0

    # sizeref 자동 스케일 (Plotly 권장 방식)
    max_size = m["abs_value"].max()
    # target max marker size in pixels ~ 40
    sizeref = 2.0 * max_size / (40.0 ** 2) if max_size > 0 else 1

    title = f"{target_month} · {measure} · {sex}"
    fig_map = px.scatter_mapbox(
        m,
        lat="lat",
        lon="lon",
        size="abs_value",
        size_max=40,
        color="value",
        hover_name="region",
        hover_data={
            "value":":,.0f",
            "abs_value":False,
            "lat":False,
            "lon":False
        },
        zoom=5,
        center={"lat":36.5, "lon":127.8},
        title=title,
        height=650
    )
    fig_map.update_traces(
        marker=dict(sizeref=sizeref, sizemode="area"),
        hovertemplate="<b>%{hovertext}</b><br>값: %{customdata[0]:,.0f}<extra></extra>"
    )
    fig_map.update_layout(
        mapbox_style="open-street-map",
        margin=dict(l=10, r=10, t=50, b=10),
        coloraxis_colorbar_title="값"
    )

    st.plotly_chart(fig_map, use_container_width=True)

    st.caption("버블 크기: 값의 절대크기(규모) / 색: 값의 부호와 크기(증가/감소 포함). 마우스를 올리면 지역명과 수치가 표시됩니다.")
