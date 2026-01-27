import os
import time
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional

import requests
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score
import matplotlib.pyplot as plt

# 設定
ESTAT_API_KEY = os.environ.get("ESTAT_API_KEY")
BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json"
HEADERS = {"User-Agent": "transport-analysis-bot/1.0 (contact: example@example.com)"}
REQUEST_INTERVAL_SEC = 1.5  # robots.txt に配慮して低頻度アクセス
DB_PATH = "data/transport_analysis.sqlite3"
os.makedirs("data", exist_ok=True)
os.makedirs("figs", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def safe_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """API を低頻度で呼び出す安全な GET"""
    time.sleep(REQUEST_INTERVAL_SEC)
    resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_stats(keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
    """e-Stat メタデータ検索 API で統計表候補を取得"""
    params = {
        "appId": ESTAT_API_KEY,
        "searchWord": keyword,
        "limit": limit,
        "statsCode": "",  # 組織絞り込みは必要に応じて設定
    }
    data = safe_get(f"{BASE_URL}/getStatsList", params)
    items = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {}).get("TABLE_INF", [])
    if not isinstance(items, list):
        items = [items] if items else []
    return items


def pick_stats_id(items: List[Dict[str, Any]], required_words: List[str]) -> Optional[str]:
    """タイトルや説明に required_words が含まれる統計表の statsDataId を選ぶ"""
    for it in items:
        title = it.get("TITLE", "")
        desc = it.get("STATISTICS_NAME", "")
        text = f"{title} {desc}".lower()
        if all(w.lower() in text for w in required_words):
            return it.get("STAT_ID")
    return None


def get_stats_data(stats_data_id: str, filters: Dict[str, Any], limit: int = 10000) -> pd.DataFrame:
    """指定統計表のデータ取得（簡易）"""
    params = {
        "appId": ESTAT_API_KEY,
        "statsDataId": stats_data_id,
        "limit": limit,
        **filters,
    }
    data = safe_get(f"{BASE_URL}/json/getStatsData", params)
    # パスの揺れに備え、柔軟に取り出す
    result = data.get("GET_STATS_DATA", {})
    stat_data = result.get("STATISTICAL_DATA", {})
    class_obj = stat_data.get("CLASS_OBJ", [])
    value = stat_data.get("DATA_INF", {}).get("VALUE", [])

    # 次元コードの展開
    class_maps = {}
    for cls in class_obj:
        cls_id = cls.get("@id")
        keys = {}
        for i in cls.get("CLASS", []):
            keys[i.get("@code")] = i.get("@name")
        class_maps[cls_id] = keys

    rows = []
    for v in value:
        row = {"value": float(v.get("$", 0))}
        # 次元属性（地域・時間など）
        for k, val in v.items():
            if k.startswith("@"):
                row[k[1:]] = val
        rows.append(row)

    df = pd.DataFrame(rows)
    # コードを人間可読に
    for k, mp in class_maps.items():
        col = k.lower()
        if col in df.columns:
            df[col + "_name"] = df[col].map(mp)
    return df


def init_db(conn: sqlite3.Connection):
    cur = conn.cursor()
    # ステージング
    cur.execute("""
    CREATE TABLE IF NOT EXISTS staging_accidents (
        year INTEGER,
        pref_code TEXT,
        pref_name TEXT,
        accidents INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS staging_population (
        year INTEGER,
        pref_code TEXT,
        pref_name TEXT,
        population INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS staging_infra (
        year INTEGER,
        pref_code TEXT,
        pref_name TEXT,
        signals INTEGER,
        crosswalks INTEGER,
        speed_reg_km REAL
    )
    """)
    # ファクト
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_panel (
        year INTEGER,
        pref_code TEXT,
        pref_name TEXT,
        accidents INTEGER,
        population INTEGER,
        signals INTEGER,
        crosswalks INTEGER,
        speed_reg_km REAL
    )
    """)
    conn.commit()


def upsert_df(conn: sqlite3.Connection, df: pd.DataFrame, table: str):
    df.to_sql(table, conn, if_exists="append", index=False)


def build_panel(conn: sqlite3.Connection):
    q = """
    INSERT INTO fact_panel
    SELECT a.year, a.pref_code, a.pref_name,
           a.accidents, p.population,
           i.signals, i.crosswalks, i.speed_reg_km
    FROM staging_accidents a
    LEFT JOIN staging_population p
      ON a.year = p.year AND a.pref_code = p.pref_code
    LEFT JOIN staging_infra i
      ON a.year = i.year AND a.pref_code = i.pref_code
    """
    conn.execute("DELETE FROM fact_panel")
    conn.execute(q)
    conn.commit()


def compute_metrics(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT * FROM fact_panel", conn)
    # 指標計算
    df["accident_rate_per_100k"] = (df["accidents"] / df["population"]) * 100000
    # 密度（人口基準）
    df["signals_per_100k"] = (df["signals"] / df["population"]) * 100000
    df["crosswalks_per_100k"] = (df["crosswalks"] / df["population"]) * 100000
    # 速度規制密度（人口当たり km は直感的でないため道路延長が理想だが、代替としてそのままスケール調整）
    df["speed_reg_km_per_100k"] = (df["speed_reg_km"] / df["population"]) * 100000
    return df


def fit_models(panel_df: pd.DataFrame) -> Dict[str, Any]:
    # 欠損除去
    d = panel_df.dropna(subset=[
        "accident_rate_per_100k",
        "signals_per_100k",
        "crosswalks_per_100k",
        "speed_reg_km_per_100k"
    ])
    X = d[["signals_per_100k", "crosswalks_per_100k", "speed_reg_km_per_100k"]].values
    y = d["accident_rate_per_100k"].values

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("linreg", LinearRegression())
    ])
    model.fit(X, y)
    y_pred = model.predict(X)
    result = {
        "r2": float(r2_score(y, y_pred)),
        "coef": model.named_steps["linreg"].coef_.tolist(),
        "intercept": float(model.named_steps["linreg"].intercept_)
    }
    return result


def plot_scatter(panel_df: pd.DataFrame, xcol: str, ycol: str, outfile: str):
    plt.figure(figsize=(6, 4))
    plt.scatter(panel_df[xcol], panel_df[ycol], alpha=0.6)
    m, b = np.polyfit(panel_df[xcol], panel_df[ycol], 1)
    xs = np.linspace(panel_df[xcol].min(), panel_df[xcol].max(), 100)
    plt.plot(xs, m*xs + b, color="red", linewidth=2)
    plt.xlabel(xcol)
    plt.ylabel(ycol)
    plt.tight_layout()
    plt.savefig(outfile)
    plt.close()


def main():
    if not ESTAT_API_KEY:
        raise RuntimeError("ESTAT_API_KEY を環境変数に設定してください。")

    # DB 初期化
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # メタデータ検索（例: 事故、人口、道路施設）
    acc_items = search_stats("交通事故 都道府県 年次")
    pop_items = search_stats("推計人口 都道府県 年次")
    infra_items = search_stats("道路施設 信号機 横断歩道 都道府県 年次")

    acc_id = pick_stats_id(acc_items, ["事故", "都道府県"])
    pop_id = pick_stats_id(pop_items, ["人口", "都道府県"])
    infra_id = pick_stats_id(infra_items, ["信号機", "横断歩道", "都道府県"])

    logging.info(f"statsDataId accidents={acc_id} population={pop_id} infra={infra_id}")

    # 年範囲（例）
    years = [str(y) for y in range(2018, 2024)]

    # データ取得（各統計のフィルタは統計表の CLASS_OBJ に応じて調整）
    # 地域コードは都道府県のコード軸（例: cdArea）
    staging_acc = []
    staging_pop = []
    staging_inf = []

    for y in years:
        # 事故
        if acc_id:
            df_acc = get_stats_data(acc_id, {"cdTime": y})
            # 想定: 列 area, area_name が存在
            if "area" in df_acc.columns:
                df_acc2 = df_acc.rename(columns={
                    "area": "pref_code",
                    "area_name": "pref_name",
                    "value": "accidents"
                })[["pref_code", "pref_name", "accidents"]]
                df_acc2["year"] = int(y)
                staging_acc.append(df_acc2)

        # 人口
        if pop_id:
            df_pop = get_stats_data(pop_id, {"cdTime": y})
            if "area" in df_pop.columns:
                df_pop2 = df_pop.rename(columns={
                    "area": "pref_code",
                    "area_name": "pref_name",
                    "value": "population"
                })[["pref_code", "pref_name", "population"]]
                df_pop2["year"] = int(y)
                staging_pop.append(df_pop2)

        # インフラ（信号機・横断歩道・速度規制延長）
        if infra_id:
            df_inf = get_stats_data(infra_id, {"cdTime": y})
            # 想定: 区分列（item 等）で種別が分かれているため pivot
            # 例: item_name が「信号機数」「横断歩道数」「速度規制延長」
            if "area" in df_inf.columns and "item_name" in df_inf.columns:
                piv = df_inf.pivot_table(
                    index=["area", "area_name"],
                    columns="item_name",
                    values="value",
                    aggfunc="sum",
                    fill_value=0
                ).reset_index()
                # 列名の標準化
                colmap = {
                    "信号機数": "signals",
                    "横断歩道数": "crosswalks",
                    "速度規制延長": "speed_reg_km"
                }
                for k, v in colmap.items():
                    if k in piv.columns:
                        piv.rename(columns={k: v}, inplace=True)
                piv.rename(columns={"area": "pref_code", "area_name": "pref_name"}, inplace=True)
                # 欠損列の補完
                for v in ["signals", "crosswalks", "speed_reg_km"]:
                    if v not in piv.columns:
                        piv[v] = 0
                piv["year"] = int(y)
                staging_inf.append(piv[["pref_code", "pref_name", "signals", "crosswalks", "speed_reg_km", "year"]])

    # ステージングに投入
    if staging_acc:
        upsert_df(conn, pd.concat(staging_acc, ignore_index=True), "staging_accidents")
    if staging_pop:
        upsert_df(conn, pd.concat(staging_pop, ignore_index=True), "staging_population")
    if staging_inf:
        upsert_df(conn, pd.concat(staging_inf, ignore_index=True), "staging_infra")

    # パネル構築
    build_panel(conn)

    # 指標計算・モデリング
    panel = compute_metrics(conn)
    model_result = fit_models(panel)
    logging.info(f"Model R2={model_result['r2']:.3f}, coef={model_result['coef']}")

    # 可視化（散布図）
    plot_scatter(panel, "signals_per_100k", "accident_rate_per_100k", "figs/signals_vs_accidents.png")
    plot_scatter(panel, "crosswalks_per_100k", "accident_rate_per_100k", "figs/crosswalks_vs_accidents.png")
    plot_scatter(panel, "speed_reg_km_per_100k", "accident_rate_per_100k", "figs/speedreg_vs_accidents.png")

    # 出力例
    panel.to_csv("data/panel_metrics.csv", index=False)
    with open("data/model_result.json", "w", encoding="utf-8") as f:
        json.dump(model_result, f, ensure_ascii=False, indent=2)

    conn.close()


if __name__ == "__main__":
    main()