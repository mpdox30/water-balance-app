// login.js — Phase 3: หน้า login จริง (แทน manual token workaround เดิม)

// ถ้า login ค้างอยู่แล้ว เด้งไปหน้าที่ตั้งใจไปต่อเลย (หรือ index.html)
(function redirectIfLoggedIn() {
  const auth = getAuth();
  if (auth && auth.access_token) {
    const params = new URLSearchParams(window.location.search);
    window.location.href = params.get("next") || "index.html";
  }
})();

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const errorEl = document.getElementById("error");
  const submitBtn = document.getElementById("submit-btn");
  errorEl.textContent = "";
  submitBtn.disabled = true;
  submitBtn.textContent = "กำลังเข้าสู่ระบบ...";

  try {
    const res = await fetch(BACKEND_URL + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const body = await res.json();
    if (!res.ok) {
      throw new Error(body.detail || "เข้าสู่ระบบไม่สำเร็จ");
    }
    setAuth(body);
    const params = new URLSearchParams(window.location.search);
    window.location.href = params.get("next") || "index.html";
  } catch (err) {
    errorEl.textContent = "เข้าสู่ระบบไม่สำเร็จ: " + err.message;
    submitBtn.disabled = false;
    submitBtn.textContent = "เข้าสู่ระบบ";
  }
});
