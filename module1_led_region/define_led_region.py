#!/usr/bin/env python3
"""
Module 1: LED検知領域定義プログラム
====================================
イベントカメラデータ（events.csv）の先頭部分を空間的に積算してヒートマップを生成し、
ユーザーがGUIでLEDの矩形領域（ROI）を指定できるようにする。
指定された領域は config/led_region.json に保存される。

使用方法:
    python define_led_region.py

必要なファイル:
    - config/params.json   (accumulation_time_us を含む)
    - input/events.csv     (x, y, polarity, timestamp_us カラム)

出力:
    - config/led_region.json  (x_min, y_min, x_max, y_max)
"""

import sys
import os
import json
import csv
import numpy as np
import cv2

# =========================================================
# パス設定（スクリプトの場所に依存しない相対パス解決）
# =========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PARAMS_FILE = os.path.join(PROJECT_ROOT, "config", "params.json")
EVENTS_FILE = os.path.join(PROJECT_ROOT, "input", "events.csv")
LED_REGION_FILE = os.path.join(PROJECT_ROOT, "config", "led_region.json")


def load_params(params_file: str) -> dict:
    """config/params.json を読み込み Module1 用パラメータを返す。"""
    with open(params_file, "r", encoding="utf-8") as f:
        params = json.load(f)
    return params["module1"]


def build_event_heatmap(events_file: str, accumulation_time_us: int) -> np.ndarray:
    """
    events.csv の先頭 accumulation_time_us [us] 分のONイベント（polarity=1）を
    空間的に積算し、2Dヒートマップ（numpy配列）を返す。

    events.csv 仕様:
        - 1行目: ヘッダ行（"%geometry:320,320" のようなメタデータ → スキップ）
        - カラム: x, y, polarity, timestamp_us
    """
    heatmap = None
    start_time_us = None
    n_events_loaded = 0

    with open(events_file, "r", encoding="utf-8") as f:
        # --- ヘッダスキップ処理 ---
        # events.csv の1行目は "%geometry:WxH" 等のメタデータを含む場合がある
        first_line = f.readline().strip()

        # geometry 情報からセンササイズを取得（例: "%geometry:320,320"）
        width, height = 320, 320  # デフォルト
        if first_line.startswith("%") or not first_line[0].isdigit():
            # メタデータ行 → スキップし、geometry があれば解析
            if "geometry" in first_line:
                try:
                    geo_part = first_line.split(":")[-1]
                    w_str, h_str = geo_part.split(",")
                    width, height = int(w_str.strip()), int(h_str.strip())
                    print(f"[Module1] センササイズ検出: {width}x{height}")
                except ValueError:
                    pass
            # 次の行がカラムヘッダの場合もスキップ
            second_line = f.readline().strip()
            if second_line and not second_line[0].isdigit():
                # カラムヘッダ行（例: "x,y,polarity,timestamp_us"）→ スキップ
                pass
            else:
                # 2行目がデータ行の場合は先頭に戻して処理
                f.seek(0)
                f.readline()  # 1行目（メタデータ）を再スキップ
        else:
            # 1行目がデータ行（ヘッダなし）
            f.seek(0)

        heatmap = np.zeros((height, width), dtype=np.float64)

        reader = csv.reader(f)
        for row in reader:
            if len(row) < 4:
                continue
            try:
                x = int(row[0].strip())
                y = int(row[1].strip())
                polarity = int(row[2].strip())
                timestamp_us = int(row[3].strip())
            except (ValueError, IndexError):
                continue  # ヘッダや不正行をスキップ

            # 開始時刻を記録
            if start_time_us is None:
                start_time_us = timestamp_us
                print(f"[Module1] 開始タイムスタンプ: {start_time_us} us")

            # 蓄積時間を超えたら終了
            if timestamp_us - start_time_us > accumulation_time_us:
                break

            # ONイベント（polarity=1）のみ積算
            if polarity == 1:
                if 0 <= x < width and 0 <= y < height:
                    heatmap[y, x] += 1.0
                    n_events_loaded += 1

    elapsed_us = (timestamp_us - start_time_us) if start_time_us is not None else 0
    print(f"[Module1] 積算完了: {n_events_loaded} ONイベント, 経過時間 {elapsed_us} us")
    return heatmap


