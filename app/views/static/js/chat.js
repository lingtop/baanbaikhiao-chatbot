// หน้าแชทบ้านใบเขียว — ส่งข้อความ/รูปไป POST /api/v1/chat/stream แล้วอ่าน SSE ทีละ event
// สถานะที่หน้าจอต้องมี (สัปดาห์ 6): empty state · กำลังประมวลผล · error · ล็อกช่องพิมพ์ระหว่างรอ · ปุ่มหยุด/เริ่มใหม่

const $ = (id) => document.getElementById(id);
const feed = $("feed"), col = $("col"), input = $("input"), sendBtn = $("send"), bar = $("bar");
const fileInput = $("file"), preview = $("preview");
const { maxChars, maxImageMb } = window.APP;
const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
const STEP_ORDER = ["guard_in", "vision", "rag", "llm", "guard_out"];
const STEP_LABEL = {
  guard_in: "ตรวจความปลอดภัย", vision: "วิเคราะห์รูปภาพ", rag: "ค้นข้อมูลจากคลังความรู้ของร้าน",
  llm: "เรียบเรียงคำตอบ", guard_out: "ตรวจคำตอบก่อนส่ง",
};

let busy = false, controller = null, attached = null;

// ---------- แสดงผล Markdown อย่างปลอดภัย (OWASP LLM10) ----------
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function renderMarkdown(text) {
  if (window.marked && window.DOMPurify) {
    return DOMPurify.sanitize(marked.parse(text, { breaks: true }), { FORBID_TAGS: ["img", "a", "style"] });
  }
  return escapeHtml(text).replace(/\n/g, "<br>");  // ถ้าโหลดไลบรารีไม่ได้ แสดงเป็นข้อความธรรมดา
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function scrollDown() { feed.scrollTop = feed.scrollHeight; }
function hideHello() { $("hello")?.remove(); }

// ---------- สถานะการเชื่อมต่อ ----------
function setStatus(kind, text) {
  const pill = $("status-pill");
  pill.className = "pill" + (kind === "off" ? " off" : kind === "busy" ? " busy" : "");
  pill.querySelector(".dot").className = "dot " + (kind === "off" ? "off" : "on");
  $("status-text").textContent = text;
  $("side-dot").className = "dot " + (kind === "off" ? "off" : "on");
  $("side-status").textContent = kind === "off" ? "เชื่อมต่อไม่ได้ชั่วคราว" : "ผู้ช่วยตอบคำถามร้านต้นไม้";
}
async function checkHealth() {
  try {
    const r = await fetch("/api/v1/health");
    const d = await r.json();
    if (d.status === "ok") setStatus("on", "ออนไลน์");
    else setStatus("off", "บางระบบขัดข้อง");
  } catch { setStatus("off", "เชื่อมต่อไม่ได้"); }
}

// ---------- ช่องพิมพ์ ----------
function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
  const n = input.value.length;
  $("count").textContent = `${n}/${maxChars}`;
  $("count").classList.toggle("over", n >= maxChars);
}
function setBusy(on) {
  busy = on;
  input.disabled = on;
  $("attach").disabled = on;
  bar.classList.toggle("dis", on);
  input.placeholder = on ? "กำลังตอบ... พิมพ์ข้อความถัดไปได้เมื่อตอบเสร็จ" : "พิมพ์คำถาม หรือแนบรูปต้นไม้... (Enter เพื่อส่ง)";
  sendBtn.classList.toggle("stop", on);
  sendBtn.textContent = on ? "■ หยุด" : "→";
  sendBtn.setAttribute("aria-label", on ? "หยุด" : "ส่ง");
  setStatus(on ? "busy" : "on", on ? "กำลังตอบ..." : "ออนไลน์");
  if (!on) input.focus();
}

