# เตรียม backend ให้พร้อมต่อกับ LIFF

วันที่: 2026-10-07 · branch `develop`

เอกสารนี้สรุปทุกอย่างที่แก้ในรอบนี้ ว่าแก้อะไร ทำไมต้องแก้ และทำไมถึงเลือกวิธีนี้
แทนวิธีอื่น จุดตั้งต้นคือผล review รอบก่อน (🔴 3 ข้อ / 🟡 5 ข้อ) บวกกับสิ่งที่ต้องมี
เพิ่มเพื่อให้หน้า LIFF เรียก backend ได้จริง

---

## TL;DR

| # | เรื่อง | ระดับเดิม | ไฟล์หลัก |
|---|---|---|---|
| 1 | LINE verify ล่ม → แจ้งแอดมิน | 🔴 | `api/reports.py` |
| 2 | ใส่ channel id ผิด → แยกออกจาก "token ผิด" + แจ้งแอดมิน | 🟡 | `line/line_id_token.py`, `api/reports.py` |
| 3 | incident ใหม่ → แจ้งแอดมิน (แทนที่ระหว่างยังไม่มี `jobs`) | 🔴 | `services/reports.py` |
| 4 | test ของ dedup บน PostGIS จริง (11 เคส รวม concurrency) | 🔴 | `tests/test_reports_service.py` |
| 5 | migration แบบ nullable → backfill → NOT NULL | 🟡 | `alembic/versions/5c1a7e3b9f42_…py` |
| 6 | error 422 ผูกกับ route ไม่ใช่ path string | 🟡 | `api/reports.py` |
| 7 | ใช้ `httpx.AsyncClient` ตัวเดียวร่วมกัน | 🔵 | `line/line_id_token.py`, `api/utils_api.py` |
| 8 | **CORS** ให้ LIFF เรียกข้าม origin ได้ | ใหม่ (จำเป็นสำหรับ LIFF) | `api/utils_api.py`, `config/config.py` |
| 9 | **`GET /districts`** สำหรับ dropdown อำเภอ | ใหม่ (จำเป็นสำหรับ LIFF) | `api/districts.py`, `services/districts.py`, `schemas/district.py` |
| 10 | `.env.example` | ใหม่ | `.env.example` |

ผล test: **33 passed** เมื่อตั้ง `TEST_DATABASE_URL` (22 passed + 11 skipped ถ้าไม่ตั้ง)
smoke test บน uvicorn จริงผ่านทั้ง `/districts`, `/reports` (422 / 401 ที่ยิงไป LINE
จริง) และ CORS preflight

