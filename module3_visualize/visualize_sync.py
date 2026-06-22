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
    """
    event_us = df["event_time_us"].values
    rgb_ms   = df["rgb_time_ms"].values

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    # --- 散布図 ---
    sc = ax.scatter(
        event_us, rgb_ms,
        c=np.arange(len(event_us)),
        cmap="plasma",
        s=80,
        edgecolors="#ffffff",
        linewidths=0.5,
        alpha=0.85,
        zorder=3,
        label="Matched LED timestamps"
    )

    # カラーバー（点灯順を色で示す）
    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("LED flash index", color="#cccccc", fontsize=11)
    cbar.ax.yaxis.set_tick_params(color="#cccccc")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#cccccc")

    # --- 近似直線 ---
    if sync_params is not None:
        A = sync_params["A"]
        B = sync_params["B"]
        x_line = np.linspace(event_us.min(), event_us.max(), 200)
        y_line = A * x_line + B
        ax.plot(
            x_line, y_line,
            color="#00d4ff",
            linewidth=2.5,
            linestyle="--",
            alpha=0.9,
            zorder=4,
            label=f"Linear fit: y = {A:.6e}·x + {B:.4f}"
        )

        # 残差の RMS を計算して表示
        y_pred = A * event_us + B
        residuals = rgb_ms - y_pred
        rms = np.sqrt(np.mean(residuals**2))
        ax.text(
            0.03, 0.95,
            f"RMS residual: {rms:.4f} ms",
            transform=ax.transAxes,
            color="#ffdd57",
            fontsize=11,
            verticalalignment="top",
            bbox=dict(facecolor="#0f3460", alpha=0.7, edgecolor="#00d4ff", boxstyle="round,pad=0.4")
        )

    # --- 軸設定 ---
    ax.set_xlabel("Event Camera Timestamp [us]", color="#cccccc", fontsize=13, labelpad=10)
    ax.set_ylabel("RGB Camera Timestamp [ms]",   color="#cccccc", fontsize=13, labelpad=10)
    ax.set_title("RGB ↔ Event Camera Time Synchronization", color="#ffffff", fontsize=16, pad=15)

    ax.tick_params(colors="#aaaaaa", labelsize=10)
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f"))

    for spine in ax.spines.values():
        spine.set_edgecolor("#444466")

    ax.grid(True, color="#334466", linewidth=0.5, linestyle="--", alpha=0.6)
    ax.legend(facecolor="#0f3460", edgecolor="#00d4ff", labelcolor="#ffffff", fontsize=11)

    # --- 保存・表示 ---
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"[Module3] プロット保存: {output_path}")
    plt.show()


def main():
    df = load_matched_timestamps(MATCHED_CSV)
    sync_params = load_sync_params(SYNC_PARAMS)
    plot_sync(df, sync_params, OUTPUT_PLOT)
    print("[Module3] 完了。")


if __name__ == "__main__":
    main()
