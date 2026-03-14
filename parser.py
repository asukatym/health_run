import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime


def _parse_date(s: str) -> datetime:
    # "2023-01-01 08:00:00 +0900" -> datetime (naive, strip tz)
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def parse_running_workouts(file) -> pd.DataFrame:
    """export.xml からランニングワークアウトを抽出して DataFrame で返す"""
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []
    for w in root.findall("Workout"):
        if w.get("workoutActivityType") != "HKWorkoutActivityTypeRunning":
            continue

        start = _parse_date(w.get("startDate"))
        end = _parse_date(w.get("endDate"))
        duration_min = float(w.get("duration", 0))

        # 属性から距離取得（旧フォーマット）
        dist_val = float(w.get("totalDistance", 0) or 0)
        dist_unit = w.get("totalDistanceUnit", "km")
        distance_km = dist_val * 1.60934 if dist_unit == "mi" else dist_val

        calories = float(w.get("totalEnergyBurned", 0) or 0)

        # WorkoutStatistics から距離・心拍・カロリーを取得（新フォーマット）
        avg_hr = None
        max_hr = None
        for stat in w.findall("WorkoutStatistics"):
            t = stat.get("type", "")
            if t == "HKQuantityTypeIdentifierDistanceWalkingRunning":
                val = float(stat.get("sum", 0) or 0)
                unit = stat.get("unit", "km")
                distance_km = val * 1.60934 if unit == "mi" else val
            elif t == "HKQuantityTypeIdentifierActiveEnergyBurned" and calories == 0:
                calories = float(stat.get("sum", 0) or 0)
            elif "HeartRate" in t:
                avg_hr = float(stat.get("average", 0) or 0) or None
                max_hr = float(stat.get("maximum", 0) or 0) or None

        rows.append(
            {
                "start": start,
                "end": end,
                "duration_min": round(duration_min, 2),
                "distance_km": round(distance_km, 3),
                "calories": round(calories, 1),
                "avg_hr": avg_hr,
                "max_hr": max_hr,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # ペース (分/km)
    df["pace_min_per_km"] = df.apply(
        lambda r: r["duration_min"] / r["distance_km"]
        if r["distance_km"] > 0
        else None,
        axis=1,
    )

    return df.sort_values("start").reset_index(drop=True)


def parse_heart_rate_records(file) -> pd.DataFrame:
    """全心拍レコードを抽出（ワークアウトとの紐付けに使用）"""
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []
    for r in root.findall("Record"):
        if r.get("type") != "HKQuantityTypeIdentifierHeartRate":
            continue
        rows.append(
            {
                "timestamp": _parse_date(r.get("startDate")),
                "bpm": float(r.get("value", 0)),
            }
        )

    return pd.DataFrame(rows)
