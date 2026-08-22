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

/** wrapper รอบ fetch ที่ใส่ Authorization header ให้อัตโนมัติ + จัดการ token หมดอายุ (401) */
async function authFetch(path, options = {}) {
  const auth = getAuth();
  const headers = Object.assign({}, options.headers || {}, {
    "Content-Type": "application/json",
  });
  if (auth && auth.access_token) {
    headers["Authorization"] = "Bearer " + auth.access_token;
  }
  const res = await fetch(BACKEND_URL + path, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    clearAuth();
    window.location.href = "login.html?next=" + encodeURIComponent(window.location.pathname);
    throw new Error("session หมดอายุ กรุณา login ใหม่");
  }
  return res;
}

function logout() {
  clearAuth();
  window.location.href = "login.html";
}
