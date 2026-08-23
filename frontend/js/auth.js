// auth.js — จัดการ login token ร่วมกันทุกหน้า (Phase 3)
// เก็บ token ใน localStorage (ไม่ใช่ sessionStorage) เพราะ JWT อายุ 30 วัน ตั้งใจให้ไม่ต้อง
// login ถี่ (ดู backend/security.py หัวไฟล์) — หน้านี้เป็นเว็บจริงที่ deploy บน GitHub Pages
// ไม่ใช่ preview ในแชท จึงใช้ browser storage ปกติได้

const BACKEND_URL = "https://water-balance-app.onrender.com";
const AUTH_STORAGE_KEY = "wb_auth";

function getAuth() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function setAuth(auth) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
}

function clearAuth() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}

/** เรียกจากหน้าที่ต้อง login เป็น admin เท่านั้น (เช่น admin-setup.html) —
 * ถ้ายังไม่ login หรือ role ไม่ใช่ admin จะเด้งไป login.html ทันที */
function requireAdmin() {
  const auth = getAuth();
  if (!auth || !auth.access_token || auth.role !== "admin") {
    window.location.href = "login.html?next=" + encodeURIComponent(window.location.pathname);
    return null;
  }
  return auth;
}

/** เรียกจากหน้าที่ต้อง login ก่อนถึงจะใช้ได้ แต่ role อะไรก็ได้ (admin หรือ village_rep) เช่น
 * หน้ารายงานพืช/ปศุสัตว์รายเดือน (report.html, Phase 4) — สิทธิ์จริงเช็คที่ backend อีกชั้น
 * (village_rep เขียนได้แค่หมู่บ้านตัวเอง, admin เขียนได้ทุกหมู่บ้าน — ดู check_can_write_village) */
function requireAuth() {
  const auth = getAuth();
  if (!auth || !auth.access_token) {
    window.location.href = "login.html?next=" + encodeURIComponent(window.location.pathname);
    return null;
  }
  return auth;
}

/** wrapper รอบ fetch ที่ใส่ Authorization header ให้อัตโนมัติ + จัดการ token หมดอายุ (401)
 * + ลองใหม่อัตโนมัติถ้า fetch() ล้มเหลวระดับ network ("Failed to fetch") — สาเหตุที่พบบ่อยที่สุด
 * คือ backend ฟรี (Render) "หลับ" อยู่ (ไม่มีคนเรียกมา 15 นาที) request แรกหลังจากนั้นอาจโดน Render
 * edge ตอบ 502 ระหว่างที่แอปยังบูตไม่เสร็จ (ไม่มี CORS header -> browser รายงานเป็น "Failed to fetch"
 * แทนที่จะเป็น HTTP error ปกติ) จึงลองซ้ำเงียบๆ ก่อน throw จริง แทนที่จะให้ผู้ใช้ต้องกดปุ่มเองซ้ำๆ */
async function authFetch(path, options = {}) {
  const auth = getAuth();
  const headers = Object.assign({}, options.headers || {}, {
    "Content-Type": "application/json",
  });
  if (auth && auth.access_token) {
    headers["Authorization"] = "Bearer " + auth.access_token;
  }
  const fetchOptions = Object.assign({}, options, { headers });

  // MAX_ATTEMPTS = 16 (15 ช่วงรอ x 6 วินาที = ~90 วินาที บวกเวลา fetch() แต่ละครั้งเพิ่มอีก) — Render เอง
  // เตือนไว้ในหน้า dashboard ว่า free tier "can delay requests by 50 seconds or more" (เน้น "or more")
  // เจอจริงว่าบางครั้งเกิน 66 วินาทีที่เคยตั้งไว้รอบก่อน โดยเฉพาะตอน request แรกๆ ยิงพร้อมกันหลายเส้น
  // (เช่นหน้า admin-setup โหลด /tambons กับปุ่มบันทึกพร้อมกัน) แข่งกันปลุก instance เดียว
  const MAX_ATTEMPTS = 16;
  let lastErr = null;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetch(BACKEND_URL + path, fetchOptions);
      if (res.status === 401) {
        clearAuth();
        window.location.href = "login.html?next=" + encodeURIComponent(window.location.pathname);
        throw new Error("session หมดอายุ กรุณา login ใหม่");
      }
      return res;
    } catch (err) {
      if (err.message === "session หมดอายุ กรุณา login ใหม่") throw err;
      lastErr = err;
      if (attempt < MAX_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, 6000));
      }
    }
  }
  throw new Error(
    "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ (เซิร์ฟเวอร์ฟรีอาจกำลังตื่นจากโหมด sleep ใช้เวลาถึง ~1 นาที) " +
    "กรุณารอสักครู่แล้วลองกดปุ่มนี้อีกครั้ง — รายละเอียด: " + (lastErr ? lastErr.message : "ไม่ทราบสาเหตุ")
  );
}

function logout() {
  clearAuth();
  window.location.href = "login.html";
}

// Warm-up ping — ยิง GET /health ทันทีตอนโหลดหน้า (ไม่ await, ไม่บล็อกอะไร, เงียบถ้า fail) เพื่อให้
// backend ฟรี (Render) เริ่มตื่นจาก sleep ตั้งแต่ตอนเปิดหน้า แทนที่จะเริ่มนับตอนผู้ใช้กดปุ่มบันทึกจริง —
// ผู้ใช้มักใช้เวลาอ่าน/กรอกฟอร์มอย่างน้อย 30 วินาทีก่อนกดปุ่มอยู่แล้ว ช่วยซ่อน cold start latency
// (~50 วินาทีขึ้นไปตาม Render) ไปได้เกือบหมดโดยแทบไม่ต้องรอเพิ่มตอนกดปุ่มจริงเลย
fetch(BACKEND_URL + "/health").catch(() => {});
