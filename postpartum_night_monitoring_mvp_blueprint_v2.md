# 產後高風險產婦夜間異常監測系統 MVP 實作藍圖 v2

## 1. 專案定位

本 MVP 目標是開發一套針對產後護理機構夜間照護情境的異常事件偵測系統，協助護理人員在人工巡房不連續的情況下，更即時發現產婦可能發生的異常狀況。

系統不以疾病診斷為目的，而是偵測夜間不合理狀態，例如：

- 產婦在床上長時間異常躁動
- 產婦離床後在床外長時間靜止
- 產婦離床但熱成像無法確認位置
- 產婦疑似跌倒、暈厥、虛弱無法起身或需要協助

核心概念：

> 用床墊壓力感測器判斷產婦是否在床，再用熱成像影片判斷人體活動量。當系統偵測到異常狀態時，擷取熱成像關鍵幀交由 VLM 輔助判讀，最後生成護理站警報與事件摘要。

**感測器職責分工：**

- 床墊壓力感測器：負責判斷產婦是否在床（`bed_occupied`），為系統分流的主要依據
- 熱成像影片：只負責判斷「是否偵測到人體熱源」與「人體活動量」，不負責空間定位

---

## 2. MVP 核心輸入與輸出

### 2.1 Input

本系統 MVP 的輸入分成兩類：

#### Input 1：是否在床上

來源：

- 床墊壓力感測器
- 壓力墊
- FSR 感測器
- MVP 階段可先用手動標記或模擬資料

資料格式範例：

```json
{
  "timestamp": "2026-05-02 02:13:10",
  "room_id": "305",
  "bed_occupied": false,
  "pressure_value": 120
}
```

其中：

- `bed_occupied = true`：產婦在床上
- `bed_occupied = false`：產婦不在床上 / 已離床

---

#### Input 2：熱成像影片

來源：

- 公開熱成像跌倒或活動辨識資料集（網路擷取）
- 自行拍攝熱成像影片
- MVP 階段可先使用公開熱成像影片搭配手動 `bed_occupied` 標籤

資料格式範例：

```json
{
  "timestamp": "2026-05-02 02:13:10",
  "room_id": "305",
  "thermal_video_path": "room305_021310.mp4"
}
```

熱成像影片主要用於判斷：

- 是否有人體熱源（`person_detected`）
- 人體熱源活動量是否過高
- 是否長時間靜止
- 異常事件發生前後的情境（關鍵幀）

熱成像**不負責**判斷人體在床上或床外的空間位置，該資訊由床墊壓力感測器提供。

---

### 2.2 Output

系統輸出分成兩層：

#### Output 1：異常判斷結果

```json
{
  "abnormal": true,
  "event_type": "床外長時間靜止",
  "risk_level": "red",
  "duration": 62,
  "bed_occupied": false,
  "movement_state": "still"
}
```

#### Output 2：VLM 輔助判讀

```json
{
  "vlm_summary": "熱成像顯示人體熱源超過 60 秒沒有明顯移動。",
  "possible_situation": [
    "疑似跌倒",
    "疑似暈厥",
    "產後虛弱無法起身"
  ],
  "recommended_action": "建議護理人員立即前往房間查看，並評估意識狀態與生命徵象。",
  "confidence": "high"
}
```

---

## 3. 系統總流程

```text
夜間監測啟動（讀取熱成像影片）
↓
讀取床墊壓力感測器
↓
判斷 bed_occupied = true / false
↓
讀取熱成像影片 frame，更新 sliding window
↓
偵測人體熱區（person_detected）
↓
若 person_detected = true：計算 movement_score
若 person_detected = false：跳過 movement_score，motion_state = None
↓
對 sliding window 內的 movement_score 取平均 → 平滑後分類 motion_state
↓
依照 bed_occupied 分流
↓
A. 在床上：
   - 偵測是否長時間高活動
   - 若是，觸發「床上異常躁動」
↓
B. 不在床上：
   - 偵測是否床外長時間靜止
   - 若是，觸發「床外長時間靜止」
↓
異常觸發時：
   - 擷取事件前後熱成像關鍵幀（3–5 張）
   - 丟給 VLM 輔助判讀
   - 重置相關計時器
↓
產出：
   - 是否異常
   - 事件類型
   - 風險等級
   - VLM 摘要
   - 護理建議
   - 事件紀錄
```

