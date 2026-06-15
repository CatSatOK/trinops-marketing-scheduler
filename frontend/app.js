"use strict";

// ---- Shared helpers --------------------------------------------------------

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = isError ? "error" : "";
  setTimeout(() => el.classList.add("hidden"), 4000);
}

function actionButton(label, cls, handler) {
  const btn = document.createElement("button");
  btn.textContent = label;
  btn.className = `btn ${cls}`;
  btn.addEventListener("click", handler);
  return btn;
}

function bindFilters(containerId, datasetKey, apply) {
  const container = document.getElementById(containerId);
  container.addEventListener("click", (event) => {
    const btn = event.target.closest(".filter");
    if (!btn) return;
    container.querySelectorAll(".filter").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    apply(btn.dataset[datasetKey]);
  });
}

const fmtDateTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });

// ---- Campaigns page --------------------------------------------------------

function initCampaignsPage() {
  let filter = "";

  function postBadges(campaign) {
    const byPlatform = Object.fromEntries(campaign.results.map((r) => [r.platform, r]));
    return campaign.platforms
      .map((p) => {
        const r = byPlatform[p];
        const status = r ? r.status : "PENDING";
        const tip = r
          ? (r.error_message || `published (attempt ${r.attempts})`)
          : "not attempted yet";
        const retries = r && r.attempts > 1 ? ` <span class="attempts">×${r.attempts}</span>` : "";
        return `<span class="pill pill-${status}" title="${tip}">${p}${retries}</span>`;
      })
      .join(" ");
  }

  async function loadCampaigns() {
    const query = filter ? `?status=${filter}` : "";
    const campaigns = await api(`/campaigns${query}`);
    const tbody = document.getElementById("campaign-rows");
    tbody.innerHTML = "";
    document.getElementById("campaign-empty").classList.toggle("hidden", campaigns.length > 0);

    for (const c of campaigns) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${c.id}</td>
        <td>${c.title}</td>
        <td class="muted">${fmtDateTime(c.scheduled_at)}</td>
        <td class="platforms">${postBadges(c)}</td>
        <td><span class="badge badge-${c.status}">${c.status}</span></td>
        <td class="actions"></td>`;
      const actions = tr.querySelector(".actions");
      if (c.status === "QUEUED") {
        actions.appendChild(actionButton("Publish now", "btn-accept", () => publishNow(c.id)));
      }
      for (const r of c.results.filter((x) => x.status === "FAILED")) {
        actions.appendChild(
          actionButton(`Retry ${r.platform}`, "btn-ghost", () => retry(c.id, r.platform))
        );
      }
      tbody.appendChild(tr);
    }
    return campaigns;
  }

  function updateCards(campaigns) {
    const count = (s) => campaigns.filter((c) => c.status === s).length;
    document.getElementById("card-queued").textContent = count("QUEUED");
    document.getElementById("card-published").textContent = count("PUBLISHED");
    document.getElementById("card-partial").textContent = count("PARTIAL");
    document.getElementById("card-failed").textContent = count("FAILED");
  }

  function renderCalendar(campaigns) {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    document.getElementById("calendar-month").textContent =
      now.toLocaleString("en-GB", { month: "long", year: "numeric" });

    const byDay = {};
    for (const c of campaigns) {
      const d = new Date(c.scheduled_at);
      if (d.getFullYear() === year && d.getMonth() === month) {
        (byDay[d.getDate()] ||= []).push(c);
      }
    }

    const first = new Date(year, month, 1).getDay(); // 0=Sun
    const offset = (first + 6) % 7; // make Monday the first column
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const cal = document.getElementById("calendar");
    cal.innerHTML = "";
    for (const label of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
      const head = document.createElement("div");
      head.className = "cal-head";
      head.textContent = label;
      cal.appendChild(head);
    }
    for (let i = 0; i < offset; i++) cal.appendChild(document.createElement("div"));
    for (let day = 1; day <= daysInMonth; day++) {
      const cell = document.createElement("div");
      cell.className = "cal-day";
      if (day === now.getDate()) cell.classList.add("today");
      cell.innerHTML = `<span class="cal-num">${day}</span>`;
      for (const c of byDay[day] || []) {
        const dot = document.createElement("div");
        dot.className = `cal-event badge-${c.status}`;
        dot.textContent = c.title;
        dot.title = `${c.title} — ${c.status}`;
        cell.appendChild(dot);
      }
      cal.appendChild(cell);
    }
  }

  async function publishNow(id) {
    try {
      await api(`/campaigns/${id}/publish`, { method: "POST" });
      toast(`Campaign ${id} dispatched`);
      refresh();
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function retry(id, platform) {
    try {
      await api(`/campaigns/${id}/retry/${platform}`, { method: "POST" });
      toast(`Retried ${platform} for campaign ${id}`);
      refresh();
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function refresh() {
    const campaigns = await loadCampaigns();
    // cards + calendar always reflect the full set, not the filtered view
    const all = filter ? await api("/campaigns") : campaigns;
    updateCards(all);
    renderCalendar(all);
  }

  bindFilters("campaign-filters", "status", (value) => { filter = value; refresh(); });

  // ---- New campaign modal --------------------------------------------------

  const backdrop = document.getElementById("modal-backdrop");

  async function openModal() {
    const platforms = await api("/campaigns/platforms");
    const box = document.getElementById("platform-choices");
    box.innerHTML = "";
    for (const p of platforms) {
      const label = document.createElement("label");
      label.className = "choice";
      label.innerHTML = `<input type="checkbox" name="platform" value="${p}" checked> ${p}`;
      box.appendChild(label);
    }
    backdrop.classList.remove("hidden");
  }

  function closeModal() {
    backdrop.classList.add("hidden");
    document.getElementById("campaign-form").reset();
  }

  async function submitCampaign(event) {
    event.preventDefault();
    const form = event.target;
    const platforms = [...form.querySelectorAll('input[name="platform"]:checked')].map((c) => c.value);
    if (platforms.length === 0) {
      toast("Pick at least one platform", true);
      return;
    }
    const payload = {
      title: form.title.value.trim(),
      content: form.content.value.trim(),
      media_url: form.media_url.value.trim() || null,
      platforms,
    };
    // datetime-local is local time; send as UTC ISO so it matches the scheduler
    if (form.scheduled_at.value) {
      payload.scheduled_at = new Date(form.scheduled_at.value).toISOString();
    }
    try {
      await api("/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast("Campaign created and queued");
      closeModal();
      refresh();
    } catch (err) {
      toast(err.message, true);
    }
  }

  document.getElementById("new-campaign-btn").addEventListener("click", openModal);
  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
  document.getElementById("campaign-form").addEventListener("submit", submitCampaign);

  refresh();
  setInterval(refresh, 30000);
}

// ---- Leads page ------------------------------------------------------------

function initLeadsPage() {
  let filter = "";

  async function loadLeads() {
    const query = filter ? `?category=${filter}` : "";
    const leads = await api(`/leads${query}`);
    const tbody = document.getElementById("lead-rows");
    tbody.innerHTML = "";
    document.getElementById("lead-empty").classList.toggle("hidden", leads.length > 0);

    for (const l of leads) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="prio prio-${l.priority}">P${l.priority}</span></td>
        <td>${l.company || "<span class='muted'>unknown</span>"}</td>
        <td class="muted">${l.name || "–"}<br><span class="email">${l.email || ""}</span></td>
        <td>${l.service_interest || "<span class='muted'>unspecified</span>"}</td>
        <td>${l.score}</td>
        <td><span class="badge badge-${l.category}">${l.category}</span></td>
        <td class="muted">${l.routed_to}</td>
        <td class="notes-cell"></td>`;

      const notes = document.createElement("textarea");
      notes.className = "notes-input";
      notes.rows = 2;
      notes.placeholder = "Add notes…";
      notes.value = l.notes || "";
      // save on blur only when the text actually changed
      let original = notes.value;
      notes.addEventListener("blur", () => {
        if (notes.value === original) return;
        saveNotes(l.id, notes.value).then(() => { original = notes.value; });
      });
      tr.querySelector(".notes-cell").appendChild(notes);
      tbody.appendChild(tr);
    }
    return leads;
  }

  async function saveNotes(id, notes) {
    try {
      await api(`/leads/${id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      toast("Notes saved");
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function loadScoringExplainer() {
    const body = document.getElementById("scoring-body");
    if (!body || body.dataset.loaded) return;
    const rubric = await api("/leads/scoring");
    const signal = (s) => `
      <div class="rubric-signal">
        <div class="rubric-name">${s.name}</div>
        ${s.bands.map((b) => `<div class="rubric-band"><span>${b.label}</span><span class="rubric-pts">+${b.points}</span></div>`).join("")}
      </div>`;
    const cat = (c) => `<li><span class="badge badge-${c.category}">${c.category}</span> ${c.rule} → priority ${c.priority}</li>`;
    body.innerHTML = `
      <p class="muted">Each lead is scored from three structured fields on the form (no AI). Points add up to a maximum of ${rubric.max_score}.</p>
      <div class="rubric-signals">${rubric.signals.map(signal).join("")}</div>
      <ul class="rubric-cats">${rubric.categories.map(cat).join("")}</ul>`;
    body.dataset.loaded = "1";
  }

  function updateCards(leads) {
    const count = (c) => leads.filter((l) => l.category === c).length;
    document.getElementById("card-hot").textContent = count("HOT");
    document.getElementById("card-warm").textContent = count("WARM");
    document.getElementById("card-cold").textContent = count("COLD");
    document.getElementById("card-total").textContent = leads.length;
  }

  async function refresh() {
    const leads = await loadLeads();
    const all = filter ? await api("/leads") : leads;
    updateCards(all);
  }

  bindFilters("lead-filters", "category", (value) => { filter = value; refresh(); });
  loadScoringExplainer();
  refresh();
  setInterval(refresh, 30000);
}
