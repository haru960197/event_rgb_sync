#!/usr/bin/env python3
"""
Module 1.5: イベントレート可視化・パラメータチューニングツール
=================================================================
LED領域内のイベント発生レートを時系列グラフで可視化し、
Module 2 のバースト検知パラメータ（burst_threshold_count, slope_threshold 等）
を視覚的に調整するための補助ツール。

使用方法:
    python tune_parameters.py

必要なファイル:
    - config/params.json      (time_bin_us, burst_threshold_count 等)
    - config/led_region.json  (x_min, y_min, x_max, y_max)
    - input/events.csv        (x, y, polarity, timestamp_us)

出力:
    - 画面表示: イベントレートの時系列グラフ
    - output/event_rate_plot.png: グラフ画像の保存（任意）
"""

import sys
import os
import json
import csv
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# =========================================================
# パス設定
# =========================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PARAMS_FILE     = os.path.join(PROJECT_ROOT, "config", "params.json")
LED_REGION_FILE = os.path.join(PROJECT_ROOT, "config", "led_region.json")
EVENTS_FILE     = os.path.join(PROJECT_ROOT, "input", "events.csv")
OUTPUT_PLOT     = os.path.join(PROJECT_ROOT, "output", "event_rate_plot.png")


# =========================================================
# パラメータ・設定読み込み
# =========================================================
def load_params(params_file: str) -> dict:
    """config/params.json を読み込み、Module1.5 に必要な設定値を返す。"""
    with open(params_file, "r", encoding="utf-8") as f:
        params = json.load(f)
    m2 = params.get("module2", {})
    return {
        "time_bin_us":           m2.get("time_bin_us",           5000),
        "burst_threshold_count": m2.get("burst_threshold_count", 50),
        "slope_threshold":       m2.get("slope_threshold",       15.0),
    }


def load_led_region(led_region_file: str) -> dict:
    """config/led_region.json を読み込んでLED領域座標を返す。"""
    with open(led_region_file, "r", encoding="utf-8") as f:
        region = json.load(f)
    return region  # {"x_min": ..., "y_min": ..., "x_max": ..., "y_max": ...}