---

## 4. 系統架構

```text
┌──────────────────────────────┐
│        產後護理房間            │
│                              │
│  床墊壓力感測器                │
│  → bed_occupied               │
│                              │
│  熱成像影片（公開資料集）       │
│  → thermal frames             │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│        異常事件偵測模組        │
│                              │
│  1. 人體熱區偵測               │
│  2. sliding window 平滑       │
│  3. movement_score 計算        │
│  4. still / normal / high 分類 │
│  5. 持續時間累積               │
│  6. 異常規則觸發               │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│          VLM 輔助判讀          │
│                              │
│  輸入：熱成像關鍵幀 + 感測數值  │
│  輸出：事件摘要 + 可能情境      │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│        護理站 Dashboard        │
│                              │
│  房號 / 事件 / 等級 / 建議處置  │
│  熱成像關鍵幀 / 事件紀錄        │
└──────────────────────────────┘
```

---

## 5. 熱成像 movement 判斷方法

### 5.1 熱成像影片轉成 frame

熱成像影片會被拆成一張張連續 frame：

```text
frame_1, frame_2, frame_3, frame_4, ...
```

每一張 frame 可以視為：

- 低解析度溫度矩陣
- 灰階影像
- 偽彩熱影像

例如：

```text
frame_t = 32 × 24 thermal image
```

---

### 5.2 人體熱區偵測

目標是先找出人體熱源區域，避免背景雜訊干擾。

若是真正溫度矩陣，可用：

```python
human_mask = thermal_frame > 30.0
```

或：

```python
human_mask = thermal_frame > room_temp + 3.0
```

若是灰階或偽彩熱影像，可用亮度 threshold：

```python
human_mask = gray_frame > threshold
```

例如：

```text
亮度 > 180 的區域 → 可能是人體熱區
```

**`person_detected` 判斷：**

```python
person_detected = human_mask.sum() > AREA_THRESHOLD
```

其中 `AREA_THRESHOLD` 使用 baseline 校正（見 5.5 節）。

**若 `person_detected = False`**，跳過 movement_score 計算，`motion_state` 設為 `None`，直接進入 `unknown_location_duration` 累積邏輯。

---

### 5.3 Sliding Window 平滑

為了避免單幀雜訊（如翻身一下、打噴嚏）被誤判為持續異常，使用短窗口對 movement_score 做平滑處理。

```python
from collections import deque

SMOOTH_WINDOW_SIZE = 30  # 幀數，依影片 fps 決定（例如 30fps → 1 秒）

score_buffer = deque(maxlen=SMOOTH_WINDOW_SIZE)

# 每幀計算後 push 進 buffer
score_buffer.append(movement_score)

# 用 buffer 平均值分類 motion_state
smoothed_score = sum(score_buffer) / len(score_buffer)
motion_state = classify_motion_state(smoothed_score)
```

`SMOOTH_WINDOW_SIZE` 應根據實際影片 fps 設定，目標是約 1–3 秒的平滑窗口。

---

### 5.4 movement_score 計算

MVP 建議使用兩個 movement 指標。

#### 指標 1：Frame Difference Movement Score

比較前後幀的差異：

```python
diff = abs(frame_t - frame_t_minus_1)
movement_score = mean(diff inside human_mask)
```

意義：

- 差異大：畫面中人體熱源變化明顯，代表有動作
- 差異小：畫面變化很少，代表靜止

適合偵測：

- 床上躁動
- 抽動
- 翻身
- 活動量變化

---

#### 指標 2：Centroid Movement Score

先找出人體熱區中心點：

```text
centroid = (x, y)
```

再計算前後幀中心點位移：

```python
centroid_movement = sqrt((x_t - x_prev)^2 + (y_t - y_prev)^2)
```

意義：

- 位移大：人體位置有明顯移動
- 位移小：人體位置大致不變

適合偵測：

- 離床走動
- 床外是否有位置變化

---