**สิ่งที่ต้องทำเองก่อนรันแอป:** เพิ่ม 2 key ใน `.env` (ดูหัวข้อ
[สิ่งที่ต้องทำเอง](#สิ่งที่ต้องทำเอง)) ตอนนี้แอป **boot ไม่ขึ้น** จนกว่าจะเพิ่ม

---

## 1. LINE verify ล่ม → แจ้งแอดมิน (🔴)

### ปัญหาเดิม

```python
except IdTokenVerificationUnavailableError as error:
    logger.error(...)
    raise report_error(503, ...)
```

ถ้า `api.line.me` ล่มหรือ timeout ผู้แจ้ง **ทุกคน** จะส่งฟอร์มไม่ได้ แต่สิ่งที่เกิดขึ้น
มีแค่บรรทัดหนึ่งใน log ซึ่งไม่มีใครเปิดอ่านตอนตี 3 dashboard ไม่มีอะไรขึ้นเลย

ขัดกฎเหล็กข้อ 1 ตรงๆ เพราะระบบหยุดรับแจ้งเหตุไปแล้วโดยไม่มีใครรู้

### แก้

ตอนนี้ path นี้เรียก `record_admin_alert_safely(...)` ระดับ `CRITICAL` ด้วย

### ทำไมใช้ `dedup_key` คงที่ (`"id_token_verify_unavailable"`)

ถ้า LINE ล่ม 10 นาทีแล้วมีคนพยายามส่ง 300 ครั้ง:

- **ถ้าใช้ key ต่อ request** จะได้ 300 แถวใน dashboard แอดมินจะจมอยู่ในกองแจ้งเตือน
  แล้วพลาดเรื่องอื่นที่สำคัญ
- **ใช้ key คงที่** จะได้ 1 แถว โดย `occurrence_count = 300` แอดมินเห็นทั้งว่า
  "เกิดอะไร" และ "หนักแค่ไหน"

ตรงนี้ใช้กลไกที่ `services/admin_alerts.py` ทำไว้อยู่แล้ว คือ upsert ด้วย `dedup_key`
ซึ่งจะล้าง `acknowledged_at` ทุกครั้งที่เกิดซ้ำ ผลคือถ้าแอดมินกดรับทราบไปแล้ว
แต่ปัญหากลับมาอีก alert จะ **เด้งกลับขึ้นมาเอง** ไม่ถูกฝังไว้

---

## 2. แยก "ตั้ง channel id ผิด" ออกจาก "token ผิด" (🟡)

### ปัญหาเดิม

ถ้า `LINE_LOGIN_CHANNEL_ID` ใน `.env` ไม่ตรงกับ LINE Login channel ที่ LIFF app
สังกัดอยู่ LINE จะปฏิเสธ token ทุกตัว ผู้แจ้งทุกคนจะได้ 401 แต่ log ออกมาระดับ
`warning` หน้าตาเหมือนกรณี user คนเดียวส่ง token หมดอายุทุกอย่าง

สรุปคือระบบพังทั้งระบบ แต่ดูจากภายนอกเหมือน user ทำอะไรผิดเอง

### แก้

`line/line_id_token.py` เพิ่ม exception ใหม่:

```python
class IdTokenConfigError(IdTokenVerificationUnavailableError):
```

จะ raise ใน 2 กรณี:

1. LINE ตอบ 400 และ `error_description` มีคำว่า `audience` (LINE ตอบ
   `"Invalid IdToken Audience."` เมื่อ `client_id` ที่ส่งไปไม่ตรงกับ token)
2. LINE ตอบ 200 แต่ `aud` ใน claims ไม่ตรงกับ config ตามปกติไม่ควรเกิด เพราะ LINE
   เช็คให้แล้ว แต่ถ้าเกิดขึ้นก็แปลว่า config เพี้ยน ไม่ได้แปลว่า user ผิด

`api/reports.py` จับ exception นี้แล้ว:

- log ระดับ `critical`
- สร้าง alert `id_token_config_error` (CRITICAL, key คงที่) พร้อมข้อความบอกแอดมินว่า
  ต้องไปตรวจ config ไหน
- ตอบ **503** ไม่ใช่ 401

### ทำไมตอบ 503 ไม่ใช่ 401

401 คือการบอก client ว่า "ตัวคุณผิด" ฝั่ง LIFF ก็จะบอกผู้ใช้ให้เปิดฟอร์มใหม่ ซึ่งเปิด
ใหม่กี่ครั้งก็ไม่หาย เพราะต้นเหตุอยู่ที่ server ส่วน 503 แปลว่า "server มีปัญหา" ซึ่ง
ตรงกับความจริงมากกว่า

### ทำไมให้เป็น subclass ของ `IdTokenVerificationUnavailableError`

ถ้ามีโค้ดที่อื่นจับแค่ `IdTokenVerificationUnavailableError` โค้ดนั้นก็ยังจับ config
error ได้ด้วย (fail ไปทางปลอดภัย) แต่ใน `api/reports.py` ต้องวาง `except
IdTokenConfigError` **ไว้ก่อน** `except IdTokenVerificationUnavailableError` ไม่งั้น
ตัวแม่จะดักไปก่อน ลองสลับลำดับดูแล้วรัน test จะเห็นว่าพัง

### Trade-off ที่ยอมรับ

คนที่ปลอม token มาจาก channel อื่นจะทำให้เกิด alert `id_token_config_error` ได้
แต่เพราะ key คงที่ มันจะแค่เพิ่ม `occurrence_count` ไม่ได้ทำให้ dashboard ท่วม
และกฎของโปรเจกต์คือ "แจ้งเกิน ดีกว่าเงียบ"

---

## 3. incident ใหม่ต้องมีคนรู้ (🔴)

### ปัญหาเดิม

`submit_report` สร้าง `Incident` แล้วก็จบตรงนั้น ยังไม่มีตาราง `jobs` ก็เลยยังไม่ส่ง
Flex หาจิตอาสา ผู้แจ้งเห็นข้อความ "ได้รับแจ้งเหตุแล้ว" **แต่ไม่มีมนุษย์คนไหนรับรู้เลย**

ถ้าเอา LIFF ขึ้นไปทดสอบกับคนจริงในสภาพนี้ จะเป็นความล้มเหลวแบบเงียบที่อันตรายที่สุด
ในระบบ

### แก้

`services/reports.py` เมื่อ outcome เป็น `NEW_INCIDENT` จะสร้าง admin alert:

- `alert_type = "incident_needs_dispatch"`, ระดับ `CRITICAL`
- ข้อความ: "ระบบยังไม่ส่งหาจิตอาสาอัตโนมัติ กรุณาประสานจิตอาสาเอง"
- payload มี `incident_id`, `report_id`, `district_code`, `lat`, `lon` ให้แอดมินโทรประสานได้ทันที
- `dedup_key = "incident_needs_dispatch:{incident_id}"` แยกตัวต่อ incident

### ทำไมเรียก `record_admin_alert` (ใน transaction เดียวกัน) ไม่ใช่ `record_admin_alert_safely`

นี่คือจุดที่สำคัญที่สุดของรอบนี้ ลองคิดสองทาง:

- **แยก transaction (`_safely`)**: incident commit แล้ว แต่ alert insert ไม่ผ่าน
  (DB สะดุด) จะได้ incident ที่ไม่มีใครรู้ ซึ่งก็คือสถานะเดิมที่เรากำลังแก้อยู่
- **transaction เดียวกัน**: ได้ทั้งสองอย่างหรือไม่ได้อะไรเลย ถ้า alert พัง incident
  ก็ rollback ด้วย แล้ว `api/reports.py` จะตอบ 500 พร้อมเบอร์ 1362 ผู้แจ้งรู้ว่าต้อง
  โทร และ path 500 ก็พยายามบันทึก alert `report_submit_failed` อีกชั้น

ต้องเลือกระหว่าง "incident ที่ไม่มีใครเห็น" กับ "ผู้แจ้งรู้ว่าส่งไม่สำเร็จ" ซึ่งอย่างหลัง
ปลอดภัยกว่าเสมอ

> **โยงไปเรื่อง `jobs`:** ตอนทำตาราง `jobs` ให้ใช้เหตุผลเดียวกันนี้ คือ insert job
> dispatch ต้องอยู่ใน transaction เดียวกับ insert incident (นี่คือ pattern ที่เรียกว่า
> *transactional outbox*)

### ⚠️ ของชั่วคราว ต้องลบเมื่อมี dispatch จริง

พอมี job ส่ง Flex หาจิตอาสาแล้ว ให้เอา alert นี้ออก ไม่งั้นแอดมินจะได้ alert ทุกเหตุ
แล้วเกิด alert fatigue ฝั่งแอดมินเอง ใน SKILLS.md ข้อ 10 จดไว้แล้ว

ส่วน `MERGED` (ผูกเข้า incident ที่ active อยู่) **ไม่มี alert** เพราะ incident นั้น
มี alert อยู่แล้วตั้งแต่ตอนถูกสร้าง

---

## 4. test ของ dedup บน PostGIS จริง (🔴)

### ปัญหาเดิม

test เดิม 15 ตัว mock `submit_report` ทิ้งทั้งหมด ทำให้ logic ที่สำคัญที่สุดของระบบ
(dedup, time window, lock) ไม่เคยถูกพิสูจน์เลย

### ทำไมต้องใช้ DB จริง ไม่ mock

logic อยู่ใน SQL ทั้งหมด (`ST_DWithin`, `pg_advisory_xact_lock`, `ON CONFLICT`)
ถ้า mock session ก็เท่ากับไปเทสต์ mock ไม่ได้เทสต์โค้ดจริง บั๊กแบบ "ใส่ lon/lat สลับกัน"
หรือ "radius เป็นองศาไม่ใช่เมตร" จะไม่มีวันเจอ

### ไฟล์: `tests/test_reports_service.py`

| test | พิสูจน์อะไร |
|---|---|
| `test_first_report_creates_incident_and_alerts_admin` | เหตุใหม่ → incident + alert + `report_count` + event `incident_created` |
| `test_report_within_radius_merges` | 950 ม. → merge เข้า incident เดิม และ **ไม่มี** alert ซ้ำ |
| `test_report_outside_radius_creates_new_incident` | 1,100 ม. → เหตุใหม่ |
| `test_same_client_request_id_is_idempotent` | กดส่งซ้ำ → report เดียว, `report_count` ไม่บวกซ้ำ |
| `test_recently_closed_incident_is_merged_and_alerted` | ปิดไป 5:59 ชม. → ผูกเข้าเดิม + alert + **สถานะยังเป็น CLOSED** (ไม่ reopen เอง) |
| `test_incident_closed_beyond_window_is_new_incident` | ปิดไป 6:01 ชม. → เหตุใหม่ (rekindle) |
| `test_active_incident_preferred_over_closer_closed_one` | มี closed อยู่ที่จุดเดียวกันพอดี กับ active ห่าง 500 ม. → ต้องเลือก active |
| `test_false_alarm_incident_is_not_matched` | `FALSE_ALARM` ไม่ถูกใช้ dedup |
| `test_unknown_district_rolls_back` | อำเภอไม่มีจริง → ไม่มี report ค้างใน DB |
| `test_blocked_reporter_is_rejected` | user ถูก block → raise และไม่มี report |
| `test_concurrent_reports_at_same_spot_create_one_incident` | 5 คนส่งจุดเดียวกัน **พร้อมกัน** → incident เดียว, NEW 1 + MERGED 4 |

### เคสขอบ: ทำไมเลือก 950/1100 และ 5:59/6:01

test ที่ดีต้องอยู่ **ติดขอบ** ทั้งสองฝั่ง ถ้าเทสต์ 100 ม. กับ 5 กม. แล้วมีคนเผลอ
แก้ radius เป็น 2 กม. test ก็ยังผ่าน แต่ 950/1100 จะพังทันที

ที่ไม่ใช้ 999/1001 เพราะแปลงองศาเป็นเมตรแบบประมาณ (`1/110_700` องศาต่อเมตร)
ซึ่งคลาดได้ระดับหลายเมตร ถ้าใช้ 999/1001 test จะ flaky

### test concurrency พิสูจน์ได้จริงไหม

ผมลองปิด `acquire_dedup_lock` (monkeypatch ใน process ไม่ได้แก้ไฟล์) แล้วรัน test นี้
**มันพัง** คือได้หลาย incident ที่จุดเดียวกัน แปลว่า test จับบั๊ก race ได้จริง ไม่ได้
ผ่านเพราะโชค ถ้าวันหนึ่งมีคนลบ lock ออก test นี้จะเตือน

### ออกแบบ fixture

- **skip ถ้าไม่ตั้ง `TEST_DATABASE_URL`** เพื่อให้ `pytest` เฉยๆ ยังรันผ่านบนเครื่องที่
  ไม่มี DB และ test ฝั่ง API ยังใช้งานได้
- **DB แยก (`paifahsai_test`)** เพราะ fixture ทำ `drop_all` / `TRUNCATE` ถ้าชี้ไป
  `gis` (dev) ข้อมูล dev จะหายหมด ผมสร้าง DB นี้ใน container `postgis` ให้แล้ว
- **สร้าง schema ด้วย `Base.metadata.create_all`** ไม่ใช่ alembic เพราะเร็วกว่าและไม่ต้อง
  พึ่ง `env.py` (ที่อ่าน `settings`) แลกกับข้อเสียคือถ้า migration กับ model ไม่ตรงกัน
  test จะไม่จับ
- **`NullPool`** เพราะ anyio สร้าง event loop ใหม่ต่อ test ถ้าใช้ pool connection
  จะถูกผูกกับ loop เก่าแล้ว error ว่า "attached to a different loop"
- **`now` ถูกส่งเข้า `submit_report`** ซึ่งเป็นการออกแบบที่ดีมาตั้งแต่ก่อนหน้านี้ ทำให้
  test เวลา 5:59 / 6:01 ได้โดยไม่ต้อง freeze clock

### วิธีรัน

```bash
TEST_DATABASE_URL="postgresql+psycopg://<user>:<pass>@127.0.0.1:5432/paifahsai_test" \
  uv run pytest
```

(container `postgis` ต้องรันอยู่ ผมเปิด OrbStack ให้แล้วในรอบนี้)

---

## 5. Migration `client_request_id` (🟡)

### ปัญหาเดิม

```python
op.add_column("reports", sa.Column("client_request_id", sa.Uuid(), nullable=False))
```

ถ้าตาราง `reports` มีแถวอยู่แล้ว Postgres จะไม่ยอม เพราะไม่รู้ว่าจะเติมค่าอะไรให้แถวเก่า
แล้ว migration ก็พัง ที่ dev ไม่เจอเพราะตารางว่าง

### แก้ด้วย pattern 3 ขั้น

1. `add_column(..., nullable=True)`
2. `UPDATE reports SET client_request_id = gen_random_uuid() WHERE ... IS NULL`
3. `alter_column(..., nullable=False)` แล้วค่อยสร้าง unique constraint

`gen_random_uuid()` มีให้ใช้ใน Postgres ตั้งแต่เวอร์ชัน 13 ไม่ต้องลง extension เพิ่ม

แถวเก่าจะได้ uuid แบบสุ่ม ซึ่งไม่ชนกับของจริงแน่นอน เพราะ uuid ใหม่จาก client ก็สุ่ม
เหมือนกัน

### สถานะ DB

migration นี้ **ยังไม่เคยถูก apply** (dev DB อยู่ที่ `8e2f4c6a1d09`) จึงแก้ไฟล์เดิมได้
เลยไม่ต้องสร้าง revision ใหม่ ผม `alembic upgrade head` บน dev DB ให้แล้ว ตอนนี้อยู่ที่
`5c1a7e3b9f42 (head)`

> **กฎ:** migration ที่ apply ไปแล้ว (โดยเฉพาะบนเครื่องคนอื่นหรือ production)
> **ห้ามแก้ไฟล์เดิม** ให้สร้าง revision ใหม่เสมอ รอบนี้แก้ได้เพราะยังไม่มีใคร apply

---

## 6. error 422 ผูกกับ route ไม่ใช่ path string (🟡)

### ปัญหาเดิม

```python
async def validation_error_handler(request, error):
    if request.url.path != REPORTS_PATH:
        return await request_validation_exception_handler(request, error)
```

handler ตัวนี้เป็นแบบ global แล้วไปเช็ค path ด้วย string ซึ่งพังได้ทันทีถ้ามี:

- prefix เช่น `app.include_router(router, prefix="/api")`
- `root_path` ตอนอยู่หลัง reverse proxy
- trailing slash

และเวลาพัง **ไม่มี error อะไรเลย** แค่ข้อความ 1362 หายไปจาก response 422 เฉยๆ
นี่ก็เป็นความล้มเหลวแบบเงียบเหมือนกัน

### แก้

ใช้ custom `APIRoute` (pattern ที่ FastAPI แนะนำในเอกสาร):

```python
class EmergencyNoticeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                ...
        return handle

router = APIRouter(route_class=EmergencyNoticeRoute)
```

ตอนนี้ทุก route ใน router นี้ได้ข้อความ 1362 เสมอ ไม่ว่าจะ mount ที่ path ไหน และ
route อื่นนอก router ก็ไม่ได้รับผลกระทบ จึงลบ `app.add_exception_handler(...)` ออกจาก
`api/utils_api.py`

เพิ่ม test `test_malformed_json_returns_422_with_emergency_phone` ด้วย คือ body ที่ไม่ใช่
JSON (เช่น LIFF ส่งผิด) ก็ยังต้องได้ 1362

refactor ไปพร้อมกัน: ดึง `emergency_detail()` ออกมาใช้ร่วมกันระหว่าง `report_error`
กับ handler 422 ก่อนหน้านี้มีสองที่ที่ประกอบข้อความ 1362 แยกกันเอง พอมีสองที่ก็มีโอกาส
ที่วันหนึ่งที่ใดที่หนึ่งจะลืม

---

## 7. `httpx.AsyncClient` ตัวเดียว (🔵)

### ปัญหาเดิม

`async with httpx.AsyncClient(...)` ในทุก request ทำให้ต้องเปิด TCP + TLS handshake
ไป `api.line.me` ใหม่ทุกครั้ง ช้าลงราว 100–300 ms ต่อการแจ้งเหตุ และไม่ได้ใช้ connection
pool เลย

### แก้

- singleton แบบ lazy ผ่าน `get_http_client()` (pattern เดียวกับ `line/line_client.py`)
- `close_id_token_client()` ถูกเรียกใน `lifespan` ตอน shutdown ไม่งั้นจะได้ warning
  เรื่อง connection ค้าง
- test เปลี่ยนจาก monkeypatch `httpx.AsyncClient` มาเป็น monkeypatch `_http_client`
  แทน ตรงกว่าเดิมและไม่ไปยุ่งกับ `httpx` ทั้ง module

เพิ่ม test `test_sends_configured_channel_id` เพื่อพิสูจน์ว่าส่ง `client_id` ไปจริง
ถ้าวันหนึ่งไม่ส่ง LINE จะไม่เช็ค audience ให้ แล้ว token ที่มาจาก channel อื่นก็ผ่านได้

---

## 8. CORS (ใหม่ จำเป็นสำหรับ LIFF)

### ทำไมต้องมี

LIFF คือหน้าเว็บ (React + Vite) ที่ host อยู่คนละ origin กับ backend เช่น
`https://liff.xxx.trycloudflare.com` เรียกไปที่ `https://api.xxx...` และเพราะ request
มี header `Authorization` browser จะยิง **preflight `OPTIONS`** ก่อนเสมอ

ถ้าไม่มี CORS middleware preflight จะได้ 405 หรือ 400 แล้ว browser จะบล็อก POST จริง
ทิ้งไป **ฝั่ง backend ไม่เห็น request นั้นเลย ไม่มี log ไม่มี alert** ผู้แจ้งเห็นแค่
"ส่งไม่สำเร็จ" ถ้าไม่มีส่วนนี้ ต่อ LIFF ไม่ได้

### config

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.LIFF_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)
```

ทำไมตั้งค่าแบบนี้:

- **origin มาจาก `.env` (required ไม่มี default)** ตามที่ตกลงไว้ว่าค่าที่ขึ้นกับ
  environment ต้องอยู่ใน `.env` และถ้าลืมตั้ง แอปจะไม่ยอม boot ซึ่งดีกว่า boot ขึ้นมาแล้ว
  LIFF เรียกไม่ได้แบบเงียบๆ
- **ไม่ใช้ `["*"]`** เพราะจะทำให้เว็บไหนก็ได้เรียก API นี้จาก browser ของผู้ใช้ได้
- **`allow_credentials=False`** เพราะเรายืนยันตัวตนด้วย Bearer ID token ใน header
  ไม่ได้ใช้ cookie (cookie จะใช้ฝั่ง admin dashboard ซึ่งเป็นอีกเรื่อง)
- **method / header จำกัดเท่าที่ใช้** ตามหลัก least privilege

test: `test_cors_preflight_allows_liff_origin` กับ `test_cors_preflight_rejects_unknown_origin`

---

## 9. `GET /districts` (ใหม่ จำเป็นสำหรับ LIFF)

### ทำไมต้องมี

`POST /reports` บังคับให้ส่ง `district_code` (ตามที่ตัดสินใจไว้ว่าใช้ dropdown
เพราะยังไม่มี polygon อำเภอ) แต่ก่อนหน้านี้ LIFF ไม่มีทางรู้ว่ามีอำเภออะไรให้เลือกบ้าง

ถ้า hardcode รายชื่อไว้ใน LIFF วันที่แอดมินเพิ่มอำเภอใหม่ใน DB หน้า LIFF จะไม่อัปเดต
หรือที่แย่กว่าคือ LIFF มีอำเภอที่ DB ไม่มี ผู้แจ้งเลือกแล้วจะได้ 422 ตอนกดส่ง ซึ่งเป็น
จังหวะที่แย่ที่สุดที่จะเจอ error

### โครงสร้าง (แยกชั้นตามข้อ 5 ของ SKILLS)

- `services/districts.py` → `list_districts(session)` เป็น pure SQLAlchemy ไม่รู้จัก FastAPI
- `schemas/district.py` → `DistrictResponse` (`from_attributes=True` เพื่อแปลงจาก ORM ได้)
- `api/districts.py` → route บางๆ

response:

```json
[{"code": "5803", "name_th": "ปาย", "province_name_th": "แม่ฮ่องสอน"}]
```

endpoint นี้ **ไม่ต้องใช้ token** เพราะรายชื่ออำเภอเป็นข้อมูลสาธารณะ และ LIFF ต้อง
โหลดได้ทันทีที่เปิดฟอร์ม ไม่ควรต้องรอ `liff.init()` เสร็จก่อน

---

## 10. `.env.example`

รวมทุก key ที่ `config/config.py` ต้องใช้ โดยไม่ใส่ค่าลับ และ `.gitignore` มี
`!.env.example` อยู่แล้ว จึง commit ได้

ทำไมต้องมี: ตอนนี้แอป boot ไม่ขึ้นเพราะ `LINE_LOGIN_CHANNEL_ID` ไม่อยู่ใน `.env`
ทั้งที่ config บังคับไว้ ถ้ามี `.env.example` ให้เทียบ จะรู้ทันทีว่าขาดอะไร

---

## สิ่งที่ต้องทำเอง

### 1. เพิ่มใน `.env`

```env
LINE_LOGIN_CHANNEL_ID=<Channel ID ของ LINE Login channel ที่ LIFF app อยู่>
LIFF_ALLOWED_ORIGINS=["http://localhost:5173","https://<โดเมน LIFF ของคุณ>"]
```

- `LINE_LOGIN_CHANNEL_ID` ต้องเป็นของ **LINE Login channel** (ที่สร้าง LIFF app)
  **ไม่ใช่** Messaging API channel ถ้าใส่ผิด ทุกคนจะได้ 503 และ alert
  `id_token_config_error` จะขึ้น
- `LIFF_ALLOWED_ORIGINS` เป็น JSON list ต้องใช้ `"` (double quote) และต้องไม่มี
  `/` ปิดท้าย origin

### 2. ใน LINE Developers Console

- LIFF app → **Scopes ต้องติ๊ก `openid`** (และ `profile` ถ้าอยากได้ display name)
  ถ้าไม่ติ๊ก `liff.getIDToken()` จะคืน `null`
- Endpoint URL ของ LIFF = โดเมนเดียวกับที่ใส่ใน `LIFF_ALLOWED_ORIGINS`

### 3. commit

ตอนนี้มีไฟล์ใหม่และไฟล์ที่ยังไม่ commit เยอะ ควร commit ก่อนเริ่มเรื่อง `jobs`

---

## Contract สำหรับฝั่ง LIFF

### `GET /districts`

ไม่ต้องใช้ auth คืน list ของ `{code, name_th, province_name_th}`

### `POST /reports`

```http
POST /reports
Authorization: Bearer <liff.getIDToken()>
Content-Type: application/json

{
  "client_request_id": "<uuid v4 — สร้างครั้งเดียวตอนเปิดฟอร์ม>",
  "latitude": 19.36,
  "longitude": 98.44,
  "district_code": "5803",
  "description": "เห็นควันบนดอย"
}
```

ข้อควรระวังฝั่ง LIFF:

- **`client_request_id` สร้างครั้งเดียวต่อการแจ้ง 1 ครั้ง** (เช่นตอนเปิดฟอร์ม) แล้ว
  ใช้ค่าเดิมทุกครั้งที่กด retry ถ้าสร้างใหม่ทุกครั้งที่กดส่ง การกันส่งซ้ำจะไม่ทำงาน
  (`crypto.randomUUID()`)
- **ส่ง ID token ไม่ใช่ access token และไม่ใช่ `userId`** เพราะ backend ไม่เชื่อ
  userId ที่ client ส่งมา
- ID token หมดอายุได้ ถ้าได้ 401 ให้เรียก `liff.getIDToken()` ใหม่ (หรือ
  `liff.login()`) ก่อน retry
- พิกัดมาจาก **หมุดที่ผู้ใช้ปักบนแผนที่** ไม่ใช่ GPS ดิบ
- ต้องอยู่ในกรอบประเทศไทย (lat 5.5–20.5, lon 97.3–105.7) ไม่งั้นได้ 422

### Response

ทุก response **รวมถึง error ทุกตัว** มี `message` (ข้อความภาษาไทยที่มีเบอร์ 1362
อยู่ในนั้นแล้ว) และ `emergency_phone: "1362"` ฝั่ง LIFF ควร **แสดง `message` ตรงๆ**
ไม่ต้องแต่งข้อความใหม่ เพื่อไม่ให้เบอร์ 1362 หลุดหายไป

| status | ตำแหน่ง message | ความหมาย | LIFF ควรทำ |
|---|---|---|---|
| 200 | `body.message` | สำเร็จ (`outcome`: `new_incident` / `merged` / `merged_recently_closed` / `duplicate_request`) | แสดงข้อความ ปิดฟอร์ม |
| 401 | `body.detail.message` | token ไม่ผ่าน | ขอ token ใหม่แล้ว retry ด้วย `client_request_id` **เดิม** |
| 403 | `body.detail.message` | ผู้ใช้ถูกระงับ | แสดงข้อความ (มี 1362) |
| 422 | `body.detail.message` (+ `errors`) | ข้อมูลผิด / อำเภอไม่มีจริง / JSON พัง | ให้แก้ฟอร์ม |
| 500 / 503 | `body.detail.message` | ฝั่ง server หรือ LINE มีปัญหา (แอดมินได้ alert แล้ว) | ปุ่ม retry ด้วย `client_request_id` **เดิม** + เน้นเบอร์ 1362 |

---

## สิ่งที่ **ยังไม่ได้ทำ** (ตั้งใจไม่ทำในรอบนี้)

| เรื่อง | ทำไมยังไม่ทำ |
|---|---|
| ตาราง `jobs` + ส่ง Flex หาจิตอาสา | เป็นงานถัดไปและงานใหญ่ ตอนนี้ใช้ alert `incident_needs_dispatch` แทนไปก่อน |
| อัปโหลดรูปจาก LIFF | ต้องตัดสินใจเรื่องที่เก็บไฟล์ ขนาด และชนิดไฟล์ก่อน ซึ่งเป็นการตัดสินใจเชิงออกแบบ ไม่ใช่การแก้บั๊ก `image_path` ยังเป็น null |
| rate limit | อยู่ใน MVP แต่ไม่ได้บล็อกการต่อ LIFF ควรทำก่อนเปิดให้คนทั่วไปใช้ |
| ผู้ใช้ที่ถูก block ได้ 403 | **ยังไม่ได้ตอบคำถามจาก review รอบก่อน** ว่าควรรับไว้แล้ว flag รอตรวจแทนหรือไม่ เป็นการตัดสินใจเชิงนโยบาย จึงคงพฤติกรรมเดิมไว้ |
| advisory lock ตัวเดียวทั้งประเทศ | ยอมรับได้สำหรับ MVP (ดูเหตุผลใน review) |
| `alembic check` แสดงตาราง tiger/topology | `include_object` ใน `alembic/env.py` กรองด้วย `obj.schema` แต่ตอน reflect ตารางเหล่านี้มี `schema=None` (เพราะอยู่ใน `search_path`) เป็นปัญหาที่มีอยู่ก่อนแล้ว ไม่กระทบ migration ที่เขียนเอง แต่ระวังเวลาใช้ `--autogenerate` อย่าให้มันสร้าง `drop_table` ของ PostGIS |
| webhook ยังใช้ `BackgroundTasks` / ยังไม่มี idempotency ด้วย `webhookEventId` | ไม่เกี่ยวกับ LIFF จะแก้พร้อมกับ `jobs` |

---

## ไฟล์ที่แตะในรอบนี้

**แก้:**
- `line/line_id_token.py` — shared client, `IdTokenConfigError`, `read_error_description`
- `api/reports.py` — alert ตอน verify ล่มหรือ config ผิด, `EmergencyNoticeRoute`, `emergency_detail`
- `api/utils_api.py` — CORS, router districts, ปิด http client ใน lifespan, ลบ global 422 handler
- `config/config.py` — `LIFF_ALLOWED_ORIGINS`
- `services/reports.py` — alert `incident_needs_dispatch`
- `alembic/versions/5c1a7e3b9f42_add_reports_client_request_id.py` — 3-step migration
- `tests/conftest.py` — env `LIFF_ALLOWED_ORIGINS`
- `tests/test_line_id_token.py` — ใช้ shared client + test audience และ client_id
- `tests/test_reports_api.py` — test 503 + alert, JSON พัง, CORS
- `SKILLS.md` ข้อ 10 — อัปเดตสถานะ

**ใหม่:**
- `api/districts.py`, `services/districts.py`, `schemas/district.py`
- `tests/test_reports_service.py`
- `.env.example`
- `docs/liff-readiness.md` (ไฟล์นี้)

**นอก repo:**
- เปิด OrbStack และสร้าง DB `paifahsai_test` ใน container `postgis`
- `alembic upgrade head` บน dev DB `gis` → `5c1a7e3b9f42`
