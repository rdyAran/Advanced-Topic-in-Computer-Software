# ต่อเพจ Facebook เข้า FloodLink (Webhook แบบเรียลไทม์)

แชทใน Messenger ของเพจ คอมเมนต์ใต้โพสต์ และโพสต์ที่คนอื่นมาโพสต์บนเพจ จะเข้าระบบเองภายในไม่กี่วินาที
AI จะแยกเคสให้ ทุกเคสเก็บ **ข้อความเต็ม ชื่อผู้โพสต์ และลิงก์กลับไปที่โพสต์/คอมเมนต์** ไว้
ถ้ามี Page token ระบบจะตอบใน Messenger ให้เอง เช่น "รับเรื่องแล้ว เคส C-xxxx" และถามข้อมูลที่ยังขาด

## 0. ทดสอบโดยยังไม่ต้องมีเพจ (ทำก่อน)
```powershell
docker compose up -d --build
python 02_api_backend/scripts/fb_simulate.py --verify     # ต้องเห็น 12345
python 02_api_backend/scripts/fb_simulate.py              # ส่งคอมเมนต์จำลอง 2 อัน + Messenger 1 อัน
```
เปิดหน้าเว็บ แล้วจะเห็นเคสใหม่ที่มาจากช่องทาง "คอมเมนต์เพจ FB" กด 📄 ข้อความต้นฉบับ เพื่อดูข้อความเต็ม

## 1. เปิดให้ Facebook ส่งข้อมูลเข้าเครื่องเราได้ (ต้องเป็น HTTPS)
Facebook ส่งข้อมูลมาที่ `localhost` ไม่ได้ ต้องเปิด tunnel ก่อน ใช้ตัวไหนก็ได้:
```powershell
cloudflared tunnel --url http://localhost:8000      # ได้ URL แบบ https://xxxx.trycloudflare.com
# หรือ  ngrok http 8000
```
URL ของ webhook คือ `https://xxxx.trycloudflare.com/webhooks/facebook`
(URL เปลี่ยนทุกครั้งที่เปิด tunnel ใหม่ ต้องกลับไปแก้ในหน้า Meta ด้วย)

## 2. สร้างเพจทดสอบและแอปใน Meta
1. สร้างเพจทดสอบ เช่น "FloodLink ทดสอบ"
2. ไปที่ https://developers.facebook.com → My Apps → Create App → เลือกแบบ Business
3. เพิ่มสมาชิกทีมเป็น **Tester หรือ Developer** ของแอป (App roles)
   ตอนแอปยังอยู่ใน **Development mode** Facebook จะส่งเหตุการณ์มาเฉพาะจากบัญชีที่มีบทบาทในแอปเท่านั้น
   ดังนั้นให้เพื่อนในทีมใช้บัญชีตัวเองคอมเมนต์หรือทักแชทเพจ (เพียงพอสำหรับเดโม ไม่ต้องส่ง App Review)
4. คัดลอก App secret (App settings → Basic) ไปใส่ `.env` ที่ `FB_APP_SECRET=`

## 3. ตั้งค่า Webhook
1. ในแอป → เพิ่ม product **Webhooks** → เลือก **Page** → Subscribe to this object
2. Callback URL: `https://xxxx.trycloudflare.com/webhooks/facebook`
   Verify token: ค่าเดียวกับ `FB_VERIFY_TOKEN` ใน `.env` → กด **Verify and save**
3. Subscribe fields: `feed` (คอมเมนต์และโพสต์) และ `messages` (Messenger)
4. ถ้าใช้ Messenger: เพิ่ม product **Messenger** → Generate token ของเพจ แล้วใส่ใน `FB_PAGE_TOKEN=`
5. ผูกเพจกับแอป (ถ้าหน้า Meta ไม่ได้ทำให้เอง):
   ```
   POST https://graph.facebook.com/v21.0/{PAGE_ID}/subscribed_apps?subscribed_fields=feed,messages&access_token={PAGE_TOKEN}
   ```
   สิทธิ์ที่ต้องมี: `pages_manage_metadata`, `pages_read_engagement`, `pages_messaging`
6. รัน `docker compose up -d --force-recreate api` เพื่อให้ระบบอ่าน `.env` ใหม่

## 4. ตรวจสอบ
- `GET http://localhost:8000/api/facebook/status` บอกว่าตั้งค่าครบหรือยัง และรับข้อความมาแล้วกี่ข้อความ
- ลองคอมเมนต์ใต้โพสต์เพจ: "ช่วยด้วย ยายติดเตียง น้ำถึงชั้น 2 คอหงส์ โทร 081..."
- ดู log ด้วย `docker compose logs -f api`

## ระบบทำอะไรให้บ้าง
| เรื่อง | ทำอย่างไร |
|---|---|
| ตอบ Facebook ให้ทันเวลา | ตอบ 200 ทันที ส่วน AI อ่านข้อความต่อในเบื้องหลัง |
| Facebook ส่งข้อความเดิมซ้ำ (retry) | กันซ้ำด้วย id ของข้อความ/คอมเมนต์ |
| ข้อความปลอมที่ไม่ได้มาจาก Facebook | ตรวจ `X-Hub-Signature-256` ด้วย App secret (**ต้องตั้ง FB_APP_SECRET ก่อนใช้จริง**) |
| ข้อความหรือคอมเมนต์ของเพจเอง | ข้ามไป ไม่สร้างเคส |
| Agent ล่ม | ข้อความต้นฉบับยังถูกเก็บไว้ ไม่หาย |
| แชทที่ไม่ใช่การขอความช่วยเหลือ เช่น ถามเรื่องบริจาค | ส่งให้แชทบอทตอบใน Messenger พร้อมลิงก์นำทาง |
| ขอข้อมูลที่ขาด | ถามเป็นการส่วนตัวทาง Messenger เท่านั้น ไม่ถามใต้คอมเมนต์สาธารณะ |

## ข้อจำกัด
- **เฟซส่วนตัวและกลุ่มต่อไม่ได้** เพราะ Facebook ไม่เปิดให้แอปอ่านโพสต์ของบุคคลทั่วไป ใช้ได้เฉพาะเพจที่เราเป็นแอดมิน
- ถ้าจะให้คนทั่วไปที่ไม่มีบทบาทในแอปใช้ได้ ต้องเปลี่ยนแอปเป็น Live mode และผ่าน App Review ของ Meta
- tunnel ฟรีจะเปลี่ยน URL ทุกครั้ง ใช้จริงควร deploy บนเซิร์ฟเวอร์ที่มีโดเมนถาวร