### 5.5 movement 狀態分類

將平滑後的 movement_score 分成三種狀態：

```text
still         → 靜止
normal_motion → 正常活動 / 短暫翻身
high_motion   → 高活動 / 異常躁動
```

範例程式邏輯：

```python
if movement_score < LOW_THRESHOLD:
    motion_state = "still"
elif movement_score > HIGH_THRESHOLD:
    motion_state = "high_motion"
else:
    motion_state = "normal_motion"
```

---

### 5.6 Threshold 設定方式

不要一開始固定死數值，因為不同熱成像資料的亮度與溫度範圍可能不同。

#### movement_score threshold

建議使用 baseline 或 percentile。

**方法 A：前 10 秒 baseline 校正**

```text
baseline_movement = 前 10 秒 movement_score 的平均
baseline_std = 前 10 秒 movement_score 的標準差
```

設定：

```text
LOW_THRESHOLD = baseline_movement + 1 × baseline_std
HIGH_THRESHOLD = baseline_movement + 3 × baseline_std
```

**方法 B：整段影片 percentile**

若是離線 demo，可先讀完整段影片的 movement_score，再設定：

```python
LOW_THRESHOLD = np.percentile(scores, 25)
HIGH_THRESHOLD = np.percentile(scores, 80)
```

#### AREA_THRESHOLD（人體熱區面積閾值）

同樣使用 baseline 校正，不使用固定值：

```python
# 前 10 秒讀取確認無人（或空房間）的幀，取最大熱區面積為 baseline
baseline_max_area = max(human_mask.sum() for each frame in first_10_seconds)

# 設定閾值：比背景熱雜訊大一倍才算有人
AREA_THRESHOLD = baseline_max_area * 2.0
```

若無法保證有空房間初始化的時機，可改用整段影片熱區面積的較低 percentile：

```python
AREA_THRESHOLD = np.percentile(all_area_values, 30)
```

---

## 6. 異常事件規則

MVP 只偵測兩個主要異常事件，第三個為選配。

---

### Event A：床上長時間異常躁動

#### 情境

夜間產婦在床上應以低活動或短暫翻身為主。若出現長時間高活動，可能代表：

- 疼痛不適
- 抽搐
- 呼吸不適
- 焦慮或恐慌
- 想求助但無法按鈴
- 產後虛弱造成反覆起身失敗

#### 觸發條件

```text
bed_occupied = true
AND motion_state = high_motion
AND high_motion_duration > 60–120 秒
→ 觸發「床上異常躁動」
```

#### 建議分級

| 條件 | 等級 | 說明 |
|---|---|---|
| 短暫高活動 < 20 秒 | 綠色 | 可能是正常翻身 |
| 高活動 > 60 秒 | 黃色 | 提醒護理師注意 |
| 高活動 > 120 秒 | 橘色 | 建議優先查看 |
| 高活動 + VLM 判斷疑似抽搐/痛苦 | 紅色或橘色高優先 | 立即確認狀況 |

---

### Event B：床外長時間靜止

#### 情境

夜間產婦離床後，如果在床外長時間不動，屬於高風險情境。可能代表：

- 跌倒
- 暈厥
- 坐倒在地
- 產後虛弱無法起身
- 在廁所或床邊無法求助

#### 觸發條件

```text
bed_occupied = false
AND person_detected = true
AND motion_state = still
AND still_duration > 30–60 秒
→ 觸發「床外長時間靜止」
```

#### 建議分級

| 條件 | 等級 | 說明 |
|---|---|---|
| 離床短時間活動 | 黃色 | 只記錄或低風險提醒 |
| 床外靜止 > 30 秒 | 橘色 | 建議優先查看 |
| 床外靜止 > 60 秒 | 紅色 | 立即前往查看 |
| 床外靜止 + VLM 判斷位於地面區域 | 紅色高優先 | 疑似跌倒或暈厥 |

---

### Event C：離床但位置未知（選配）

#### 情境

若壓力感測器顯示產婦離床，但熱成像未偵測到人體熱源，可能代表：

- 熱成像視角死角
- 產婦走到浴室
- 產婦離開可視範圍
- 熱成像偵測失敗

