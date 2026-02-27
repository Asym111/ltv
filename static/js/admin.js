// =========================
// Helpers (UI)
// =========================
function show(el, msg, isErr = false) {
  if (!el) return;
  el.textContent = msg || "";
  el.classList.remove("d-none");
  el.className = isErr ? "text-danger small mt-2" : "text-success small mt-2";
}

function hide(el) {
  if (!el) return;
  el.classList.add("d-none");
}

function safeNum(val, def = 0) {
  const n = Number(val);
  return Number.isFinite(n) ? n : def;
}

function fmt0(x) {
  const n = Number(x || 0);
  return Number.isFinite(n) ? Math.round(n).toString() : "0";
}

function fmtMoney(val) {
  const n = safeNum(val, 0);
  return n.toLocaleString("ru-RU");
}

function fmtDate(dt) {
  try {
    if (!dt) return "—";
    return new Date(dt).toLocaleString("ru-RU");
  } catch {
    return "—";
  }
}

function ymdLocal(d) {
  try {
    const x = d instanceof Date ? d : new Date(d);
    const y = x.getFullYear();
    const m = String(x.getMonth() + 1).padStart(2, "0");
    const day = String(x.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  } catch {
    return "";
  }
}

function normalizePhone(phone) {
  if (!phone) return "";
  let p = String(phone).replace(/\D/g, "");
  if (!p) return "";
  if (p.startsWith("8") && p.length === 11) p = "7" + p.slice(1);
  if (p.length === 10) p = "7" + p;
  if (p.length > 11) p = p.slice(-11);
  return p;
}

function getQueryParam(name) {
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get(name);
  } catch {
    return null;
  }
}

// =========================
// AI reco dismiss (localStorage)
// =========================
const AI_DISMISS_KEY = "ltv_ai_dismissed_v1";

function aiLoadDismissed() {
  try {
    const raw = localStorage.getItem(AI_DISMISS_KEY);
    const obj = raw ? JSON.parse(raw) : {};
    return obj && typeof obj === "object" ? obj : {};
  } catch {
    return {};
  }
}

function aiSaveDismissed(obj) {
  try {
    localStorage.setItem(AI_DISMISS_KEY, JSON.stringify(obj || {}));
  } catch {
    // ignore
  }
}

function aiRecoKey(context, phone, r) {
  const c = String(context || "business").trim();
  const p = String(phone || "").trim();
  const a = String(r?.action || "").trim();
  const t = String(r?.target || "").trim();
  const w = String(r?.why || "").trim();
  return `${c}|${p}|${a}|${t}|${w}`.slice(0, 480);
}

function aiIsDismissed(key) {
  const obj = aiLoadDismissed();
  return Boolean(obj && obj[key]);
}

function aiDismiss(key) {
  const obj = aiLoadDismissed();
  obj[key] = Date.now();
  aiSaveDismissed(obj);
}

// =========================
// API
// =========================
async function apiGet(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data?.detail || `${r.status} ${r.statusText}`);
  return data;
}

async function apiPost(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(data),
  });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(out?.detail || `${r.status} ${r.statusText}`);
  return out;
}

// =========================
// Execute recommendation (SERVER-validated)
// =========================
async function aiExecuteReco(context, phone, r) {
  try {
    const payload = {
      context: String(context || "business"),
      phone: phone ? String(phone) : null,
      recommendation: r || {},
    };

    const res = await apiPost("/api/ai/execute", payload);

    // Backend decides what is allowed
    const nav = res?.nav ? String(res.nav) : "";
    if (nav && nav.startsWith("/")) {
      window.location.href = nav;
      return true;
    }

    if (typeof uiToast === "function") uiToast(res?.message || "Действие не выполнено", "warning");
    return false;
  } catch (e) {
    if (typeof uiToast === "function") uiToast(`Execute ошибка: ${String(e.message || e)}`, "error");
    return false;
  }
}

// =========================
// Русификация "Tier" (только UI; API оставляем Bronze/Silver/Gold)
// =========================
const TIER_RU = { Bronze: "Бронза", Silver: "Серебро", Gold: "Золото" };

function tierRu(tier) {
  const t = String(tier || "").trim();
  return TIER_RU[t] || (t ? t : "Бронза");
}

function tierBadgeClass(tier) {
  const t = String(tier || "").trim();
  if (t === "Gold") return "bg-warning text-dark";
  if (t === "Silver") return "bg-info text-dark";
  return "bg-secondary";
}

// ТОЛЕРАНТНОСТЬ к старым/разным полям
function getRedeem(t) {
  return safeNum(t?.redeem_points ?? t?.redeemPoints ?? t?.redeem_bonus ?? t?.redeemBonus ?? 0, 0);
}
function getEarned(t) {
  return safeNum(t?.earned_points ?? t?.earnedPoints ?? t?.earned_bonus ?? t?.earnedBonus ?? 0, 0);
}

// =========================
// Theme
// =========================
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  const icon = document.getElementById("themeIcon");
  if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
}

function initTheme() {
  const saved = localStorage.getItem("theme");
  // ✅ по умолчанию LIGHT (под ваш дизайн)
  applyTheme(saved || "light");

  const btn = document.getElementById("themeToggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") || "light";
      applyTheme(cur === "dark" ? "light" : "dark");
    });
  }
}

// =========================
// Add page class to <body> (critical for per-page styles)
// =========================
function applyBodyPageClass() {
  const page = String(window.__ADMIN_PAGE__ || "").trim();
  if (!page) return;
  try {
    document.body.classList.add(`page-${page}`);
    document.body.dataset.page = page;
  } catch {
    // ignore
  }
}

// =========================
// Global AI Panel (offcanvas)
// =========================
function initAiPanel() {
  const ctxEl = document.getElementById("aiPanelContext");
  const qEl = document.getElementById("aiPanelQuestion");
  const sendBtn = document.getElementById("aiPanelSendBtn");
  const clearBtn = document.getElementById("aiPanelClearBtn");
  const modeBadge = document.getElementById("aiPanelMode");
  const errEl = document.getElementById("aiPanelError");
  const ansEl = document.getElementById("aiPanelAnswer");
  const ulInsights = document.getElementById("aiPanelInsights");
  const boxRecos = document.getElementById("aiPanelRecos");

  if (!qEl || !sendBtn || !modeBadge || !ansEl || !ulInsights || !boxRecos || !ctxEl) return;

  let currentContext = "business";
  let currentPhone = null;
  let currentRecos = [];

  function setMode(mode) {
    const m = String(mode || "—");
    modeBadge.textContent = m;

    modeBadge.classList.remove("text-bg-secondary", "text-bg-success", "text-bg-warning", "text-bg-danger", "text-bg-info");
    if (m === "openai") modeBadge.classList.add("text-bg-success");
    else if (m === "gemini") modeBadge.classList.add("text-bg-success"); // на случай старых ответов
    else if (m === "heuristic") modeBadge.classList.add("text-bg-info");
    else if (m === "error") modeBadge.classList.add("text-bg-danger");
    else modeBadge.classList.add("text-bg-secondary");
  }

  function setError(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function clearError() {
    if (!errEl) return;
    errEl.classList.add("d-none");
    errEl.textContent = "";
  }

  function renderInsights(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      ulInsights.innerHTML = `<li class="text-muted">—</li>`;
      return;
    }
    ulInsights.innerHTML = list.slice(0, 10).map((s) => `<li>${String(s)}</li>`).join("");
  }

  function renderRecos(items) {
    const list = Array.isArray(items) ? items : [];

    // filter dismissed
    const filtered = list.filter((r) => !aiIsDismissed(aiRecoKey(currentContext, currentPhone, r)));
    currentRecos = filtered;

    if (!filtered.length) {
      boxRecos.innerHTML = `<div class="text-muted small">—</div>`;
      return;
    }

    boxRecos.innerHTML = filtered.slice(0, 10).map((r, idx) => {
      const action = r?.action ? String(r.action) : "Действие";
      const target = r?.target ? String(r.target) : "—";
      const why = r?.why ? String(r.why) : "";
      const expected = r?.expected_effect ? String(r.expected_effect) : "";
      const risk = r?.risk ? String(r.risk) : "";
      const bonus = Number.isFinite(Number(r?.suggested_bonus)) ? Math.trunc(Number(r.suggested_bonus)) : null;

      return `
        <div class="border rounded p-2">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div class="fw-semibold">${action}</div>
            ${bonus !== null ? `<span class="badge text-bg-secondary">Бонус: ${bonus}</span>` : ``}
          </div>
          <div class="text-muted small mt-1"><span class="fw-semibold">Цель:</span> ${target}</div>
          ${why ? `<div class="small mt-2"><span class="text-muted">Почему:</span> ${why}</div>` : ``}
          ${expected ? `<div class="small mt-1"><span class="text-muted">Эффект:</span> ${expected}</div>` : ``}
          ${risk ? `<div class="small mt-1"><span class="text-muted">Риск:</span> ${risk}</div>` : ``}

          <div class="d-flex gap-2 mt-2">
            <button class="btn btn-sm btn-primary" type="button" data-ai-act="execute" data-ai-idx="${idx}">
              Выполнить
            </button>
            <button class="btn btn-sm btn-outline-secondary" type="button" data-ai-act="dismiss" data-ai-idx="${idx}">
              Скрыть
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  function inferContext() {
    // default: business
    const page = window.__ADMIN_PAGE__ || "";
    const rawPhone = window.__CLIENT_PHONE__ || "";
    const phone = normalizePhone(rawPhone);

    if (String(page) === "client" && phone) {
      return { context: "client", phone, label: `Контекст: client · ${phone}` };
    }
    return { context: "business", phone: null, label: "Контекст: business" };
  }

  async function ask() {
    clearError();

    const { context, phone, label } = inferContext();
    currentContext = context;
    currentPhone = phone;
    ctxEl.textContent = label;

    const question = String(qEl.value || "").trim();
    if (question.length < 2) {
      setError("Введите вопрос (минимум 2 символа)");
      return;
    }

    setMode("—");
    ansEl.textContent = "Загрузка…";
    renderInsights([]);
    renderRecos([]);
    sendBtn.disabled = true;

    try {
      const payload = { context, question, phone };
      const data = await apiPost("/api/ai/ask", payload);

      setMode(data?.mode || "—");
      ansEl.textContent = data?.answer ? String(data.answer) : "—";
      renderInsights(data?.insights);
      jsrenderAiRecos(data?.recommendations, "aiPanelRecos");

      // Сохраняем контекст для кнопок execute в renderAiRecos
      window.__AI_EXEC_CTX = { context, phone };

      // Показываем блок с ответом
      const ansBlock = document.getElementById("aiAnswerBlock");
      if (ansBlock) ansBlock.classList.remove("d-none");

      if (typeof uiToast === "function") uiToast(`AI ответил (${String(data?.mode || "ai")})`, "info");
    } catch (e) {
      setMode("error");
      ansEl.textContent = "—";
      setError(String(e.message || e));
      if (typeof uiToast === "function") uiToast("AI ошибка", "error");
    } finally {
      sendBtn.disabled = false;
    }
  }

  function clearAll() {
    clearError();
    qEl.value = "";
    ansEl.textContent = "—";
    renderInsights([]);
    renderRecos([]);
    setMode("—");
  }

  // recos click delegation
  boxRecos.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-ai-act]");
    if (!btn) return;

    const act = btn.getAttribute("data-ai-act");
    const idx = Number(btn.getAttribute("data-ai-idx") || "-1");
    if (!Number.isFinite(idx) || idx < 0 || idx >= currentRecos.length) return;

    const r = currentRecos[idx];
    const key = aiRecoKey(currentContext, currentPhone, r);

    if (act === "dismiss") {
      aiDismiss(key);
      renderRecos(currentRecos);
      if (typeof uiToast === "function") uiToast("Рекомендация скрыта", "info");
      return;
    }

    if (act === "execute") {
      if (typeof uiToast === "function") uiToast("Выполняю…", "info");
      await aiExecuteReco(currentContext, currentPhone, r);
    }
  });

  // init context label once
  const initCtx = inferContext();
  currentContext = initCtx.context;
  currentPhone = initCtx.phone;
  ctxEl.textContent = initCtx.label;

  sendBtn.addEventListener("click", ask);
  clearBtn?.addEventListener("click", clearAll);

  qEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      ask();
    }
  });
}

// =========================
// AI Overview Widget (универсально для любых страниц)
// =========================
function initAiOverviewWidget() {
  const btn = document.getElementById("aiReloadBtn");
  const badge = document.getElementById("aiModeBadge");
  const ulInsights = document.getElementById("aiInsights");
  const boxRecos = document.getElementById("aiRecos");
  const errEl = document.getElementById("aiError");

  if (!btn || !badge || !ulInsights || !boxRecos) return;

  let currentContext = "business";
  let currentPhone = null;
  let currentRecos = [];

  function setBadge(mode) {
    const m = String(mode || "—");
    badge.textContent = m;

    badge.classList.remove(
      "text-bg-secondary",
      "text-bg-success",
      "text-bg-warning",
      "text-bg-danger",
      "text-bg-info"
    );
    if (m === "openai") badge.classList.add("text-bg-success");
    else if (m === "gemini") badge.classList.add("text-bg-success"); // на случай старых ответов
    else if (m === "heuristic") badge.classList.add("text-bg-info");
    else if (m === "error") badge.classList.add("text-bg-danger");
    else badge.classList.add("text-bg-secondary");
  }

  function setLoading() {
    hide(errEl);
    setBadge("—");
    ulInsights.innerHTML = `<li class="text-muted">Загрузка…</li>`;
    boxRecos.innerHTML = `<div class="text-muted small">Загрузка…</div>`;
  }

  function showError(msg) {
    if (!errEl) return;
    errEl.textContent = msg || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function renderInsights(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      ulInsights.innerHTML = `<li class="text-muted">Нет инсайтов</li>`;
      return;
    }
    ulInsights.innerHTML = list
      .slice(0, 10)
      .map((s) => `<li>${String(s)}</li>`)
      .join("");
  }

  function renderRecos(items) {
    const list = Array.isArray(items) ? items : [];
    const filtered = list.filter((r) => !aiIsDismissed(aiRecoKey(currentContext, currentPhone, r)));
    currentRecos = filtered;

    if (!filtered.length) {
      boxRecos.innerHTML = `<div class="text-muted small">Нет рекомендаций</div>`;
      return;
    }

    boxRecos.innerHTML = filtered.slice(0, 10).map((r, idx) => {
      const action = r?.action ? String(r.action) : "Действие";
      const target = r?.target ? String(r.target) : "—";
      const why = r?.why ? String(r.why) : "";
      const expected = r?.expected_effect ? String(r.expected_effect) : "";
      const risk = r?.risk ? String(r.risk) : "";
      const bonus = Number.isFinite(Number(r?.suggested_bonus))
        ? Math.trunc(Number(r.suggested_bonus))
        : null;

      return `
        <div class="border rounded p-2">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div class="fw-semibold">${action}</div>
            ${bonus !== null ? `<span class="badge text-bg-secondary">Бонус: ${bonus}</span>` : ``}
          </div>
          <div class="text-muted small mt-1"><span class="fw-semibold">Цель:</span> ${target}</div>
          ${why ? `<div class="small mt-2"><span class="text-muted">Почему:</span> ${why}</div>` : ``}
          ${expected ? `<div class="small mt-1"><span class="text-muted">Эффект:</span> ${expected}</div>` : ``}
          ${risk ? `<div class="small mt-1"><span class="text-muted">Риск:</span> ${risk}</div>` : ``}

          <div class="d-flex gap-2 mt-2">
            <button class="btn btn-sm btn-primary" type="button" data-ai-act="execute" data-ai-idx="${idx}">
              Выполнить
            </button>
            <button class="btn btn-sm btn-outline-secondary" type="button" data-ai-act="dismiss" data-ai-idx="${idx}">
              Скрыть
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  function inferRequest() {
    const page = String(window.__ADMIN_PAGE__ || "");
    const phone = normalizePhone(window.__CLIENT_PHONE__ || "");

    if (page === "client" && phone) {
      currentContext = "client";
      currentPhone = phone;
      return {
        kind: "ask",
        payload: {
          context: "client",
          phone,
          question:
            "Дай персональные инсайты и рекомендации по этому клиенту. Укажи следующий лучший шаг (Next Best Action). " +
            "Пожалуйста, заполняй target как nav:/admin/...."
        }
      };
    }

    currentContext = "business";
    currentPhone = null;
    return { kind: "overview" };
  }

  async function load() {
    setLoading();
    btn.disabled = true;

    try {
      const req = inferRequest();
      const data =
        req.kind === "ask"
          ? await apiPost("/api/ai/ask", req.payload)
          : await apiGet("/api/ai/overview");

      setBadge(data?.mode || "—");
      renderInsights(data?.insights);
      renderRecos(data?.recommendations);

      if (typeof uiToast === "function") {
        const mode = data?.mode ? String(data.mode) : "ai";
        uiToast(`AI обновлён (${mode})`, "info");
      }
    } catch (e) {
      setBadge("error");
      showError(`AI ошибка: ${e.message}`);
      ulInsights.innerHTML = `<li class="text-muted">—</li>`;
      boxRecos.innerHTML = `<div class="text-muted small">—</div>`;
      if (typeof uiToast === "function") uiToast("AI ошибка", "error");
    } finally {
      btn.disabled = false;
    }
  }

  window.__AI_OVERVIEW_RELOAD__ = load;

  // click delegation for recos
  boxRecos.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-ai-act]");
    if (!b) return;

    const act = b.getAttribute("data-ai-act");
    const idx = Number(b.getAttribute("data-ai-idx") || "-1");
    if (!Number.isFinite(idx) || idx < 0 || idx >= currentRecos.length) return;

    const r = currentRecos[idx];
    const key = aiRecoKey(currentContext, currentPhone, r);

    if (act === "dismiss") {
      aiDismiss(key);
      renderRecos(currentRecos);
      if (typeof uiToast === "function") uiToast("Рекомендация скрыта", "info");
      return;
    }

    if (act === "execute") {
      if (typeof uiToast === "function") uiToast("Выполняю…", "info");
      await aiExecuteReco(currentContext, currentPhone, r);
    }
  });

  btn.addEventListener("click", load);
  load();
}

