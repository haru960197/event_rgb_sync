# event_rgb_sync

RGBカメラとイベントカメラ（Prophesee GenX320 等）で別々に撮影されたデータの **時間軸を同期** するプログラム群です。  
同期の基準として「画面内の特定座標で定期的に点滅する LED」の光学的な発光タイミングを使用します。

---

## システム概要

```
[RGBカメラ]          [イベントカメラ]
sync_log.csv    →    events.csv
（led_status）        （x, y, polarity, timestamp_us）
      ↓                     ↓
  LED立ち上がり          バースト検知
  タイムスタンプ         タイムスタンプ
      ↓                     ↓
      ┗━━━━━━ 対応付け ━━━━━━┛
              ↓
    matched_timestamps.csv
              ↓
        線形回帰 (y = Ax + B)
              ↓
        sync_params.json
```

---

## ディレクトリ構成

```
event_rgb_sync/
├── README.md
├── .gitignore
├── requirements.txt
├── config/
│   ├── params.json              # 共通パラメータ設定
│   └── led_region.json          # LED領域（Module1実行後に生成）
├── input/
│   ├── sync_log.csv             # RGBカメラログ（ユーザーが配置）
│   └── events.csv               # イベントカメラデータ（ユーザーが配置）
├── output/
│   ├── matched_timestamps.csv   # Module2の出力
│   ├── sync_plot.png            # Module3/4の出力
│   └── sync_params.json         # Module4の出力
├── module1_led_region/
│   └── define_led_region.py
├── module2_timestamp_matching/
│   ├── CMakeLists.txt
│   ├── main.cpp
│   └── third_party/
│       └── nlohmann/
│           └── json.hpp
├── module3_visualize/
│   └── visualize_sync.py
└── module4_regression/
    └── derive_sync_params.py
```

---

## 入力データ仕様

### `input/sync_log.csv`

RGBカメラ側のフレームごとの撮影ログ。

| カラム | 型 | 説明 |
|---|---|---|
| `frame_index` | int | フレーム番号 |
| `timestamp_ms` | float | 撮影タイムスタンプ [ms] |
| `led_status` | int | LED点灯状態（0=消灯, 1=点灯） |

```csv
frame_index,timestamp_ms,led_status
0,0.000,0
1,33.333,0
3,100.000,1
4,133.333,1
...
```

`led_status` が `0→1` に切り替わった瞬間を「LED点灯タイミング」として検出します。

---

### `input/events.csv`

イベントカメラの出力データ（数GB になる場合あり）。

| カラム | 型 | 説明 |
|---|---|---|
| `x` | int | ピクセルX座標 |
| `y` | int | ピクセルY座標 |
| `polarity` | int | イベント極性（0=OFF, 1=ON） |
| `timestamp_us` | int64 | タイムスタンプ [マイクロ秒] |

```csv
%geometry:320,320
x,y,polarity,timestamp_us
155,160,1,12345
...
```

> **注意**: 1行目の `%geometry:WxH` ヘッダは自動的にスキップされます。

---

## セットアップ

### 1. Python 仮想環境の作成と依存ライブラリのインストール

```bash
cd event_rgb_sync
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**依存ライブラリ**:
- `numpy` — 数値計算
- `pandas` — CSVデータ処理
- `opencv-python` — GUI での ROI 選択
- `matplotlib` — プロット描画
- `scipy` — 線形回帰（`stats.linregress`）

---

### 2. C++ モジュールのビルド（Module 2）

#### 必要なツール

- CMake 3.14 以上
- GCC / Clang（C++17対応）

Ubuntu でのインストール:

```bash
sudo apt-get install cmake build-essential
```

#### ビルド手順

```bash
cd module2_timestamp_matching
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

ビルド成功後、`module2_timestamp_matching/build/sync_timestamps` が生成されます。

> **注意**: `nlohmann/json.hpp`（ヘッダオンリーの JSON パーサー）は `third_party/nlohmann/` に含まれており、追加インストールは不要です。

---

## 実行手順

### ステップ 1: LED検知領域の定義（Module 1）

```bash
source .venv/bin/activate
python module1_led_region/define_led_region.py
```

1. `events.csv` の先頭 5 秒分（デフォルト）のONイベントを積算したヒートマップが表示されます。
2. OpenCV ウィンドウで **マウスドラッグ** により LED の矩形領域を選択します。
3. `SPACE` または `ENTER` で確定すると、`config/led_region.json` に保存されます。

**出力**: `config/led_region.json`

```json
{
  "x_min": 150,
  "y_min": 155,
  "x_max": 160,
  "y_max": 165
}
```