#### 觸發條件

```text
bed_occupied = false
AND person_detected = false
AND duration > 60–180 秒
→ 觸發「離床但位置未知」
```

#### 建議分級

| 條件 | 等級 |
|---|---|
| 離床但位置未知 > 60 秒 | 黃色 |
| 離床但位置未知 > 180 秒 | 橘色 |

---

## 7. Pseudo-code

### 7.1 主流程

```python
from collections import deque

prev_frame = None
high_motion_duration = 0
still_duration = 0
unknown_location_duration = 0

SMOOTH_WINDOW_SIZE = 30  # 依影片 fps 設定，約 1–3 秒
score_buffer = deque(maxlen=SMOOTH_WINDOW_SIZE)

for frame in thermal_video:
    gray = preprocess(frame)

    bed_occupied = read_bed_sensor_or_label()

    human_mask = detect_human_region(gray)
    person_detected = human_mask.sum() > AREA_THRESHOLD

    if prev_frame is None:
        prev_frame = gray
        continue

    # 若偵測到人體熱源，計算 movement_score；否則跳過
    if person_detected:
        diff = abs(gray - prev_frame)
        movement_score = diff[human_mask].mean()
        score_buffer.append(movement_score)

        if len(score_buffer) >= SMOOTH_WINDOW_SIZE:
            smoothed_score = sum(score_buffer) / len(score_buffer)
            motion_state = classify_motion_state(smoothed_score)
        else:
            motion_state = None  # buffer 尚未填滿，先不分類
    else:
        motion_state = None  # 無人體熱源，不計算 movement

    event = check_abnormal_event(
        bed_occupied=bed_occupied,
        person_detected=person_detected,
        motion_state=motion_state
    )

    if event is not None:
        # 重置計時器
        reset_duration_counters(event["event_type"])

        keyframes = extract_keyframes(before=10, after=10, n=5)
        vlm_result = call_vlm(keyframes, event)
        send_dashboard_alert(event, vlm_result)
        save_event_log(event, vlm_result)

    prev_frame = gray
```

---

### 7.2 事件判斷

```python
def check_abnormal_event(bed_occupied, person_detected, motion_state):
    global high_motion_duration
    global still_duration
    global unknown_location_duration

    if bed_occupied:
        still_duration = 0
        unknown_location_duration = 0

        if motion_state == "high_motion":
            high_motion_duration += dt
        else:
            high_motion_duration = 0

        if high_motion_duration > 120:
            return {
                "event_type": "床上異常躁動",
                "risk_level": "orange",
                "duration": high_motion_duration
            }

        if high_motion_duration > 60:
            return {
                "event_type": "床上高活動提醒",
                "risk_level": "yellow",
                "duration": high_motion_duration
            }

    else:
        high_motion_duration = 0

        if person_detected and motion_state == "still":
            still_duration += dt
        elif person_detected:
            still_duration = 0

        if not person_detected:
            unknown_location_duration += dt
        else:
            unknown_location_duration = 0

        # 注意：先判斷較短時間，再判斷較長時間，確保橘色警報有機會觸發
        if still_duration > 30:
            if still_duration > 60:
                return {
                    "event_type": "床外長時間靜止",
                    "risk_level": "red",
                    "duration": still_duration
                }
            return {
                "event_type": "床外靜止提醒",
                "risk_level": "orange",
                "duration": still_duration
            }

        if unknown_location_duration > 60:
            if unknown_location_duration > 180:
                return {
                    "event_type": "離床但位置未知",
                    "risk_level": "orange",
                    "duration": unknown_location_duration
                }
            return {
                "event_type": "離床位置未知提醒",
                "risk_level": "yellow",
                "duration": unknown_location_duration
            }

    return None


def reset_duration_counters(event_type):
    global high_motion_duration, still_duration, unknown_location_duration

    if "床上" in event_type:
        high_motion_duration = 0
    elif "靜止" in event_type:
        still_duration = 0
    elif "位置未知" in event_type:
        unknown_location_duration = 0
```

---

## 8. VLM 輔助判讀設計

### 8.1 VLM 介入時機

