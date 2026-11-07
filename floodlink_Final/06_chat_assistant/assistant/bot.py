"""FloodLink Assistant — chatbot agent for victims, relatives, donors and volunteers.

Flow per message:  understand (rules → LLM if unsure)  →  call a TOOL  →  build a grounded reply.
Tools: recommend_hubs · nearest shelter/distribution/medical · create case (intake AI pipeline) ·
       case status · needs by area · knowledge-base search (RAG).
Locations, phone numbers and case data in replies come ONLY from the database / KB — the LLM is used
to classify intent and to phrase KB answers from retrieved text, never to invent places.
"""
import json, re, time
from . import places as P
from .kb import KB
from .nlu import understand, R, looks_like_info

MENU = ["🆘 ขอความช่วยเหลือ", "📦 มีของจะบริจาค", "🙋 อยากเป็นอาสา", "🏠 ศูนย์พักพิงใกล้ฉัน", "🍱 ไปรับของได้ที่ไหน", "☎️ เบอร์ฉุกเฉิน"]
QUICK_TEXT = {"🆘 ขอความช่วยเหลือ": "ขอความช่วยเหลือ", "📦 มีของจะบริจาค": "มีของจะบริจาค ควรส่งที่ไหน",
              "🙋 อยากเป็นอาสา": "อยากเป็นอาสาไปช่วย", "🏠 ศูนย์พักพิงใกล้ฉัน": "ศูนย์พักพิงอยู่ที่ไหน",
              "🍱 ไปรับของได้ที่ไหน": "ไปรับของแจกได้ที่ไหน", "☎️ เบอร์ฉุกเฉิน": "เบอร์โทรฉุกเฉิน"}
EMERGENCY_LINE = "📞 **ถ้ามีคนอยู่ในอันตรายถึงชีวิตตอนนี้ โทร 1669 (การแพทย์ฉุกเฉิน) หรือ 1784 (ปภ.) ทันที**"
KB_SYSTEM = """คุณคือผู้ช่วยตอบคำถามช่วงน้ำท่วม ตอบเป็นภาษาไทยสั้น กระชับ เป็นข้อ ๆ ได้
ใช้เฉพาะข้อมูลใน CONTEXT ห้ามแต่งเบอร์โทร สถานที่ หรือข้อมูลการแพทย์เพิ่ม ถ้า CONTEXT ไม่มีคำตอบ ให้บอกว่าไม่มีข้อมูล
และแนะนำให้โทร 1784 ตอบ JSON {"answer": "..."}"""


