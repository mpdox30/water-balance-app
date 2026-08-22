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

  const MAX_ATTEMPTS = 6; // รวมเวลารอสูงสุด ~30 วินาที ครอบคลุม cold start ของ Render free tier ส่วนใหญ่
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