# =========================================================
# events.csv のストリーム読み込みとヒストグラム計算
# =========================================================
def compute_event_rate(events_file: str, region: dict, time_bin_us: int) -> tuple:
    """
    events.csv をストリーム読み込みし、LED領域内のイベント発生レートを
    time_bin_us ごとのビンでカウントして返す。

    Returns:
        (bin_centers_s, counts, slope)
        - bin_centers_s: 各ビンの中心時刻 [秒]
        - counts: 各ビンのイベントカウント数
        - slopes: 各ビンにおける前ビンとの差（傾き）
    """
    x_min = region["x_min"]
    y_min = region["y_min"]
    x_max = region["x_max"]
    y_max = region["y_max"]

    # bin_index -> count の辞書（スパース表現）
    bin_counts: dict[int, int] = {}

    total_lines   = 0
    filtered_count = 0

    print(f"[Module1.5] LED領域: x=[{x_min},{x_max}] y=[{y_min},{y_max}]")
    print(f"[Module1.5] 時間ビン幅: {time_bin_us} us = {time_bin_us / 1e6:.3f} s")
    print(f"[Module1.5] events.csv を読み込んでいます（ストリーム処理）...")

    with open(events_file, "r", encoding="utf-8") as f:
        # --- ヘッダスキップ処理 ---
        first_line = f.readline().strip()
        if first_line.startswith("%") or not first_line[:1].isdigit():
            # メタデータ行はスキップ。続く行がカラムヘッダの場合もスキップ
            second_line = f.readline().strip()
            if second_line and not second_line[:1].isdigit():
                pass  # カラムヘッダ行もスキップ
            else:
                # 2行目がデータ行なら読み直し（シーク）
                pos = f.tell() - len(second_line.encode("utf-8")) - 1
                f.seek(max(0, pos))
                # 簡易再現: second_line を手動でパース
                if second_line:
                    total_lines += 1
                    parts = second_line.split(",")
                    if len(parts) >= 4:
                        try:
                            x  = int(parts[0].strip())
                            y  = int(parts[1].strip())
                            ts = int(parts[3].strip())
                            if x_min <= x <= x_max and y_min <= y <= y_max:
                                idx = ts // time_bin_us
                                bin_counts[idx] = bin_counts.get(idx, 0) + 1
                                filtered_count += 1
                        except (ValueError, IndexError):
                            pass
        else:
            # 1行目がデータ行（ヘッダなし）の場合はシーク先頭に戻す
            f.seek(0)

        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue
            total_lines += 1

            # 進捗表示（100万行ごと）
            if total_lines % 1_000_000 == 0:
                print(f"[Module1.5]   {total_lines // 1_000_000}M 行処理中...")

            try:
                x  = int(row[0].strip())
                y  = int(row[1].strip())
                ts = int(row[3].strip())
            except (ValueError, IndexError):
                continue

            # LED領域外のイベントは破棄
            if not (x_min <= x <= x_max and y_min <= y <= y_max):
                continue

            # 時間ビンにカウント
            bin_idx = ts // time_bin_us
            bin_counts[bin_idx] = bin_counts.get(bin_idx, 0) + 1
            filtered_count += 1

    print(f"[Module1.5] 処理完了: {total_lines:,} 行読み込み, LED領域内 {filtered_count:,} イベント")

    if not bin_counts:
        print("[ERROR] LED領域内にイベントが見つかりませんでした。led_region.jsonを確認してください。")
        sys.exit(1)

    # ビン辞書を時刻順ソートして配列化
    sorted_bins = sorted(bin_counts.items())  # [(bin_idx, count), ...]
    bin_indices = np.array([b for b, _ in sorted_bins], dtype=np.int64)
    counts      = np.array([c for _, c in sorted_bins], dtype=np.int64)

    # ビンが抜けている区間は 0 で埋める（連続した時間軸のために）
    idx_min, idx_max = bin_indices[0], bin_indices[-1]
    full_indices = np.arange(idx_min, idx_max + 1, dtype=np.int64)
    full_counts  = np.zeros(len(full_indices), dtype=np.int64)
    # スパース → 密に変換
    for i, (b, c) in enumerate(sorted_bins):
        full_counts[b - idx_min] = c

    # ビンの中心時刻を秒に変換
    bin_centers_s = (full_indices * time_bin_us + time_bin_us / 2) / 1e6

    # 傾き（前ビンとの差、最初は 0）
    slopes = np.diff(full_counts.astype(float), prepend=0.0)

    return bin_centers_s, full_counts, slopes