// ---------- แนบรูป ----------
function pickFile() { if (!busy) fileInput.click(); }
function clearAttachment() {
  attached = null;
  fileInput.value = "";
  preview.hidden = true;
}
fileInput.addEventListener("change", () => {
  const f = fileInput.files[0];
  if (!f) return;
  if (!ALLOWED.includes(f.type)) return showInlineError("รองรับเฉพาะไฟล์ .jpg .png .webp ค่ะ"), clearAttachment();
  if (f.size > maxImageMb * 1024 * 1024) return showInlineError(`รูปใหญ่เกิน ${maxImageMb} MB ค่ะ`), clearAttachment();
  attached = f;
  $("preview-img").src = URL.createObjectURL(f);
  $("preview-name").textContent = `${f.name} · ${(f.size / 1024 / 1024).toFixed(1)} MB`;
  preview.hidden = false;
  input.focus();
});
$("preview-remove").addEventListener("click", clearAttachment);
$("attach").addEventListener("click", pickFile);
$("upload-cta").addEventListener("click", () => { closeSide(); pickFile(); });

function showInlineError(text) {
  hideHello();
  const box = el("div", "err", `<b>แนบรูปไม่ได้</b>${escapeHtml(text)}`);
  col.appendChild(box);
  scrollDown();
  setTimeout(() => box.remove(), 5000);
}