// =========================
// Page: Desktop (/admin)
// =========================
function initDesktopPage() {
  const elNewClients = document.getElementById("dashNewClients");
  const elActiveCampaigns = document.getElementById("dashActiveCampaigns");
  const elCampaignList = document.getElementById("dashCampaignList");

  const elKpiRevenue7 = document.getElementById("dashKpiRevenue7");
  const elKpiRevenue30 = document.getElementById("dashKpiRevenue30");
  const elKpiTx30 = document.getElementById("dashKpiTx30");
  const elKpiAvg30 = document.getElementById("dashKpiAvg30");

  const elAlerts = document.getElementById("dashAlertsList");
  const elSegments = document.getElementById("dashSegmentsList");
  const elUpdatedAt = document.getElementById("dashUpdatedAt");
  const reloadBtn = document.getElementById("dashReloadBtn");

  // today + recent
  const elTodayRevenue = document.getElementById("dashTodayRevenue");
  const elTodayTx = document.getElementById("dashTodayTx");
  const elTodayAvg = document.getElementById("dashTodayAvg");
  const elRecentTx = document.getElementById("dashRecentTxList");

  const any =
    elNewClients || elActiveCampaigns || elCampaignList || elKpiRevenue7 || elAlerts || elSegments || elUpdatedAt ||
    elTodayRevenue || elRecentTx;
  if (!any) return;

  function pickWindow(windows, days) {
    const list = Array.isArray(windows) ? windows : [];
    const d = Number(days);
    return (
      list.find((w) => Number(w?.days) === d) ||
      list.find((w) => String(w?.label || "").includes(String(d))) ||
      null
    );
  }

  function renderCampaigns(list) {
    const arr = Array.isArray(list) ? list : [];
    if (!arr.length) {
      if (elCampaignList) elCampaignList.innerHTML = `<div class="text-muted small">Рекламных кампаний пока нет</div>`;
      if (elActiveCampaigns) elActiveCampaigns.textContent = "0";
      return;
    }

    const active = arr.filter((c) => {
      const st = String(c?.status || "draft");
      return st === "draft" || st === "ready";
    });

    if (elActiveCampaigns) elActiveCampaigns.textContent = fmt0(active.length);

    const sorted = [...arr].sort((a, b) => {
      const ida = safeNum(a?.id ?? 0, 0);
      const idb = safeNum(b?.id ?? 0, 0);
      return idb - ida;
    });

    const top = sorted.slice(0, 4);
    if (!elCampaignList) return;

    elCampaignList.innerHTML = top
      .map((c) => {
        const id = c?.id ?? "—";
        const name = c?.name ? String(c.name) : `Рекламная кампания #${id}`;
        const st = String(c?.status || "draft");
        const seg = c?.segment_key ? String(c.segment_key) : "—";
        return `
          <a class="dash-item" href="/admin/campaigns/${id}">
            <i class="bi bi-megaphone"></i>
            <div class="flex-grow-1">
              <div class="fw-semibold">${name}</div>
              <div class="meta">Сегмент: ${seg} · Статус: ${st}</div>
            </div>
            <i class="bi bi-chevron-right ms-auto"></i>
          </a>
        `;
      })
      .join("");
  }

  function renderAlerts(alerts) {
    const list = Array.isArray(alerts) ? alerts : [];
    if (!elAlerts) return;

    if (!list.length) {
      elAlerts.innerHTML = `<div class="text-muted small">Алертов нет</div>`;
      return;
    }

    elAlerts.innerHTML = list.slice(0, 6).map((a) => {
      const title = a?.title ? String(a.title) : "Алерт";
      const hint = a?.hint ? String(a.hint) : "";
      const cnt = fmt0(a?.count ?? 0);
      const href = a?.href ? String(a.href) : "/admin/analytics";
      const level = String(a?.level || "info");

      const badge =
        level === "danger"
          ? "text-bg-danger"
          : level === "warning"
          ? "text-bg-warning text-dark"
          : "text-bg-secondary";

      return `
        <a class="dash-item" href="${href}">
          <i class="bi bi-bell"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${title}</div>
            ${hint ? `<div class="meta">${hint}</div>` : ``}
          </div>
          <span class="badge ${badge}">${cnt}</span>
        </a>
      `;
    }).join("");
  }

  function renderSegments(segments) {
    const list = Array.isArray(segments) ? segments : [];
    if (!elSegments) return;

    if (!list.length) {
      elSegments.innerHTML = `<div class="text-muted small">Сегментов нет</div>`;
      return;
    }

    elSegments.innerHTML = list.slice(0, 6).map((s) => {
      const key = s?.key ? String(s.key) : "";
      const title = s?.title ? String(s.title) : "Сегмент";
      const cnt = fmt0(s?.clients ?? 0);
      const hint = s?.hint ? String(s.hint) : "";
      const href = key ? `/admin/analytics/segment/${encodeURIComponent(key)}` : "/admin/analytics";

      return `
        <a class="dash-item" href="${href}">
          <i class="bi bi-people"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${title}</div>
            ${hint ? `<div class="meta">${hint}</div>` : ``}
          </div>
          <span class="badge text-bg-secondary">${cnt}</span>
        </a>
      `;
    }).join("");
  }

  function renderRecentTx(list) {
    if (!elRecentTx) return;
    const arr = Array.isArray(list) ? list : [];
    if (!arr.length) {
      elRecentTx.innerHTML = `<div class="text-muted small">Транзакций пока нет</div>`;
      return;
    }

    const top = arr.slice(0, 6);
    elRecentTx.innerHTML = top.map((t) => {
      const phone = String(t?.user_phone || "—");
      const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
      const created = t?.created_at ? fmtDate(t.created_at) : "—";
      const redeem = fmt0(getRedeem(t));
      const earned = fmt0(getEarned(t));
      return `
        <a class="dash-item" href="/admin/client/${encodeURIComponent(phone)}">
          <i class="bi bi-receipt"></i>
          <div class="flex-grow-1">
            <div class="fw-semibold">${fmtMoney(paid)} ₸ · ${phone}</div>
            <div class="meta">${created} · списано ${redeem} · начислено ${earned}</div>
          </div>
          <i class="bi bi-chevron-right ms-auto"></i>
        </a>
      `;
    }).join("");
  }

  function computeToday(txList) {
    const today = ymdLocal(new Date());
    let sum = 0;
    let cnt = 0;

    (Array.isArray(txList) ? txList : []).forEach((t) => {
      const dt = t?.created_at ? new Date(t.created_at) : null;
      if (!dt || Number.isNaN(dt.getTime())) return;
      if (ymdLocal(dt) !== today) return;
      const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
      sum += paid;
      cnt += 1;
    });

    const avg = cnt > 0 ? sum / cnt : 0;
    return { sum, cnt, avg };
  }

  async function load() {
    if (reloadBtn) reloadBtn.disabled = true;

    try {
      // analytics overview for KPI + alerts + segments
      const an = await apiGet("/api/analytics/overview");

      const win7 = pickWindow(an?.windows, 7);
      const win30 = pickWindow(an?.windows, 30);

      if (elKpiRevenue7) elKpiRevenue7.textContent = fmtMoney(win7?.revenue ?? 0);
      if (elKpiRevenue30) elKpiRevenue30.textContent = fmtMoney(win30?.revenue ?? 0);
      if (elKpiTx30) elKpiTx30.textContent = fmt0(win30?.transactions ?? 0);

      const tx30 = safeNum(win30?.transactions ?? 0, 0);
      const rev30 = safeNum(win30?.revenue ?? 0, 0);
      const avg30 =
        Number.isFinite(Number(win30?.avg_check)) ? safeNum(win30?.avg_check, 0) : (tx30 > 0 ? rev30 / tx30 : 0);
      if (elKpiAvg30) elKpiAvg30.textContent = fmtMoney(avg30);

      // new clients (segment "new" if present)
      const segs = Array.isArray(an?.segments) ? an.segments : [];
      const segNew = segs.find((s) => String(s?.key || "") === "new");
      if (elNewClients) elNewClients.textContent = fmt0(segNew?.clients ?? 0);

      renderAlerts(an?.alerts);
      renderSegments(an?.segments);

      if (elUpdatedAt) elUpdatedAt.textContent = fmtDate(new Date());
    } catch (e) {
      if (elUpdatedAt) elUpdatedAt.textContent = "Ошибка обновления";
      if (elAlerts) elAlerts.innerHTML = `<div class="text-danger small">Ошибка: ${String(e.message || e)}</div>`;
      if (elSegments) elSegments.innerHTML = `<div class="text-danger small">Ошибка: ${String(e.message || e)}</div>`;
    }

    try {
      // campaigns list for right panel
      const cps = await apiGet("/api/campaigns/");
      renderCampaigns(cps);
    } catch (e) {
      if (elCampaignList) elCampaignList.innerHTML = `<div class="text-danger small">Ошибка кампаний: ${String(e.message || e)}</div>`;
      if (elActiveCampaigns) elActiveCampaigns.textContent = "—";
    }

    try {
      // recent transactions + today metrics
      const tx = await apiGet("/api/transactions/?limit=200&offset=0");
      const list = Array.isArray(tx) ? tx : [];

      // render recent
      renderRecentTx(list);

      // compute today
      const today = computeToday(list);
      if (elTodayRevenue) elTodayRevenue.textContent = `${fmtMoney(today.sum)} ₸`;
      if (elTodayTx) elTodayTx.textContent = fmt0(today.cnt);
      if (elTodayAvg) elTodayAvg.textContent = `${fmtMoney(today.avg)} ₸`;
    } catch (e) {
      if (elRecentTx) elRecentTx.innerHTML = `<div class="text-danger small">Ошибка транзакций: ${String(e.message || e)}</div>`;
      if (elTodayRevenue) elTodayRevenue.textContent = "—";
      if (elTodayTx) elTodayTx.textContent = "—";
      if (elTodayAvg) elTodayAvg.textContent = "—";
    }

    if (reloadBtn) reloadBtn.disabled = false;
  }

  reloadBtn?.addEventListener("click", async () => {
    await load();
    if (typeof window.__AI_OVERVIEW_RELOAD__ === "function") window.__AI_OVERVIEW_RELOAD__();
  });

  load();
  initDashFeed();
  initDashTasks();
}