class Assistant:
    def __init__(self, conn, intake=None, get_case=None, llm_json=None, web_url: str = "http://localhost:5173", tracker=None):
        """tracker: object with view(token) / followup(token, case_id, text) / safe(token, case_id) — the reporter's
        private tracking link, so a chat that created a case can keep adding to it, ask its status, or close it."""
        self.conn, self.intake, self.get_case, self.llm_json, self.tracker = conn, intake, get_case, llm_json, tracker
        self.web = web_url.rstrip("/")
        self.kb = KB()
        self.sessions: dict[str, dict] = {}
        P.init(conn)
        conn.executescript("CREATE TABLE IF NOT EXISTS chat_sessions (id TEXT PRIMARY KEY, data TEXT, updated_at TEXT);")

    # a chat remembers the case it created even after the API restarts (stored in the database)
    def _session(self, sid: str) -> dict:
        if sid not in self.sessions:
            r = self.conn.execute("SELECT data FROM chat_sessions WHERE id=?", (sid,)).fetchone()
            try:
                self.sessions[sid] = json.loads(r[0]) if r else {}
            except (TypeError, ValueError):
                self.sessions[sid] = {}
        return self.sessions[sid]

    def _save(self, sid: str, s: dict):
        if not s:
            return
        self.conn.execute("INSERT OR REPLACE INTO chat_sessions VALUES (?,?,datetime('now'))", (sid, json.dumps(s, ensure_ascii=False, default=list)))
        self.conn.commit()

    # ------------------------------------------------------------------ entry
    def handle(self, message: str, session_id: str = "anon", lat=None, lng=None) -> dict:
        t0 = time.time()
        text = QUICK_TEXT.get(message.strip(), message.strip())
        s = self._session(session_id)
        if lat is not None:
            s["lat"], s["lng"], s["gps"] = lat, lng, True          # real position from the 📍 button
            s["gps_new"] = [lat, lng] != list(s.get("gps_sent") or [])
            s["gps_sent"] = [lat, lng]
        nlu = understand(text, s.get("lat"), s.get("lng"), self.llm_json)
        if nlu["lat"] is not None:
            s["lat"], s["lng"], s["gps"] = nlu["lat"], nlu["lng"], True
        if nlu["area"] and nlu["lat"] is None:                        # area name only -> centroid
            s["lat"], s["lng"] = P.geocode(nlu["area"])
        # a short follow-up like "แถวคอหงส์" continues the previous question
        if s.get("pending") and nlu["intent"] in ("info", "greeting") and (nlu["area"] or lat is not None or nlu["items"]):
            nlu["intent"] = s["pending"]
            nlu["items"] = nlu["items"] or s.get("items", [])
            nlu["qty"], nlu["unit"] = nlu["qty"] or s.get("qty"), nlu["unit"] or s.get("unit")
        out = self._session_route(text, nlu, s, lat)        # this chat already made a case -> add to it / status / safe
        if out is None:
            handler = getattr(self, f"_{nlu['intent']}", self._info)
            out = handler(text, nlu, s)
        out.setdefault("quick_replies", [])
        out.update({"intent": nlu["intent"], "nlu_source": nlu["source"], "latency_ms": round((time.time() - t0) * 1000)})
        self._save(session_id, s)
        return out

    # ------------------------------------------------------------------ helpers
    def _place_card(self, p: dict, extra: list[str] | None = None) -> dict:
        lines = [x for x in [p.get("address"), f"🕘 {p['hours']}" if p.get("hours") else None,
                             f"☎ {p['contact']}" if p.get("contact") else None] if x]
        if p.get("capacity"):
            lines.append(f"🛏 ว่างประมาณ {max(p['capacity'] - (p.get('occupancy') or 0), 0)} ที่ (จาก {p['capacity']})")
        if p.get("services"):
            lines.append("บริการ: " + ", ".join(p["services"]))
        return {"kind": "place", "id": p["id"], "title": p["name"], "subtitle": p["type_th"] + (f" · ~{p['distance_km']} กม." if p.get("distance_km") is not None else ""),
                "lines": (extra or []) + lines, "nav_url": p.get("nav_url"), "page_url": f"{self.web}/?place={p['id']}",
                "tel": re.sub(r"[^\d]", "", p.get("contact") or "") or None, "is_demo": bool(p.get("is_demo"))}

    def _demo_note(self, cards):
        return "\n\n_⚠️ จุดสถานที่ในระบบตอนนี้เป็นข้อมูลตัวอย่างสำหรับเดโม_" if any(c.get("is_demo") for c in cards) else ""

    def _has_location(self, s, nlu):
        return s.get("lat") is not None or nlu["area"]

    # ------------------------------------------------------------------ the case this chat created
    def _session_route(self, text, nlu, s, lat):
        intent, tok = nlu["intent"], s.get("track")
        if not tok or self.tracker is None:
            if intent == "safe_now":
                return {"reply": "ดีใจด้วยครับ 🙏 ถ้าแจ้งเคสไว้ เปิดลิงก์ติดตามเคสแล้วกด **ทุกคนปลอดภัยแล้ว** ทีมจะได้ไปช่วยบ้านอื่นครับ "
                                 "(หรือพิมพ์เลขเคส เช่น C-1A2B3C)"}
            if intent == "my_status":
                return {"reply": "พิมพ์เลขเคส (เช่น C-1A2B3C) หรือเปิดลิงก์ติดตามเคสที่ได้ตอนแจ้งครับ จะเห็นว่าตรวจแล้ว มีทีมรับ หรือกำลังช่วย"}
            return None
        if s.pop("confirm_safe", False):
            if re.search(r"^(?:ยืนยัน|ใช่|ปลอดภัยแล้ว|ok|โอเค)", text.strip(), re.I):
                return self._do_safe(s)
            if re.search(r"ยังไม่ปลอดภัย|ไม่ใช่|ยกเลิก", text):
                return {"reply": "รับทราบครับ เคสยังเปิดอยู่ ทีมยังจะไปช่วย ถ้าสถานการณ์แย่ลงพิมพ์บอกได้เลย\n\n" + EMERGENCY_LINE}
        if intent == "safe_now":
            s["confirm_safe"] = True
            return {"reply": f"ยืนยันว่า**ทุกคนในเคส {s['cases'][0]} ปลอดภัยแล้ว** ไม่ต้องส่งทีมไปใช่ไหมครับ? (ทีมจะไปช่วยบ้านอื่นแทน)",
                    "quick_replies": ["ยืนยัน ปลอดภัยแล้ว", "ยังไม่ปลอดภัย"]}
        if intent == "my_status" or (intent == "case_status" and not nlu.get("case_id")):
            return self._my_status(s)
        if R["new_case"].search(text):
            return None                                        # another house -> a new case as usual
        adds = looks_like_info(text) or lat is not None
        answering = s.get("awaiting") and not re.search(r"\?|ยังไง|อย่างไร|ทำไง|ไหม|มั้ย|ที่ไหน|อะไร|เท่าไหร่", text)
        if intent in ("emergency", "request_help") or (intent in ("info", "greeting", None) and (adds or answering)):
            out = self._add_to_case(text, s, nlu)
            if intent == "emergency":
                out["reply"] = EMERGENCY_LINE + "\n\n" + out["reply"]
                out["links"] = [{"label": "โทร 1669", "url": "tel:1669"}, {"label": "โทร 1784", "url": "tel:1784"}]
            return out
        return None

    ASK = {"location": "📍 **บ้านอยู่ตรงไหนครับ?** กด 📍 ส่งตำแหน่ง หรือพิมพ์บ้านเลขที่ ซอย และจุดสังเกต (เช่น ตรงข้ามเซเว่น หลังวัด)",
           "contact": "☎ **เบอร์ที่ทีมโทรกลับได้คือเบอร์อะไรครับ?** (เบอร์ญาติก็ได้) แล้วแบตเหลือประมาณเท่าไหร่",
           "people": "👥 **ในบ้านมีกี่คนครับ?** มีเด็ก ผู้สูงอายุ หรือผู้ป่วยไหม",
           "water": "🌊 **ตอนนี้น้ำสูงแค่ไหนครับ?**"}
    QUICK = {"location": ["📍 ส่งตำแหน่งของฉัน"], "water": ["น้ำถึงเข่า", "น้ำถึงเอว", "น้ำถึงอก", "น้ำมิดชั้น 1", "น้ำถึงชั้น 2", "อยู่บนหลังคา"],
             "people": ["อยู่คนเดียว", "ผู้ใหญ่ 2 คน", "มีเด็กเล็กด้วย", "มีผู้สูงอายุด้วย"], "contact": []}

    def _ask_next(self, need: list[dict]) -> tuple[str, list[str]]:
        """Ask ONE question at a time — the most important missing item first."""
        if not need:
            return ("✅ **ข้อมูลสำคัญครบแล้วครับ** ทีมใช้ข้อมูลนี้ออกไปช่วยได้เลย\n"
                    "ถ้ามีอะไรเปลี่ยน (น้ำขึ้น ผู้ป่วยอาการแย่ลง ย้ายที่อยู่) พิมพ์บอกได้ตลอด หรือถามว่า \"ทีมมายัง\"", ["ทีมมายัง", "ปลอดภัยแล้ว"])
        head = f"ทีมยังต้องการอีก **{len(need)} อย่าง**: " + ", ".join(n["label"] + (" (ยังไม่ชัด)" if n["state"] == "partial" else "") for n in need)
        return head + "\n\n" + self.ASK.get(need[0]["key"], need[0]["hint"]), self.QUICK.get(need[0]["key"], [])

    def _add_to_case(self, text, s, nlu):
        cid = next((c for c in s["cases"] if c in text.upper()), s["cases"][0])
        if s.pop("gps_new", False) and nlu.get("lat") is None and not re.search(r"\d+\.\d{3,}\s*,\s*\d+\.\d{3,}", text):
            text += f" พิกัด {s['lat']:.6f}, {s['lng']:.6f}"
        try:
            out = self.tracker.followup(s["track"], cid, text)
        except Exception as e:
            return {"reply": f"เพิ่มข้อมูลไม่ได้ครับ: {e}"}
        need = [n for n in (out.get("case") or {}).get("checklist", []) if n["level"] == "need" and n["state"] != "ok"]
        s["awaiting"] = bool(need)
        ask, quick = self._ask_next(need)
        return {"reply": f"เพิ่มข้อมูลเข้า**เคส {cid}** แล้วครับ ✔\n\n" + ask, "quick_replies": quick, "case_id": cid}

    def _my_status(self, s):
        v = self.tracker.view(s["track"]) or {"cases": []}
        if not v["cases"]:
            return {"reply": "ยังไม่พบเคสจากแชทนี้ครับ"}
        lines, cards = [], []
        for c in v["cases"]:
            last = c["timeline"][-1]["text"] if c["timeline"] else c["status_th"]
            team = f"ทีมที่รับ: **{c['assigned_team']}**" if c.get("assigned_team") else "ยังไม่มีทีมรับ — ศูนย์จัดตามความเร่งด่วน เคสวิกฤตก่อน"
            need = [n for n in c["checklist"] if n["level"] == "need" and n["state"] != "ok"]
            lines.append(f"**เคส {c['id']}** — {c['status_th']}\n{team}\nล่าสุด: {last}" +
                         (f"\n⚠️ ยังขาด: {', '.join(n['label'] for n in need)} — ส่งเพิ่มจะช่วยให้ไปถึงเร็วขึ้น" if need and c["status"] != "resolved" else ""))
        track = f"{self.web}/track/{s['track']}"
        return {"reply": "\n\n".join(lines), "links": [{"label": "เปิดหน้าติดตามเคส", "url": track}], "quick_replies": ["ปลอดภัยแล้ว"]}

    def _do_safe(self, s):
        cid = s["cases"][0]
        try:
            self.tracker.safe(s["track"], cid)
        except Exception as e:
            return {"reply": f"ปิดเคสไม่ได้ครับ: {e}"}
        return {"reply": f"รับทราบครับ ปิด**เคส {cid}** แล้ว ดีใจที่ปลอดภัยครับ 🙏 ทีมจะไปช่วยบ้านอื่นต่อ\n"
                         "ถ้ายังต้องการความช่วยเหลือ พิมพ์บอกได้ตลอด", "quick_replies": MENU}

    # ------------------------------------------------------------------ intents
    def _thanks(self, text, nlu, s):
        return {"reply": "ยินดีครับ 🙏 ถ้ามีอะไรเปลี่ยนแปลง พิมพ์บอกได้ตลอด" + ("" if s.get("track") else ""),
                "quick_replies": ["ทีมมายัง", "ปลอดภัยแล้ว"] if s.get("track") else MENU}

    def _safe_now(self, text, nlu, s):
        return self._session_route(text, {**nlu, "intent": "safe_now"}, {}, None)

    def _greeting(self, text, nlu, s):
        return {"reply": "สวัสดีครับ ผมคือผู้ช่วย FloodLink 🌊\nช่วยได้ทั้ง **แจ้งขอความช่วยเหลือ** (สร้างเคสส่งถึงทีมกู้ภัย), **หาจุดส่งของบริจาค**, "
                         "**หาศูนย์พักพิง/จุดแจกของ**, **เช็กสถานะเคส** และตอบคำถามเรื่องความปลอดภัยครับ\n\n" + EMERGENCY_LINE,
                "quick_replies": MENU}

    def _donate(self, text, nlu, s):
        items = nlu["items"]
        s.update(pending="donate", items=items, qty=nlu["qty"], unit=nlu["unit"])
        if not items:
            return {"reply": "ขอบคุณที่อยากช่วยครับ 🙏 จะบริจาคอะไร ประมาณเท่าไหร่ครับ? เช่น \"น้ำดื่ม 200 แพ็ค\" หรือ \"ข้าวกล่อง 100 กล่อง\"",
                    "quick_replies": ["น้ำดื่ม", "อาหาร/ข้าวกล่อง", "นมเด็ก", "ยา", "เสื้อผ้า", "ผ้าอ้อม/ผ้าอนามัย"]}
        item = items[0]
        hubs = P.recommend_hubs(self.conn, item, s.get("lat"), s.get("lng"))
        name = P.ITEM_TH.get(item, item)
        qty = f" {nlu['qty']} {nlu['unit']}" if nlu.get("qty") else ""
        if not hubs:
            return {"reply": f"ตอนนี้ยังไม่มีจุดรับของที่รับ{name}ในระบบครับ ลองโทร 1784 เพื่อสอบถามจุดรับของในพื้นที่", "cards": []}
        cards = [self._place_card(h, ["✅ " + " · ".join(h["why"])] if h["why"] else None) for h in hubs]
        lines = [f"สำหรับ**{name}{qty}** แนะนำจุดนี้ก่อนครับ (เรียงจากจุดที่ขาด{name}มากที่สุด" + (" และใกล้คุณ" if s.get("lat") is not None else "") + "):"]
        big = (nlu.get("qty") or 0) >= 50
        if big:
            lines.append(f"\n📞 **ของจำนวนมาก ({nlu['qty']} {nlu['unit']}) กรุณาโทรนัดจุดรับก่อน** และส่งมอบให้เจ้าหน้าที่ลงชื่อรับ อย่าวางกองทิ้งไว้ — "
                         "จากเหตุการณ์จริง ของที่วางทิ้งไว้ไม่มีคนดูแลมักหายหรือแจกไม่ทั่วถึง")
        if len(items) > 1:
            lines.append(f"\n(คุณมี{', '.join(P.ITEM_TH.get(i, i) for i in items[1:])} ด้วย — พิมพ์ชื่อของนั้นเพื่อดูจุดที่ขาดได้ครับ)")
        q = [] if s.get("lat") is not None else ["📍 ส่งตำแหน่งของฉัน", "อยู่แถวคอหงส์", "อยู่แถวบ้านพรุ"]
        if s.get("lat") is None:
            lines.append("\nบอกตำแหน่งคุณ (กด 📍 หรือพิมพ์ชื่อย่าน) ผมจะเรียงจุดที่ใกล้ที่สุดให้ครับ")
        return {"reply": "\n".join(lines) + self._demo_note(cards), "cards": cards, "quick_replies": q}

    def _request_help(self, text, nlu, s):
        s["pending"] = None
        signal = R["request_help"].search(text) and (nlu["area"] or nlu["lat"] is not None or len(text) > 40)
        if not signal or self.intake is None:
            s["pending"] = "request_help"
            return {"reply": "ส่งรายละเอียดในข้อความเดียวได้เลยครับ ผมจะสร้างเคสส่งถึงทีมกู้ภัยทันที:\n"
                             "1) ตำแหน่ง (แชร์พิกัด/บ้านเลขที่ ซอย จุดสังเกต) 2) เบอร์ติดต่อ 3) จำนวนคน 4) ผู้ป่วย/ผู้สูงอายุ/เด็ก "
                             "5) ระดับน้ำ 6) สิ่งที่ต้องการ\n\n" + EMERGENCY_LINE,
                    "quick_replies": ["📍 ส่งตำแหน่งของฉัน"]}
        return self._create_cases(text, s, emergency=False)

    def _emergency(self, text, nlu, s):
        out = self._create_cases(text, s, emergency=True) if self.intake else {"reply": "", "cards": []}
        out["reply"] = EMERGENCY_LINE + "\n\n" + out["reply"]
        out["links"] = [{"label": "โทร 1669", "url": "tel:1669"}, {"label": "โทร 1784", "url": "tel:1784"}] + out.get("links", [])
        return out

    def _create_cases(self, text, s, emergency):
        if s.get("gps") and not re.search(r"\d+\.\d{3,}\s*,\s*\d+\.\d{3,}", text):
            text += f" พิกัด {s['lat']:.6f}, {s['lng']:.6f}"          # location shared via 📍 button (never an area centre)
        res = self.intake(text, "chatbot")
        results = res.get("results") or [res]
        cards, lines = [], []
        track = f"{self.web}/track/{res['track_token']}" if res.get("track_token") else None
        for r in results:
            if not r.get("case_id"):
                continue
            c = self.get_case(r["case_id"]) if self.get_case else None
            color = {"red": "🔴 แดง (วิกฤต)", "orange": "🟠 ส้ม", "yellow": "🟡 เหลือง", "green": "🟢 เขียว"}.get((c or {}).get("priority"), "")
            cards.append({"kind": "case", "id": r["case_id"], "title": f"เคส {r['case_id']} · {color}",
                          "subtitle": (c or {}).get("priority_reason", ""), "lines": [r["extraction"].get("summary") or ""],
                          "nav_url": ((c or {}).get("nav") or {}).get("url"), "page_url": track or f"{self.web}/?case={r['case_id']}"})
            if r.get("followup"):
                lines.append(r["followup"])
        n = len(cards)
        if n:
            ids = [c["id"] for c in cards]
            s["track"], s["cases"] = res.get("track_token") or s.get("track"), ids
        need = next((r.get("needs_info") for r in results if r.get("case_id") and r.get("needs_info")), None)
        ask, quick = self._ask_next(need or []) if n and self.tracker is not None else (None, [])
        s["awaiting"] = bool(n and need)
        if ask:
            lines = [ask]
        head = (f"รับเรื่องแล้วครับ สร้าง **{n} เคส** ส่งเข้าคิวทีมกู้ภัยแล้ว" + (" (เคสที่ซ้ำกับที่มีคนแจ้งไว้แล้ว ระบบรวมให้)" if any(r.get("action") == "merged" for r in results) else "")) if n else \
               "ยังสร้างเคสไม่ได้ครับ ข้อความยังไม่มีข้อมูลพอ ลองบอกตำแหน่ง จำนวนคน และสิ่งที่ต้องการ"
        tail = ("\n\n🔗 ลิงก์ติดตามเคส (เก็บไว้ อย่าแชร์ในที่สาธารณะ): " + track +
                "\nเปิดลิงก์นี้เพื่อดูสถานะ ส่งข้อมูลหรือรูปเพิ่ม หรือแจ้งว่าปลอดภัยแล้ว") if track else \
               "\n\nเก็บเลขเคสไว้ พิมพ์เลขเคสมาเมื่อไหร่ก็เช็กสถานะได้ครับ"
        out = {"reply": head + ("\n\n" + "\n\n".join(lines) if lines else "") + (tail if n else ""), "cards": cards,
               "quick_replies": quick}
        if track and n:
            out["links"] = [{"label": "เปิดหน้าติดตามเคส", "url": track}]
        return out

    def _case_status(self, text, nlu, s):
        c = self.get_case(nlu["case_id"]) if self.get_case else None
        if not c:
            return {"reply": f"ไม่พบเคส {nlu['case_id']} ครับ ตรวจเลขเคสอีกครั้ง"}
        st = {"new": "รอเจ้าหน้าที่ยืนยัน", "verified": "ยืนยันแล้ว รอทีมรับ", "assigned": f"มีทีมรับแล้ว ({c.get('assigned_team') or '-'})",
              "in_progress": f"ทีมกำลังเข้าช่วย ({c.get('assigned_team') or '-'})", "resolved": "ช่วยเหลือเสร็จแล้ว ✅"}.get(c["status"], c["status"])
        # anyone can type a case id here, so only the status is shown (no address, summary or map);
        # the reporter's private tracking link shows the full details
        card = {"kind": "case", "id": c["id"], "title": f"เคส {c['id']} · {st}", "subtitle": "",
                "lines": [f"แจ้งเข้ามา {c.get('report_count', 1)} ครั้ง · อัปเดตล่าสุด {c.get('updated_at', '')}"]}
        return {"reply": f"สถานะเคส **{c['id']}**: {st}", "cards": [card]}

    def _nearest(self, s, type_, empty_msg, intro):
        ps = P.nearest(self.conn, type_, s.get("lat"), s.get("lng"))
        if not ps:
            return {"reply": empty_msg}
        cards = [self._place_card(p) for p in ps]
        ask = "" if s.get("lat") is not None else "\n\nบอกตำแหน่ง (กด 📍 หรือพิมพ์ชื่อย่าน) เพื่อเรียงจุดที่ใกล้ที่สุดครับ"
        return {"reply": intro + ask + self._demo_note(cards), "cards": cards,
                "quick_replies": [] if s.get("lat") is not None else ["📍 ส่งตำแหน่งของฉัน"]}

    def _find_shelter(self, text, nlu, s):
        s["pending"] = "find_shelter"
        return self._nearest(s, "shelter", "ยังไม่มีข้อมูลศูนย์พักพิงในระบบครับ โทร 1784 เพื่อสอบถาม",
                             "ศูนย์พักพิงที่เปิดอยู่" + (" ใกล้คุณ" if s.get("lat") is not None else " (เรียงตามที่ว่าง)") + " ครับ ถ้าต้องการเรือไปรับ พิมพ์ตำแหน่งและจำนวนคนมาได้เลย:")

    def _find_distribution(self, text, nlu, s):
        s["pending"] = "find_distribution"
        out = self._nearest(s, "distribution", "ยังไม่มีข้อมูลจุดแจกของในระบบครับ",
                            "จุดแจกอาหาร/ถุงยังชีพ" + (" ใกล้คุณ" if s.get("lat") is not None else "") + " ครับ")
        out["reply"] += "\n\nถ้าออกจากบ้านไม่ได้ (ผู้สูงอายุ/ผู้ป่วย/น้ำสูง) พิมพ์ตำแหน่งกับสิ่งที่ต้องการมา ผมจะสร้างเคสให้ทีมนำของไปส่งครับ"
        return out

    def _find_medical(self, text, nlu, s):
        s["pending"] = "find_medical"
        out = self._nearest(s, "medical", "ยังไม่มีข้อมูลหน่วยแพทย์ในระบบครับ", "หน่วยปฐมพยาบาลที่เปิดอยู่ครับ")
        out["reply"] = EMERGENCY_LINE + "\n\n" + out["reply"]
        return out

    def _volunteer(self, text, nlu, s):
        areas = P.needs_summary(self.conn)
        lines = ["ขอบคุณมากครับ 🙏 พื้นที่ที่ยังต้องการความช่วยเหลือมากที่สุดตอนนี้ (จากเคสที่เปิดอยู่):"]
        for a in areas:
            need = ", ".join(f"{P.ITEM_TH.get(k, k)} {v}" for k, v in sorted(a["needs"].items(), key=lambda x: -x[1])[:3])
            lines.append(f"• **{a['area']}** — เคสเปิด {a['open']} (แดง {a['red']})" + (f" · ขาด {need}" if need else ""))
        if not areas:
            lines.append("• ตอนนี้ยังไม่มีเคสเปิดในระบบ")
        lines.append("\nติดต่อศูนย์ประสานงานเพื่อรับมอบหมายงาน อย่าลงพื้นที่เองถ้าไม่มีประสบการณ์/อุปกรณ์ "
                     "และอย่าจอดรถขวางทางเรือกู้ภัย ดูเคสทั้งหมดบนแผนที่ได้ที่ลิงก์ด้านล่างครับ")
        return {"reply": "\n".join(lines), "links": [{"label": "เปิดแผนที่เคส", "url": f"{self.web}/"}]}

    def _needs_overview(self, text, nlu, s):
        out = self._volunteer(text, nlu, s)
        out["reply"] = out["reply"].replace("ขอบคุณมากครับ 🙏 ", "")
        return out

    def _info(self, text, nlu, s):
        hits = self.kb.search(text, k=3)
        if not hits:
            return {"reply": "ขอโทษครับ ผมยังไม่มีข้อมูลเรื่องนี้ ลองโทร 1784 (ปภ.) หรือเลือกจากเมนูได้ครับ", "quick_replies": MENU}
        sources = [{"title": h["title"], "file": h["source"]} for h in hits]
        if self.llm_json is not None:
            try:
                ctx = "\n\n".join(f"[{h['title']}]\n{h['text']}" for h in hits)
                ans = self.llm_json(KB_SYSTEM, f"CONTEXT:\n{ctx}\n\nคำถาม: {text}").get("answer")
                if ans:
                    return {"reply": ans, "sources": sources, "answer_source": "llm+kb"}
            except Exception:
                pass
        best = self.kb.best_answer(hits)
        return {"reply": f"**{best['title']}**\n{best['text']}", "sources": sources, "answer_source": "kb"}
