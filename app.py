import streamlit as st
import pandas as pd
import io

# ------- ページ設定 -------
st.set_page_config(page_title="装置ログビューア", page_icon="📊", layout="wide")

# ------- ヘッダ -------
st.title("📊 装置ログビューア")
st.caption("CSV/Excel/JSON を読み込み、期間フィルタ・集計・可視化・エクスポートを行います。")

# ------- サイドバー：入出力とフィルタ -------
with st.sidebar:
    st.header("⚙️ 入力・フィルタ")
    uploaded_file = st.file_uploader("データファイルを選択", type=["csv","xlsx","xls","json"])
    st.divider()
    st.subheader("オプション")
    agg_func = st.selectbox("集計関数", ["sum","mean","median","max","min","count"], index=0)
    chart_type = st.selectbox("グラフ種類", ["line","bar","area","scatter"], index=0)
    time_gran = st.selectbox("時系列の粒度", ["そのまま","日","週","月"], index=0)

# 何もないときはガイドを表示
if uploaded_file is None:
    st.info("左のサイドバーからファイルをアップロードしてください。想定列：**日時 / 装置 / 稼働時間 / 不良数**")
    st.stop()

# ------- 読み込み -------
def read_any(file):
    name = str(getattr(file, "name", "")).lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(file)
    if name.endswith(".json"):
        return pd.read_json(file)
    # fallback: 可能ならCSVとして読む
    try:
        return pd.read_csv(file)
    except Exception:
        return pd.DataFrame()

df = read_any(uploaded_file)

# ------- 列自動検出 -------
COL_TIME = next((c for c in df.columns if c in ["日時","date","timestamp","time"]), None)
COL_MACHINE = next((c for c in df.columns if c in ["装置","機番","machine","device"]), None)
COL_RUNTIME = next((c for c in df.columns if c in ["稼働時間","runtime","run_time","uptime"]), None)
COL_DEFECT = next((c for c in df.columns if c in ["不良数","defect","rejects","ng"]), None)

if COL_TIME:
    df[COL_TIME] = pd.to_datetime(df[COL_TIME], errors="coerce")

# ------- 期間フィルタ（上段横並び） -------
with st.container():
    st.subheader("📅 期間フィルタ")
    if COL_TIME and df[COL_TIME].notna().any():
        min_d = pd.to_datetime(df[COL_TIME]).min().date()
        max_d = pd.to_datetime(df[COL_TIME]).max().date()
        default_start = max(max_d - pd.Timedelta(days=6), min_d)
        c1, c2, c3 = st.columns([2,2,1])
        with c1:
            date_range = st.date_input(
                "対象期間（開始日〜終了日）", value=(default_start, max_d),
                min_value=min_d, max_value=max_d
            )
        with c2:
            st.write("")  # spacing
            st.metric("全体行数", f"{len(df):,}")
        with c3:
            st.write("")
            st.metric("列数", f"{df.shape[1]}")
    else:
        date_range = None
        st.caption("※ 日時列が見つからないため期間フィルタは無効です。")

