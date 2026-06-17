/**
 * Module 2: イベント・RGB 時刻対応付けプログラム
 * =================================================
 * イベントカメラデータ（events.csv）とRGBカメラログ（sync_log.csv）から
 * それぞれのLED点灯タイミングを検出し、インデックス順に1対1対応付けして
 * output/matched_timestamps.csv として出力する。
 *
 * ビルド:
 *   cd module2_timestamp_matching
 *   mkdir build && cd build
 *   cmake .. -DCMAKE_BUILD_TYPE=Release
 *   make -j$(nproc)
 *
 * 実行:
 *   ./sync_timestamps
 *   または引数でプロジェクトルートを指定:
 *   ./sync_timestamps /path/to/event_rgb_sync
 *
 * 依存:
 *   - nlohmann/json (ヘッダオンリー, third_party/nlohmann/json.hpp)
 *   - C++17以上
 */

#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"

namespace fs = std::filesystem;
using json   = nlohmann::json;

// =========================================================
// 型エイリアス
// =========================================================
using TimestampUs = int64_t;  // イベントカメラタイムスタンプ [us]
using TimestampMs = double;   // RGBカメラタイムスタンプ [ms]

// =========================================================
// 設定構造体
// =========================================================
struct Config {
    // LED領域
    int x_min = 0, y_min = 0, x_max = 319, y_max = 319;

    // Module2 パラメータ
    TimestampUs time_bin_us         = 5000;   // 時間ビン幅 [us]
    int         burst_threshold_count = 50;   // バースト判定カウント閾値
    double      slope_threshold     = 15.0;   // バースト判定傾き閾値 [カウント/ビン]
};

// =========================================================
// ユーティリティ: 文字列トリム
// =========================================================
static std::string trim(const std::string& s) {
    const char* ws = " \t\r\n";
    size_t start = s.find_first_not_of(ws);
    size_t end   = s.find_last_not_of(ws);
    if (start == std::string::npos) return "";
    return s.substr(start, end - start + 1);
}

// =========================================================
// 設定読み込み
// =========================================================
Config load_config(const fs::path& project_root) {
    Config cfg;

    // --- led_region.json ---
    fs::path led_region_file = project_root / "config" / "led_region.json";
    if (!fs::exists(led_region_file)) {
        std::cerr << "[WARN] " << led_region_file
                  << " が見つかりません。センサ全域をLED領域として使用します。\n";
    } else {
        std::ifstream f(led_region_file);
        json j;
        f >> j;
        cfg.x_min = j.at("x_min").get<int>();
        cfg.y_min = j.at("y_min").get<int>();
        cfg.x_max = j.at("x_max").get<int>();
        cfg.y_max = j.at("y_max").get<int>();
        std::cout << "[Module2] LED領域: x=[" << cfg.x_min << "," << cfg.x_max
                  << "] y=[" << cfg.y_min << "," << cfg.y_max << "]\n";
    }

    // --- params.json ---
    fs::path params_file = project_root / "config" / "params.json";
    if (!fs::exists(params_file)) {
        std::cerr << "[WARN] " << params_file
                  << " が見つかりません。デフォルト値を使用します。\n";
    } else {
        std::ifstream f(params_file);
        json j;
        f >> j;
        auto& m2 = j.at("module2");
        cfg.time_bin_us          = m2.at("time_bin_us").get<TimestampUs>();
        cfg.burst_threshold_count = m2.at("burst_threshold_count").get<int>();
        cfg.slope_threshold      = m2.at("slope_threshold").get<double>();
        std::cout << "[Module2] パラメータ:"
                  << " time_bin_us="       << cfg.time_bin_us
                  << " burst_threshold="   << cfg.burst_threshold_count
                  << " slope_threshold="   << cfg.slope_threshold << "\n";
    }

    return cfg;
}

// =========================================================
// バースト検知器
// =========================================================
class BurstDetector {
public:
    explicit BurstDetector(const Config& cfg)
        : time_bin_us_(cfg.time_bin_us),
          burst_threshold_(cfg.burst_threshold_count),
          slope_threshold_(cfg.slope_threshold) {}

    /**
     * イベントのタイムスタンプを追加する（ストリーミング処理用）。
     * 内部でビンにカウントアップし、バーストを検知する。
     */
    void add_event(TimestampUs ts) {
        if (current_bin_start_ < 0) {
            current_bin_start_ = ts;
        }

        // 現在のビン外に出たら確定
        while (ts >= current_bin_start_ + time_bin_us_) {
            finalize_bin();
        }

        ++current_bin_count_;
    }

    /** ストリーミング終了後に残りのビンを確定する。 */
    void finalize() {
        if (current_bin_count_ > 0) {
            finalize_bin();
        }
    }