def normalize_to_uint8(heatmap: np.ndarray) -> np.ndarray:
    """ヒートマップを 0-255 の uint8 画像に正規化する。"""
    if heatmap.max() == 0:
        return np.zeros_like(heatmap, dtype=np.uint8)
    normalized = (heatmap / heatmap.max() * 255).astype(np.uint8)
    return normalized


def select_roi_opencv(gray_img: np.ndarray) -> tuple:
    """
    OpenCV の selectROI を使ってユーザーに矩形領域を選択させる。
    戻り値: (x_min, y_min, x_max, y_max)
    """
    # 見やすさのため COLORMAP_JET でカラーマップ化
    color_img = cv2.applyColorMap(gray_img, cv2.COLORMAP_JET)

    # 画像を2倍に拡大（小さいセンサの場合に操作しやすくする）
    scale = 2
    display_img = cv2.resize(
        color_img,
        (color_img.shape[1] * scale, color_img.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )

    print("\n[Module1] ウィンドウが開きます。")
    print("  マウスドラッグでLED領域を選択し、SPACE または ENTER で確定してください。")
    print("  'c' キーでキャンセルできます。\n")

    # selectROI はウィンドウ名を第1引数に取る
    roi = cv2.selectROI("Event Heatmap - LED Region Selection", display_img, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = roi
    if w == 0 or h == 0:
        print("[Module1] 選択がキャンセルされました。")
        return None

    # 拡大スケールを戻す
    x_min = x // scale
    y_min = y // scale
    x_max = (x + w) // scale
    y_max = (y + h) // scale

    return (x_min, y_min, x_max, y_max)


def save_led_region(led_region_file: str, x_min: int, y_min: int, x_max: int, y_max: int):
    """LED領域座標を JSON ファイルに保存する。"""
    region = {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_max,
        "y_max": y_max,
    }
    with open(led_region_file, "w", encoding="utf-8") as f:
        json.dump(region, f, indent=2)
    print(f"[Module1] LED領域を保存しました: {led_region_file}")
    print(f"          x_min={x_min}, y_min={y_min}, x_max={x_max}, y_max={y_max}")


def main():
    # --- パラメータ読み込み ---
    print("[Module1] パラメータを読み込みます...")
    if not os.path.exists(PARAMS_FILE):
        print(f"[ERROR] {PARAMS_FILE} が見つかりません。")
        sys.exit(1)

    params = load_params(PARAMS_FILE)
    accumulation_time_us = params["accumulation_time_us"]
    print(f"[Module1] accumulation_time_us = {accumulation_time_us} us")

    # --- イベントデータ読み込みとヒートマップ生成 ---
    print(f"[Module1] イベントデータを読み込みます: {EVENTS_FILE}")
    if not os.path.exists(EVENTS_FILE):
        print(f"[ERROR] {EVENTS_FILE} が見つかりません。input/ ディレクトリにデータを配置してください。")
        sys.exit(1)

    heatmap = build_event_heatmap(EVENTS_FILE, accumulation_time_us)
    gray_img = normalize_to_uint8(heatmap)

    # --- GUI でROI選択 ---
    result = select_roi_opencv(gray_img)
    if result is None:
        print("[Module1] 領域が選択されなかったため終了します。")
        sys.exit(0)

    x_min, y_min, x_max, y_max = result

    # --- 結果を保存 ---
    save_led_region(LED_REGION_FILE, x_min, y_min, x_max, y_max)
    print("[Module1] 完了。")


if __name__ == "__main__":
    main()
