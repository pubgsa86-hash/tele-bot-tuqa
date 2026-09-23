import "./style.css";
import { telegram } from "./telegram";
import { ApiError, getJob, getSession, startProcess, videoUrl } from "./api";

const MIN_SEG = 0.3;
const MAX_SEG = 60;

type SizeSetting = number | "original";

interface Settings {
  start: number;
  end: number;
  zoom: number;
  pan: { x: number; y: number };
  circle: { cx: number; cy: number; d: number };
  size: SizeSetting;
  mask: boolean;
  frame: { enabled: boolean; color: string; width: number };
  watermark: { enabled: boolean; text: string; size: number; opacity: number; pos: string };
}

const token = new URLSearchParams(window.location.search).get("token")?.trim() || "";
const settings: Settings = {
  start: 0,
  end: 0,
  zoom: 1,
  pan: { x: 0, y: 0 },
  circle: { cx: 0.5, cy: 0.5, d: 0.9 },
  size: 320,
  mask: false,
  frame: { enabled: false, color: "#ffffff", width: 4 },
  watermark: { enabled: false, text: "", size: 0.06, opacity: 0.8, pos: "br" },
};

let duration = 0;
let videoW = 0;
let videoH = 0;
let processing = false;
let subState: "none" | "watermark" | "result" = "none";
let controlsBound = false;
let timelineBound = false;

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function round3(v: number): number {
  return Math.round(v * 1000) / 1000;
}

function fmtTime(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function hide(node: HTMLElement): void {
  node.hidden = true;
}

function show(node: HTMLElement): void {
  node.hidden = false;
}

const ERROR_AR: Record<string, string> = {
  session_not_found: "جلسة منتهية — ارجع للبوت وأعد المحاولة",
  file_missing: "الملف غير متوفر على الخادم — أعد فتح المحرر من البوت",
  invalid_init_data: "تعذّر التحقق من هويتك — أغلق المحرر وأعد فتحه من البوت",
  invalid_json: "طلب غير صالح",
  invalid_settings: "إعدادات غير صالحة",
  not_video: "هذا الملف ليس فيديو",
  busy: "الخدمة مشغولة — حاول لاحقًا",
  job_running: "المهمة قيد التشغيل — انتظر حتى تنتهي",
  job_not_found: "تعذّر العثور على المهمة",
  video_too_long: "الفيديو أطول من الحد المسموح به",
  no_font: "الخط غير متوفر على الخادم",
  no_video_stream: "لا يوجد مسار فيديو في هذا الملف",
  empty: "الفيديو فارغ",
  unsupported: "الصيغة غير مدعومة",
  network_error: "تعذّر الاتصال بالخادم — تحقق من اتصالك",
  http_error: "خطأ في الاتصال بالخادم",
  invalid_response: "استجابة غير متوقعة من الخادم",
};

function errText(e: unknown): string {
  if (e instanceof ApiError) return ERROR_AR[e.code] ?? e.code;
  return "خطأ غير متوقع";
}

let toastTimer: number | undefined;

function toast(message: string): void {
  const t = el("toast");
  t.textContent = message;
  show(t);
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => hide(t), 3500);
}

function outNum(): number {
  if (typeof settings.size === "number") return clampEven(settings.size, 16, 1080);
  if (videoW > 0 && videoH > 0) return clampEven(Math.min(videoW, videoH), 16, 1080);
  return 320;
}

function clampEven(v: number, lo: number, hi: number): number {
  let x = clamp(Math.round(v), lo, hi);
  x -= x % 2;
  return Math.max(2, x);
}

function showError(title: string, message: string): void {
  hide(el("loading-view"));
  hide(el("main-view"));
  hide(el("app-back"));
  el("error-title").textContent = title;
  el("error-msg").textContent = message;
  show(el("error-view"));
}

function syncBackButton(): void {
  if (!telegram.available) return;
  if (subState !== "none") telegram.backButton.show();
  else telegram.backButton.hide();
}