    /** 検知したLED点灯タイムスタンプ一覧を返す。 */
    const std::vector<TimestampUs>& led_timestamps() const {
        return led_timestamps_;
    }

private:
    void finalize_bin() {
        int64_t count = current_bin_count_;
        TimestampUs bin_start = current_bin_start_;

        // バースト判定: カウント閾値 OR 傾き（前ビンとの差）閾値
        double slope = static_cast<double>(count) - static_cast<double>(prev_bin_count_);
        bool is_burst = (count >= burst_threshold_) || (slope >= slope_threshold_);

        if (is_burst && !in_burst_) {
            // バースト開始 → LED点灯タイミングとして記録
            led_timestamps_.push_back(bin_start);
            in_burst_ = true;
            std::cout << "[Module2] LED点灯検知 (イベント): "
                      << bin_start << " us  (count=" << count
                      << ", slope=" << slope << ")\n";
        } else if (!is_burst) {
            in_burst_ = false;
        }

        prev_bin_count_  = count;
        current_bin_start_ += time_bin_us_;
        current_bin_count_  = 0;
    }

    TimestampUs time_bin_us_;
    int         burst_threshold_;
    double      slope_threshold_;

    TimestampUs current_bin_start_  = -1;
    int64_t     current_bin_count_  = 0;
    int64_t     prev_bin_count_     = 0;
    bool        in_burst_           = false;

    std::vector<TimestampUs> led_timestamps_;
};

// =========================================================
// events.csv の処理（ストリーム読み込み）
// =========================================================
std::vector<TimestampUs> process_events_csv(const fs::path& events_file,
                                             const Config&   cfg) {
    const size_t READ_BUFFER_SIZE = 1 << 20;  // 1 MB 読み込みバッファ
    std::ifstream fin(events_file, std::ios::binary);
    if (!fin) {
        throw std::runtime_error("events.csv を開けません: " + events_file.string());
    }

    fin.rdbuf()->pubsetbuf(nullptr, READ_BUFFER_SIZE);

    BurstDetector detector(cfg);
    std::string line;
    bool header_skipped = false;
    size_t line_count = 0;

    auto t_start = std::chrono::steady_clock::now();

    while (std::getline(fin, line)) {
        ++line_count;
        if (line.empty()) continue;

        // 最初の非空行がメタデータ（'%'で始まる）またはカラムヘッダの場合はスキップ
        if (!header_skipped) {
            char first = line.front();
            if (first == '%' || !std::isdigit(static_cast<unsigned char>(first))) {
                // さらに次の行がカラムヘッダの可能性がある（'x' などアルファベット）
                std::string peeked;
                auto pos = fin.tellg();
                if (std::getline(fin, peeked) && !peeked.empty() &&
                    !std::isdigit(static_cast<unsigned char>(peeked.front()))) {
                    // 2行スキップ
                } else {
                    // 1行だけスキップ、peeked は処理対象
                    fin.seekg(pos);
                }
                header_skipped = true;
                continue;
            }
            header_skipped = true;
        }

        // CSV パース: x, y, polarity, timestamp_us
        // 高速化のため手動パース（sscanf 相当）
        const char* ptr = line.c_str();
        char* end;

        int x = static_cast<int>(std::strtol(ptr, &end, 10));
        if (ptr == end || *end != ',') continue;
        ptr = end + 1;

        int y = static_cast<int>(std::strtol(ptr, &end, 10));
        if (ptr == end || *end != ',') continue;
        ptr = end + 1;

        int polarity = static_cast<int>(std::strtol(ptr, &end, 10));
        if (ptr == end || *end != ',') continue;
        ptr = end + 1;

        TimestampUs ts = static_cast<TimestampUs>(std::strtoll(ptr, &end, 10));
        if (ptr == end) continue;

        // LED領域内かつ ONイベントのみ
        if (polarity == 1 &&
            x >= cfg.x_min && x <= cfg.x_max &&
            y >= cfg.y_min && y <= cfg.y_max) {
            detector.add_event(ts);
        }

        // 進捗表示（100万行ごと）
        if (line_count % 1'000'000 == 0) {
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::steady_clock::now() - t_start).count();
            std::cout << "[Module2] " << line_count / 1'000'000
                      << "M 行処理完了 (" << elapsed << "s)\n";
        }
    }

    detector.finalize();

    auto elapsed_total = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - t_start).count();
    std::cout << "[Module2] events.csv 処理完了: " << line_count
              << " 行, " << elapsed_total << " ms\n";

    return detector.led_timestamps();
}