// ── Feed (лента событий) ──────────────────────────────────
function initDashFeed() {
  const box = document.getElementById("dashFeedList");
  const filters = document.querySelectorAll(".feed-filter-btn");
  if (!box) return;

  let allItems = [];
  let activeType = "";

  function feedIcon(type) {
    if (type === "earn") return `<span class="feed-icon earn"><i class="bi bi-plus-circle-fill"></i></span>`;
    if (type === "redeem") return `<span class="feed-icon redeem"><i class="bi bi-dash-circle-fill"></i></span>`;
    if (type === "alert") return `<span class="feed-icon alert-icon"><i class="bi bi-bell-fill"></i></span>`;
    return `<span class="feed-icon other"><i class="bi bi-dot"></i></span>`;
  }

  function renderFeed(items) {
    const filtered = activeType ? items.filter((i) => i.type === activeType) : items;

    if (!filtered.length) {
      box.innerHTML = `<div class="text-muted small">Событий нет</div>`;
      return;
    }

    box.innerHTML = filtered.map((item) => {
      const amount = item.amount ? `${Number(item.amount).toLocaleString("ru-RU")} ₸` : "";
      const bonusValue = item.bonus ?? "";
      const bonusNumber = Number(bonusValue);
      const bonusText = Number.isFinite(bonusNumber)
        ? `${bonusNumber > 0 ? "+" : ""}${bonusNumber}`
        : String(bonusValue || "");
      const bonus = bonusText
        ? `<span class="ms-1 badge text-bg-secondary">${bonusText}</span>`
        : "";
      const time = item.time
        ? `<span class="text-muted" style="font-size:.75rem;margin-left:auto">${item.time}</span>`
        : "";
      const phone = item.phone
        ? `<a class="text-muted small text-decoration-none" href="/admin/client/${encodeURIComponent(item.phone)}">${item.phone}</a>`
        : "";

      return `
        <div class="feed-item">
          ${feedIcon(item.type)}
          <div class="feed-body">
            <div class="d-flex align-items-center gap-1 flex-wrap">
              <span class="feed-title">${item.title || "Событие"}</span>
              ${bonus}
              ${time}
            </div>
            <div class="d-flex align-items-center gap-2">
              ${phone}
              ${amount ? `<span class="text-muted small">${amount}</span>` : ""}
            </div>
          </div>
        </div>`;
    }).join("");
  }

  async function loadFeed() {
    box.innerHTML = `<div class="text-muted small">Загрузка…</div>`;
    try {
      const today = new Date().toISOString().slice(0, 10);
      const data = await apiGet(`/api/transactions/?date_from=${today}&date_to=${today}&limit=50`);
      const txs = Array.isArray(data) ? data : (data.items || data.transactions || []);

      allItems = [];

      try {
        const an = await apiGet("/api/analytics/overview");
        (an.alerts || []).forEach((a) => {
          allItems.push({
            type: "alert",
            title: a.title || "Алерт",
            time: "",
            phone: "",
            bonus: Number(a.count || 0),
          });
        });
      } catch {
        // ignore analytics errors for feed
      }

      txs.forEach((tx) => {
        const earned = Number(tx.earned_points ?? tx.earned_bonus ?? 0);
        const redeem = Number(tx.redeem_points ?? tx.redeem_bonus ?? 0);
        const amount = Number(tx.paid_amount ?? tx.amount ?? 0);
        const phone = tx.user_phone || "";
        const dt = tx.created_at
          ? new Date(tx.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
          : "";

        if (earned > 0) {
          allItems.push({
            type: "earn",
            title: "Начисление бонусов",
            phone,
            time: dt,
            amount,
            bonus: earned,
          });
        }
        if (redeem > 0) {
          allItems.push({
            type: "redeem",
            title: "Списание бонусов",
            phone,
            time: dt,
            amount,
            bonus: -redeem,
          });
        }
        if (earned === 0 && redeem === 0) {
          allItems.push({
            type: "other",
            title: "Транзакция",
            phone,
            time: dt,
            amount,
          });
        }
      });

      renderFeed(allItems);
    } catch (e) {
      box.innerHTML = `<div class="text-muted small">Ошибка: ${e.message}</div>`;
    }
  }

  filters.forEach((btn) => {
    btn.addEventListener("click", () => {
      filters.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeType = btn.dataset.type || "";
      renderFeed(allItems);
    });
  });

  loadFeed();
  document.getElementById("dashReloadBtn")?.addEventListener("click", loadFeed);
}

// ── Tasks (задачи) ────────────────────────────────────────
const TASKS_KEY = "ltv_tasks_v1";

function loadTasksFromStorage() {
  try {
    return JSON.parse(localStorage.getItem(TASKS_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveTasksToStorage(tasks) {
  try {
    localStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
  } catch {
    // ignore
  }
}

function initDashTasks() {
  const role = window.__USER_ROLE__ || "owner";
  const addBtn = document.getElementById("taskAddBtn");
  const form = document.getElementById("taskAddForm");
  const saveBtn = document.getElementById("taskSaveBtn");
  const cancelBtn = document.getElementById("taskCancelBtn");
  const taskText = document.getElementById("taskText");
  const assignSel = document.getElementById("taskAssignee");
  const tasksList = document.getElementById("tasksList");
  const errEl = document.getElementById("taskErr");
  const staffList = document.getElementById("staffTasksList");

  async function loadStaff() {
    if (!assignSel) return;
    try {
      const data = await apiGet("/api/accounts/users");
      const users = Array.isArray(data) ? data : (data.users || []);
      users.filter((u) => u.role !== "owner").forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u.phone || u.id;
        opt.textContent = `${u.name || u.phone} (${u.role})`;
        assignSel.appendChild(opt);
      });
    } catch {
      // ignore
    }
  }

  function renderTasks(box, tasks, isStaff = false) {
    if (!box) return;

    const withIndex = (Array.isArray(tasks) ? tasks : []).map((t, idx) => ({ t, idx }));
    const myPhone = String(window.__USER_PHONE__ || "");
    const rows = isStaff
      ? withIndex.filter(({ t }) => !t.assignee || String(t.assignee) === myPhone)
      : withIndex;

    if (!rows.length) {
      box.innerHTML = `<div class="text-muted small">Задач нет</div>`;
      return;
    }

    box.innerHTML = rows.map(({ t, idx }) => `
      <div class="task-item ${t.done ? "done" : ""}">
        <button class="task-check ${t.done ? "checked" : ""}"
                onclick="toggleTask(${idx})"
                title="${t.done ? "Отменить" : "Выполнено"}">
          <i class="bi bi-${t.done ? "check-circle-fill" : "circle"}"></i>
        </button>
        <div class="task-body">
          <div class="task-text">${t.text || "—"}</div>
          ${t.assignee ? `<div class="task-meta">${t.assignee}</div>` : ""}
        </div>
        ${!isStaff ? `
        <button class="task-del" onclick="deleteTask(${idx})" title="Удалить">
          <i class="bi bi-x"></i>
        </button>` : ""}
      </div>
    `).join("");
  }

  window.toggleTask = function toggleTask(idx) {
    const tasks = loadTasksFromStorage();
    if (tasks[idx]) tasks[idx].done = !tasks[idx].done;
    saveTasksToStorage(tasks);
    if (role === "staff") renderTasks(staffList, tasks, true);
    else renderTasks(tasksList, tasks);
  };

  window.deleteTask = function deleteTask(idx) {
    const tasks = loadTasksFromStorage();
    tasks.splice(idx, 1);
    saveTasksToStorage(tasks);
    renderTasks(tasksList, tasks);
  };

  if (role !== "staff" && tasksList) {
    renderTasks(tasksList, loadTasksFromStorage());
    loadStaff();

    addBtn?.addEventListener("click", () => {
      form?.classList.toggle("d-none");
      taskText?.focus();
    });

    cancelBtn?.addEventListener("click", () => form?.classList.add("d-none"));

    saveBtn?.addEventListener("click", () => {
      const text = (taskText?.value || "").trim();
      if (!text) {
        if (errEl) {
          errEl.textContent = "Введите текст задачи";
          errEl.classList.remove("d-none");
        }
        return;
      }
      if (errEl) errEl.classList.add("d-none");

      const tasks = loadTasksFromStorage();
      tasks.unshift({
        text,
        assignee: assignSel?.value || "",
        done: false,
        created: new Date().toISOString(),
      });
      saveTasksToStorage(tasks);
      renderTasks(tasksList, tasks);

      if (taskText) taskText.value = "";
      if (assignSel) assignSel.value = "";
      form?.classList.add("d-none");
      uiToast("Задача добавлена", "success");
    });
  }

  if (role === "staff" && staffList) {
    renderTasks(staffList, loadTasksFromStorage(), true);
  }
}

// =========================
// Page: News (/admin/news)
// =========================
function initNewsPage() {
  const feed = document.getElementById("newsFeed");
  const updatedAt = document.getElementById("newsUpdatedAt");
  const reloadBtn = document.getElementById("newsReloadBtn");
  if (!feed) return;

  let currentFilter = "all";

  function setActiveFilter(val) {
    currentFilter = val;
    document.querySelectorAll("[data-news-filter]").forEach((b) => {
      const f = b.getAttribute("data-news-filter");
      b.classList.toggle("active", f === val);
    });
  }

  function item(icon, title, meta, href, kind) {
    const k = kind ? `data-kind="${kind}"` : "";
    const tagOpen = href ? `<a class="dash-item" href="${href}" ${k}>` : `<div class="dash-item" ${k}>`;
    const tagClose = href ? `</a>` : `</div>`;
    return `
      ${tagOpen}
        <i class="bi ${icon}"></i>
        <div class="flex-grow-1">
          <div class="fw-semibold">${title}</div>
          <div class="meta">${meta}</div>
        </div>
        <i class="bi bi-chevron-right ms-auto"></i>
      ${tagClose}
    `;
  }

  function applyFilterHtml(html) {
    // simple: rebuild by filtering rendered nodes
    const wrap = document.createElement("div");
    wrap.innerHTML = html;
    const nodes = [...wrap.querySelectorAll(".dash-item")];

    const filtered = nodes.filter((n) => {
      const k = n.getAttribute("data-kind") || "all";
      if (currentFilter === "all") return true;
      return k === currentFilter;
    });

    if (!filtered.length) {
      feed.innerHTML = `<div class="text-muted small">Нет событий по фильтру</div>`;
      return;
    }
    feed.innerHTML = filtered.map((n) => n.outerHTML).join("");
  }

  async function load() {
    if (reloadBtn) reloadBtn.disabled = true;
    feed.innerHTML = `<div class="text-muted small">Загрузка…</div>`;

    let html = "";

    try {
      const an = await apiGet("/api/analytics/overview");
      const alerts = Array.isArray(an?.alerts) ? an.alerts : [];
      if (alerts.length) {
        html += `<div class="text-muted small mt-1">Алерты</div>`;
        html += alerts.slice(0, 6).map((a) => {
          const title = String(a?.title || "Алерт");
          const meta = String(a?.hint || "");
          const cnt = fmt0(a?.count ?? 0);
          const href = String(a?.href || "/admin/analytics");
          return item("bi-bell", `${title} · ${cnt}`, meta || "—", href, "al");
        }).join("");
      }
    } catch {
      // ignore
    }

    try {
      const cps = await apiGet("/api/campaigns/");
      const list = Array.isArray(cps) ? cps : [];
      html += `<div class="text-muted small mt-3">Кампании</div>`;
      if (!list.length) {
        html += `<div class="text-muted small">Рекламных кампаний пока нет</div>`;
      } else {
        const top = [...list].sort((a,b)=>safeNum(b?.id,0)-safeNum(a?.id,0)).slice(0, 6);
        html += top.map((c) => {
          const id = c?.id ?? "—";
          const name = String(c?.name || `Рекламная кампания #${id}`);
          const seg = String(c?.segment_key || "—");
          const st = String(c?.status || "draft");
          return item("bi-megaphone", name, `Сегмент: ${seg} · Статус: ${st}`, `/admin/campaigns/${id}`, "cp");
        }).join("");
      }
    } catch {
      // ignore
    }

    try {
      const tx = await apiGet("/api/transactions/?limit=30&offset=0");
      const list = Array.isArray(tx) ? tx : [];
      html += `<div class="text-muted small mt-3">Транзакции</div>`;
      if (!list.length) {
        html += `<div class="text-muted small">Транзакций пока нет</div>`;
      } else {
        html += list.slice(0, 10).map((t) => {
          const phone = String(t?.user_phone || "—");
          const paid = safeNum(t?.paid_amount ?? t?.amount ?? 0, 0);
          const dt = t?.created_at ? fmtDate(t.created_at) : "—";
          return item("bi-receipt", `${fmtMoney(paid)} ₸ · ${phone}`, dt, `/admin/client/${encodeURIComponent(phone)}`, "tx");
        }).join("");
      }
    } catch {
      // ignore
    }

    if (!html.trim()) html = `<div class="text-muted small">Нет данных</div>`;
    if (updatedAt) updatedAt.textContent = fmtDate(new Date());

    applyFilterHtml(html);
    if (reloadBtn) reloadBtn.disabled = false;
  }

  document.querySelectorAll("[data-news-filter]").forEach((b) => {
    b.addEventListener("click", () => {
      setActiveFilter(b.getAttribute("data-news-filter") || "all");
      // rerender by re-loading to keep simple and consistent
      load();
    });
  });

  reloadBtn?.addEventListener("click", load);

  setActiveFilter("all");
  load();
}

// =========================
// Page: Analytics (/admin/analytics)
// =========================
// =========================
// Page: Analytics (/admin/analytics)
// ПОЛНАЯ ЗАМЕНА initAnalyticsPage()
// =========================
// =========================
// Page: Analytics — ПОЛНАЯ ЗАМЕНА initAnalyticsPage()
// Периоды: 7/14/30/60/90/180/365 дней
// Полная ширина: график + сводка
// Сегменты внизу
// =========================
function initAnalyticsPage() {

  let revenueChart = null;
  let segmentChart = null;
  let overviewData = null;
  let currentPeriod = 30;

  // ── Chart colors ──────────────────────────────────
  const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";

  function chartColors() {
    return {
      grid:   isDark() ? "rgba(255,255,255,.06)" : "rgba(0,0,0,.06)",
      text:   isDark() ? "rgba(255,255,255,.45)" : "rgba(0,0,0,.45)",
      mint:   "#35c37d",
      mintBg: isDark() ? "rgba(53,195,125,.15)" : "rgba(53,195,125,.10)",
    };
  }

  // ── Revenue Chart ─────────────────────────────────
  function buildRevenueChart(daily) {
    const ctx = document.getElementById("anRevenueChart");
    if (!ctx || typeof Chart === "undefined") return;

    const labels = (daily || []).map(d => {
      const parts = (d.day || "").split("-");
      return `${parts[2]}.${parts[1]}`;
    });
    const values = (daily || []).map(d => d.revenue || 0);
    const c = chartColors();

    if (revenueChart) revenueChart.destroy();

    revenueChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Выручка ₸",
          data: values,
          borderColor: c.mint,
          backgroundColor: c.mintBg,
          borderWidth: 2,
          pointRadius: values.length > 60 ? 0 : 3,
          pointBackgroundColor: c.mint,
          fill: true,
          tension: 0.4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${Number(ctx.raw).toLocaleString("ru-RU")} ₸`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: c.grid },
            ticks: {
              color: c.text,
              maxTicksLimit: 12,
              font: { size: 11 },
            },
          },
          y: {
            grid: { color: c.grid },
            ticks: {
              color: c.text,
              font: { size: 11 },
              callback: v => Number(v).toLocaleString("ru-RU"),
            },
          },
        },
      },
    });
  }

  // ── Segment Doughnut ──────────────────────────────
  const SEG_COLORS = {
    vip: "#f59e0b", active: "#35c37d", risk: "#f97316",
    lost: "#ef4444", new: "#6366f1", all: "#64748b",
  };

  function buildSegmentChart(segments) {
    const ctx = document.getElementById("anSegmentChart");
    if (!ctx || typeof Chart === "undefined") return;

    const filtered = (segments || []).filter(s => s.key !== "all" && (s.clients || 0) > 0);
    if (!filtered.length) return;

    if (segmentChart) segmentChart.destroy();
    const c = chartColors();

    segmentChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: filtered.map(s => s.title),
        datasets: [{
          data: filtered.map(s => s.clients),
          backgroundColor: filtered.map(s => SEG_COLORS[s.key] || "#94a3b8"),
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "65%",
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.label}: ${ctx.raw} клиентов`,
            },
          },
        },
      },
    });
  }

  // ── KPI Cards ─────────────────────────────────────
  function fillKpi(data, period) {
    const windows = data.windows || [];
    const w = windows.find(w => w.days === period)
           || windows.find(w => w.days === 30)
           || {};

    const el = id => document.getElementById(id);

    if (el("anClientsTotal"))
      el("anClientsTotal").textContent = (data.clients_total || 0).toLocaleString("ru-RU");

    if (el("anActiveClients"))
      el("anActiveClients").textContent = (data.users_with_tx || w.clients || 0).toLocaleString("ru-RU");

    if (el("anRevenue30"))
      el("anRevenue30").textContent = (w.revenue || 0).toLocaleString("ru-RU");

    if (el("anAvgCheck30"))
      el("anAvgCheck30").textContent = Math.round(w.avg_check || 0).toLocaleString("ru-RU");

    // Подписи периода
    const periodLabels = {
      7: "7 дней", 14: "14 дней", 30: "30 дней",
      60: "60 дней", 90: "90 дней", 180: "6 мес", 365: "год",
    };
    const pLabel = periodLabels[period] || `${period} дн`;
    ["anActivePeriodLabel", "anRevenuePeriodLabel", "anAvgPeriodLabel"].forEach(id => {
      const e = el(id);
      if (e) e.textContent = `за ${pLabel}`;
    });

    // Мини-статистика под графиком
    if (el("anPeriodRevenue"))
      el("anPeriodRevenue").textContent = (w.revenue || 0).toLocaleString("ru-RU") + " ₸";
    if (el("anPeriodTx"))
      el("anPeriodTx").textContent = (w.transactions || 0).toLocaleString("ru-RU");
    if (el("anPeriodClients"))
      el("anPeriodClients").textContent = (w.clients || 0).toLocaleString("ru-RU");
  }

  // ── Windows table ─────────────────────────────────
  function renderWindows(windows) {
    const tbody = document.getElementById("anWindowsTbody");
    if (!tbody) return;

    if (!windows || !windows.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-muted">Нет данных</td></tr>`;
      return;
    }

    tbody.innerHTML = windows.map(w => `
      <tr>
        <td class="fw-semibold">${w.label || w.days + " дн"}</td>
        <td class="text-end">${(w.revenue || 0).toLocaleString("ru-RU")} ₸</td>
        <td class="text-end">${(w.transactions || 0).toLocaleString("ru-RU")}</td>
        <td class="text-end">${(w.clients || 0).toLocaleString("ru-RU")}</td>
        <td class="text-end">${Math.round(w.avg_check || 0).toLocaleString("ru-RU")} ₸</td>
      </tr>
    `).join("");
  }

  // ── Alerts ────────────────────────────────────────
  function renderAlerts(alerts) {
    const box = document.getElementById("anAlertsBox");
    if (!box) return;

    if (!alerts || !alerts.length) {
      box.innerHTML = `<div class="text-muted small">Нет активных алертов 🎉</div>`;
      return;
    }

    const icons = { info: "bi-info-circle", warning: "bi-exclamation-triangle", danger: "bi-x-circle" };

    box.innerHTML = alerts.map(a => `
      <a href="${a.href || '#'}" class="an-alert-item ${a.level || 'info'}">
        <i class="bi ${icons[a.level] || 'bi-info-circle'} an-alert-icon"></i>
        <div>
          <div class="an-alert-title">${a.title}</div>
          <div class="an-alert-hint">${a.hint || ''}</div>
        </div>
        <span class="an-alert-count">${a.count || 0}</span>
      </a>
    `).join("");
  }

  // ── Segments list ─────────────────────────────────
  function renderSegments(segments) {
    const box = document.getElementById("anSegmentsBox");
    if (!box) return;

    box.innerHTML = (segments || []).map(s => {
      const color = SEG_COLORS[s.key] || "#64748b";
      return `
        <a href="/admin/analytics/segment/${s.key}" class="an-segment-row">
          <div class="an-segment-dot" style="background:${color}"></div>
          <div class="an-segment-info">
            <div class="an-segment-name">${s.title}</div>
            <div class="an-segment-hint">${s.hint || ''}</div>
          </div>
          <div class="an-segment-count">${(s.clients || 0).toLocaleString("ru-RU")}</div>
          <i class="bi bi-chevron-right text-muted" style="font-size:.8rem"></i>
        </a>
      `;
    }).join("");
  }

  // ── Chart subtitle ────────────────────────────────
  function setChartSubtitle(label) {
    const el = document.getElementById("anChartSubtitle");
    if (el) el.textContent = label;
  }

  // ── Apply period ──────────────────────────────────
  function applyPeriod(period) {
    if (!overviewData) return;
    currentPeriod = period;

    const daily = overviewData.daily_30 || [];
    const since = new Date();
    since.setDate(since.getDate() - period);

    // Фильтруем только если данных достаточно, иначе берём все
    const filtered = daily.length > period
      ? daily.filter(d => new Date(d.day) >= since)
      : daily;

    buildRevenueChart(filtered);
    fillKpi(overviewData, period);

    const labels = {
      7: "7 дней", 14: "14 дней", 30: "30 дней",
      60: "60 дней", 90: "90 дней", 180: "6 месяцев", 365: "Год"
    };
    setChartSubtitle(`Последние ${labels[period] || period + " дней"}`);
  }

  // ── Period buttons ────────────────────────────────
  document.querySelectorAll(".an-period-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".an-period-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      applyPeriod(parseInt(btn.dataset.period));
    });
  });

  // ── Load ──────────────────────────────────────────
  async function load() {
    const reloadBtn = document.getElementById("anReloadBtn");
    if (reloadBtn) { reloadBtn.disabled = true; }

    try {
      const data = await apiGet("/api/analytics/overview");
      overviewData = data;

      fillKpi(data, currentPeriod);
      renderWindows(data.windows);
      renderAlerts(data.alerts);
      renderSegments(data.segments);
      buildSegmentChart(data.segments);
      applyPeriod(currentPeriod);

    } catch (e) {
      if (typeof uiToast === "function") uiToast(`Ошибка загрузки: ${e.message}`, "error");
    } finally {
      if (reloadBtn) { reloadBtn.disabled = false; }
    }
  }

  document.getElementById("anReloadBtn")?.addEventListener("click", load);

  // Перестраиваем при смене темы
  document.getElementById("themeToggle")?.addEventListener("click", () => {
    setTimeout(() => {
      if (overviewData) {
        applyPeriod(currentPeriod);
        buildSegmentChart(overviewData.segments);
      }
    }, 100);
  });

  load();
}

