import streamlit as st
import pandas as pd
import io

st.title("装置ログビューア（Step 1.4：期間フィルタ＋プルダウン＋ダウンロード）")

uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])
if uploaded_file is None:
    st.info("サンプル: 日時, 装置, 稼働時間, 不良数 の列を想定（ヘッダは日本語でOK）")
    st.stop()

# ===== 読み込み & 簡易列検出
df = pd.read_csv(uploaded_file)
COL_TIME = next((c for c in df.columns if c in ["日時","date","timestamp","time"]), None)
COL_MACHINE = next((c for c in df.columns if c in ["装置","機番","machine","device"]), None)
COL_RUNTIME = next((c for c in df.columns if c in ["稼働時間","runtime","run_time","uptime"]), None)
COL_DEFECT = next((c for c in df.columns if c in ["不良数","defect","rejects","ng"]), None)

if COL_TIME:
    df[COL_TIME] = pd.to_datetime(df[COL_TIME], errors="coerce")

# ===== 期間指定フィルタ（サイドバー）
with st.sidebar:
    st.header("期間フィルタ")
    if COL_TIME and df[COL_TIME].notna().any():
        min_d = pd.to_datetime(df[COL_TIME]).min().date()
        max_d = pd.to_datetime(df[COL_TIME]).max().date()
        default_start = max_d - pd.Timedelta(days=6)
        if default_start < min_d:
            default_start = min_d
        date_range = st.date_input(
            "対象期間（開始日〜終了日）",
            value=(default_start, max_d),
            min_value=min_d,
            max_value=max_d,
        )
    else:
        date_range = None

# ===== フィルタ適用
work = df.copy()
if COL_TIME and date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start_d = pd.to_datetime(date_range[0])
    end_d = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    work = work[(work[COL_TIME] >= start_d) & (work[COL_TIME] <= end_d)]

# ===== プレビュー
st.subheader("① プレビュー")
st.caption(f"全体: {len(df):,}行 / フィルタ後: {len(work):,}行")
st.dataframe(work, use_container_width=True)

# ===== オプション（プルダウン）
st.subheader("② オプション（プルダウン）")
colA, colB, colC = st.columns([1,1,1])
with colA:
    agg_func = st.selectbox("集計関数", ["sum","mean","median","max","min","count"], index=0)
with colB:
    chart_type = st.selectbox("グラフ種類", ["line","bar","area","scatter"], index=0)
with colC:
    time_gran = st.selectbox("時系列の粒度", ["そのまま","日","週","月"], index=0)

# ===== 基本KPI
st.subheader("③ 基本KPI")
total_runtime = work[COL_RUNTIME].sum() if COL_RUNTIME in work else None
total_defect = work[COL_DEFECT].sum() if COL_DEFECT in work else None
defect_rate = (total_defect / total_runtime * 100) if (total_runtime and total_runtime != 0) else None

k1, k2, k3 = st.columns(3)
k1.metric("稼働時間 合計", f"{total_runtime:.0f}" if total_runtime is not None else "—")
k2.metric("不良数 合計", f"{total_defect:.0f}" if total_defect is not None else "—")
k3.metric("不良率(%)", f"{defect_rate:.2f}" if defect_rate is not None else "—")

# ===== 装置別 集計（by_machine）
st.subheader("④ 装置別 集計")
if COL_MACHINE and (COL_RUNTIME or COL_DEFECT):
    agg_dict = {}
    if COL_RUNTIME: agg_dict[f"稼働時間({agg_func})"] = (COL_RUNTIME, agg_func)
    if COL_DEFECT:  agg_dict[f"不良数({agg_func})"]   = (COL_DEFECT,  agg_func)
    by_machine = work.groupby(COL_MACHINE).agg(**agg_dict).reset_index()
    if COL_RUNTIME and COL_DEFECT and agg_func == "sum" and not by_machine.empty:
        by_machine["不良率(%)"] = (by_machine[f"不良数(sum)"] / by_machine[f"稼働時間(sum)"].replace(0, pd.NA)) * 100
    st.dataframe(by_machine, use_container_width=True)
else:
    by_machine = pd.DataFrame()
    st.caption("※ 装置列が見つからない or 集計対象列がないためスキップ")

# ===== ダウンロードユーティリティ
def download_csv(df_out: pd.DataFrame, label: str):
    csv = df_out.to_csv(index=False).encode("utf-8")
    st.download_button(f"⬇️ {label} をCSVで保存", data=csv, file_name=f"{label}.csv", mime="text/csv")

def download_excel(df_out: pd.DataFrame, label: str):
    try:
        import xlsxwriter  # インストール済み想定
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_out.to_excel(writer, index=False, sheet_name="Sheet1")
        st.download_button(
            f"⬇️ {label} をExcelで保存",
            data=buffer.getvalue(),
            file_name=f"{label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.caption(f"Excel出力には xlsxwriter が必要です（エラー: {e}）")

# ===== ダウンロード（原データ・装置別）
st.subheader("⑤ ダウンロード")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**フィルタ後データ（原明細）**")
    download_csv(work, "filtered_rows")
    download_excel(work, "filtered_rows")
with c2:
    st.markdown("**装置別 集計テーブル**")
    if not by_machine.empty:
        download_csv(by_machine, "by_machine_summary")
        download_excel(by_machine, "by_machine_summary")
    else:
        st.caption("装置別集計が空のため、出力ボタンは無効です。")

# ===== 時系列グラフ
st.subheader("⑥ 推移グラフ")
try:
    import altair as alt
    if COL_TIME and (COL_RUNTIME or COL_DEFECT):
        plot_df = work.copy()
        if time_gran != "そのまま":
            rule = {"日": "D", "週": "W", "月": "M"}[time_gran]
            plot_df = plot_df.set_index(COL_TIME)
            agg_ts = {}
            if COL_RUNTIME: agg_ts[COL_RUNTIME] = agg_func
            if COL_DEFECT:  agg_ts[COL_DEFECT]  = agg_func
            plot_df = plot_df.resample(rule).agg(agg_ts)
            plot_df.index.name = COL_TIME
            plot_df = plot_df.reset_index()

        if COL_RUNTIME:
            base = alt.Chart(plot_df).encode(x=f"{COL_TIME}:T", y=f"{COL_RUNTIME}:Q")
            ch1 = {"line": base.mark_line(), "bar": base.mark_bar(),
                   "area": base.mark_area(), "scatter": base.mark_point()}[chart_type]
            st.altair_chart(ch1.properties(height=280), use_container_width=True)

        if COL_DEFECT and COL_RUNTIME:
            tmp = work.groupby(COL_TIME).agg(run_sum=(COL_RUNTIME, "sum"),
                                             defect_sum=(COL_DEFECT, "sum")).reset_index()
            if time_gran != "そのまま":
                rule = {"日": "D", "週": "W", "月": "M"}[time_gran]
                tmp = tmp.set_index(COL_TIME).resample(rule).sum().reset_index()
            tmp["defect_rate(%)"] = (tmp["defect_sum"] / tmp["run_sum"].replace(0, pd.NA)) * 100
            base2 = alt.Chart(tmp).encode(x=f"{COL_TIME}:T", y="defect_rate(%):Q")
            ch2 = {"line": base2.mark_line(), "bar": base2.mark_bar(),
                   "area": base2.mark_area(), "scatter": base2.mark_point()}[chart_type]
            st.altair_chart(ch2.properties(height=280), use_container_width=True)
    else:
        st.caption("※ 日時列が見つからないので、推移グラフはスキップしました")
except Exception as e:
    st.warning(f"グラフ描画に失敗しました: {e}")