// ---------- ส่งข้อความ ----------
async function send(text, file) {
  if (busy) return;
  text = (text || "").trim();
  if (!text && !file) return;
  hideHello();

  if (file) {
    const img = el("img", "user-img");
    img.src = URL.createObjectURL(file);
    img.alt = "รูปที่ส่ง";
    col.appendChild(img);
  }
  const userMsg = el("div", "msg user");
  userMsg.textContent = text || "(ส่งรูปภาพ)";
  col.appendChild(userMsg);

  const steps = el("div", "steps");
  STEP_ORDER.filter((s) => s !== "vision" || file).forEach((s) => {
    steps.appendChild(el("div", "r", `<i>○</i><span>${STEP_LABEL[s]}</span>`)).dataset.step = s;
  });
  col.appendChild(steps);
  scrollDown();

  input.value = "";
  autoGrow();
  clearAttachment();
  setBusy(true);

  const form = new FormData();
  form.append("message", text);
  if (file) form.append("image", file);
  controller = new AbortController();

  let gotAnswer = false;
  try {
    const res = await fetch("/api/v1/chat/stream", { method: "POST", body: form, signal: controller.signal });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || `เซิร์ฟเวอร์ตอบผิดพลาด (รหัส ${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "", visionSeen = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const ev = JSON.parse(part.slice(6));
        if (ev.type === "status") updateStep(steps, ev.step, ev.state);
        else if (ev.type === "vision") visionSeen = ev.seen;
        else if (ev.type === "answer") { gotAnswer = true; steps.remove(); renderAnswer(ev, visionSeen); }
        else if (ev.type === "done") renderMeta(ev);
        else if (ev.type === "error") throw new Error(ev.message);
      }
    }
    if (!gotAnswer) throw new Error("ไม่ได้รับคำตอบจากระบบ");
  } catch (err) {
    steps.remove();
    if (err.name === "AbortError") {
      col.appendChild(el("div", "meta", "หยุดการตอบแล้ว"));
    } else {
      renderError(userMsg, text, file, err.message);
    }
  } finally {
    controller = null;
    setBusy(false);
    scrollDown();
  }
}

function updateStep(steps, step, state) {
  const row = steps.querySelector(`[data-step="${step}"]`);
  if (!row) return;
  row.className = "r " + state;
  row.querySelector("i").textContent = state === "done" ? "✓" : state === "running" ? "●" : "○";
  row.querySelector(".typing")?.remove();
  if (state === "running") row.appendChild(el("span", "typing", "<i></i><i></i><i></i>"));
}

function renderAnswer(ev, visionSeen) {
  if (ev.blocked) {
    const box = el("div", "warn");
    box.innerHTML = `<span class="tag2">${escapeHtml(ev.label || "ไม่สามารถตอบได้")}</span>` + renderMarkdown(ev.text);
    col.appendChild(box);
  } else {
    const box = el("div", "msg bot");
    if (visionSeen) box.appendChild(el("div", "seen", `<b>สิ่งที่เห็นในรูป</b>${escapeHtml(visionSeen)}`));
    box.appendChild(el("div", "", renderMarkdown(ev.text)));
    if (ev.products?.length) box.appendChild(productGrid(ev.products));
    col.appendChild(box);
  }
  col.lastMeta = { sources: ev.sources || [], blocked: ev.blocked, layer: ev.layer, categories: ev.categories };
  if (ev.suggestions?.length) {
    const chips = el("div", "chips");
    ev.suggestions.forEach((s) => {
      const b = el("button", "chip");
      b.textContent = s;
      b.addEventListener("click", () => send(s));
      chips.appendChild(b);
    });
    col.chipsPending = chips;
  }
}

function productGrid(products) {
  const grid = el("div", "grid3");
  products.forEach((p) => {
    const card = el("div", "pcard");
    const prices = p.prices.map((x) => `${x.price.toLocaleString("th-TH")} บาท <span>${escapeHtml(x.size)}</span>`).join("<br>");
    const stock = p.stock.startsWith("มีสินค้า") ? "" : `<small class="stock">${escapeHtml(p.stock)}</small>`;
    card.innerHTML = `<div class="img">${p.icon}</div><b>${escapeHtml(p.name)}</b>
      <small>${escapeHtml(p.tag)} · ${escapeHtml(p.difficulty)} <span class="tag">${escapeHtml(p.id)}</span></small>
      <div class="pr">${prices}</div>${stock}`;
    grid.appendChild(card);
  });
  return grid;
}

function renderMeta(ev) {
  const m = col.lastMeta || {};
  let text = `ตอบใน ${ev.total.toFixed(1)} วินาที`;
  if (m.blocked) text += ` · ปฏิเสธโดย ${m.layer === "business_rules" ? "กฎของร้าน" : m.layer === "blocklist" ? "คำต้องห้าม" : "ระบบตรวจความปลอดภัย"}` +
    (m.categories?.length ? ` (${m.categories.join(", ")})` : "");
  else if (m.sources?.length) text += ` · อ้างอิง: ${m.sources.join(", ")}`;
  const meta = el("div", "meta");
  meta.textContent = text;
  meta.title = Object.entries(ev.timings || {}).map(([k, v]) => `${STEP_LABEL[k] || k}: ${v} วิ`).join("\n");
  col.appendChild(meta);
  if (col.chipsPending) { col.appendChild(col.chipsPending); col.chipsPending = null; }
}

function renderError(userMsg, text, file, message) {
  userMsg.classList.add("unsent");
  userMsg.after(el("div", "unsent-l", "⚠ ยังไม่ได้ส่ง"));
  const box = el("div", "err", `<b>ส่งข้อความไม่สำเร็จ</b>${escapeHtml(message)} ลองใหม่อีกครั้ง หรือทัก LINE @baanbaikhiao ได้ค่ะ`);
  const btns = el("div", "btns");
  const retry = el("button", "btn p", "ลองใหม่");
  const edit = el("button", "btn s", "แก้ข้อความ");
  retry.addEventListener("click", () => { box.remove(); send(text, file); });
  edit.addEventListener("click", () => { box.remove(); input.value = text; autoGrow(); input.focus(); });
  btns.append(retry, edit);
  box.appendChild(btns);
  col.appendChild(box);
  setStatus("off", "ระบบขัดข้องชั่วคราว");
}

// ---------- events ----------
$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  if (busy) { controller?.abort(); return; }  // ปุ่มเดียวกันเป็นปุ่มหยุดระหว่างรอ
  send(input.value, attached);
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("form").requestSubmit(); }
});
input.addEventListener("input", autoGrow);
document.addEventListener("click", (e) => {
  const q = e.target.closest("[data-q]");
  if (q) { closeSide(); send(q.dataset.q); }
  if (e.target.closest("[data-upload]")) pickFile();
});
$("reset").addEventListener("click", async () => {
  if (busy) controller?.abort();
  await fetch("/api/v1/chat/reset", { method: "POST" }).catch(() => {});
  location.reload();
});

// เมนูข้างบนมือถือ
function closeSide() { $("side").classList.remove("open"); }
$("open-side").addEventListener("click", () => $("side").classList.add("open"));
$("close-side").addEventListener("click", closeSide);

autoGrow();
checkHealth();
input.focus();
