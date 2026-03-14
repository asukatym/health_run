import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent / "workouts.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            start       TEXT PRIMARY KEY,
            end         TEXT,
            duration_min REAL,
            distance_km  REAL,
            calories     REAL,
            avg_hr       REAL,
            max_hr       REAL,
            pace_min_per_km REAL,
            comment     TEXT
        )
    """)
    # 既存DBにカラムがなければ追加（マイグレーション）
    existing = [r[1] for r in conn.execute("PRAGMA table_info(workouts)").fetchall()]
    if "comment" not in existing:
        conn.execute("ALTER TABLE workouts ADD COLUMN comment TEXT")
    conn.commit()
    return conn


def upsert_workouts(df: pd.DataFrame) -> int:
    """DataFrame をDBに追加（重複は start をキーとしてスキップ）。追加件数を返す"""
    if df.empty:
        return 0

    conn = _connect()
    df_copy = df.copy()
    df_copy["start"] = df_copy["start"].astype(str)
    df_copy["end"] = df_copy["end"].astype(str)

    before = conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
    df_copy.to_sql("workouts", conn, if_exists="append", index=False, method="multi")

    # 重複削除（PRIMARY KEY 違反を INSERT OR IGNORE で回避できないため後処理）
    conn.execute("""
        DELETE FROM workouts WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM workouts GROUP BY start
        )
    """)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
    conn.close()
    return after - before


def load_workouts() -> pd.DataFrame:
    conn = _connect()
    df = pd.read_sql("SELECT * FROM workouts ORDER BY start", conn)
    conn.close()
    if df.empty:
        return df
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    return df


def save_comment(start: str, comment: str) -> None:
    conn = _connect()
    conn.execute("UPDATE workouts SET comment = ? WHERE start = ?", (comment, start))
    conn.commit()
    conn.close()


def delete_all() -> None:
    conn = _connect()
    conn.execute("DELETE FROM workouts")
    conn.commit()
    conn.close()