VLM 不需要持續讀取影片，只在異常規則觸發時介入。

```text
異常規則觸發
↓
擷取事件前 10 秒 + 後 10 秒熱成像片段
↓
抽取 3–5 張關鍵幀（JPEG/PNG）
  - 事件觸發前的最後一幀（還在動的狀態）
  - 事件觸發當下的幀
  - 靜止持續中間某幀
  - 事件結束後第一幀（若有）
↓
送給 VLM（base64 編碼的影像 + 結構化資料）
↓
生成事件判讀摘要
```

---

### 8.2 給 VLM 的輸入

結合結構化資料與熱成像關鍵幀，讓 VLM 判讀更穩定。

```json
{
  "room_id": "305",
  "initial_event": "床外長時間靜止",
  "risk_level": "red",
  "bed_occupied": false,
  "person_detected": true,
  "motion_state": "still",
  "stillness_duration": 62,
  "movement_score": 0.03,
  "time": "02:13",
  "keyframes": ["frame_01.jpg", "frame_02.jpg", "frame_03.jpg"]
}
```

關鍵幀以 base64 格式直接嵌入 API 請求，支援 JPEG 或 PNG，不需傳送完整影片檔案。

---

### 8.3 VLM 輸出格式

建議要求 VLM 固定輸出 JSON，方便接 dashboard。

`confidence` 欄位由系統根據事件資料計算，不由 VLM 自行判斷，以確保一致性與可解釋性。

```json
{
  "vlm_event_summary": "熱成像顯示人體熱源持續超過 60 秒未明顯移動。",
  "possible_situation": [
    "疑似跌倒",
    "疑似暈厥",
    "產後虛弱無法起身"
  ],
  "recommended_action": "建議護理人員立即前往房間查看，並評估意識狀態、生命徵象與是否需要通知醫師。",
  "confidence": "high"
}
```

**Confidence 計算規則（由系統決定，寫入 prompt）：**

```text
- stillness_duration > 90 且 movement_score < 0.02 → high
- stillness_duration 在 30–90 之間 → medium
- 其餘情況 → low
```

---

### 8.4 VLM Prompt 範例

```text
你是一個產後護理機構夜間安全監測系統的輔助判讀模組。
你會收到數張熱成像事件關鍵幀，以及系統前端感測器產生的結構化資料。

請注意：
1. 你不是醫療診斷系統，不要做疾病診斷。
2. 你只能根據熱成像與感測器資料描述可能發生的情境。
3. 請用護理站可理解的方式輸出。
4. 請固定輸出 JSON 格式，不要輸出其他文字。

輸入資料：
- room_id: {room_id}
- initial_event: {initial_event}
- risk_level: {risk_level}
- bed_occupied: {bed_occupied}
- person_detected: {person_detected}
- motion_state: {motion_state}
- duration: {duration}
- movement_score: {movement_score}
- confidence: {confidence}  ← 由系統計算後傳入

請輸出：
{
  "vlm_event_summary": "...",
  "possible_situation": ["...", "..."],
  "recommended_action": "...",
  "confidence": "{confidence}"
}
```

---

## 9. Dashboard 設計

### 9.1 技術選型

MVP demo 採用本地端 web app，建議使用 **Streamlit**：

- 開發速度快，適合 demo 週期
- 支援 `st.rerun()` 模擬即時更新
- 不需額外前後端分離

若需要外觀更接近真實護理站介面，可考慮 FastAPI + 簡單 HTML，但開發成本較高。

---

### 9.2 即時房間狀態

| 房號 | 在床狀態 | 熱成像活動狀態 | 風險 |
|---|---|---|---|
| 301 | 在床 | 低活動 | 綠 |
| 302 | 在床 | 高活動 80 秒 | 黃 |
| 305 | 離床 | 靜止 62 秒 | 紅 |
| 308 | 離床 | 正常移動 | 黃 |

---

### 9.3 警報卡片

```text
[紅色警報] 305 房

事件：床外長時間靜止
持續時間：62 秒
初步判斷：離床後床外長時間未動
VLM 判讀：熱成像顯示人體熱源長時間未明顯移動，可能為跌倒、暈厥或產後虛弱無法起身。
建議處置：立即前往房間查看，評估意識狀態與生命徵象。
```