# =========================================================
# プロット描画
# =========================================================
def plot_event_rate(
    bin_centers_s: np.ndarray,
    counts: np.ndarray,
    slopes: np.ndarray,
    burst_threshold_count: int,
    slope_threshold: float,
    time_bin_us: int,
    output_path: str,
):
    """
    イベントレートの時系列グラフを描画する。
    上段: イベントカウント（バースト閾値を赤破線で表示）
    下段: 傾き（前ビンとの差。傾き閾値を赤破線で表示）
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True)
    fig.patch.set_facecolor("#1a1a2e")
    for ax in (ax1, ax2):
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="#aaaaaa", labelsize=9)
        ax.grid(True, color="#334466", linewidth=0.5, linestyle="--", alpha=0.6)
        for spine in ax.spines.values():
            spine.set_edgecolor("#444466")

    time_bin_label = (f"{time_bin_us} us" if time_bin_us < 1000
                      else f"{time_bin_us / 1000:.1f} ms" if time_bin_us < 1_000_000
                      else f"{time_bin_us / 1_000_000:.2f} s")

    # ------ 上段: イベントカウント ------
    ax1.fill_between(bin_centers_s, counts, alpha=0.35, color="#5588ff", linewidth=0)
    ax1.plot(bin_centers_s, counts, color="#88aaff", linewidth=0.8, label="Event count / bin")

    # burst_threshold_count: 赤破線
    ax1.axhline(
        burst_threshold_count,
        color="#ff4444", linewidth=1.8, linestyle="--",
        label=f"burst_threshold_count = {burst_threshold_count}",
        zorder=5,
    )

    ax1.set_ylabel(f"Events per bin\n(bin = {time_bin_label})", color="#cccccc", fontsize=11)
    ax1.set_title(
        "LED Region Event Rate — Parameter Tuning View",
        color="#ffffff", fontsize=14, pad=12,
    )
    ax1.legend(facecolor="#0f3460", edgecolor="#5588ff", labelcolor="#ffffff", fontsize=10)

    # Y軸の上限にゆとりを持たせる（クリッピング対策）
    peak = counts.max()
    ax1.set_ylim(0, max(peak * 1.15, burst_threshold_count * 1.5))

    # ピーク位置にアノテーション
    peak_idx = counts.argmax()
    ax1.annotate(
        f"  peak={peak}",
        xy=(bin_centers_s[peak_idx], peak),
        xytext=(bin_centers_s[peak_idx], peak * 1.05),
        color="#ffdd57",
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="#ffdd57", lw=1.2),
    )

    # ------ 下段: 傾き ------
    pos_slopes = np.where(slopes > 0, slopes, 0)
    neg_slopes = np.where(slopes < 0, slopes, 0)
    ax2.fill_between(bin_centers_s, pos_slopes, alpha=0.4, color="#00d4aa", linewidth=0, label="Rising slope")
    ax2.fill_between(bin_centers_s, neg_slopes, alpha=0.3, color="#ff8844", linewidth=0, label="Falling slope")
    ax2.plot(bin_centers_s, slopes, color="#aaddcc", linewidth=0.7)

    # slope_threshold: 赤破線
    ax2.axhline(
        slope_threshold,
        color="#ff4444", linewidth=1.8, linestyle="--",
        label=f"slope_threshold = {slope_threshold}",
        zorder=5,
    )
    ax2.axhline(0, color="#555577", linewidth=0.8, linestyle="-")

    ax2.set_xlabel("Time [s]", color="#cccccc", fontsize=11, labelpad=8)
    ax2.set_ylabel("Slope\n(count diff / bin)", color="#cccccc", fontsize=11)
    ax2.legend(facecolor="#0f3460", edgecolor="#00d4aa", labelcolor="#ffffff", fontsize=10)

    # X軸のフォーマット
    ax2.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))

    # パラメータ情報をフッターに表示
    fig.text(
        0.5, 0.01,
        f"time_bin_us={time_bin_us}  |  burst_threshold_count={burst_threshold_count}  |  slope_threshold={slope_threshold}",
        ha="center", color="#888899", fontsize=9,
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"[Module1.5] グラフを保存しました: {output_path}")

    plt.show()


# =========================================================
# main
# =========================================================
def main():
    # --- ファイル存在チェック ---
    for path, name in [(PARAMS_FILE, "params.json"),
                       (LED_REGION_FILE, "led_region.json"),
                       (EVENTS_FILE, "events.csv")]:
        if not os.path.exists(path):
            print(f"[ERROR] {name} が見つかりません: {path}")
            sys.exit(1)

    # --- 設定読み込み ---
    params = load_params(PARAMS_FILE)
    time_bin_us           = params["time_bin_us"]
    burst_threshold_count = params["burst_threshold_count"]
    slope_threshold       = params["slope_threshold"]
    region = load_led_region(LED_REGION_FILE)

    print(f"[Module1.5] time_bin_us           = {time_bin_us} us")
    print(f"[Module1.5] burst_threshold_count = {burst_threshold_count}")
    print(f"[Module1.5] slope_threshold       = {slope_threshold}")

    # --- イベントレート計算 ---
    bin_centers_s, counts, slopes = compute_event_rate(EVENTS_FILE, region, time_bin_us)

    # --- プロット ---
    plot_event_rate(
        bin_centers_s, counts, slopes,
        burst_threshold_count, slope_threshold,
        time_bin_us, OUTPUT_PLOT,
    )

    print("[Module1.5] 完了。")


if __name__ == "__main__":
    main()
