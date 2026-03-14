from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from parser import parse_running_workouts
from database import upsert_workouts, load_workouts, delete_all, save_comment
from commentator import generate_comment, generate_overall_comment, answer_question

st.set_page_config(page_title="マラソン分析", page_icon="🏃", layout="wide")
st.title("🏃 iPhoneヘルスケア マラソン分析")


# ---- サイドバー: データインポート ----
with st.sidebar:
    st.header("データインポート")
    uploaded = st.file_uploader("export.xml をアップロード", type="xml")
    if uploaded and st.button("読み込む", type="primary"):
        with st.spinner("解析中... (大きいファイルは数分かかる場合があります)"):
            df_new = parse_running_workouts(uploaded)
        if df_new.empty:
            st.warning("ランニングワークアウトが見つかりませんでした。")
        else:
            added = upsert_workouts(df_new)
            st.success(f"{len(df_new)} 件を解析 / {added} 件を新規追加")

    st.divider()
    if st.button("全データ削除", type="secondary"):
        delete_all()
        st.rerun()


# ---- データ読み込み ----
df = load_workouts()

if df.empty:
    st.info("左サイドバーから export.xml をアップロードしてください。")
    st.stop()


# ---- フィルタ ----
with st.expander("フィルタ", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        min_km = st.number_input("最小距離 (km)", value=0.0, step=1.0)
        max_km = st.number_input("最大距離 (km)", value=float(df["distance_km"].max() + 1), step=1.0)
    with col2:
        date_range = st.date_input(
            "期間",
            value=(df["start"].dt.date.min(), df["start"].dt.date.max()),
        )

df_f = df[
    (df["distance_km"] >= min_km)
    & (df["distance_km"] <= max_km)
    & (df["start"].dt.date >= date_range[0])
    & (df["start"].dt.date <= date_range[1])
].copy()


# ---- サマリーカード ----
st.subheader("サマリー")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("総ランニング数", len(df_f))
c2.metric("総距離", f"{df_f['distance_km'].sum():.1f} km")
c3.metric("平均距離", f"{df_f['distance_km'].mean():.1f} km")
c4.metric("最長距離", f"{df_f['distance_km'].max():.1f} km")
best_pace = df_f[df_f["distance_km"] >= 5]["pace_min_per_km"].min()
if pd.notna(best_pace):
    m, s = divmod(best_pace * 60, 60)
    c5.metric("最速ペース(5km+)", f"{int(m)}'{int(s):02d}\"/km")


# ---- グラフ ----
tab1, tab2, tab3, tab4 = st.tabs(["距離推移", "ペース推移", "心拍数", "一覧"])

with tab1:
    fig = px.bar(
        df_f,
        x="start",
        y="distance_km",
        labels={"start": "日付", "distance_km": "距離 (km)"},
        title="ランニング距離の推移",
        color="distance_km",
        color_continuous_scale="Blues",
    )
    fig.update_layout(showlegend=False, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    df_pace = df_f[df_f["pace_min_per_km"].notna() & (df_f["distance_km"] >= 1)].copy()

    def fmt_pace(v):
        m, s = divmod(v * 60, 60)
        return f"{int(m)}'{int(s):02d}\""

    df_pace["pace_label"] = df_pace["pace_min_per_km"].map(fmt_pace)

    fig2 = px.scatter(
        df_pace,
        x="start",
        y="pace_min_per_km",
        size="distance_km",
        color="distance_km",
        hover_data={"pace_label": True, "distance_km": ":.1f", "start": True},
        labels={"start": "日付", "pace_min_per_km": "ペース (分/km)", "distance_km": "距離"},
        title="ペース推移（バブルサイズ = 距離）",
        color_continuous_scale="RdYlGn_r",
    )
    # Y軸を反転（ペースは小さいほど速い）
    fig2.update_yaxes(autorange="reversed")
    fig2.update_layout(coloraxis_showscale=False)

    # Y軸ラベルを 分'秒" 形式に
    ticks = df_pace["pace_min_per_km"].dropna()
    if not ticks.empty:
        tick_vals = pd.Series(
            [ticks.min() + (ticks.max() - ticks.min()) * i / 5 for i in range(6)]
        )
        fig2.update_yaxes(
            tickvals=tick_vals,
            ticktext=[fmt_pace(v) for v in tick_vals],
        )
    st.plotly_chart(fig2, use_container_width=True)

with tab3:
    df_hr = df_f[df_f["avg_hr"].notna()]
    if df_hr.empty:
        st.info("心拍データが含まれていません。")
    else:
        fig3 = go.Figure()
        fig3.add_trace(
            go.Scatter(
                x=df_hr["start"],
                y=df_hr["avg_hr"],
                mode="lines+markers",
                name="平均心拍",
                line=dict(color="#e74c3c"),
            )
        )
        fig3.add_trace(
            go.Scatter(
                x=df_hr["start"],
                y=df_hr["max_hr"],
                mode="lines+markers",
                name="最大心拍",
                line=dict(color="#c0392b", dash="dot"),
            )
        )
        fig3.update_layout(
            title="心拍数の推移",
            xaxis_title="日付",
            yaxis_title="心拍数 (bpm)",
        )
        st.plotly_chart(fig3, use_container_width=True)

with tab4:
    # AIコメント一括生成ボタン
    no_comment = df_f[df_f["comment"].isna() | (df_f["comment"] == "")]
    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        if not no_comment.empty:
            st.caption(f"未コメント: {len(no_comment)}件")
    with col_btn2:
        gen_all = st.button("🤖 未生成をAIコメント", disabled=no_comment.empty)

    if gen_all:
        progress = st.progress(0, text="AIコメント生成中...")
        for i, (_, row) in enumerate(no_comment.iterrows()):
            progress.progress((i + 1) / len(no_comment), text=f"{i+1}/{len(no_comment)} 件処理中...")
            comment = generate_comment(row, df)
            save_comment(str(row["start"]), comment)
        progress.empty()
        st.rerun()

    # 一覧テーブル
    for _, row in df_f.iterrows():
        with st.expander(
            f"📅 {row['start'].strftime('%Y-%m-%d %H:%M')}  |  "
            f"📏 {row['distance_km']:.2f}km  |  "
            f"⏱ {int(row['duration_min']//60)}h{int(row['duration_min']%60):02d}m"
            if row['duration_min'] >= 60 else
            f"📅 {row['start'].strftime('%Y-%m-%d %H:%M')}  |  "
            f"📏 {row['distance_km']:.2f}km  |  "
            f"⏱ {int(row['duration_min'])}分"
        ):
            c1, c2, c3 = st.columns(3)
            pace = row.get("pace_min_per_km")
            pace_str = f"{int(pace)}'{int((pace%1)*60):02d}\"" if pd.notna(pace) else "-"
            c1.metric("ペース", pace_str + "/km")
            c2.metric("平均心拍", f"{row['avg_hr']:.0f} bpm" if pd.notna(row.get("avg_hr")) else "-")
            c3.metric("カロリー", f"{row['calories']:.0f} kcal")

            comment = row.get("comment")
            if comment:
                st.info(f"💬 {comment}")
            else:
                if st.button("🤖 AIコメントを生成", key=f"btn_{row['start']}"):
                    with st.spinner("生成中..."):
                        comment = generate_comment(row, df)
                        save_comment(str(row["start"]), comment)
                    st.rerun()

# ---- 総評 ----
st.divider()
st.subheader("🏅 総評")
if st.button("🤖 AIに総評を生成させる"):
    with st.spinner("総評を生成中..."):
        overall = generate_overall_comment(df_f)
    st.info(f"💬 {overall}")

# ---- AIチャット ----
st.divider()
st.subheader("💬 AIに質問する")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if question := st.chat_input("例: 心拍数はどう？ / ペースの改善は？"):
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            answer = answer_question(question, df_f)
        st.write(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})