---

### 9.4 事件紀錄表

| 時間 | 房號 | 事件 | 等級 | 處理狀態 |
|---|---|---|---|---|
| 02:13 | 305 | 床外長時間靜止 | 紅 | 待處理 |
| 01:42 | 302 | 床上異常躁動 | 橘 | 已確認 |
| 00:58 | 306 | 離床位置未知 | 黃 | 已記錄 |

---

## 10. 資料表設計

### 10.1 sensor_logs

```text
id
timestamp
room_id
bed_occupied
pressure_value
person_detected
movement_score
smoothed_movement_score
motion_state
high_motion_duration
still_duration
unknown_location_duration
thermal_centroid_x
thermal_centroid_y
thermal_area
```

---

### 10.2 events

```text
event_id
room_id
start_time
end_time
event_type
risk_level
bed_occupied
duration
movement_score
motion_state
keyframe_paths
vlm_summary
possible_situation
recommended_action
confidence
status
nurse_confirm_time
nurse_note
```

---

### 10.3 patients（選配）

```text
patient_id
room_id
risk_level
risk_tags
```

範例：

```text
risk_tags = ["剖腹產", "產後虛弱", "夜間需協助下床"]
```

---

## 11. Test Data 策略

### 11.1 熱成像影片來源

MVP 階段從網路擷取公開熱成像資料集：

```text
thermal fall detection dataset
thermal human activity recognition dataset
thermal infrared fall detection video
thermal surveillance fall detection dataset
infrared fall detection dataset
```

可用資料類型：

- 熱成像跌倒影片
- 熱成像人體活動辨識影片
- 熱紅外監控影片
- 自行拍攝熱成像測試影片

注意事項：影片的 fps 決定 `SMOOTH_WINDOW_SIZE` 的設定，取得影片後應先確認 fps。

---

### 11.2 bed_occupied 標籤

公開熱成像資料通常不會有床墊壓力資料，因此 MVP 可先用以下方式處理：

#### 方法 A：手動標記

針對每段影片標記：

```text
bed_occupied = true / false
```

#### 方法 B：模擬資料

根據影片情境建立簡單時間序列：

```csv
timestamp,bed_occupied
00:00,true
00:01,true
00:02,false
00:03,false
```

#### 方法 C：未來接實體壓力感測器

實際 prototype 階段再接壓力墊或 FSR 感測器。

---

### 11.3 Demo 場景設計

至少準備三種情境。

#### Demo 1：正常睡眠

```text
bed_occupied = true
movement_score = low
→ normal
```

目的：

> 證明正常睡覺不會誤報。

---

#### Demo 2：床上異常躁動

```text
bed_occupied = true
movement_score = high
duration > 60 秒
→ abnormal = true
→ event_type = 床上異常躁動
```

目的：

> 展示產婦在床上長時間高活動時，系統會提醒護理師。

---

#### Demo 3：床外長時間靜止

```text
bed_occupied = false
person_detected = true
movement_score = low
duration > 60 秒
→ abnormal = true
→ event_type = 床外長時間靜止
```

目的：

> 展示產婦離床後疑似跌倒、暈厥或虛弱無法起身時，系統會發出紅色警報。

---

## 12. 開發時程建議

### Week 1：資料輸入與前處理

目標：

- 從網路擷取並確認熱成像影片格式與 fps
- 可讀取熱成像影片（OpenCV VideoCapture）
- 可讀取或模擬 bed_occupied
- 將影片拆成 frame
- 建立基本資料格式與 sliding window buffer

交付：

```text
thermal_video_loader.py
bed_status_loader.py
sample bed_occupied.csv
```

---

### Week 2：movement_score 與狀態分類

目標：

- 完成人體熱區偵測與 AREA_THRESHOLD baseline 校正
- 完成 frame difference movement score
- 完成 sliding window 平滑邏輯
- 完成 still / normal_motion / high_motion 分類
- 完成 movement_score threshold 設定

交付：

```text
movement_detector.py
movement_score visualization
motion_state output json
```

---

### Week 3：異常事件偵測