// =========================================================
// sync_log.csv の処理: LED立ち上がりタイミング検出
// =========================================================
std::vector<TimestampMs> process_sync_log_csv(const fs::path& sync_log_file) {
    std::ifstream fin(sync_log_file);
    if (!fin) {
        throw std::runtime_error("sync_log.csv を開けません: " + sync_log_file.string());
    }

    std::vector<TimestampMs> led_times_ms;
    std::string line;
    bool header_skipped = false;
    int prev_status = -1;

    while (std::getline(fin, line)) {
        line = trim(line);
        if (line.empty()) continue;

        // ヘッダ行スキップ（最初の非数字行）
        if (!header_skipped) {
            if (!std::isdigit(static_cast<unsigned char>(line.front()))) {
                header_skipped = true;
                continue;
            }
            header_skipped = true;
        }

        // CSV パース: frame_index, timestamp_ms, led_status
        std::istringstream ss(line);
        std::string tok;

        if (!std::getline(ss, tok, ',')) continue;
        // frame_index は使用しない

        if (!std::getline(ss, tok, ',')) continue;
        TimestampMs ts_ms;
        try { ts_ms = std::stod(trim(tok)); } catch (...) { continue; }

        if (!std::getline(ss, tok, ',')) continue;
        int status;
        try { status = std::stoi(trim(tok)); } catch (...) { continue; }

        // led_status が 0→1 に切り替わった瞬間を検出
        if (prev_status == 0 && status == 1) {
            led_times_ms.push_back(ts_ms);
            std::cout << "[Module2] LED点灯検知 (RGB): " << ts_ms << " ms\n";
        }

        prev_status = status;
    }

    return led_times_ms;
}

// =========================================================
// マッチング & CSV出力
// =========================================================
void write_matched_timestamps(const fs::path&                  output_file,
                               const std::vector<TimestampMs>& rgb_times,
                               const std::vector<TimestampUs>& event_times) {
    size_t n = std::min(rgb_times.size(), event_times.size());
    if (n == 0) {
        std::cerr << "[WARN] マッチング結果が0件です。\n";
        return;
    }

    if (rgb_times.size() != event_times.size()) {
        std::cerr << "[WARN] LED点灯数が一致しません。"
                  << " RGB=" << rgb_times.size()
                  << " Event=" << event_times.size()
                  << " → 少ない方に合わせます（n=" << n << "）\n";
    }

    // output/ ディレクトリが存在しない場合は作成
    fs::create_directories(output_file.parent_path());

    std::ofstream fout(output_file);
    if (!fout) {
        throw std::runtime_error("出力ファイルを開けません: " + output_file.string());
    }

    fout << "rgb_time_ms,event_time_us\n";
    for (size_t i = 0; i < n; ++i) {
        fout << rgb_times[i] << "," << event_times[i] << "\n";
    }

    std::cout << "[Module2] 対応付け完了: " << n << " ペア → " << output_file << "\n";
}

// =========================================================
// main
// =========================================================
int main(int argc, char* argv[]) {
    // プロジェクトルートの決定
    // デフォルト: このバイナリの2階層上（build/ → module2/ → project_root）
    fs::path project_root;
    if (argc >= 2) {
        project_root = fs::path(argv[1]);
    } else {
        // バイナリのパスから推定
        project_root = fs::canonical(fs::path(argv[0])).parent_path()  // build/
                                                         .parent_path()  // module2/
                                                         .parent_path(); // project_root/
    }
    std::cout << "[Module2] プロジェクトルート: " << project_root << "\n";

    try {
        // --- 設定読み込み ---
        Config cfg = load_config(project_root);

        // --- events.csv 処理 ---
        fs::path events_file = project_root / "input" / "events.csv";
        std::cout << "[Module2] events.csv を処理します: " << events_file << "\n";
        auto event_led_times = process_events_csv(events_file, cfg);
        std::cout << "[Module2] イベント側LED点灯数: " << event_led_times.size() << "\n";

        // --- sync_log.csv 処理 ---
        fs::path sync_log_file = project_root / "input" / "sync_log.csv";
        std::cout << "[Module2] sync_log.csv を処理します: " << sync_log_file << "\n";
        auto rgb_led_times = process_sync_log_csv(sync_log_file);
        std::cout << "[Module2] RGB側LED点灯数: " << rgb_led_times.size() << "\n";

        // --- マッチング & 出力 ---
        fs::path output_file = project_root / "output" / "matched_timestamps.csv";
        write_matched_timestamps(output_file, rgb_led_times, event_led_times);

    } catch (const std::exception& e) {
        std::cerr << "[ERROR] " << e.what() << "\n";
        return 1;
    }

    std::cout << "[Module2] 正常終了\n";
    return 0;
}
