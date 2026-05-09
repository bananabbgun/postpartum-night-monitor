# Postpartum Night Monitoring — Pipeline Walkthrough

對照目前 codebase 的技術說明，從「拿到一段影片」到「輸出事件與 VLM 摘要」的完整流程。

主要程式檔案：
[app/main.py](../app/main.py) · [app/config.py](../app/config.py) · [app/types.py](../app/types.py) · [app/detection/](../app/detection/) · [app/rules/](../app/rules/) · [app/state/runtime_state.py](../app/state/runtime_state.py) · [app/vlm/client.py](../app/vlm/client.py) · [app/dashboard/](../app/dashboard/)

---

## 1. 資料流

```
video
→ frame iterator
→ grayscale preprocess
→ threshold-based human mask
→ single-frame metrics (frame diff + centroid step)
→ sliding window aggregation
→ window_state classification
→ event detection
→ VLM summary（事件觸發當下，送當前 window frames）
→ csv / jsonl outputs
```

---

## 2. 設定參數

所有設定在 [app/config.py](../app/config.py) 的 `AppConfig`。

| 參數 | 預設值 | 說明 |
|---|---:|---|
| `smooth_window_seconds` | `3.0` | sliding window 長度（秒） |
| `grayscale_threshold` | `90` | 人體熱區二值化 threshold |
| `area_threshold` | `5` | 單幀判定有人的最小像素面積 |
| `local_motion_threshold` | `5.0` | 什麼算明顯局部動作 |
| `high_motion_persistence_ratio` | `0.75` | window 內幾比例的幀達到明顯動作才算 `high_motion` |
| `centroid_motion_threshold` | `60.0` | 重心位移多少算整體移位 |
| `centroid_motion_consistency_threshold` | `0.75` | 移動方向要多一致才算 `relocating` |
| `person_presence_ratio_threshold` | `0.4` | window 內有人比例低於此值 → `no_person` |
| `still_event_seconds` | `30.0` | 離床後靜止多久觸發事件 |
| `unknown_location_seconds` | `60.0` | 離床後看不到人多久觸發事件 |
| `grace_period_seconds` | `30.0` | 離床後前幾秒不觸發事件 |

---

## 3. 每幀流程

### 3.1 前處理

`preprocess_frame` 把彩色 frame 轉灰階（BGR → gray），已是灰階則直接複製。後續所有計算都在灰階圖上進行。

### 3.2 人體熱區偵測

`detect_human_region` 對灰階圖做固定 threshold 二值化，取亮區為人體熱區。

輸出 `DetectionResult`：`person_detected`、`human_mask`、`thermal_area`、`centroid_x/y`。

### 3.3 單幀量測

`compute_frame_metrics` 計算兩個值：

- **`local_motion_score`**：當前幀與上一幀在人體 mask 區域內的平均差分，代表局部動作強度。
- **`centroid_step`**：當前幀與上一幀重心的距離，代表人體整體位置的單幀位移量（噪音大，不直接用於判斷）。

第一幀因為沒有前一幀，兩個值都是 `None`。

---

## 4. Sliding Window 聚合

相關實作：[app/detection/smoothing.py](../app/detection/smoothing.py) · [app/state/runtime_state.py](../app/state/runtime_state.py)

每幀計算完後，立刻更新四個 window 統計值（皆為最近 `smooth_window_seconds` 內的聚合）：

| 值 | 計算方式 | 意義 |
|---|---|---|
| `local_motion_mean` | window 內 `local_motion_score` 的平均 | 這段時間局部動作的平均強度 |
| `local_motion_persistence` | window 內 `local_motion_score >= local_motion_threshold` 的幀比例 | 明顯動作是否持續存在 |
| `centroid_displacement` | 當前重心與 window 內最早重心的直線距離 | 這段時間人體整體漂移了多遠 |
| `centroid_motion_consistency` | `displacement / path_length` | 移動方向是否一致（接近 1 = 一路往同方向，接近 0 = 原地來回） |
| `person_presence_ratio` | window 內 `person_detected == True` 的幀比例 | 這段時間有多少比例的幀看得到人 |

另外，`RuntimeContext` 的 `FrameWindowBuffer` 同步滾動存放最近 `smooth_window_seconds` 內的 gray frames，供事件觸發時送 VLM 用。