目標：

- 完成床上長時間高活動規則
- 完成床外長時間靜止規則
- 完成離床位置未知規則（選配）
- 完成警報觸發後計時器重置邏輯
- 產出 event JSON

交付：

```text
event_detector.py
event_log.json
abnormal event keyframes
```

---

### Week 4：VLM 與 Dashboard

目標：

- 異常事件觸發時擷取熱成像關鍵幀（3–5 張）
- 將關鍵幀（base64）+ sensor data 丟給 VLM
- 取得 VLM 摘要（confidence 由系統計算後傳入）
- 顯示 Streamlit dashboard

交付：

```text
vlm_interpreter.py
dashboard app（Streamlit）
event summary cards
```

---

## 13. 第一版最小可行功能清單

### 必做

- 讀取熱成像影片（OpenCV）
- 讀取或模擬 bed_occupied
- Sliding window 平滑 movement_score
- 判斷 still / normal / high_motion
- 偵測床上長時間異常躁動
- 偵測床外長時間靜止
- 觸發警報後重置計時器
- 產生 abnormal / normal 結果
- 異常時擷取熱成像關鍵幀
- VLM 生成事件摘要
- Dashboard 顯示警報（Streamlit）

### 暫時不做

- 真實疾病診斷
- 完整電子病歷串接
- 真實產後護理機構部署
- 複雜深度學習模型
- 手機 App
- 產婦個人化模型
- 法規等級醫療器材宣稱
- 即時硬體串流

---

## 14. 風險與限制

### 14.1 熱成像資料不一定符合產後場域

公開資料可能不是產後護理機構，也不一定是床邊情境。因此 MVP 階段應誠實說明：

> 本階段使用公開熱成像活動資料進行流程驗證，未來需在實際產後照護場域蒐集資料進行調整與驗證。

---

### 14.2 VLM 不應作為主判斷來源

VLM 可能會受熱成像解析度、影像品質或提示詞影響，因此應定位為：

> 輔助判讀與事件摘要生成，不是主要安全判斷器。

主要異常觸發仍由下列三者負責：

- bed_occupied
- movement_score（sliding window 平滑後）
- duration rule

---

### 14.3 在床長時間靜止不應直接判斷異常

產婦晚上睡覺時長時間靜止是正常狀態。因此本系統不將「在床長時間靜止」視為異常。

本系統主要偵測：

```text
在床長時間高活動
床外長時間靜止
```

---

### 14.4 離床上廁所可能造成誤報

解法：

- 設定 grace period
- 離床後前 30 秒只記錄不警報
- 離床且正常移動不警報
- 只有床外長時間靜止才升級警報

---

### 14.5 Sliding window 在影片開頭的冷啟動問題

影片開始的前 `SMOOTH_WINDOW_SIZE` 幀，buffer 尚未填滿，motion_state 設為 `None`，系統不做異常判斷。這是正常行為，冷啟動期約為 1–3 秒，不影響整體功能。

---

## 15. 專題描述版本

本系統以床墊壓力感測器與熱成像影片作為主要輸入。床墊壓力感測器負責判斷產婦是否在床，為系統分流的唯一依據；熱成像影片則用於偵測人體熱源是否存在與人體活動量，不負責空間定位。系統於夜間依據是否在床進行分流：若產婦在床上，系統透過 sliding window 平滑後的 movement_score 監測是否出現長時間高活動量，作為疼痛不適、抽搐、躁動或求助困難的可能徵象；若產婦不在床上，系統監測是否出現床外長時間靜止，作為跌倒、暈厥或產後虛弱無法起身的高風險徵象。當異常規則被觸發時，系統重置計時器，擷取事件前後的熱成像關鍵幀，交由 VLM 輔助判讀事件情境，並產生護理站警報、事件摘要與建議處置。

---

## 16. 一句話版

> 本 MVP 透過「是否在床上」與「熱成像活動量」偵測夜間不合理狀態：在床上長時間異常躁動，或離床後床外長時間靜止；一旦觸發異常，系統會重置計時器、擷取熱成像關鍵幀交給 VLM 輔助判讀，並即時通知護理站。