function boot(): void {
  telegram.init();
  hide(el("app-back"));
  if (!telegram.available && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.classList.add("dark");
  }
  const errorClose = el("error-close");
  errorClose.addEventListener("click", () => {
    if (telegram.available) telegram.close();
  });
  if (telegram.available) {
    telegram.backButton.onClick(() => {
      if (processing) return;
      if (subState === "watermark") {
        el<HTMLInputElement>("wm-text").blur();
        subState = "none";
        syncBackButton();
        return;
      }
      if (subState === "result") {
        backFromResult();
        return;
      }
      if (telegram.available) telegram.close();
    });
  }
  el("app-back").addEventListener("click", () => {
    if (processing) return;
    if (subState === "watermark") {
      el<HTMLInputElement>("wm-text").blur();
      subState = "none";
      syncBackButton();
      return;
    }
    if (subState === "result") {
      backFromResult();
      return;
    }
    if (telegram.available) telegram.close();
  });

  if (!token) {
    showError("جلسة غير صالحة", "لم يتم العثور على رمز الجلسة — ارجع للبوت وأعد المحاولة.");
    return;
  }
  void loadSession();
}

async function loadSession(): Promise<void> {
  const loading = el("loading-view");
  show(loading);
  let info;
  try {
    info = await getSession(token);
  } catch (e) {
    showError("تعذّر فتح الجلسة", errText(e));
    return;
  }
  if (info.kind !== "video") {
    showError("تعذّر فتح الجلسة", "هذا الملف ليس فيديو.");
    return;
  }
  videoW = info.width || 0;
  videoH = info.height || 0;
  duration = info.duration || 0;

  const video = el<HTMLVideoElement>("preview");
  video.src = videoUrl(token);
  video.addEventListener("loadedmetadata", () => {
    videoW = video.videoWidth || videoW;
    videoH = video.videoHeight || videoH;
    if (!duration && video.duration) duration = video.duration;
    updateMeta();
    setupAll();
    redraw();
  });

  updateMeta();
  setupAll();
  redraw();

  hide(loading);
  show(el("main-view"));
  show(el("app-back"));
  window.setTimeout(redraw, 50);

  window.addEventListener("resize", redraw);

  telegram.mainButton.setText("تحويل");
  telegram.mainButton.show();
  telegram.mainButton.enable();
  telegram.mainButton.onClick(() => void convert());

  new ResizeObserver(() => updateOverlay()).observe(el("video-wrap"));
}

function updateMeta(): void {
  const dims: string[] = [];
  if (videoW > 0 && videoH > 0) dims.push(`${videoW}×${videoH}`);
  el("meta-dims").textContent = dims.length ? dims.join(" · ") : "الأبعاد غير معروفة";
  el("meta-dur").textContent = duration > 0 ? `المدة ${fmtTime(duration)}` : "المدة غير معروفة";
}

function setupAll(): void {
  if (!controlsBound) {
    controlsBound = true;
    setupSize();
    setupZoomPan();
    setupFrame();
    setupCircle();
    setupWatermark();
    setupConvert();
  }
  if (duration > 0 && !timelineBound) {
    timelineBound = true;
    setupTimeline();
  } else {
    el("start-slider").disabled = true;
    el("end-slider").disabled = true;
  }
}

function setupTimeline(): void {
  const startSlider = el<HTMLInputElement>("start-slider");
  const endSlider = el<HTMLInputElement>("end-slider");
  const max100 = Math.max(100, Math.round(duration * 100));
  startSlider.min = "0";
  startSlider.max = String(max100);
  startSlider.step = "1";
  endSlider.min = "0";
  endSlider.max = String(max100);
  endSlider.step = "1";
  startSlider.disabled = false;
  endSlider.disabled = false;
  startSlider.value = "0";
  endSlider.value = String(Math.min(Math.round(Math.min(duration, MAX_SEG) * 100), max100));

  settings.start = 0;
  settings.end = Math.min(duration, MAX_SEG);

  startSlider.addEventListener("input", () => {
    applyStart(parseFloat(startSlider.value) / 100);
    syncSliders();
    redraw();
  });
  endSlider.addEventListener("input", () => {
    applyEnd(parseFloat(endSlider.value) / 100);
    syncSliders();
    redraw();
  });

  syncSliders();
}

function syncSliders(): void {
  el<HTMLInputElement>("start-slider").value = String(Math.round(clamp(settings.start, 0, Math.max(0, settings.end - MIN_SEG)) * 100));
  el<HTMLInputElement>("end-slider").value = String(Math.round(clamp(settings.end, settings.start + MIN_SEG, duration) * 100));
  el("start-val").textContent = fmtTime(settings.start);
  el("end-val").textContent = fmtTime(settings.end);
  el("seg-len").textContent = `المقطع: من ${fmtTime(settings.start)} إلى ${fmtTime(settings.end)} (${(settings.end - settings.start).toFixed(1)} ثانية)`;
}

