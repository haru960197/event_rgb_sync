#!/usr/bin/env python3
"""
Module 3: 時系列関係の可視化プログラム
=======================================
output/matched_timestamps.csv を読み込み、
X軸=event_time_us、Y軸=rgb_time_ms の散布図を描画して
output/sync_plot.png として保存する。

output/sync_params.json が存在する場合は、
線形回帰直線も重ねて描画する（Module4との統合）。

使用方法:
    python visualize_sync.py

必要なファイル:
    - output/matched_timestamps.csv  (Module2の出力)

オプション:
    - output/sync_params.json        (Module4の出力 → 近似直線を追加)

出力:
    - output/sync_plot.png
"""

import sys
import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# =========================================================
# パス設定
# =========================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

MATCHED_CSV   = os.path.join(PROJECT_ROOT, "output", "matched_timestamps.csv")
SYNC_PARAMS   = os.path.join(PROJECT_ROOT, "output", "sync_params.json")
OUTPUT_PLOT   = os.path.join(PROJECT_ROOT, "output", "sync_plot.png")


def load_matched_timestamps(csv_path: str) -> pd.DataFrame:
    """matched_timestamps.csv を読み込んで DataFrame を返す。"""
    if not os.path.exists(csv_path):
        print(f"[ERROR] {csv_path} が見つかりません。Module2 を先に実行してください。")
        sys.exit(1)
    df = pd.read_csv(csv_path)
    print(f"[Module3] データ読み込み完了: {len(df)} ペア")
    print(df.describe())
    return df


import hashlib

def _csv_sha256(csv_path: str) -> str:
    """CSVファイルのSHA256ハッシュを返す（整合性チェック用）。"""
    h = hashlib.sha256()
    with open(csv_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sync_params(params_path: str) -> dict | None:
    """sync_params.json が存在すれば読み込んで返す。なければ None。
    matched_timestamps.csv のハッシュが記録されている場合、
    現在のCSVと照合して不一致なら警告を出す（古い回帰結果の誤使用防止）。
    """
    if not os.path.exists(params_path):
        return None
    with open(params_path, "r", encoding="utf-8") as f:
        params = json.load(f)

    # --- 整合性チェック ---
    saved_hash = params.get("source_csv_sha256")
    if saved_hash and os.path.exists(MATCHED_CSV):
        current_hash = _csv_sha256(MATCHED_CSV)
        if saved_hash != current_hash:
            print(
                f"[WARN] sync_params.json は現在の matched_timestamps.csv と一致しません!\n"
                f"       保存済みハッシュ: {saved_hash[:16]}...\n"
                f"       現在のCSVハッシュ: {current_hash[:16]}...\n"
                f"       Module4 を再実行して sync_params.json を更新してください。"
            )
        else:
            print(f"[Module3] 整合性チェック OK: sync_params.json はCSVと一致しています。")

    print(f"[Module3] 線形回帰パラメータ読み込み: A={params.get('A')}, B={params.get('B')}")
    return params


def plot_sync(df: pd.DataFrame, sync_params: dict | None, output_path: str):
    """
    散布図を描画する。sync_params が指定されていれば近似直線も描画する。
    論文掲載用のシンプルなスタイル（白背景、単色プロット）。
    """
    event_us = df["event_time_us"].values
    rgb_ms   = df["rgb_time_ms"].values

    fig, ax = plt.subplots(figsize=(8, 6))

    # --- X軸スケーリング（1e6 μs 単位に変換） ---
    SCALE = 1e6
    event_x = event_us / SCALE

    # --- 散布図（単色） ---
    ax.scatter(
        event_x, rgb_ms,
        color="C0",
        s=40,
        alpha=0.7,
        zorder=3,
        label="Matched LED timestamps"
    )

    # --- 近似直線 ---
    if sync_params is not None:
        A = sync_params["A"]
        B = sync_params["B"]
        # 元の単位で近似: rgb_ms = A * event_us + B
        # スケール後: rgb_ms = (A * SCALE) * event_x + B
        A_scaled = A * SCALE
        x_line = np.linspace(event_x.min(), event_x.max(), 200)
        y_line = A_scaled * x_line + B
        ax.plot(
            x_line, y_line,
            color="C1",
            linewidth=1.5,
            linestyle="--",
            zorder=4,
            label=f"Linear fit: $y = {A_scaled:.4f} \\cdot x {B:+.4f}$"
        )

    # --- 軸設定 ---
    ax.set_xlabel(r"Event Camera Timestamp [$\times 10^6\ \mu$s]", fontsize=12)
    ax.set_ylabel("RGB Camera Timestamp [ms]", fontsize=12)
    ax.set_title("RGB \u2194 Event Camera Time Synchronization", fontsize=13)

    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))

    ax.grid(True, linewidth=0.5, linestyle="--", alpha=0.5)
    ax.legend(fontsize=10, framealpha=0.8)

    # --- 保存・表示 ---
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"[Module3] プロット保存: {output_path}")
    plt.show()


def main():
    df = load_matched_timestamps(MATCHED_CSV)
    sync_params = load_sync_params(SYNC_PARAMS)
    plot_sync(df, sync_params, OUTPUT_PLOT)
    print("[Module3] 完了。")


if __name__ == "__main__":
    main()
