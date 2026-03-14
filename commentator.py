import anthropic
import pandas as pd

client = anthropic.Anthropic()


def _build_prompt(row: pd.Series, history: pd.DataFrame) -> str:
    """1回分のランニングデータからプロンプトを構築する"""
    pace = row.get("pace_min_per_km")
    pace_str = "-"
    if pd.notna(pace) and pace and pace > 0:
        m, s = divmod(pace * 60, 60)
        pace_str = f"{int(m)}'{int(s):02d}\"/km"

    avg_hr = row.get("avg_hr")
    max_hr = row.get("max_hr")
    hr_str = f"平均{avg_hr:.0f}bpm / 最大{max_hr:.0f}bpm" if pd.notna(avg_hr) else "データなし"

    dur = row.get("duration_min", 0)
    dur_str = f"{int(dur//60)}時間{int(dur%60):02d}分" if dur >= 60 else f"{int(dur)}分"

    # 直近5件との比較情報
    recent = history[history["start"] < row["start"]].tail(5)
    comparison = ""
    if not recent.empty:
        avg_dist = recent["distance_km"].mean()
        avg_pace = recent["pace_min_per_km"].dropna().mean()
        dist_diff = row["distance_km"] - avg_dist
        comparison = f"\n直近{len(recent)}回の平均距離: {avg_dist:.1f}km（今回との差: {dist_diff:+.1f}km）"
        if pd.notna(avg_pace) and pd.notna(pace):
            pace_diff = pace - avg_pace
            sign = "速" if pace_diff < 0 else "遅"
            comparison += f"\n直近{len(recent)}回の平均ペース: {int(avg_pace)}'{int((avg_pace%1)*60):02d}\"/km（今回は{abs(pace_diff*60):.0f}秒{sign}い）"

    return f"""以下のランニングデータについて、ランニング専門家として短い日本語コメントをしてください。

【今回のラン】
日時: {row['start'].strftime('%Y年%m月%d日 %H:%M')}
距離: {row['distance_km']:.2f}km
タイム: {dur_str}
ペース: {pace_str}
心拍数: {hr_str}
消費カロリー: {row.get('calories', 0):.0f}kcal{comparison}

【指示】
- 3〜4文程度で簡潔に
- 良い点を認め、改善アドバイスも一言添える
- データがない場合は推測せず触れない
- 励ます口調で"""


def generate_comment(row: pd.Series, history: pd.DataFrame) -> str:
    """1件のランにAIコメントを生成して返す"""
    prompt = _build_prompt(row, history)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def generate_overall_comment(df: pd.DataFrame) -> str:
    """全ランニングデータの総評コメントを生成する"""
    total_runs = len(df)
    total_km = df["distance_km"].sum()
    avg_km = df["distance_km"].mean()
    max_km = df["distance_km"].max()
    long_runs = df[df["distance_km"] >= 5]
    best_pace = long_runs["pace_min_per_km"].min() if not long_runs.empty and long_runs["pace_min_per_km"].notna().any() else None
    avg_pace = df["pace_min_per_km"].dropna().mean()

    pace_str = "-"
    if best_pace and pd.notna(best_pace):
        m, s = divmod(best_pace * 60, 60)
        pace_str = f"{int(m)}'{int(s):02d}\"/km"

    avg_pace_str = "-"
    if pd.notna(avg_pace):
        m, s = divmod(avg_pace * 60, 60)
        avg_pace_str = f"{int(m)}'{int(s):02d}\"/km"

    first_date = df["start"].min().strftime("%Y年%m月%d日")
    last_date = df["start"].max().strftime("%Y年%m月%d日")

    prompt = f"""以下は、あるランナーの全ランニング記録のサマリーです。ランニング専門家として総評コメントをしてください。

【全体サマリー】
期間: {first_date} 〜 {last_date}
総ラン回数: {total_runs}回
総距離: {total_km:.1f}km
平均距離: {avg_km:.1f}km
最長距離: {max_km:.1f}km
平均ペース: {avg_pace_str}
最速ペース（5km以上）: {pace_str}

【指示】
- 5〜6文程度で総評を述べる
- 継続性・成長・課題を含めてバランスよく評価する
- 今後のトレーニングへのアドバイスを添える
- 励ます口調で、日本語で"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def answer_question(question: str, df: pd.DataFrame) -> str:
    """ランニングデータについての質問に答える"""
    first_date = df["start"].min().strftime("%Y年%m月%d日")
    last_date = df["start"].max().strftime("%Y年%m月%d日")

    # ラン一覧（各回のデータ）
    rows = []
    for _, row in df.iterrows():
        pace = row.get("pace_min_per_km")
        pace_str = "-"
        if pd.notna(pace) and pace and pace > 0:
            m, s = divmod(pace * 60, 60)
            pace_str = f"{int(m)}'{int(s):02d}\"/km"
        avg_hr = row.get("avg_hr")
        max_hr = row.get("max_hr")
        hr_str = f"avg{avg_hr:.0f}/max{max_hr:.0f}bpm" if pd.notna(avg_hr) else "-"
        rows.append(
            f"{row['start'].strftime('%Y-%m-%d')} "
            f"{row['distance_km']:.1f}km "
            f"ペース:{pace_str} 心拍:{hr_str}"
        )

    runs_text = "\n".join(rows)

    prompt = f"""以下はランナーの全ランニング記録です（期間: {first_date}〜{last_date}、{len(df)}件）。

【ラン一覧】
{runs_text}

【質問】
{question}

ランニング専門家として、上記のデータをもとに質問に答えてください。
- 日本語で簡潔に（3〜5文程度）
- 各ランのデータを参照して具体的なコメントをする
- 励ます口調で"""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