// =========================
// Page: Campaigns (/admin/campaigns)
// =========================

// Global helper — используется в campaigns и campaign_detail
function badgeStatus(s) {
  const st = String(s || "draft");
  if (st === "ready") return "text-bg-success";
  if (st === "sent") return "text-bg-secondary";
  return "text-bg-warning text-dark";
}

function initCampaignsPage() {
  const tbody = document.getElementById("cpTbody");
  if (!tbody) return;

  const msgEl = document.getElementById("cpMsg");

  const openBtn = document.getElementById("cpOpenCreateBtn");
  const closeBtn = document.getElementById("cpCloseCreateBtn");
  const box = document.getElementById("cpCreateBox");
  const errEl = document.getElementById("cpCreateErr");

  const fName = document.getElementById("cpName");
  const fSeg = document.getElementById("cpSegment");
  const fR = document.getElementById("cpR");
  const fF = document.getElementById("cpF");
  const fM = document.getElementById("cpM");
  const fBonus = document.getElementById("cpBonus");
  const fQ = document.getElementById("cpQ");
  const fSort = document.getElementById("cpSort");
  const fNote = document.getElementById("cpNote");
  const createBtn = document.getElementById("cpCreateBtn");

  function setMsg(text) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
  }

  function showErr(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }

  function hideErr() {
    if (!errEl) return;
    errEl.classList.add("d-none");
  }

  function row(c) {
    const id = c?.id ?? "—";
    const name = c?.name || "—";
    const seg = c?.segment_key || "—";
    const bonus = safeNum(c?.suggested_bonus ?? 0, 0);
    const st = c?.status || "draft";
    const total = safeNum(c?.recipients_total ?? 0, 0);
    const created = fmtDate(c?.created_at);

    return `
      <tr>
        <td>${id}</td>
        <td>${String(name)}</td>
        <td><span class="badge text-bg-secondary">${String(seg)}</span></td>
        <td class="text-end">${fmtMoney(bonus)}</td>
        <td><span class="badge ${badgeStatus(st)}">${String(st)}</span></td>
        <td class="text-end">${fmt0(total)}</td>
        <td class="text-muted">${created}</td>
        <td class="text-end">
          <a class="btn btn-sm btn-outline-primary" href="/admin/campaigns/${id}">Открыть</a>
        </td>
      </tr>
    `;
  }

  async function load() {
    try {
      const data = await apiGet("/api/campaigns/");
      const list = Array.isArray(data) ? data : [];
      if (!list.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-muted">Рекламных кампаний пока нет</td></tr>`;
        return;
      }
      tbody.innerHTML = list.map(row).join("");
      setMsg(`Рекламных кампаний: ${fmt0(list.length)}`);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-danger">Ошибка: ${String(e.message || e)}</td></tr>`;
    }
  }

  function openCreate() {
    hideErr();
    box?.classList.remove("d-none");
  }
  function closeCreate() {
    hideErr();
    box?.classList.add("d-none");
  }

  // ✅ prefill from query params (для AI "Выполнить")
  function tryPrefillFromQuery() {
    const name = getQueryParam("name");
    const segment_key = getQueryParam("segment_key") || getQueryParam("segment");
    const bonus = getQueryParam("bonus");

    if (!name && !segment_key && !bonus) return;

    openCreate();
    if (fName && name) fName.value = String(name);
    if (fSeg && segment_key) fSeg.value = String(segment_key);
    if (fBonus && bonus !== null && bonus !== undefined && bonus !== "") fBonus.value = String(Math.trunc(safeNum(bonus, 0)));

    // очистим URL (чтобы не повторялось при refresh)
    try {
      const u = new URL(window.location.href);
      u.searchParams.delete("name");
      u.searchParams.delete("segment");
      u.searchParams.delete("segment_key");
      u.searchParams.delete("bonus");
      window.history.replaceState({}, "", u.pathname + (u.searchParams.toString() ? "?" + u.searchParams.toString() : ""));
    } catch {
      // ignore
    }
  }

  openBtn?.addEventListener("click", openCreate);
  closeBtn?.addEventListener("click", closeCreate);

  createBtn?.addEventListener("click", async () => {
    hideErr();

    const name = String(fName?.value || "").trim();
    const segment_key = String(fSeg?.value || "").trim();
    if (!name) return showErr("Укажи название рекламной кампании");
    if (!segment_key) return showErr("Укажи сегмент");

    const payload = {
      name,
      segment_key,
      r_min: fR?.value ? Number(fR.value) : null,
      f_min: fF?.value ? Number(fF.value) : null,
      m_min: fM?.value ? Number(fM.value) : null,
      q: (fQ?.value || "").trim() || null,
      sort: (fSort?.value || "").trim() || null,
      suggested_bonus: Math.trunc(safeNum(fBonus?.value, 0)),
      note: (fNote?.value || "").trim() || null,
    };

    try {
      createBtn.disabled = true;
      const created = await apiPost("/api/campaigns/", payload);
      if (typeof uiToast === "function") uiToast("Рекламная кампания создана", "success");

      if (fName) fName.value = "";
      if (fBonus) fBonus.value = "0";
      if (fQ) fQ.value = "";
      if (fNote) fNote.value = "";
      if (fR) fR.value = "";
      if (fF) fF.value = "";
      if (fM) fM.value = "";

      closeCreate();
      await load();

      if (created?.id) window.location.href = `/admin/campaigns/${created.id}`;
    } catch (e) {
      showErr(String(e.message || e));
      if (typeof uiToast === "function") uiToast("Ошибка создания рекламной кампании", "error");
    } finally {
      createBtn.disabled = false;
    }
  });

  load();
  tryPrefillFromQuery();
}