---

### ステップ 2: 時刻対応付け（Module 2）

```bash
./module2_timestamp_matching/build/sync_timestamps
# または、プロジェクトルートを明示的に指定する場合:
./module2_timestamp_matching/build/sync_timestamps /path/to/event_rgb_sync
```

**処理内容**:
- `events.csv` をストリーム読み込みし、LED 領域内のONイベントを抽出
- `time_bin_us` 刻みのビンでカウントし、急激な増加（バースト）を検知
- `sync_log.csv` の `led_status` 立ち上がりを検出
- 2つのリストをインデックス順に1対1対応付け

**出力**: `output/matched_timestamps.csv`

```csv
rgb_time_ms,event_time_us
100.0,93000
266.667,258000
400.0,393000
```

---

### ステップ 3: 可視化（Module 3）

```bash
python module3_visualize/visualize_sync.py
```

- `output/matched_timestamps.csv` を読み込み、散布図を描画
- `output/sync_params.json` が存在する場合は近似直線も重ねて描画
- `output/sync_plot.png` として保存

**出力**: `output/sync_plot.png`

---

### ステップ 4: 変換式の導出（Module 4）

```bash
python module4_regression/derive_sync_params.py
```

- 最小二乗法で線形回帰: `rgb_time_ms = A × event_time_us + B`
- 傾き `A`、切片 `B`、決定係数 R²、標準誤差を算出
- Module 3 の可視化を呼び出して近似直線付きプロットを生成

**出力**: `output/sync_params.json`

```json
{
  "A": 1.00036921e-03,
  "B": 7.464102,
  "r_squared": 0.99995914,
  "p_value": 4.05e-05,
  "std_err_A": 6.39e-06,
  "std_err_B": 1.7694,
  "n": 3
}
```

**変換式の利用例（Python）**:

```python
import json
with open("output/sync_params.json") as f:
    p = json.load(f)

def event_us_to_rgb_ms(event_us):
    return p["A"] * event_us + p["B"]

# 例: イベント時刻 500000 us を RGB時刻に変換
rgb_ms = event_us_to_rgb_ms(500000)
```

---

## パラメータのカスタマイズ

`config/params.json` を編集することで動作を調整できます。

```json
{
  "module1": {
    "accumulation_time_us": 10000000,
    "start_delay_us": 0
  },
  "module2": {
    "time_bin_us": 5000,
    "burst_threshold_count": 50,
    "slope_threshold": 15.0
  }
}
```

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `accumulation_time_us` | 10,000,000 | Module1: ヒートマップ生成に使う積算時間 [us] |
| `start_delay_us` | 0 | Module1: イベントの積算開始を遅らせる時間 [us] （最初のイベント時刻を基準） |
| `time_bin_us` | 5,000 | Module2: バースト検知の時間ビン幅 [us] |
| `burst_threshold_count` | 50 | Module2: バースト判定カウント閾値 |
| `slope_threshold` | 15.0 | Module2: バースト判定の傾き閾値 [カウント/ビン] |

> **チューニングのヒント**: LEDの点滅周波数が高い場合は `time_bin_us` を小さくしてください。ノイズが多い環境では `burst_threshold_count` と `slope_threshold` を大きくしてください。また、起動直後に不要なノイズ等が含まれる場合は `start_delay_us` を用いて積算対象から除外できます。

---

## バージョン管理

このリポジトリは Git で管理されています。

### 初回セットアップ（GitHub へのプッシュ）

```bash
# GitHubで新しいリポジトリを作成後:
git remote add origin https://github.com/<ユーザー名>/event_rgb_sync.git
git branch -M main
git push -u origin main
```

### `.gitignore` の方針

- `input/*.csv` — 大容量データ（数GB）は追跡しない
- `output/` — プログラム生成物は追跡しない
- `module2_timestamp_matching/build/` — ビルドアーティファクトは追跡しない
- `config/led_region.json` — 環境依存のROI設定は追跡しない
- `.venv/` — Python 仮想環境は追跡しない

---

## 動作環境

| 項目 | 要件 |
|---|---|
| OS | Ubuntu 20.04 以上（高スペックPC推奨） |
| Python | 3.10 以上 |
| C++ | GCC 9 以上（C++17対応） |
| CMake | 3.14 以上 |

---

## ライセンス

本プロジェクトは研究用途を目的としています。  
組み込みの `nlohmann/json` は [MIT License](https://github.com/nlohmann/json/blob/develop/LICENSE.MIT) のもとで配布されています。
