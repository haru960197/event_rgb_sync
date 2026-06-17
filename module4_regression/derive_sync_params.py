#!/usr/bin/env python3
"""
Module 4: 関係式導出プログラム
================================
output/matched_timestamps.csv に対して最小二乗法（線形回帰）を適用し、
RGB時刻とイベント時刻の変換式を導出する。

変換式: rgb_time_ms = A * event_time_us + B

結果を output/sync_params.json に保存した後、
Module3 の可視化関数を呼び出して近似直線付きプロットを生成する。

使用方法:
    python derive_sync_params.py

必要なファイル:
    - output/matched_timestamps.csv  (Module2の出力)

出力:
    - output/sync_params.json        (A, B, R^2, N を含む)
    - output/sync_plot.png           (Module3と統合、近似直線付き)
"""

import sys
import os
import json
import numpy as np
import pandas as pd
from scipy import stats

# =========================================================
# パス設定
# =========================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

MATCHED_CSV = os.path.join(PROJECT_ROOT, "output", "matched_timestamps.csv")
SYNC_PARAMS = os.path.join(PROJECT_ROOT, "output", "sync_params.json")

# Module3 の可視化関数を呼び出す
sys.path.insert(0, os.path.join(PROJECT_ROOT, "module3_visualize"))
from visualize_sync import load_matched_timestamps, plot_sync

OUTPUT_PLOT = os.path.join(PROJECT_ROOT, "output", "sync_plot.png")


def linear_regression(event_us: np.ndarray, rgb_ms: np.ndarray) -> dict:
    """
    最小二乗法で線形回帰を実行する。
    モデル: rgb_ms = A * event_us + B

    Returns:
        dict with keys: A, B, r_squared, n, std_err_A, std_err_B
    """
    slope, intercept, r_value, p_value, std_err = stats.linregress(event_us, rgb_ms)

    result = {
        "A":          float(slope),
        "B":          float(intercept),
        "r_squared":  float(r_value ** 2),
        "p_value":    float(p_value),
        "std_err_A":  float(std_err),
        "n":          int(len(event_us)),
    }

    # 切片の標準誤差を手動計算
    n = len(event_us)
    x_mean = np.mean(event_us)
    ss_x = np.sum((event_us - x_mean) ** 2)
    y_pred = slope * event_us + intercept
    residuals = rgb_ms - y_pred
    s2 = np.sum(residuals ** 2) / (n - 2)  # 残差分散
    std_err_B = np.sqrt(s2 * (1.0 / n + x_mean**2 / ss_x))
    result["std_err_B"] = float(std_err_B)

    return result


def save_sync_params(params_path: str, result: dict):
    """回帰結果を JSON ファイルに保存する。"""
    os.makedirs(os.path.dirname(params_path), exist_ok=True)
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[Module4] 同期パラメータを保存しました: {params_path}")


def print_result(result: dict):
    """回帰結果をコンソールに分かりやすく表示する。"""
    A = result["A"]
    B = result["B"]
    r2 = result["r_squared"]
    n  = result["n"]
    se_A = result["std_err_A"]
    se_B = result["std_err_B"]

    print("\n" + "=" * 60)
    print("  線形回帰結果")
    print("=" * 60)
    print(f"  変換式: rgb_time_ms = A × event_time_us + B")
    print(f"  A (傾き)    = {A:.8e}  ±{se_A:.2e}")
    print(f"  B (切片)    = {B:.6f} ms  ±{se_B:.4f} ms")
    print(f"  R²          = {r2:.8f}")
    print(f"  n (サンプル数) = {n}")
    print("=" * 60)
    print(f"\n  [解釈]")
    print(f"  イベントカメラのタイムスタンプ (us) を RGB時刻 (ms) に変換:")
    print(f"  rgb_ms = {A:.6e} * event_us + {B:.4f}")

    # 傾きの物理的意味チェック
    # 理想的には A ≈ 1e-3 (usからmsへの変換 = 1/1000)
    expected_A = 1e-3
    ratio = A / expected_A
    print(f"\n  [チェック] 理想傾き(1e-3)との比: {ratio:.6f}")
    if abs(ratio - 1.0) < 0.01:
        print("  → タイムスタンプスケールはほぼ一致しています (クロックドリフト < 1%)")
    else:
        print(f"  → クロックドリフトが検出されました ({(ratio-1)*100:+.2f}%)")
    print()


def main():
    # --- データ読み込み ---
    df = load_matched_timestamps(MATCHED_CSV)

    if len(df) < 2:
        print(f"[ERROR] データが少なすぎます（{len(df)}件）。最低2ペア必要です。")
        sys.exit(1)

    event_us = df["event_time_us"].values.astype(np.float64)
    rgb_ms   = df["rgb_time_ms"].values.astype(np.float64)

    # --- 線形回帰 ---
    print("[Module4] 最小二乗法による線形回帰を実行します...")
    result = linear_regression(event_us, rgb_ms)
    print_result(result)

    # --- 結果保存 ---
    save_sync_params(SYNC_PARAMS, result)

    # --- Module3 と統合: 近似直線付きプロット生成 ---
    print("[Module4] Module3 の可視化を呼び出します（近似直線付き）...")
    plot_sync(df, result, OUTPUT_PLOT)

    print("[Module4] 完了。")


if __name__ == "__main__":
    main()