// =========================
// Page: Campaign detail (/admin/campaigns/{id})
// =========================
function initCampaignDetailPage() {
  const id = Number(window.__CAMPAIGN_ID__ || 0);
  if (!id) return;

  const titleEl = document.getElementById("cdTitle");
  const metaEl = document.getElementById("cdMeta");
  const msgEl = document.getElementById("cdMsg");
  const errEl = document.getElementById("cdErr");
  const tbody = document.getElementById("cdTbody");

  const reloadBtn = document.getElementById("cdReloadBtn");
  const buildBtn = document.getElementById("cdBuildBtn");

  if (!tbody) return;

  function setMsg(text) {
    if (!msgEl) return;
    msgEl.textContent = text || "";
  }

  function showErr(text) {
    if (!errEl) return;
    errEl.textContent = text || "Ошибка";
    errEl.classList.remove("d-none");
  }
  function hideErr() {
    if (!errEl) return;
    errEl.classList.add("d-none");
  }


  async function load() {
    hideErr();
    tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Загрузка…</td></tr>`;

    try {
      const data = await apiGet(`/api/campaigns/${id}`);
      const c = data?.campaign;

      if (titleEl) titleEl.textContent = c?.name || `Кампания #${id}`;
      if (metaEl) {
        const seg = c?.segment_key || "—";
        const st = c?.status || "draft";
        const bonus = fmtMoney(c?.suggested_bonus ?? 0);
        const total = fmt0(data?.recipients_total ?? 0);
        metaEl.textContent = `Сегмент: ${seg} · Статус: ${st} · Бонус: ${bonus} · Клиентов: ${total}`;
      }

      const preview = Array.isArray(data?.recipients_preview) ? data.recipients_preview : [];
      if (!preview.length) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Список клиентов не собран. Нажми “Собрать список клиентов”.</td></tr>`;
      } else {
        tbody.innerHTML = preview.map(row).join("");
      }

      setMsg(`Обновлено: ${fmtDate(new Date())}`);
    } catch (e) {
      showErr(String(e.message || e));
      tbody.innerHTML = `<tr><td colspan="9" class="text-danger">Ошибка</td></tr>`;
      setMsg("");
    }
  }

  async function build() {
    hideErr();
    try {
      buildBtn.disabled = true;
      setMsg("Сбор клиентов…");
      await apiPost(`/api/campaigns/${id}/build`, {});
      if (typeof uiToast === "function") uiToast("Список клиентов собран", "success");
      await load();
    } catch (e) {
      showErr(String(e.message || e));
      if (typeof uiToast === "function") uiToast("Ошибка сборки списка", "error");
    } finally {
      buildBtn.disabled = false;
    }
  }

  reloadBtn?.addEventListener("click", load);
  buildBtn?.addEventListener("click", build);

  load();
}

// =========================
// Page: Clients list (/admin/clients)
// =========================
function initClientsList() {
  const btnSearch = document.getElementById("btnSearch");
  const btnRefresh = document.getElementById("btnRefresh");
  const btnRefreshTop = document.getElementById("btnRefreshTop");
  const searchPhone = document.getElementById("searchPhone");
  const usersTableBody = document.getElementById("usersTableBody");
  const usersError = document.getElementById("usersError");
  const searchError = document.getElementById("searchError");

  if (!usersTableBody) return;

  async function loadUsers() {
    try {
      hide(usersError);
      const data = await apiGet("/api/users/");
      const items = Array.isArray(data) ? data : [];

      // Обновляем счётчик
      const countBadge = document.getElementById("clientsCount");
      if (countBadge) countBadge.textContent = items.length;

      usersTableBody.innerHTML = items
        .map((u) => {
          const t = u.tier || "Bronze";
          return `
            <tr>
              <td>${u.id}</td>
              <td>${u.phone}</td>
              <td>${u.full_name || "—"}</td>
              <td><span class="badge ${tierBadgeClass(t)}">${tierRu(t)}</span></td>
              <td class="text-end">${fmt0(u.bonus_balance || 0)}</td>
              <td class="text-end">
                <a href="/admin/client/${u.phone}" class="btn btn-sm btn-outline-primary">
                  <i class="bi bi-arrow-right"></i>
                </a>
              </td>
            </tr>
          `;
        })
        .join("");
    } catch (e) {
      show(usersError, `Ошибка: ${e.message}`, true);
      usersTableBody.innerHTML = `<tr><td colspan="5" class="text-muted">Ошибка загрузки</td></tr>`;
    }
  }

  if (btnSearch) {
    btnSearch.addEventListener("click", () => {
      hide(searchError);
      const phone = normalizePhone((searchPhone?.value || "").trim());
      if (!phone) {
        show(searchError, "Введите номер телефона", true);
        return;
      }
      window.location.href = `/admin/client/${phone}`;
    });

    searchPhone?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") btnSearch.click();
    });
  }

  [btnRefresh, btnRefreshTop].forEach((b) => b?.addEventListener("click", loadUsers));
  loadUsers();
}

// =========================
// Page: Client card (/admin/client/{phone})
// =========================
function initClientCard() {
  const phoneRaw = window.__CLIENT_PHONE__ || "";
  const phone = normalizePhone(phoneRaw);
  if (!phone) return;

  const btnReload = document.getElementById("btnReload");
  const btnCreateTx = document.getElementById("btnCreateTx");

  const clientError = document.getElementById("clientError");
  const clientNotFound = document.getElementById("clientNotFound");
  const birthdayBanner = document.getElementById("birthdayBanner");

  // Metrics
  const mFullName = document.getElementById("mFullName");
  const mTier = document.getElementById("mTier");
  const mTotalSpent = document.getElementById("mTotalSpent");
  const mCount = document.getElementById("mCount");
  const mAvg = document.getElementById("mAvg");
  const mBonus = document.getElementById("mBonus");

  // Tx table
  const txTableBody = document.getElementById("txTableBody");
  const txError = document.getElementById("txError");
  const txMsg = document.getElementById("txMsg");

  // Form fields
  const fAmount = document.getElementById("fAmount");
  const fPaid = document.getElementById("fPaid");
  const fRedeem = document.getElementById("fRedeem");
  const fMethod = document.getElementById("fMethod");
  const fName = document.getElementById("fName");
  const fBirth = document.getElementById("fBirth");
  const fTier = document.getElementById("fTier");
  const fComment = document.getElementById("fComment");

  function resetMetrics() {
    if (mFullName) mFullName.textContent = "—";
    if (mTier) {
      mTier.textContent = "—";
      mTier.className = "badge text-bg-secondary";
    }
    if (mTotalSpent) mTotalSpent.textContent = "0";
    if (mCount) mCount.textContent = "0";
    if (mAvg) mAvg.textContent = "0";
    if (mBonus) mBonus.textContent = "0";
  }

  async function loadMetrics() {
    try {
      hide(clientError);
      clientNotFound?.classList.add("d-none");
      birthdayBanner?.classList.add("d-none");

      const data = await apiGet(`/api/crm/client/${phone}`);

      if (mFullName) mFullName.textContent = data.full_name || "—";

      const tier = data.tier || "Bronze";
      if (mTier) {
        mTier.textContent = tierRu(tier);
        mTier.className = `badge ${tierBadgeClass(tier)}`;
      }

      if (mTotalSpent) mTotalSpent.textContent = fmtMoney(data.total_spent);
      if (mCount) mCount.textContent = fmt0(data.purchases_count);
      if (mAvg) mAvg.textContent = fmtMoney(data.avg_check);
      if (mBonus) mBonus.textContent = fmt0(data.bonus_balance);
    } catch (e) {
      resetMetrics();
      const msg = String(e.message || "");
      if (msg.toLowerCase().includes("client not found") || msg.includes("404")) {
        clientNotFound?.classList.remove("d-none");
        return;
      }
      show(clientError, `Ошибка CRM: ${e.message}`, true);
      clientError?.classList.remove("d-none");
    }
  }

  async function loadTransactions() {
    if (!txTableBody) return;
    try {
      hide(txError);
      const rows = await apiGet(`/api/transactions/by-phone/${phone}`);
      const list = Array.isArray(rows) ? rows : [];

      if (!list.length) {
        txTableBody.innerHTML = `<tr><td colspan="6" class="text-muted">Транзакций пока нет</td></tr>`;
        return;
      }

      txTableBody.innerHTML = list
        .map(
          (t) => `
          <tr>
            <td>${t.id ?? "—"}</td>
            <td>${fmtDate(t.created_at)}</td>
            <td class="text-end">${fmtMoney(t.amount)}</td>
            <td class="text-end">${fmtMoney(t.paid_amount ?? t.amount)}</td>
            <td class="text-end">${fmt0(getRedeem(t))}</td>
            <td class="text-end">${fmt0(getEarned(t))}</td>
          </tr>
        `
        )
        .join("");
    } catch (e) {
      show(txError, `Ошибка загрузки транзакций: ${e.message}`, true);
      txError?.classList.remove("d-none");
      txTableBody.innerHTML = `<tr><td colspan="6" class="text-muted">Ошибка</td></tr>`;
    }
  }

  async function reloadAll() {
    await loadMetrics();
    await loadTransactions();
  }

  btnReload?.addEventListener("click", reloadAll);

  btnCreateTx?.addEventListener("click", async () => {
    hide(txMsg);

    const amount = Math.trunc(safeNum(fAmount?.value, 0));
    if (!amount || amount <= 0) {
      show(txMsg, "Введите сумму > 0", true);
      txMsg?.classList.remove("d-none");
      return;
    }

    const paid = fPaid?.value ? Math.trunc(safeNum(fPaid.value, 0)) : null;
    const redeem = Math.trunc(safeNum(fRedeem?.value, 0));

    const payload = {
      user_phone: phone,
      amount,
      paid_amount: paid && paid > 0 ? paid : null,
      redeem_points: redeem >= 0 ? redeem : 0,
      payment_method: fMethod?.value || "CASH",
      full_name: (fName?.value || "").trim() || null,
      birth_date: (fBirth?.value || "").trim() || null,
      tier: (fTier?.value || "").trim() || null,
      comment: (fComment?.value || "").trim() || "",
    };

    try {
      btnCreateTx.disabled = true;
      const res = await apiPost("/api/transactions/", payload);

      show(txMsg, `✓ Транзакция создана (ID: ${res.id || "—"})`, false);
      txMsg?.classList.remove("d-none");
      if (typeof uiToast === "function") uiToast("Транзакция проведена", "success");

      if (fPaid) fPaid.value = "";
      if (fRedeem) fRedeem.value = "0";
      if (fName) fName.value = "";
      if (fBirth) fBirth.value = "";
      if (fTier) fTier.value = "";
      if (fComment) fComment.value = "";

      setTimeout(reloadAll, 250);
    } catch (e) {
      show(txMsg, `✗ ${e.message}`, true);
      txMsg?.classList.remove("d-none");
      if (typeof uiToast === "function") uiToast("Ошибка создания транзакции", "error");
    } finally {
      btnCreateTx.disabled = false;
    }
  });

  reloadAll();
}

// =========================
// Page: Transactions (/admin/transactions)
// =========================
function initTransactionsPage() {
  const tbody = document.getElementById("txTbody");
  if (!tbody) return;

  const count = document.getElementById("txCount");
  const phoneEl = document.getElementById("txPhone");
  const searchBtn = document.getElementById("txSearchBtn");
  const refreshBtn = document.getElementById("txRefreshBtn");

  function setCount(n) {
    if (count) count.textContent = String(n ?? "—");
  }

  function renderRows(list) {
    const arr = Array.isArray(list) ? list : [];
    setCount(arr.length);

    if (!arr.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-muted">Транзакции не найдены.</td></tr>`;
      return;
    }

    tbody.innerHTML = arr
      .map((t) => {
        const phone = t.user_phone ?? "—";
        return `
          <tr>
            <td>${t.id ?? "—"}</td>
            <td class="text-muted">${fmtDate(t.created_at)}</td>
            <td>${phone}</td>
            <td class="text-end">${fmtMoney(t.amount)}</td>
            <td class="text-end">${fmtMoney(t.paid_amount ?? t.amount)}</td>
            <td class="text-end">${fmtMoney(getRedeem(t))}</td>
            <td class="text-end">${fmtMoney(getEarned(t))}</td>
            <td class="text-muted">${(t.comment ?? "").toString()}</td>
            <td class="text-end">
              <a class="btn btn-sm btn-outline-secondary" href="/admin/client/${phone}">
                Карточка
              </a>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  async function loadByPhone(phone) {
    const data = await apiGet(`/api/transactions/by-phone/${phone}`);
    renderRows(data);
  }

  async function onSearch() {
    const phone = normalizePhone(phoneEl?.value || "");
    if (!phone) {
      if (typeof uiToast === "function") uiToast("Введите корректный телефон", "warning");
      return;
    }
    try {
      await loadByPhone(phone);
    } catch (e) {
      if (typeof uiToast === "function") uiToast(`Ошибка: ${e.message}`, "error");
      tbody.innerHTML = `<tr><td colspan="9" class="text-danger">Ошибка загрузки транзакций</td></tr>`;
      setCount("—");
    }
  }

  searchBtn?.addEventListener("click", onSearch);
  phoneEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onSearch();
  });
  refreshBtn?.addEventListener("click", onSearch);

  // ✅ prefill from query ?phone=
  const qPhone = normalizePhone(getQueryParam("phone") || "");
  if (qPhone && phoneEl) {
    phoneEl.value = qPhone;
    onSearch();
  }
}

// =========================
// Page: Settings (/admin/settings)
// =========================
// =========================
// Page: Settings — ПОЛНАЯ ЗАМЕНА initSettingsPage()
// =========================
function initSettingsPage() {
  // ── Tabs ──────────────────────────────────────────
  const navItems = document.querySelectorAll(".settings-nav-item");
  const tabs = document.querySelectorAll(".settings-tab");

  function switchTab(tabId) {
    navItems.forEach(n => n.classList.toggle("active", n.dataset.tab === tabId));
    tabs.forEach(t => t.classList.toggle("active", t.id === `tab-${tabId}`));
  }

  navItems.forEach(n => {
    n.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(n.dataset.tab);
    });
  });

  // ── State ─────────────────────────────────────────
  let tiers = [];  // [{name, spend_from, bonus_percent}]

  // ── Field helpers ──────────────────────────────────
  function v(id) { return document.getElementById(id); }
  function getInt(id, def = 0) { return Math.trunc(safeNum(v(id)?.value, def)); }
  function setVal(id, val) { const el = v(id); if (el) el.value = val ?? ""; }
  function setBool(id, val) { const el = v(id); if (el) el.checked = Boolean(val); }
  function getBool(id) { return Boolean(v(id)?.checked); }

  // ── Activation toggle ─────────────────────────────
  const activationImmediate = v("activationImmediate");
  const activationDaysWrap = v("activationDaysWrap");

  function updateActivationUI() {
    if (!activationImmediate || !activationDaysWrap) return;
    activationDaysWrap.style.display = activationImmediate.checked ? "none" : "block";
  }

  activationImmediate?.addEventListener("change", updateActivationUI);

  // ── Boost toggle ──────────────────────────────────
  const boostEnabled = v("boost_enabled");
  const boostAlways = v("boost_always");
  const boostFormContent = v("boostFormContent");

  function updateBoostUI() {
    if (boostFormContent) boostFormContent.style.opacity = getBool("boost_enabled") ? "1" : "0.5";
    const schedWrap = v("boostScheduleWrap");
    if (schedWrap) schedWrap.style.display = getBool("boost_always") ? "none" : "block";
  }

  boostEnabled?.addEventListener("change", updateBoostUI);
  boostAlways?.addEventListener("change", updateBoostUI);

  // ── Boost scheduler ───────────────────────────────────
  let boostDatesArr = [];

  function renderBoostDates() {
    const box = v("boostDatesList");
    if (!box) return;
    const el = v("boost_dates_json");
    if (el) el.value = JSON.stringify(boostDatesArr);
    box.innerHTML = boostDatesArr.map((d, i) => `
      <span class="boost-date-tag">
        ${d}
        <button type="button" class="boost-date-del" onclick="removeBoostDate(${i})">
          <i class="bi bi-x"></i>
        </button>
      </span>
    `).join("");
  }

  window.removeBoostDate = function(idx) {
    boostDatesArr.splice(idx, 1);
    renderBoostDates();
  };

  function updateBoostModeUI(mode) {
    const wdWrap = v("boostWeekdaysWrap");
    const dtWrap = v("boostDatesWrap");
    if (wdWrap) wdWrap.classList.toggle("d-none", mode !== "days");
    if (dtWrap) dtWrap.classList.toggle("d-none", mode !== "dates");
  }

  function initBoostSchedule() {
    document.querySelectorAll(".boost-mode-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".boost-mode-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const mode = btn.dataset.mode;
        const modeEl = v("boost_mode");
        if (modeEl) modeEl.value = mode;
        updateBoostModeUI(mode);
      });
    });

    v("boostDateAddBtn")?.addEventListener("click", () => {
      const picker = v("boostDatePicker");
      const date = picker?.value;
      if (!date) return;
      if (!boostDatesArr.includes(date)) {
        boostDatesArr.push(date);
        boostDatesArr.sort();
        renderBoostDates();
      }
      if (picker) picker.value = "";
    });

    document.querySelectorAll("input[name='boost_weekday']").forEach(cb => {
      cb.addEventListener("change", () => {
        const days = [];
        document.querySelectorAll("input[name='boost_weekday']:checked").forEach(c => days.push(c.value));
        const el = v("boost_weekdays_json");
        if (el) el.value = JSON.stringify(days);
      });
    });
  }

  initBoostSchedule();

  // ── Birthday toggle ───────────────────────────────
  const birthdayEnabled = v("birthday_enabled");
  const birthdayFormContent = v("birthdayFormContent");

  function updateBirthdayUI() {
    if (birthdayFormContent) birthdayFormContent.style.opacity = getBool("birthday_enabled") ? "1" : "0.5";
  }

  birthdayEnabled?.addEventListener("change", updateBirthdayUI);

  // ── Tiers table ───────────────────────────────────
  function tierBadgeClass(name) {
    const n = (name || "").toLowerCase();
    if (n === "bronze") return "bronze";
    if (n === "silver") return "silver";
    if (n === "gold")   return "gold";
    return "custom";
  }

  function renderTiers() {
    const tbody = v("stTiersTbody");
    if (!tbody) return;

    if (!tiers.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-muted" style="padding:16px">Нет уровней. Нажмите «Добавить уровень».</td></tr>`;
      return;
    }

    const sorted = [...tiers].sort((a, b) => a.spend_from - b.spend_from);
    tbody.innerHTML = sorted.map((t, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>
          <span class="tier-badge ${tierBadgeClass(t.name)}">
            ${t.name}
          </span>
        </td>
        <td><strong>${t.bonus_percent}%</strong> от суммы транзакции</td>
        <td>${Number(t.spend_from).toLocaleString("ru-RU")} ₸</td>
        <td class="text-end">
          <button class="btn btn-sm btn-outline-danger" type="button"
                  onclick="stDeleteTier(${i})">
            <i class="bi bi-trash me-1"></i> Удалить
          </button>
        </td>
      </tr>
    `).join("");
  }

  window.stDeleteTier = function(idx) {
    tiers.splice(idx, 1);
    renderTiers();
  };

  // Add tier form
  const addBtn = v("stAddTierBtn");
  const newTierForm = v("stNewTierForm");
  const confirmBtn = v("stConfirmTierBtn");
  const cancelBtn = v("stCancelTierBtn");

  addBtn?.addEventListener("click", () => {
    newTierForm.style.display = "block";
  });

  cancelBtn?.addEventListener("click", () => {
    newTierForm.style.display = "none";
    ["newTierName","newTierSpend","newTierPercent"].forEach(id => setVal(id, ""));
  });

  confirmBtn?.addEventListener("click", () => {
    const name = (v("newTierName")?.value || "").trim();
    const spend_from = Math.trunc(safeNum(v("newTierSpend")?.value, 0));
    const bonus_percent = Math.trunc(safeNum(v("newTierPercent")?.value, 0));

    if (!name) { uiToast("Введите название уровня", "warning"); return; }
    if (spend_from < 0) { uiToast("Сумма должна быть ≥ 0", "warning"); return; }
    if (bonus_percent < 0 || bonus_percent > 100) { uiToast("Бонус: 0–100%", "warning"); return; }

    tiers.push({ name, spend_from, bonus_percent });
    renderTiers();
    newTierForm.style.display = "none";
    ["newTierName","newTierSpend","newTierPercent"].forEach(id => setVal(id, ""));
  });

  // ── Fill form from API data ────────────────────────
  function fillForm(data) {
    setVal("bonus_name", data.bonus_name ?? "баллы");

    setVal("earn_bronze_percent", data.earn_bronze_percent ?? 3);
    setVal("earn_silver_percent", data.earn_silver_percent ?? 5);
    setVal("earn_gold_percent",   data.earn_gold_percent   ?? 7);
    setVal("silver_threshold", data.silver_threshold ?? 50000);
    setVal("gold_threshold",   data.gold_threshold   ?? 200000);
    setVal("welcome_bonus_percent", data.welcome_bonus_percent ?? 0);

    // Redeem
    const redeemSel = v("redeem_max_percent");
    if (redeemSel) redeemSel.value = String(data.redeem_max_percent ?? 30);

    // Activation
    const activationDays = data.activation_days ?? 0;
    if (activationImmediate) activationImmediate.checked = activationDays === 0;
    const actSel = v("activation_days");
    if (actSel && activationDays > 0) actSel.value = String(activationDays);
    updateActivationUI();

    // Burn
    const burnPctSel = v("burn_percent");
    if (burnPctSel) burnPctSel.value = String(data.burn_percent ?? 100);
    const burnDaysSel = v("burn_days");
    if (burnDaysSel) burnDaysSel.value = String(data.burn_days ?? 180);

    // Birthday
    setBool("birthday_enabled", data.birthday_enabled ?? true);
    setVal("birthday_bonus_amount",      data.birthday_bonus_amount ?? 5000);
    const bdDaysSel = v("birthday_bonus_ttl_days");
    if (bdDaysSel) bdDaysSel.value = String(data.birthday_bonus_ttl_days ?? 30);
    const bdBeforeSel = v("birthday_bonus_days_before");
    if (bdBeforeSel) bdBeforeSel.value = String(data.birthday_bonus_days_before ?? 7);
    setBool("birthday_notify_7d", data.birthday_notify_7d ?? true);
    setBool("birthday_notify_3d", data.birthday_notify_3d ?? true);
    setBool("birthday_notify_1d", data.birthday_notify_1d ?? true);
    setVal("birthday_message",    data.birthday_message ?? "");
    setVal("birthday_message_7d", data.birthday_message_7d ?? "");
    updateBirthdayUI();

    // Boost
    setBool("boost_enabled", data.boost_enabled ?? false);
    setVal("boost_percent",  data.boost_percent ?? 7);
    setBool("boost_always",  data.boost_always ?? false);

    const boostMode = data.boost_mode || "days";
    const boostModeEl = v("boost_mode");
    if (boostModeEl) boostModeEl.value = boostMode;

    const weekdays = Array.isArray(data.boost_weekdays) ? data.boost_weekdays : [];
    document.querySelectorAll("input[name='boost_weekday']").forEach(cb => {
      cb.checked = weekdays.includes(cb.value);
    });
    const wdJson = v("boost_weekdays_json");
    if (wdJson) wdJson.value = JSON.stringify(weekdays);

    boostDatesArr = Array.isArray(data.boost_dates) ? [...data.boost_dates] : [];
    const dtJson = v("boost_dates_json");
    if (dtJson) dtJson.value = JSON.stringify(boostDatesArr);
    renderBoostDates();

    document.querySelectorAll(".boost-mode-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.mode === boostMode);
    });
    updateBoostModeUI(boostMode);

    setVal("cost_per_lead",   data.cost_per_lead   ?? 0);
    setVal("cost_per_client", data.cost_per_client ?? 0);

    updateBoostUI();

    // Tiers
    tiers = Array.isArray(data.tiers) ? data.tiers.map(t => ({...t})) : [];
    renderTiers();
  }

  // ── Read form → payload ────────────────────────────
  function readForm() {
    const activDays = getBool("activationImmediate")
      ? 0
      : getInt("activation_days", 1);

    return {
      bonus_name: (v("bonus_name")?.value || "баллы").trim(),

      earn_bronze_percent: getInt("earn_bronze_percent", 3),
      earn_silver_percent: getInt("earn_silver_percent", 5),
      earn_gold_percent:   getInt("earn_gold_percent",   7),
      silver_threshold: getInt("silver_threshold", 50000),
      gold_threshold:   getInt("gold_threshold",   200000),
      welcome_bonus_percent: getInt("welcome_bonus_percent", 0),

      redeem_max_percent: getInt("redeem_max_percent", 30),

      activation_days: activDays,
      burn_days:       getInt("burn_days",    180),
      burn_percent:    getInt("burn_percent", 100),

      birthday_bonus_amount:      getInt("birthday_bonus_amount", 5000),
      birthday_bonus_days_before: getInt("birthday_bonus_days_before", 7),
      birthday_bonus_ttl_days:    getInt("birthday_bonus_ttl_days", 30),
      birthday_notify_7d:  getBool("birthday_notify_7d"),
      birthday_notify_3d:  getBool("birthday_notify_3d"),
      birthday_notify_1d:  getBool("birthday_notify_1d"),
      birthday_message:    v("birthday_message")?.value || null,
      birthday_message_7d: v("birthday_message_7d")?.value || null,
      birthday_enabled:    getBool("birthday_enabled"),

      boost_enabled:   getBool("boost_enabled"),
      boost_percent:   getInt("boost_percent", 7),
      boost_always:    getBool("boost_always"),
      boost_mode:      v("boost_mode")?.value || "days",
      boost_weekdays:  (() => {
        const days = [];
        document.querySelectorAll("input[name='boost_weekday']:checked").forEach(cb => days.push(cb.value));
        return days;
      })(),
      boost_dates:     (() => {
        try { return JSON.parse(v("boost_dates_json")?.value || "[]"); } catch { return []; }
      })(),
      cost_per_lead:   getInt("cost_per_lead", 0),
      cost_per_client: getInt("cost_per_client", 0),

      tiers: tiers.map(t => ({
        name: String(t.name),
        spend_from: Number(t.spend_from),
        bonus_percent: Number(t.bonus_percent),
      })),
    };
  }

  // ── Load ──────────────────────────────────────────
  async function load() {
    try {
      const data = await apiGet("/api/settings/");
      fillForm(data);
    } catch (e) {
      uiToast(`Ошибка загрузки: ${e.message}`, "error");
    }
  }

  // ── Save ──────────────────────────────────────────
  async function save() {
    const saveBtn   = v("stSaveBtn");
    const saveBtnB  = v("stSaveBtnBottom");
    const statusEl  = v("stSaveStatus");
    const msgEl     = v("stMsg");

    [saveBtn, saveBtnB].forEach(b => { if (b) b.disabled = true; });

    try {
      const payload = readForm();
      const data = await fetch("/api/settings/", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || `${r.status}`);
        return j;
      });

      fillForm(data);
      uiToast("Настройки сохранены", "success");

      if (statusEl) {
        statusEl.textContent = "✓ Сохранено";
        statusEl.className = "small text-success";
        statusEl.classList.remove("d-none");
        setTimeout(() => statusEl.classList.add("d-none"), 3000);
      }
      if (msgEl) {
        msgEl.textContent = "✓ Изменения сохранены";
        msgEl.className = "small text-success";
        msgEl.classList.remove("d-none");
      }
    } catch (e) {
      uiToast(`Ошибка: ${e.message}`, "error");
      if (msgEl) {
        msgEl.textContent = `✗ ${e.message}`;
        msgEl.className = "small text-danger";
        msgEl.classList.remove("d-none");
      }
    } finally {
      [saveBtn, saveBtnB].forEach(b => { if (b) b.disabled = false; });
    }
  }

  // ── Events ────────────────────────────────────────
  v("stSaveBtn")?.addEventListener("click", save);
  v("stSaveBtnBottom")?.addEventListener("click", save);
  v("stReloadBtn")?.addEventListener("click", load);
  v("stReloadBtnBottom")?.addEventListener("click", load);

  load();
}
// =========================
// Page: Accounts (/admin/accounts)
// Добавить как новую функцию в admin.js
// И в DOMContentLoaded добавить: else if (page === "accounts") initAccountsPage();
// =========================
function initAccountsPage() {

  // ── Helpers ──────────────────────────────────────
  function v(id) { return document.getElementById(id); }
  function showMsg(el, text, isErr = false) {
    if (!el) return;
    el.textContent = text;
    el.className = `small ${isErr ? "text-danger" : "text-success"}`;
    el.classList.remove("d-none");
  }

  // ── Tenant profile ────────────────────────────────
  async function loadProfile() {
    try {
      const data = await apiGet("/api/accounts/profile");
      if (v("accTenantName")) v("accTenantName").textContent = data.name || "—";
      if (v("accTenantNameInput")) v("accTenantNameInput").value = data.name || "";
      if (v("accTenantAccess")) {
        if (data.access_until) {
          const d = new Date(data.access_until);
          v("accTenantAccess").textContent = `Доступ до: ${d.toLocaleDateString("ru-RU")}`;
        } else {
          v("accTenantAccess").textContent = "Доступ: бессрочный";
        }
      }
    } catch (e) {
      console.warn("Profile load error:", e.message);
    }
  }

  v("accSaveNameBtn")?.addEventListener("click", async () => {
    const name = (v("accTenantNameInput")?.value || "").trim();
    if (!name) { uiToast("Введите название", "warning"); return; }
    try {
      const data = await apiPost("/api/accounts/profile", { name }); // PUT через fetch
      await fetch("/api/accounts/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }).then(r => { if (!r.ok) throw new Error("Ошибка"); return r.json(); });
      if (v("accTenantName")) v("accTenantName").textContent = name;
      uiToast("Название обновлено", "success");
    } catch (e) {
      uiToast(`Ошибка: ${e.message}`, "error");
    }
  });

  // ── Change password ───────────────────────────────
  v("accChangePwdBtn")?.addEventListener("click", async () => {
    const oldPwd = v("accOldPwd")?.value || "";
    const newPwd = v("accNewPwd")?.value || "";
    const newPwd2 = v("accNewPwd2")?.value || "";
    const msgEl = v("accPwdMsg");

    if (!oldPwd || !newPwd) { showMsg(msgEl, "Заполните все поля", true); return; }
    if (newPwd !== newPwd2) { showMsg(msgEl, "Новые пароли не совпадают", true); return; }
    if (newPwd.length < 4) { showMsg(msgEl, "Минимум 4 символа", true); return; }

    try {
      await fetch("/api/accounts/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });

      showMsg(msgEl, "✓ Пароль успешно изменён", false);
      [v("accOldPwd"), v("accNewPwd"), v("accNewPwd2")].forEach(el => { if (el) el.value = ""; });
      uiToast("Пароль изменён", "success");
    } catch (e) {
      showMsg(msgEl, `✗ ${e.message}`, true);
    }
  });

  // ── Users list ────────────────────────────────────
  function roleBadge(role) {
    const r = (role || "").toLowerCase();
    if (r === "owner") return `<span class="badge text-bg-warning text-dark">OWNER</span>`;
    if (r === "admin") return `<span class="badge text-bg-primary">ADMIN</span>`;
    return `<span class="badge text-bg-secondary">STAFF</span>`;
  }

  async function loadUsers() {
    const tbody = v("accUsersTbody");
    const countEl = v("accUsersCount");
    const errEl = v("accUsersErr");
    if (!tbody) return;

    try {
      const list = await apiGet("/api/accounts/users");
      if (countEl) countEl.textContent = list.length;

      if (!list.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-muted">Нет сотрудников</td></tr>`;
        return;
      }

      tbody.innerHTML = list.map(u => `
        <tr>
          <td>
            <div class="d-flex align-items-center gap-2">
              <div class="acc-user-avatar">${(u.name || "?")[0].toUpperCase()}</div>
              <span class="fw-semibold">${u.name || "—"}</span>
            </div>
          </td>
          <td class="text-muted">${u.phone || "—"}</td>
          <td>${roleBadge(u.role)}</td>
          <td>
            ${u.is_active
              ? `<span class="badge text-bg-success">Активен</span>`
              : `<span class="badge text-bg-danger">Неактивен</span>`
            }
          </td>
          <td class="text-muted small">${u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
          <td class="text-end">
            <div class="d-flex gap-1 justify-content-end">
              <button class="btn btn-sm btn-outline-secondary"
                      onclick="accToggleUser(${u.id}, ${!u.is_active})"
                      title="${u.is_active ? "Деактивировать" : "Активировать"}">
                <i class="bi bi-${u.is_active ? "pause" : "play"}-circle"></i>
              </button>
              <button class="btn btn-sm btn-outline-danger"
                      onclick="accDeleteUser(${u.id}, '${u.name}')"
                      title="Удалить">
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `).join("");

    } catch (e) {
      if (errEl) { errEl.textContent = `Ошибка: ${e.message}`; errEl.classList.remove("d-none"); }
    }
  }

  window.accToggleUser = async function(userId, isActive) {
    try {
      await fetch(`/api/accounts/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: isActive }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });
      uiToast(isActive ? "Пользователь активирован" : "Пользователь деактивирован", "success");
      loadUsers();
    } catch (e) {
      uiToast(`Ошибка: ${e.message}`, "error");
    }
  };

  window.accDeleteUser = async function(userId, name) {
    if (!confirm(`Удалить пользователя «${name}»? Это действие необратимо.`)) return;
    try {
      await fetch(`/api/accounts/users/${userId}`, { method: "DELETE" })
        .then(async r => {
          const j = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(j?.detail || "Ошибка");
          return j;
        });
      uiToast("Пользователь удалён", "success");
      loadUsers();
    } catch (e) {
      uiToast(`Ошибка: ${e.message}`, "error");
    }
  };

  // ── Create user form ──────────────────────────────
  v("accOpenCreateBtn")?.addEventListener("click", () => {
    v("accCreateBox")?.classList.remove("d-none");
  });

  v("accCloseCreateBtn")?.addEventListener("click", () => {
    v("accCreateBox")?.classList.add("d-none");
    ["accNewName","accNewPhone","accNewPwdCreate"].forEach(id => { const el = v(id); if (el) el.value = ""; });
  });

  v("accCreateBtn")?.addEventListener("click", async () => {
    const errEl = v("accCreateErr");
    const name  = (v("accNewName")?.value || "").trim();
    const phone = (v("accNewPhone")?.value || "").trim();
    const pwd   = v("accNewPwdCreate")?.value || "";
    const role  = v("accNewRole")?.value || "staff";

    if (!name || !phone || !pwd) {
      errEl.textContent = "Заполните все обязательные поля";
      errEl.classList.remove("d-none");
      return;
    }

    try {
      await fetch("/api/accounts/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, phone, password: pwd, role }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });

      v("accCreateBox")?.classList.add("d-none");
      ["accNewName","accNewPhone","accNewPwdCreate"].forEach(id => { const el = v(id); if (el) el.value = ""; });
      uiToast("Сотрудник добавлен", "success");
      loadUsers();
    } catch (e) {
      errEl.textContent = `✗ ${e.message}`;
      errEl.classList.remove("d-none");
    }
  });

  // ── Init ──────────────────────────────────────────
  loadProfile();
  loadUsers();
}

// =========================
// Page: Videos (/admin/videos)
// Добавить как новую функцию в admin.js
// В DOMContentLoaded: else if (page === "videos") initVideosPage();
// =========================
function initVideosPage() {

  let allVideos = [];
  let currentCat = "";
  let searchTimer = null;

  // ── Helpers ──────────────────────────────────────
  function v(id) { return document.getElementById(id); }

  function fmtDateShort(dt) {
    try {
      return new Date(dt).toLocaleDateString("ru-RU", { day:"2-digit", month:"short", year:"numeric" });
    } catch { return "—"; }
  }

  // ── Render ───────────────────────────────────────
  function renderGrid(videos) {
    const grid = v("vidGrid");
    const countEl = v("vidCount");
    if (!grid) return;

    if (countEl) countEl.textContent = `${videos.length} видео`;

    if (!videos.length) {
      grid.innerHTML = `
        <div class="vid-empty">
          <div class="vid-empty-icon"><i class="bi bi-camera-video-off"></i></div>
          <div class="fw-semibold mb-1">Видео не найдены</div>
          <div class="small">Попробуйте изменить фильтры или добавьте первое видео</div>
        </div>`;
      return;
    }

    grid.innerHTML = videos.map(vid => `
      <div class="vid-card" data-id="${vid.id}">
        <div class="vid-thumb-wrap">
          <img class="vid-thumb" src="${vid.thumbnail}" alt="${vid.title}"
               loading="lazy" onerror="this.src='https://img.youtube.com/vi/${vid.youtube_id}/mqdefault.jpg'">
          <a class="vid-play-btn" href="https://www.youtube.com/watch?v=${vid.youtube_id}"
             target="_blank" rel="noopener">
            <div class="vid-play-circle">
              <i class="bi bi-play-fill"></i>
            </div>
          </a>
        </div>
        <div class="vid-body">
          <div class="vid-category-badge">${vid.category_label}</div>
          <div class="vid-title">${vid.title}</div>
          ${vid.description ? `<div class="vid-desc">${vid.description}</div>` : ""}
          ${vid.tags ? `
            <div class="vid-tags">
              ${vid.tags.split(",").map(t => `<span class="vid-tag">${t.trim()}</span>`).join("")}
            </div>` : ""}
        </div>
        <div class="vid-footer">
          <span class="vid-date">${fmtDateShort(vid.created_at)}</span>
          <div class="d-flex gap-2">
            <a href="https://www.youtube.com/watch?v=${vid.youtube_id}"
               target="_blank" rel="noopener"
               class="btn btn-sm btn-outline-secondary">
              <i class="bi bi-youtube me-1"></i> Смотреть
            </a>
            <button class="btn btn-sm btn-outline-danger vid-del-btn"
                    data-id="${vid.id}" title="Удалить">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </div>
      </div>
    `).join("");

    // Delete handlers
    grid.querySelectorAll(".vid-del-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Удалить видео?")) return;
        const id = btn.dataset.id;
        try {
          await fetch(`/api/videos/${id}`, { method: "DELETE" })
            .then(async r => {
              const j = await r.json().catch(() => ({}));
              if (!r.ok) throw new Error(j?.detail || "Ошибка");
            });
          uiToast("Видео удалено", "success");
          loadVideos();
        } catch (e) {
          uiToast(`Ошибка: ${e.message}`, "error");
        }
      });
    });
  }

  // ── Filter & search ───────────────────────────────
  function applyFilters() {
    const q = (v("vidSearchInput")?.value || "").toLowerCase().trim();
    let filtered = allVideos;

    if (currentCat) {
      filtered = filtered.filter(vid => vid.category === currentCat);
    }
    if (q) {
      filtered = filtered.filter(vid =>
        (vid.title || "").toLowerCase().includes(q) ||
        (vid.tags  || "").toLowerCase().includes(q) ||
        (vid.description || "").toLowerCase().includes(q)
      );
    }
    renderGrid(filtered);
  }

  // Category filters
  document.querySelectorAll(".vid-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".vid-filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentCat = btn.dataset.cat || "";
      applyFilters();
    });
  });

  // Search with debounce
  v("vidSearchInput")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 250);
  });

  // ── Load ──────────────────────────────────────────
  async function loadVideos() {
    try {
      allVideos = await apiGet("/api/videos/");
      applyFilters();
    } catch (e) {
      const grid = v("vidGrid");
      if (grid) grid.innerHTML = `<div class="text-danger">Ошибка: ${e.message}</div>`;
    }
  }

  // ── Add form ──────────────────────────────────────
  v("vidOpenAddBtn")?.addEventListener("click", () => {
    v("vidAddBox")?.classList.remove("d-none");
  });

  function closeAddForm() {
    v("vidAddBox")?.classList.add("d-none");
    ["vidNewUrl","vidNewTitle","vidNewTags","vidNewDesc"].forEach(id => {
      const el = v(id); if (el) el.value = "";
    });
    const err = v("vidAddErr");
    if (err) err.classList.add("d-none");
  }

  v("vidCloseAddBtn")?.addEventListener("click",  closeAddForm);
  v("vidCancelAddBtn")?.addEventListener("click", closeAddForm);

  v("vidAddBtn")?.addEventListener("click", async () => {
    const errEl = v("vidAddErr");
    const url   = (v("vidNewUrl")?.value   || "").trim();
    const title = (v("vidNewTitle")?.value || "").trim();
    const cat   = v("vidNewCategory")?.value || "general";
    const tags  = (v("vidNewTags")?.value  || "").trim() || null;
    const desc  = (v("vidNewDesc")?.value  || "").trim() || null;

    if (!url)   { errEl.textContent = "Введите YouTube ссылку"; errEl.classList.remove("d-none"); return; }
    if (!title) { errEl.textContent = "Введите название";        errEl.classList.remove("d-none"); return; }

    try {
      await fetch("/api/videos/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url, title, category: cat, tags, description: desc }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });

      closeAddForm();
      uiToast("Видео добавлено", "success");
      loadVideos();
    } catch (e) {
      errEl.textContent = `✗ ${e.message}`;
      errEl.classList.remove("d-none");
    }
  });

  // ── Init ──────────────────────────────────────────
  loadVideos();
}

// =========================
// MOBILE MENU + AI PANEL UPGRADES
// Добавить в НАЧАЛО admin.js (до DOMContentLoaded)
// =========================

// ── Mobile sidebar ────────────────────────────────────────
function initMobileSidebar() {
  const btn      = document.getElementById("mobileMenuBtn");
  const sidebar  = document.getElementById("appSidebar");
  const overlay  = document.getElementById("sidebarOverlay");

  if (!btn || !sidebar) return;

  function open() {
    sidebar.classList.add("open");
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function close() {
    sidebar.classList.remove("open");
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }

  btn.addEventListener("click", () => {
    sidebar.classList.contains("open") ? close() : open();
  });

  overlay.addEventListener("click", close);

  // Закрыть при клике по ссылке в меню (мобилка)
  sidebar.querySelectorAll(".nav-item").forEach(link => {
    link.addEventListener("click", close);
  });
}

function jsinitMobileSidebar() {
  initMobileSidebar();
}

// ── AI Panel upgrades ─────────────────────────────────────
function initAiPanelUpgrades() {
  // Быстрые вопросы
  document.querySelectorAll(".ai-quick-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const q = btn.dataset.q;
      const ta = document.getElementById("aiPanelQuestion");
      if (ta) {
        ta.value = q;
        ta.focus();
      }
    });
  });

  // Clear button
  document.getElementById("aiPanelClearBtn")?.addEventListener("click", () => {
    const ta = document.getElementById("aiPanelQuestion");
    if (ta) ta.value = "";
    const block = document.getElementById("aiAnswerBlock");
    if (block) block.classList.add("d-none");
  });
}

// ── Human-readable target ─────────────────────────────────
function formatTarget(target) {
  if (!target || target === "—") return null;

  if (target.startsWith("action:grant_bonus")) {
    const parts = {};
    target.split("|").slice(1).forEach(p => {
      const [k, v] = p.split("=");
      parts[k] = v;
    });
    const amount = parts.amount ? Number(parts.amount).toLocaleString("ru-RU") : "?";
    return { label: `💰 Начислить ${amount} бонусов`, isAction: true };
  }

  if (target.startsWith("nav:")) {
    const url = target.slice(4);
    const map = {
      "/admin/analytics":         "📊 Открыть аналитику",
      "/admin/campaigns":         "🎯 Рекламные кампании",
      "/admin/clients":           "👥 Открыть клиентов",
      "/admin/settings":          "⚙️ Открыть настройки",
      "/admin/accounts":          "👤 Открыть аккаунт",
      "/admin/transactions":      "🧾 Открыть транзакции",
    };
    if (map[url]) return { label: map[url], isAction: false };
    if (url.includes("/segment/")) return { label: "📋 Открыть сегмент", isAction: false };
    if (url.includes("/client/"))  return { label: "👤 Карточка клиента", isAction: false };
    if (url.includes("create=1"))  return { label: "➕ Создать рекламную кампанию", isAction: true };
    return { label: "🔗 Перейти", isAction: false };
  }

  return null;
}

// ── Render AI recos (улучшенный) ──────────────────────────
function renderAiRecos(recos, containerId) {
  const box = document.getElementById(containerId);
  if (!box) return;

  if (!recos || !recos.length) {
    box.innerHTML = `<div class="text-muted small">Нет рекомендаций</div>`;
    return;
  }

  box.innerHTML = recos.map((r, i) => {
    const tgt = formatTarget(r.target);
    const bonusBadge = r.suggested_bonus > 0
      ? `<span class="ai-reco-bonus">Бонус: ${Number(r.suggested_bonus).toLocaleString("ru-RU")}</span>`
      : "";

    const btnLabel = tgt ? tgt.label : "Выполнить";
    const btnClass = tgt?.isAction ? "btn-success" : "btn-outline-secondary";

    return `
      <div class="ai-reco-card">
        <div class="ai-reco-action">${r.action || "—"}</div>
        <div class="ai-reco-why">${r.why || ""}</div>
        ${r.expected_effect ? `<div class="ai-reco-why text-success" style="margin-top:4px">↑ ${r.expected_effect}</div>` : ""}
        <div class="ai-reco-footer">
          ${bonusBadge}
          <div class="d-flex gap-2 ms-auto">
            <button class="btn btn-sm ${btnClass}"
                    onclick="(async()=>{const r=window.__lastAiRecos&&window.__lastAiRecos[${i}];if(!r)return;uiToast('Выполняю…','info');const ctx=window.__AI_EXEC_CTX||{context:'business',phone:null};await aiExecuteReco(ctx.context,ctx.phone,r);})()"
                    data-reco-idx="${i}">
              ${btnLabel}
            </button>
            <button class="btn btn-sm btn-outline-secondary"
                    onclick="this.closest('.ai-reco-card').remove()"
                    title="Скрыть">✕</button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  // Сохраняем recos в window для execute
  window.__lastAiRecos = recos;
}

function jsrenderAiRecos(recos, containerId) {
  renderAiRecos(recos, containerId);
}

// =========================
// Page: WhatsApp (/admin/whatsapp)
// Добавить в admin.js
// В DOMContentLoaded: else if (page === "whatsapp") initWhatsappPage();
// =========================
function initWhatsappPage() {

  // ── Helpers ───────────────────────────────────────
  function v(id) { return document.getElementById(id); }
  function showErr(el, msg) { if (!el) return; el.textContent = msg; el.classList.remove("d-none"); }
  function showOk(el, msg)  { if (!el) return; el.textContent = msg; el.classList.remove("d-none"); }
  function hideMsg(...ids)   { ids.forEach(id => { const el = v(id); if (el) el.classList.add("d-none"); }); }

  // ── Status ────────────────────────────────────────
  async function loadStatus() {
    const badge = v("waStatusBadge");
    if (!badge) return;
    try {
      const data = await apiGet("/api/whatsapp/status");
      if (data.ok) {
        badge.textContent = "✓ Подключён";
        badge.className = "badge text-bg-success";
      } else if (data.error && data.error.includes("не настроен")) {
        badge.textContent = "Не настроен";
        badge.className = "badge text-bg-secondary";
      } else {
        badge.textContent = `Отключён (${data.state || "unknown"})`;
        badge.className = "badge text-bg-warning text-dark";
      }
    } catch {
      badge.textContent = "Ошибка";
      badge.className = "badge text-bg-danger";
    }
  }

  v("waRefreshStatus")?.addEventListener("click", loadStatus);

  // ── Char count ────────────────────────────────────
  v("waMessage")?.addEventListener("input", () => {
    const cnt = v("waCharCount");
    if (cnt) cnt.textContent = (v("waMessage")?.value || "").length;
  });

  // ── Templates ─────────────────────────────────────
  async function loadTemplates() {
    const box = v("waTemplatesList");
    if (!box) return;
    try {
      const data = await apiGet("/api/whatsapp/templates");
      const list = data.templates || [];
      box.innerHTML = list.map(t => `
        <div class="wa-template-item" data-text="${encodeURIComponent(t.text)}">
          <div class="wa-template-title">
            <i class="bi bi-chat-left-text" style="color:var(--mint);font-size:.85rem"></i>
            ${t.title}
          </div>
          <div class="wa-template-preview">${t.text}</div>
        </div>
      `).join("");

      box.querySelectorAll(".wa-template-item").forEach(item => {
        item.addEventListener("click", () => {
          const text = decodeURIComponent(item.dataset.text || "");
          // Вставляем в активное поле (одиночное или кампания)
          const single = v("waMessage");
          const campaign = v("waCampaignTemplate");
          const active = document.activeElement;

          if (active === campaign || !single) {
            if (campaign) campaign.value = text;
          } else {
            if (single) single.value = text;
            const cnt = v("waCharCount");
            if (cnt) cnt.textContent = text.length;
          }

          uiToast("Шаблон вставлен", "success");
        });
      });
    } catch (e) {
      box.innerHTML = `<div class="text-danger small">Ошибка: ${e.message}</div>`;
    }
  }

  // ── Send single ───────────────────────────────────
  v("waSendBtn")?.addEventListener("click", async () => {
    hideMsg("waSendErr", "waSendOk");
    const phone   = (v("waPhone")?.value   || "").trim();
    const message = (v("waMessage")?.value || "").trim();

    if (!phone)   { showErr(v("waSendErr"), "Введите номер телефона"); return; }
    if (!message) { showErr(v("waSendErr"), "Введите текст сообщения"); return; }

    const btn = v("waSendBtn");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Отправка…`;

    try {
      await fetch("/api/whatsapp/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, message }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });
      showOk(v("waSendOk"), "✓ Сообщение отправлено!");
      uiToast("Сообщение отправлено", "success");
    } catch (e) {
      showErr(v("waSendErr"), `✗ ${e.message}`);
      uiToast("Ошибка отправки", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="bi bi-whatsapp me-1"></i> Отправить`;
    }
  });

  // ── Load campaigns ────────────────────────────────
  async function loadCampaigns() {
    const sel = v("waCampaignSelect");
    if (!sel) return;
    try {
      const data = await apiGet("/api/campaigns/");
      const list = Array.isArray(data) ? data : (data.campaigns || data.items || []);
      sel.innerHTML = `<option value="">— Выберите кампанию —</option>` +
        list.map(c => `<option value="${c.id}">${c.name || "Кампания #" + c.id} (${c.recipients_total || 0} чел.)</option>`).join("");
    } catch (e) {
      uiToast("Не удалось загрузить кампании", "error");
    }
  }

  v("waCampaignSelect")?.addEventListener("change", () => {
    const id = v("waCampaignSelect")?.value;
    const info = v("waCampaignInfo");
    if (id && info) {
      info.textContent = `Кампания #${id} выбрана`;
      info.classList.remove("d-none");
    } else if (info) {
      info.classList.add("d-none");
    }
  });

  // ── Preview ───────────────────────────────────────
  v("waPreviewBtn")?.addEventListener("click", async () => {
    const tpl = (v("waCampaignTemplate")?.value || "").trim();
    if (!tpl) { uiToast("Введите шаблон", "warning"); return; }

    try {
      const data = await fetch("/api/whatsapp/preview-template", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template: tpl }),
      }).then(r => r.json());

      const box = v("waPreviewBox");
      if (box) box.textContent = data.preview || tpl;
    } catch {
      uiToast("Ошибка предпросмотра", "error");
    }
  });

  // ── Send campaign ─────────────────────────────────
  async function sendCampaign(dry_run) {
    hideMsg("waCampaignErr", "waCampaignOk");
    const campaign_id = parseInt(v("waCampaignSelect")?.value || "0");
    const template    = (v("waCampaignTemplate")?.value || "").trim();

    if (!campaign_id) { showErr(v("waCampaignErr"), "Выберите кампанию"); return; }
    if (!template)    { showErr(v("waCampaignErr"), "Введите шаблон сообщения"); return; }

    if (!dry_run && !confirm(`Отправить WhatsApp-рассылку по кампании? Это реальная отправка!`)) return;

    const btn = dry_run ? v("waDryRunBtn") : v("waSendCampaignBtn");
    if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>`; }

    try {
      const res = await fetch("/api/whatsapp/send-campaign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id, template, dry_run }),
      }).then(async r => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.detail || "Ошибка");
        return j;
      });

      renderResult(res);
      const msg = dry_run
        ? `Тест: ${res.sent} сообщений готово к отправке`
        : `Отправлено: ${res.sent}, ошибок: ${res.failed}`;
      uiToast(msg, res.failed > 0 ? "warning" : "success");

    } catch (e) {
      showErr(v("waCampaignErr"), `✗ ${e.message}`);
      uiToast("Ошибка рассылки", "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = dry_run
          ? `<i class="bi bi-eye me-1"></i> Тест (dry run)`
          : `<i class="bi bi-whatsapp me-1"></i> Отправить рассылку`;
      }
    }
  }

  function renderResult(res) {
    const card = v("waResultCard");
    const body = v("waResultBody");
    if (!card || !body) return;
    card.classList.remove("d-none");

    const dryTag = res.dry_run ? ` <span class="badge text-bg-info ms-1">dry run</span>` : "";

    body.innerHTML = `
      <div class="row g-2 mb-3">
        <div class="col-4">
          <div class="wa-result-stat">
            <div class="wa-result-num text-success">${res.sent}</div>
            <div class="text-muted small">Отправлено${dryTag}</div>
          </div>
        </div>
        <div class="col-4">
          <div class="wa-result-stat">
            <div class="wa-result-num text-danger">${res.failed}</div>
            <div class="text-muted small">Ошибок</div>
          </div>
        </div>
        <div class="col-4">
          <div class="wa-result-stat">
            <div class="wa-result-num text-muted">${res.skipped}</div>
            <div class="text-muted small">Пропущено</div>
          </div>
        </div>
      </div>
      ${res.dry_run ? `<div class="text-muted small"><i class="bi bi-info-circle me-1"></i>Это тестовый запуск — сообщения не отправлены реально</div>` : ""}
    `;
  }

  v("waDryRunBtn")?.addEventListener("click",        () => sendCampaign(true));
  v("waSendCampaignBtn")?.addEventListener("click",  () => sendCampaign(false));

  // ── Init ──────────────────────────────────────────
  loadStatus();
  loadTemplates();
  loadCampaigns();
}

// =========================
// Entry
// =========================
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  jsinitMobileSidebar();
  initAiPanelUpgrades();

  // важно: чтобы работали page-* стили (и твой .page-desktop #aiPanelBtn)
  applyBodyPageClass();

  const page = window.__ADMIN_PAGE__;
  if (page === "desktop") initDesktopPage();
  else if (page === "news") initNewsPage();
  else if (page === "clients" || page === "index") initClientsList();
  else if (page === "client") initClientCard();
  else if (page === "transactions") initTransactionsPage();
  else if (page === "settings") initSettingsPage();
  else if (page === "analytics") initAnalyticsPage();
  else if (page === "campaigns") initCampaignsPage();
  else if (page === "campaign_detail") initCampaignDetailPage();
  else if (page === "accounts") initAccountsPage();
  else if (page === "videos") initVideosPage();
  else if (page === "whatsapp") initWhatsappPage();

  initAiOverviewWidget();
  initAiPanel();
});
// Р”РѕР±Р°РІРёС‚СЊ РІ static/js/admin.js вЂ” РІ РєРѕРЅРµС† С„Р°Р№Р»Р° РёР»Рё РїРѕСЃР»Рµ DOMContentLoaded
// РђРґР°РїС‚РёРІРЅС‹Р№ С€СЂРёС„С‚ РґР»СЏ Р±РѕР»СЊС€РёС… С‡РёСЃРµР» РЅР° РґР°С€Р±РѕСЂРґРµ

function adaptiveFontSize(el) {
  if (!el) return;
  const text = el.textContent.replace(/\s/g, '');
  const len = text.length;
  let size;
  if (len <= 7)       size = '2rem';      // РґРѕ 9 999 999
  else if (len <= 9)  size = '1.5rem';    // РґРѕ 999 999 999
  else if (len <= 11) size = '1.2rem';    // РґРѕ 99 999 999 999
  else                size = '1rem';
  el.style.fontSize = size;
  el.style.fontWeight = len > 9 ? '700' : '900';
  el.style.lineHeight = '1.2';
}

function applyAdaptiveFonts() {
  // Р’СЃРµ С‡РёСЃР»Р° РЅР° РґР°С€Р±РѕСЂРґРµ вЂ” РёС‰РµРј СЌР»РµРјРµРЅС‚С‹ СЃ Р±РѕР»СЊС€РёРјРё С‡РёСЃР»Р°РјРё
  const selectors = [
    '#dashRevenue30', '#dashAvgCheck30', '#dashTxCount30',
    '#dashNewClients',
    '[data-adaptive-font]',
    '.stat-big', '.kpi-value', '.metric-value',
    // РђРЅР°Р»РёС‚РёРєР°
    '#anRevenue30', '#anAvgCheck', '#anClients',
  ];
  selectors.forEach(sel => {
    document.querySelectorAll(sel).forEach(adaptiveFontSize);
  });
}

// Р—Р°РїСѓСЃРєР°С‚СЊ РїРѕСЃР»Рµ Р·Р°РіСЂСѓР·РєРё РґР°РЅРЅС‹С…
document.addEventListener('DOMContentLoaded', () => {
  // РќР°Р±Р»СЋРґР°РµРј Р·Р° РёР·РјРµРЅРµРЅРёСЏРјРё РІ С‡РёСЃР»Р°С…
  const observer = new MutationObserver((mutations) => {
    mutations.forEach(m => {
      if (m.type === 'characterData' || m.type === 'childList') {
        const el = m.target.nodeType === 3 ? m.target.parentElement : m.target;
        if (el && (el.id?.includes('Revenue') || el.id?.includes('Check') || 
                   el.id?.includes('Count') || el.id?.includes('Clients') ||
                   el.classList?.contains('stat-big'))) {
          adaptiveFontSize(el);
        }
      }
    });
  });

  observer.observe(document.body, {
    childList: true, subtree: true, characterData: true
  });

  // РџРµСЂРІС‹Р№ Р·Р°РїСѓСЃРє С‡РµСЂРµР· 500РјСЃ (РїРѕСЃР»Рµ Р·Р°РіСЂСѓР·РєРё РґР°РЅРЅС‹С…)
  setTimeout(applyAdaptiveFonts, 500);
  setTimeout(applyAdaptiveFonts, 1500);
});