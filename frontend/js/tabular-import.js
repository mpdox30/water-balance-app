// tabular-import.js — ตัวช่วยอ่านไฟล์ Excel/CSV แบบ bulk import ใช้ร่วมกันหลายหน้า (admin-setup.html
// ขั้นตอนที่ 1 หมู่บ้าน, report.html ขั้นตอนที่ 5 พืชที่ปลูก) — ใช้ SheetJS (โหลดผ่าน CDN ในแต่ละหน้าเอง)
// แปลง .xlsx/.xls/.csv เป็น array of row object โดยแถวแรกของไฟล์เป็น header
//
// ทำไมไม่ผูก schema คอลัมน์ตายตัว: อปท./ทีมสำรวจแต่ละที่ตั้งชื่อคอลัมน์ไม่เหมือนกัน (เช่น "หมู่" vs "หมู่ที่"
// vs "moo") — findColumn()/getCell() จับคู่แบบยืดหยุ่น (ตรงเป๊ะก่อน ถ้าไม่เจอค่อย fallback เป็น contains)
// เพื่อลดโอกาสที่ไฟล์จริงจะอ่านไม่ออกเพราะแค่ชื่อหัวคอลัมน์ไม่ตรง

/** อ่านไฟล์ .xlsx/.xls/.csv คืน Promise<Array<Object>> (key = header ของคอลัมน์นั้น) — ตัดแถวว่างทั้งแถวออก */
function parseTabularFile(file) {
  return new Promise((resolve, reject) => {
    if (typeof XLSX === "undefined") {
      reject(new Error("โหลดไลบรารีอ่านไฟล์ Excel/CSV ไม่สำเร็จ (XLSX) — ลองรีเฟรชหน้าใหม่"));
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const workbook = XLSX.read(data, { type: "array" });
        const sheet = workbook.Sheets[workbook.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(sheet, { defval: null, raw: true });
        resolve(rows.filter((r) => Object.values(r).some((v) => v !== null && String(v).trim() !== "")));
      } catch (err) {
        reject(new Error("อ่านไฟล์ไม่สำเร็จ: " + err.message));
      }
    };
    reader.onerror = () => reject(new Error("อ่านไฟล์ไม่สำเร็จ"));
    reader.readAsArrayBuffer(file);
  });
}

/** หาชื่อ header จริงในแถวที่ตรง/คล้ายกับ alias ที่ให้มา (ไม่สนตัวพิมพ์เล็กใหญ่/ช่องว่างหัวท้าย)
 * ลองตรงเป๊ะก่อนทุก alias แล้วค่อย fallback เป็น "header มีคำนี้อยู่" — คืน null ถ้าไม่เจอเลย */
function findColumn(row, aliases) {
  const keys = Object.keys(row);
  for (const alias of aliases) {
    const found = keys.find((k) => k.trim() === alias);
    if (found) return found;
  }
  for (const alias of aliases) {
    const found = keys.find((k) => k.trim().includes(alias));
    if (found) return found;
  }
  return null;
}

/** ดึงค่าจากแถวตาม alias list — คืน null ถ้าหาคอลัมน์ไม่เจอหรือค่าว่าง */
function getCell(row, aliases) {
  const col = findColumn(row, aliases);
  if (!col) return null;
  const v = row[col];
  return v === null || v === undefined || String(v).trim() === "" ? null : v;
}

/** แปลงค่าจากไฟล์เป็นตัวเลข (float) หรือ null ถ้าแปลงไม่ได้/ว่าง — กันไฟล์จริงที่มีข้อความปนอยู่ในช่องตัวเลข */
function getCellNumber(row, aliases) {
  const v = getCell(row, aliases);
  if (v === null) return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}
