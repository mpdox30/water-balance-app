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

/** อ่านไฟล์ .xlsx/.xls/.csv คืน Promise<Array<Array<any>>> (raw rows ของ "แผ่นงานแรก" เท่านั้น, ไม่สมมติว่า
 * แถวแรกเป็น header) — ใช้กับตารางแบบ "1 แถวต่อ 1 หมู่บ้าน หลายคอลัมน์ = พืชแต่ละชนิด" ที่มักมีแถวหัวเรื่อง/
 * หมายเหตุปนอยู่ก่อนแถวหัวตารางจริง ต่างจาก parseTabularFile() ที่ตัดสินใจแทนผู้ใช้ว่าแถวแรกคือ header เสมอ
 * — ที่นี่ให้ผู้ใช้เลือกแถว header เองจาก preview (ไฟล์ที่มีหลายแผ่นงาน ให้ใช้ parseWorkbookAllSheetsAOA แทน) */
function parseTabularFileAOA(file) {
  return parseWorkbookAllSheetsAOA(file).then((wb) => wb.sheetsAOA[wb.sheetNames[0]]);
}

/** อ่านไฟล์ .xlsx/.xls/.csv ทุกแผ่นงานพร้อมกัน คืน Promise<{sheetNames: string[], sheetsAOA: {name: AOA}}>
 * — ไฟล์จริงมักมีหลายแผ่นงาน (เช่น "ข้อมูลดิบ" แบบ 1 แถวต่อ 1 รายการ ปนอยู่กับ "สรุป...รายหมู่บ้าน" แบบ
 * pivot ที่ใช้ import จริงได้) เลือกแผ่นงานแรกที่โหลดมาให้ผิดจะได้ column mapping ที่ไม่มีความหมายเลย
 * จึงต้องให้ผู้ใช้เลือกแผ่นงานเองแทนที่จะเดา sheet[0] เสมอ */
function parseWorkbookAllSheetsAOA(file) {
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
        const sheetsAOA = {};
        workbook.SheetNames.forEach((name) => {
          sheetsAOA[name] = XLSX.utils.sheet_to_json(workbook.Sheets[name], {
            header: 1,
            defval: null,
            raw: true,
            blankrows: false,
          });
        });
        resolve({ sheetNames: workbook.SheetNames, sheetsAOA });
      } catch (err) {
        reject(new Error("อ่านไฟล์ไม่สำเร็จ: " + err.message));
      }
    };
    reader.onerror = () => reject(new Error("อ่านไฟล์ไม่สำเร็จ"));
    reader.readAsArrayBuffer(file);
  });
}

/** เดาแถวที่เป็น header จริงจาก AOA — หาแถวแรกที่มีเซลล์ "ตรงเป๊ะ" กับคำว่า "หมู่ที่"/"หมู่"/"moo"/"village"
 * ก่อน (กันไม่ให้ไปจับแถวหมายเหตุ/คำอธิบายที่บังเอิญมีคำว่า "หมู่บ้าน" ปนอยู่ในประโยคยาวๆ) ถ้าไม่เจอเลยค่อย
 * fallback เป็นแถวแรกที่มีอย่างน้อย 3 เซลล์ไม่ว่างและมีคำว่า "หมู่" ปนอยู่ (แถวหัวตารางจริงมักมีหลายคอลัมน์
 * ต่างจากแถวหมายเหตุที่มักมีข้อความยาวอยู่เซลล์เดียว) — คืน index (0-based) หรือ 0 ถ้าเดาไม่ได้เลย
 * (ให้ผู้ใช้เลือกเองจาก dropdown แทน ไม่ block การทำงานต่อ) */
function guessHeaderRowIndex(aoa) {
  const exactKeywords = ["หมู่ที่", "หมู่", "moo", "village"];
  const maxScan = Math.min(aoa.length, 15);
  for (let i = 0; i < maxScan; i++) {
    const row = aoa[i] || [];
    const hit = row.some((cell) => {
      if (cell === null || cell === undefined) return false;
      const s = String(cell).trim().toLowerCase();
      return exactKeywords.some((k) => s === k.toLowerCase());
    });
    if (hit) return i;
  }
  for (let i = 0; i < maxScan; i++) {
    const row = aoa[i] || [];
    const nonEmptyCount = row.filter((c) => c !== null && c !== undefined && String(c).trim() !== "").length;
    if (nonEmptyCount < 3) continue;
    const hit = row.some((cell) => cell !== null && cell !== undefined && String(cell).includes("หมู่"));
    if (hit) return i;
  }
  return 0;
}