function applyStart(raw: number): void {
  let start = clamp(raw, 0, Math.max(0, duration - MIN_SEG));
  if (duration - start < MIN_SEG) start = Math.max(0, duration - MIN_SEG);
  let end = settings.end;
  if (end - start < MIN_SEG) end = Math.min(duration, start + MIN_SEG);
  if (end - start > MAX_SEG) end = start + MAX_SEG;
  settings.start = round3(start);
  settings.end = round3(end);
}

function applyEnd(raw: number): void {
  let end = clamp(raw, settings.start + MIN_SEG, duration);
  if (end - settings.start > MAX_SEG) end = settings.start + MAX_SEG;
  settings.end = round3(end);
  if (settings.end - settings.start < MIN_SEG) {
    settings.start = round3(Math.max(0, settings.end - MIN_SEG));
  }
  syncSliders();
}

function setupSize(): void {
  const chips = Array.from(document.querySelectorAll<HTMLButtonElement>("#size-chips button"));
  const sizeInput = el<HTMLInputElement>("size-input");
  const setChips = (): void => {
    for (const b of chips) {
      const v = b.dataset.size;
      const active =
        typeof settings.size === "number" ? Number(b.dataset.size) === settings.size : b.dataset.size === "original";
      b.classList.toggle("active", active);
    }
  };
  for (const b of chips) {
    b.addEventListener("click", () => {
      settings.size = b.dataset.size === "original" ? "original" : Number(b.dataset.size);
      sizeInput.value = typeof settings.size === "number" ? String(settings.size) : "";
      sizeInput.disabled = settings.size === "original";
      el("size-val").textContent = typeof settings.size === "number" ? String(settings.size) : "أصلي";
      setChips();
      redraw();
    });
  }
  sizeInput.addEventListener("input", () => {
    const raw = parseInt(sizeInput.value, 10);
    if (Number.isNaN(raw)) return;
    const v = clampEven(raw, 16, 1080);
    if (v !== raw) sizeInput.value = String(v);
    settings.size = v;
    el("size-val").textContent = String(v);
    setChips();
    redraw();
  });
  el("size-val").textContent = "320";
}

function setupZoomPan(): void {
  const zoom = el<HTMLInputElement>("zoom-slider");
  const panX = el<HTMLInputElement>("pan-x");
  const panY = el<HTMLInputElement>("pan-y");

  zoom.addEventListener("input", () => {
    settings.zoom = clamp(parseFloat(zoom.value), 1, 4);
    el("zoom-val").textContent = `×${settings.zoom.toFixed(1)}`;
    redraw();
  });

  const panMax = (): number => outNum() * (settings.zoom - 1);
  panX.addEventListener("input", () => {
    const p = (parseFloat(panX.value) / 100) * panMax();
    settings.pan.x = p;
    el("pan-x-val").textContent = String(Math.round(p));
    redraw();
  });
  panY.addEventListener("input", () => {
    const p = (parseFloat(panY.value) / 100) * panMax();
    settings.pan.y = p;
    el("pan-y-val").textContent = String(Math.round(p));
    redraw();
  });
  el("zoom-val").textContent = "×1.0";
}

function setupFrame(): void {
  const toggle = el<HTMLInputElement>("frame-toggle");
  const color = el<HTMLInputElement>("frame-color");
  const width = el<HTMLInputElement>("frame-width");

  toggle.addEventListener("change", () => {
    settings.frame.enabled = toggle.checked;
    syncToggle(toggle, settings.frame.enabled);
    redraw();
  });
  color.addEventListener("input", () => {
    settings.frame.color = color.value;
    redraw();
  });
  width.addEventListener("input", () => {
    settings.frame.width = Math.round(clamp(parseFloat(width.value), 1, 40));
    el("frame-width-val").textContent = String(settings.frame.width);
    redraw();
  });
}