# ------- フィルタ適用 -------
work = df.copy()
if COL_TIME and date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start_d = pd.to_datetime(date_range[0])
    end_d = pd.to_datetime(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    work = work[(work[COL_TIME] >= start_d) & (work[COL_TIME] <= end_d)]

# ------- タブ構成 -------
tab_preview, tab_summary, tab_charts, tab_export = st.tabs(["🗂 データ", "📌 集計", "📈 グラフ", "⬇️ エクスポート"])

# === タブ1: データプレビュー ===
with tab_preview:
    st.subheader("データプレビュー")
    st.caption(f"フィルタ後：**{len(work):,}** 行（全体 **{len(df):,}** 行）")
    with st.expander("列の自動検出（確認用）", expanded=False):
        st.write({
            "日時": COL_TIME, "装置": COL_MACHINE,
            "稼働時間": COL_RUNTIME, "不良数": COL_DEFECT
        })
    st.dataframe(work, use_container_width=True, height=420)

# === タブ2: 集計（KPI + 装置別） ===
with tab_summary:
    st.subheader("KPI")
    total_runtime = work[COL_RUNTIME].sum() if COL_RUNTIME in work else None
    total_defect = work[COL_DEFECT].sum() if COL_DEFECT in work else None
    defect_rate = (total_defect / total_runtime * 100) if (total_runtime and total_runtime != 0) else None

    k1, k2, k3 = st.columns(3)
    k1.metric("稼働時間 合計", f"{total_runtime:.0f}" if total_runtime is not None else "—")
    k2.metric("不良数 合計", f"{total_defect:.0f}" if total_defect is not None else "—")
    k3.metric("不良率(%)", f"{defect_rate:.2f}" if defect_rate is not None else "—")

    st.markdown("---")
    st.subheader("装置別 集計")
    if COL_MACHINE and (COL_RUNTIME or COL_DEFECT):
        agg_dict = {}
        if COL_RUNTIME: agg_dict[f"稼働時間({agg_func})"] = (COL_RUNTIME, agg_func)
        if COL_DEFECT:  agg_dict[f"不良数({agg_func})"]   = (COL_DEFECT,  agg_func)
        by_machine = work.groupby(COL_MACHINE).agg(**agg_dict).reset_index()
        if COL_RUNTIME and COL_DEFECT and agg_func == "sum" and not by_machine.empty:
            by_machine["不良率(%)"] = (by_machine[f"不良数(sum)"] / by_machine[f"稼働時間(sum)"].replace(0, pd.NA)) * 100
        st.dataframe(by_machine, use_container_width=True, height=360)
    else:
        st.caption("※ 装置列が見つからない or 集計対象列がないためスキップ")

# === タブ3: グラフ ===
with tab_charts:
    st.subheader("時系列グラフ")
    try:
        import altair as alt
        if COL_TIME and (COL_RUNTIME or COL_DEFECT):
            plot_df = work.copy()

            # 粒度（リサンプリング）
            if time_gran != "そのまま":
                rule = {"日": "D", "週": "W", "月": "M"}[time_gran]
                plot_df = plot_df.set_index(COL_TIME)
                agg_ts = {}
                if COL_RUNTIME: agg_ts[COL_RUNTIME] = agg_func
                if COL_DEFECT:  agg_ts[COL_DEFECT]  = agg_func
                plot_df = plot_df.resample(rule).agg(agg_ts)
                plot_df.index.name = COL_TIME
                plot_df = plot_df.reset_index()

            # 稼働時間
            if COL_RUNTIME:
                base = alt.Chart(plot_df).encode(x=f"{COL_TIME}:T", y=f"{COL_RUNTIME}:Q")
                ch1 = {"line": base.mark_line(), "bar": base.mark_bar(),
                       "area": base.mark_area(), "scatter": base.mark_point()}[chart_type]
                st.altair_chart(ch1.properties(height=300), use_container_width=True)

            # 不良率（sum基準で厳密）
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
                st.altair_chart(ch2.properties(height=300), use_container_width=True)
        else:
            st.caption("※ 日時列が見つからないためグラフは表示できません。")
    except Exception as e:
        st.warning(f"グラフ描画に失敗しました: {e}")

# === タブ4: エクスポート ===
with tab_export:
    st.subheader("ダウンロード")
    def download_csv(df_out: pd.DataFrame, label: str):
        data = df_out.to_csv(index=False).encode("utf-8")
        st.download_button(f"⬇️ {label} (CSV)", data=data, file_name=f"{label}.csv", mime="text/csv")

    def download_excel(df_out: pd.DataFrame, label: str):
        try:
            import xlsxwriter
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df_out.to_excel(writer, index=False, sheet_name="Sheet1")
            st.download_button(
                f"⬇️ {label} (Excel)",
                data=buffer.getvalue(),
                file_name=f"{label}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.caption(f"Excel出力には xlsxwriter が必要です（エラー: {e}）")

    # 原データ
    st.markdown("**フィルタ後の明細データ**")
    download_csv(work, "filtered_rows")
    download_excel(work, "filtered_rows")

    # 装置別集計（あれば）
    if COL_MACHINE and (COL_RUNTIME or COL_DEFECT):
        agg_dict = {}
        if COL_RUNTIME: agg_dict[f"稼働時間({agg_func})"] = (COL_RUNTIME, agg_func)
        if COL_DEFECT:  agg_dict[f"不良数({agg_func})"]   = (COL_DEFECT,  agg_func)
        by_machine = work.groupby(COL_MACHINE).agg(**agg_dict).reset_index()
        if COL_RUNTIME and COL_DEFECT and agg_func == "sum" and not by_machine.empty:
            by_machine["不良率(%)"] = (by_machine[f"不良数(sum)"] / by_machine[f"稼働時間(sum)"].replace(0, pd.NA)) * 100
        st.markdown("---")
        st.markdown("**装置別 集計テーブル**")
        download_csv(by_machine, "by_machine_summary")
        download_excel(by_machine, "by_machine_summary")
    else:
        st.caption("装置別集計のエクスポート対象はありません。")