---

## 5. Window State 分類

[app/rules/motion_state.py](../app/rules/motion_state.py) 根據上述 window 值，依序判斷（順序重要）：

| 優先順序 | 狀態 | 條件 |
|---|---|---|
| 1 | `None` | `local_motion_mean is None`（冷啟動） |
| 2 | `no_person` | `person_presence_ratio < 0.4` |
| 3 | `relocating` | `centroid_displacement >= 60` 且 `centroid_motion_consistency >= 0.75` |
| 4 | `still` | `local_motion_mean < 5.0` 且 `local_motion_persistence < 0.5` |
| 5 | `high_motion` | `local_motion_persistence >= 0.75` |
| 6 | `minor_motion` | 以上皆未命中（剩餘類別） |

---

## 6. 事件觸發

[app/rules/event_rules.py](../app/rules/event_rules.py) 每幀執行一次，依 `bed_occupied` 分流：

**在床上（`bed_occupied = True`）**

| 條件 | 事件 | 等級 |
|---|---|---|
| `window_state == "high_motion"` | `bed_high_motion` | yellow |

window_state 被分類為 `high_motion` 的當幀就觸發，不需要額外累積時間。

**不在床上（`bed_occupied = False`）**

前 `grace_period_seconds` 秒不觸發任何事件。

| 條件 | 事件 | 等級 |
|---|---|---|
| `window_state == "still"` 且 `still_duration >= still_event_seconds` | `out_of_bed_stillness` | red |
| `window_state == "no_person"` 且 `unknown_location_duration >= unknown_location_seconds` | `out_of_bed_unknown_location` | yellow |

事件觸發後計時器歸零，等待下一次累積。

---

## 7. VLM 摘要

[app/vlm/client.py](../app/vlm/client.py) 在事件觸發當下立即被呼叫，不是事後批次。

送給 VLM 的內容：
1. System prompt（角色定義、輸出格式要求）
2. 結構化感測器資料（event_type、risk_level、bed_occupied、window_state、local_motion_mean）
3. 當前 window 的 gray frames，每秒抽 1 張（`FrameWindowBuffer.sampled_frames(interval_seconds=1.0)`）

沒有 API key、取不到 frames、或 API 失敗時，走 `_fallback_summary`，依 event type 回傳規則式文字摘要。

VLM 結果存在 `EventRecord.vlm_result`，每個事件各自帶一份。

---

## 8. Duration 累積邏輯

`RuntimeContext.update_durations` 每幀更新 `still_duration` 與 `unknown_location_duration`：

- **在床**：兩個計時器都歸零
- **離床 + `still`**：`still_duration += dt`
- **離床 + `no_person`**：`unknown_location_duration += dt`，並清空所有 window tracker（避免看不到人之前的歷史污染後續判斷）
- **離床 + 其他狀態**：對應計時器歸零

---

## 9. 輸出

**`outputs/frame_metrics.csv`**：每幀一列，包含所有單幀值、window 值、window_state、duration 計時器，主要 debug 來源。

**`outputs/events.jsonl`**：每個 `EventRecord` 一行 JSON，包含 `vlm_result`。

---

## 10. Dashboard

[app/dashboard/service.py](../app/dashboard/service.py) 接收使用者上傳的影片與參數，生成臨時 bed label CSV（整段固定一個 `bed_occupied` 值），呼叫 `run_pipeline`，再從 `frame_metrics.csv` 建立 state segments 供圖表顯示。VLM 結果直接從 `result.events[-1].vlm_result` 取用。

---

## 11. 調參指引

調參時最有用的 CSV 欄位：`local_motion_mean`、`local_motion_persistence`、`centroid_displacement`、`centroid_motion_consistency`、`window_state`。

建議順序：
1. 找一支確定應該是 `still` 的影片，確認 `local_motion_mean` 低、`local_motion_persistence` 低
2. 找一支確定應該是 `high_motion` 的影片，確認 `local_motion_persistence` 高
3. 依照觀察調整 `local_motion_threshold` 和 `high_motion_persistence_ratio`
4. 再看 `relocating` 的影片調整 `centroid_motion_threshold` 和 `centroid_motion_consistency_threshold`