function setupCircle(): void {
  const cx = el<HTMLInputElement>("c-cx");
  const cy = el<HTMLInputElement>("c-cy");
  const d = el<HTMLInputElement>("c-d");
  const mask = el<HTMLInputElement>("mask-toggle");

  cx.addEventListener("input", () => {
    settings.circle.cx = parseFloat(cx.value) / 100;
    el("c-cx-val").textContent = settings.circle.cx.toFixed(2);
    redraw();
  });
  cy.addEventListener("input", () => {
    settings.circle.cy = parseFloat(cy.value) / 100;
    el("c-cy-val").textContent = settings.circle.cy.toFixed(2);
    redraw();
  });
  d.addEventListener("input", () => {
    settings.circle.d = parseFloat(d.value) / 100;
    el("c-d-val").textContent = settings.circle.d.toFixed(2);
    redraw();
  });
  mask.addEventListener("change", () => {
    settings.mask = mask.checked;
    syncToggle(mask, settings.mask);
    redraw();
  });
}

function setupWatermark(): void {
  const toggle = el<HTMLInputElement>("wm-toggle");
  const text = el<HTMLInputElement>("wm-text");
  const size = el<HTMLInputElement>("wm-size");
  const opacity = el<HTMLInputElement>("wm-opacity");
  const pos = el<HTMLSelectElement>("wm-pos");

  toggle.addEventListener("change", () => {
    settings.watermark.enabled = toggle.checked;
    syncToggle(toggle, settings.watermark.enabled);
  });

  text.addEventListener("input", () => {
    settings.watermark.text = text.value;
  });

  text.addEventListener("focus", () => {
    subState = "watermark";
    syncBackButton();
  });
  text.addEventListener("blur", () => {
    subState = "none";
    syncBackButton();
  });

  size.addEventListener("input", () => {
    settings.watermark.size = parseFloat(size.value) / 100;
    el("wm-size-val").textContent = settings.watermark.size.toFixed(2);
  });
  opacity.addEventListener("input", () => {
    settings.watermark.opacity = parseFloat(opacity.value) / 100;
    el("wm-opacity-val").textContent = settings.watermark.opacity.toFixed(2);
  });
  pos.addEventListener("change", () => {
    settings.watermark.pos = pos.value;
  });
}

function syncToggle(input: HTMLInputElement, on: boolean): void {
  const row = input.closest(".switch");
  if (row) row.classList.toggle("on", on);
}

function setupConvert(): void {
  const convertBtn = el<HTMLButtonElement>("convert-btn");
  convertBtn.addEventListener("click", () => void convert());
  el("result-close").addEventListener("click", () => backFromResult());
}

function payloadSettings(): unknown {
  return {
    start: settings.start,
    end: settings.end,
    zoom: settings.zoom,
    pan: { x: settings.pan.x, y: settings.pan.y },
    circle: { cx: settings.circle.cx, cy: settings.circle.cy, d: settings.circle.d },
    size: settings.size,
    mask: settings.mask,
    frame: {
      enabled: settings.frame.enabled,
      color: settings.frame.color,
      width: Math.round(settings.frame.width),
    },
    watermark: {
      enabled: settings.watermark.enabled,
      text: settings.watermark.text.slice(0, 120),
      size: settings.watermark.size,
      opacity: settings.watermark.opacity,
      pos: settings.watermark.pos,
    },
  };
}

async function convert(): Promise<void> {
  if (processing) return;
  if (duration <= 0) {
    toast("الجدول الزمني للفيديو غير متاح");
    return;
  }
  if (settings.watermark.enabled && !settings.watermark.text.trim()) {
    toast("أدخل نص العلامة المائية أو عطّلها");
    const text = el<HTMLInputElement>("wm-text");
    text.focus();
    return;
  }

  processing = true;
  subState = "none";
  syncBackButton();
  setUIProcessing(true);
  telegram.mainButton.setText("معالجة…");
  telegram.mainButton.setProgress(true);
  telegram.mainButton.disable();

  try {
    const res = await startProcess(token, payloadSettings());
    await pollUntilDone(res.job_id);
  } catch (e) {
    onFail(errText(e));
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollUntilDone(jobId: string): Promise<void> {
  let fails = 0;
  for (;;) {
    await sleep(1500);
    let job;
    try {
      job = await getJob(jobId);
      fails = 0;
    } catch (e) {
      fails += 1;
      if (fails > 6) {
        onFail(errText(e));
        return;
      }
      continue;
    }
    setProgressUI(job.progress, job.status);
    if (job.status === "done") {
      onDone();
      return;
    }
    if (job.status === "failed") {
      onFail(job.error ? errorTextOf(job.error) : "فشلت المعالجة");
      return;
    }
  }
}

function errorTextOf(code: string): string {
  return ERROR_AR[code] ?? `فشلت المعالجة: ${code}`;
}

function setUIProcessing(on: boolean): void {
  const mainView = el("main-view");
  mainView.classList.toggle("busy", on);
  el("convert-btn").textContent = on ? "معالجة…" : "تحويل";
  (el("convert-btn") as HTMLButtonElement).disabled = on;
  el("progress-box").hidden = !on;
  if (on) el("result-box").hidden = true;
}

function setProgressUI(progress: number, status: string): void {
  const p = clamp(progress, 0, 100);
  el("progress-bar").style.width = `${p}%`;
  el("progress-bar").textContent = `${Math.round(p)}%`;
  if (status === "done") {
    el("progress-text").textContent = "اكتمل التحويل ✅";
  } else if (status === "failed") {
    el("progress-text").textContent = "فشل التحويل ❌";
  } else {
    const label = status === "queued" ? "في الانتظار" : "جارٍ المعالجة";
    el("progress-text").textContent = `${label}… ${Math.round(p)}%`;
  }
}

function onDone(): void {
  processing = false;
  setUIProcessing(false);
  setProgressUI(100, "done");
  el("convert-btn").hidden = true;
  hide(el("progress-box"));
  el("result-box").classList.remove("error");
  el("result-msg").textContent = "✅ تم التحويل — سيصلك الفيديو الدائري في بوت تليجرام";
  show(el("result-box"));
  subState = "result";
  syncBackButton();
  telegram.mainButton.setProgress(false);
  telegram.mainButton.setText("تم ✅");
  telegram.mainButton.enable();
}

function onFail(message: string): void {
  processing = false;
  setUIProcessing(false);
  el("convert-btn").hidden = false;
  el("result-msg").textContent = `❌ ${message}`;
  el("result-box").classList.add("error");
  show(el("result-box"));
  telegram.mainButton.setProgress(false);
  telegram.mainButton.setText("تحويل");
  telegram.mainButton.enable();
}

function backFromResult(): void {
  hide(el("result-box"));
  el("convert-btn").hidden = false;
  subState = "none";
  syncBackButton();
  telegram.mainButton.setProgress(false);
  telegram.mainButton.setText("تحويل");
  telegram.mainButton.enable();
}

function redraw(): void {
  drawTimeline();
  updateOverlay();
}

function drawTimeline(): void {
  const canvas = el<HTMLCanvasElement>("timeline");
  const dpr = window.devicePixelRatio || 1;
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--tg-button").trim() || "#2ea6ff";
  const hintColor = css.getPropertyValue("--tg-hint").trim() || "#8a8f98";
  const secondary = css.getPropertyValue("--tg-secondary-bg").trim() || "#eef1f4";
  const textColor = css.getPropertyValue("--tg-text").trim() || "#222";

  const W = Math.max(200, canvas.clientWidth);
  const H = 60;
  if (canvas.width !== Math.round(W * dpr)) {
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.height = `${H}px`;
  }
  const g = canvas.getContext("2d");
  if (!g) return;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);

  const pad = 10;
  const tw = W - pad * 2;
  const mid = H / 2;
  const mapX = (t: number): number => pad + clamp(t / (duration > 0 ? duration : 1), 0, 1) * tw;

  if (duration <= 0) {
    g.fillStyle = hintColor;
    g.font = "13px system-ui, sans-serif";
    g.textAlign = "center";
    g.fillText("المدة غير متاحة", W / 2, mid + 5);
    return;
  }

  g.fillStyle = secondary;
  roundRect(g, pad, mid - 4, tw, 8, 4);
  g.fill();

  const segStart = settings.start;
  const segEnd = settings.end;
  const windowEnd = Math.min(duration, segStart + MAX_SEG);

  if (duration > MAX_SEG) {
    g.fillStyle = hexA(hintColor, 0.25);
    roundRect(g, mapX(segStart), mid - 5, mapX(windowEnd) - mapX(segStart), 10, 5);
    g.fill();
  }

  g.fillStyle = border2(accent, 0.85);
  roundRect(g, mapX(segStart), mid - 7, Math.max(2, mapX(segEnd) - mapX(segStart)), 14, 5);
  g.fill();

  g.fillStyle = textColor;
  g.font = "12px system-ui, sans-serif";
  g.textAlign = "left";
  g.fillText(fmtTime(0), pad, H - 4);
  g.textAlign = "right";
  g.fillText(fmtTime(duration), pad + tw, H - 4);
  g.textAlign = "center";
  g.fillStyle = hexA(textColor, 0.75);
  g.fillText(`من ${fmtTime(segStart)} إلى ${fmtTime(segEnd)}`, W / 2, 16);
}

function roundRect(
  g: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  const rr = Math.min(r, w / 2, h / 2);
  g.beginPath();
  g.moveTo(x + rr, y);
  g.arcTo(x + w, y, x + w, y + h, rr);
  g.arcTo(x + w, y + h, x, y + h, rr);
  g.arcTo(x, y + h, x, y, rr);
  g.arcTo(x, y, x + w, y, rr);
  g.closePath();
}

function hexA(hex: string, alpha: number): string {
  const ok = hex.replace(/^#/, "");
  const full = ok.length === 3 ? ok.split("").map((c) => c + c).join("") : ok;
  const num = parseInt(full.slice(0, 6), 16);
  if (Number.isNaN(num)) return hex;
  const r = (num >> 16) & 255;
  const gg = (num >> 8) & 255;
  const b = num & 255;
  return `rgba(${r},${gg},${b},${alpha})`;
}

function border2(hex: string, alpha: number): string {
  return hexA(hex, alpha);
}

function updateOverlay(): void {
  const overlay = el<HTMLDivElement>("crop-overlay");
  const wrap = el<HTMLDivElement>("video-wrap");
  if (videoW <= 0 || videoH <= 0 || duration <= 0) {
    overlay.hidden = true;
    return;
  }
  const out = outNum();
  const baseCover = Math.max(out / videoW, out / videoH);
  const scale = baseCover * settings.zoom;
  const dw = Math.max(videoW * scale, 1);
  const dh = Math.max(videoH * scale, 1);
  const minTx = out - dw;
  const minTy = out - dh;
  const tx = Math.max(minTx, Math.min(0, settings.pan.x));
  const ty = Math.max(minTy, Math.min(0, settings.pan.y));

  let diameter = Math.min(out * clamp(settings.circle.d, 0.2, 1), dw, dh);
  diameter = Math.max(8, diameter);
  if (diameter > out) diameter = out;
  diameter = Math.floor(diameter);
  diameter -= diameter % 2;
  if (diameter < 2) diameter = 2;

  const maxOff = (out - diameter) / 2;
  const cx = clamp(settings.circle.cx * out, maxOff, out - maxOff);
  const cy = clamp(settings.circle.cy * out, maxOff, out - maxOff);
  const cropX = clamp(cx - diameter / 2 - tx, 0, dw - diameter);
  const cropY = clamp(cy - diameter / 2 - ty, 0, dh - diameter);

  const srcSide = diameter / scale;
  const srcCX = (cropX + diameter / 2) / scale;
  const srcCY = (cropY + diameter / 2) / scale;

  const Wd = wrap.clientWidth;
  const Hd = wrap.clientHeight;
  if (Wd <= 0 || Hd <= 0) return;

  const f = Math.min(Wd / videoW, Hd / videoH);
  const offX = (Wd - videoW * f) / 2;
  const offY = (Hd - videoH * f) / 2;
  const px = offX + (srcCX - srcSide / 2) * f;
  const py = offY + (srcCY - srcSide / 2) * f;
  const pz = srcSide * f;

  overlay.hidden = false;
  overlay.style.left = `${px}px`;
  overlay.style.top = `${py}px`;
  overlay.style.width = `${pz}px`;
  overlay.style.height = `${pz}px`;

  if (settings.frame.enabled) {
    overlay.style.border = `${Math.max(1, Math.round(settings.frame.width))}px solid ${settings.frame.color}`;
    overlay.style.boxShadow = "none";
  } else {
    overlay.style.border = "2px dashed rgba(127,135,150,0.75)";
    overlay.style.boxShadow = "none";
  }
  if (settings.mask) {
    overlay.style.boxShadow = "0 0 0 9999px rgba(0,0,0,0.45)";
  }
}

document.addEventListener("DOMContentLoaded", boot);