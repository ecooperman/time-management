let categories = [];
let categoriesById = {};
let jobs = [];
let jobsById = {};
let activeTaskId = null;

let currentView = "workWeek"; // 'day' | 'workWeek' | 'week' | 'month'
let anchorDate = new Date();
anchorDate.setHours(0, 0, 0, 0);

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `${url} -> ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (e) {
      // ignore, use default detail
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function minutesLabel(mins) {
  if (mins === null || mins === undefined) return null;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

// --- date helpers (all local-time, no UTC conversion) ---

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function startOfWeek(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function isoDateTime(date) {
  return `${toISODate(date)}T00:00:00`;
}

function getVisibleDays(view, anchor) {
  if (view === "day") return [new Date(anchor)];
  if (view === "workWeek") {
    const monday = addDays(startOfWeek(anchor), 1);
    return [0, 1, 2, 3, 4].map((i) => addDays(monday, i));
  }
  if (view === "week") {
    const sunday = startOfWeek(anchor);
    return [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(sunday, i));
  }
  // month: pad to full weeks so the grid always shows complete rows
  const firstOfMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const lastOfMonth = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const gridStart = startOfWeek(firstOfMonth);
  const gridEnd = addDays(startOfWeek(lastOfMonth), 6);
  const days = [];
  for (let d = new Date(gridStart); d <= gridEnd; d = addDays(d, 1)) {
    days.push(new Date(d));
  }
  return days;
}

function shiftAnchor(direction) {
  if (currentView === "day") {
    anchorDate = addDays(anchorDate, direction);
  } else if (currentView === "workWeek" || currentView === "week") {
    anchorDate = addDays(anchorDate, 7 * direction);
  } else {
    anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() + direction, 1);
  }
  loadAndRenderCalendar();
}

function updateNavTitle(days) {
  const title = document.getElementById("nav-title");
  if (currentView === "day") {
    title.textContent = anchorDate.toLocaleDateString(undefined, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  } else if (currentView === "month") {
    title.textContent = anchorDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  } else {
    const first = days[0];
    const last = days[days.length - 1];
    title.textContent = `${first.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${last.toLocaleDateString(
      undefined,
      { month: "short", day: "numeric", year: "numeric" }
    )}`;
  }
}

// --- categories ---

function populateCategorySelects() {
  const selects = [document.getElementById("task-category"), document.getElementById("modal-task-category")];
  for (const select of selects) {
    select.innerHTML = "";
    for (const cat of categories) {
      const opt = document.createElement("option");
      opt.value = cat.id;
      opt.textContent = cat.name;
      select.appendChild(opt);
    }
  }
}

async function loadCategories() {
  categories = await fetchJSON("/api/categories");
  categoriesById = Object.fromEntries(categories.map((c) => [c.id, c]));
  populateCategorySelects();
}

function getApplyingCategoryId() {
  const match = categories.find((c) => c.name === "Applying for Jobs");
  if (match) return match.id;
  return categories.length ? categories[0].id : null;
}

// --- task card + sortable lists ---

function companyNode(job) {
  if (!job || !job.company) return null;
  if (job.company_url) {
    const link = document.createElement("a");
    link.href = job.company_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = job.company;
    link.addEventListener("click", (e) => e.stopPropagation());
    return link;
  }
  return document.createTextNode(job.company);
}

function taskCardElement(task) {
  const cat = categoriesById[task.category_id];
  const card = document.createElement("div");
  card.className = "task-card status-" + task.status + (task.is_important ? " important" : "");
  card.dataset.taskId = task.id;
  card.style.setProperty("--cat-color", cat ? cat.color : "#999");

  const title = document.createElement("div");
  title.className = "task-title";
  if (task.is_important) {
    const star = document.createElement("span");
    star.className = "star";
    star.textContent = "★ ";
    title.appendChild(star);
  }
  if (task.repeat_daily || task.series_id) {
    const repeatIcon = document.createElement("span");
    repeatIcon.className = "repeat-icon";
    repeatIcon.textContent = "⟳ ";
    repeatIcon.title = "Repeats daily";
    title.appendChild(repeatIcon);
  }
  title.appendChild(document.createTextNode(task.title));
  card.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "task-meta";
  const metaParts = [document.createTextNode(cat ? cat.name : "Uncategorized")];
  const est = minutesLabel(task.estimate_minutes);
  if (est) metaParts.push(document.createTextNode(`est ${est}`));
  const company = companyNode(task.job);
  if (company) metaParts.push(company);
  if (task.status === "on_hold") metaParts.push(document.createTextNode("on hold"));
  metaParts.forEach((node, i) => {
    if (i > 0) meta.appendChild(document.createTextNode(" · "));
    meta.appendChild(node);
  });
  card.appendChild(meta);

  card.addEventListener("click", () => openModal(task));
  return card;
}

function attachSortable(el) {
  if (el._sortable) el._sortable.destroy();
  el._sortable = new Sortable(el, {
    group: { name: "tasks", put: ["tasks", "jobs"] },
    animation: 150,
    onEnd: handleSortEnd,
  });
}

function attachJobsSortable(el) {
  if (el._sortable) el._sortable.destroy();
  el._sortable = new Sortable(el, {
    group: { name: "jobs", pull: "clone", put: false },
    sort: false,
    animation: 150,
    onEnd: handleSortEnd,
  });
}

async function handleJobDroppedOnTaskList(evt) {
  const jobId = Number(evt.item.dataset.jobId);
  evt.item.remove();
  const job = jobsById[jobId];
  if (!job) return;

  const date = evt.to.dataset.date || null;
  const task = await fetchJSON("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: `Apply to ${job.name}`,
      category_id: getApplyingCategoryId(),
      job_id: jobId,
    }),
  });
  if (date) {
    await fetchJSON(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheduled_date: `${date}T00:00:00`, due_date: `${date}T00:00:00` }),
    });
  }
  refreshAll();
}

async function handleSortEnd(evt) {
  const fromEl = evt.from;
  const toEl = evt.to;

  // A job card was dragged (cloned) from the Jobs list onto a task list -
  // create a linked task rather than treating this as a task reorder.
  if (evt.item.dataset.jobId && toEl.id !== "jobs-list") {
    await handleJobDroppedOnTaskList(evt);
    return;
  }

  if (fromEl === toEl && evt.oldIndex === evt.newIndex) return;

  const updates = [];
  const collect = (containerEl) => {
    const date = containerEl.dataset.date || null;
    Array.from(containerEl.children).forEach((el, idx) => {
      if (!el.dataset.taskId) return;
      updates.push({
        id: Number(el.dataset.taskId),
        scheduled_date: date ? `${date}T00:00:00` : null,
        due_date: date ? `${date}T00:00:00` : null,
        sort_order: (idx + 1) * 10,
      });
    });
  };
  collect(toEl);
  if (fromEl !== toEl) collect(fromEl);

  await fetchJSON("/api/tasks/reorder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
}

function bucketTasksByDate(tasks) {
  const map = {};
  for (const task of tasks) {
    if (!task.scheduled_date) continue;
    const key = task.scheduled_date.slice(0, 10);
    (map[key] = map[key] || []).push(task);
  }
  return map;
}

function renderGrid(days, buckets) {
  const calendarEl = document.getElementById("calendar");
  calendarEl.className = currentView === "month" ? "grid-view" : "row-view";
  calendarEl.innerHTML = "";

  const grid = document.createElement("div");
  grid.className = "cal-grid";
  const todayKey = toISODate(new Date());

  for (const day of days) {
    const key = toISODate(day);
    const col = document.createElement("div");
    col.className =
      "day-col" + (currentView === "month" && day.getMonth() !== anchorDate.getMonth() ? " other-month" : "");

    const header = document.createElement("div");
    header.className = "day-col-header" + (key === todayKey ? " today" : "");
    const weekdayShort = day.toLocaleDateString(undefined, { weekday: "short" });
    const dateLabel = day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    header.innerHTML = `<span class="weekday">${weekdayShort}</span>${dateLabel}`;
    col.appendChild(header);

    const list = document.createElement("div");
    list.className = "task-list";
    list.dataset.date = key;
    for (const task of buckets[key] || []) {
      list.appendChild(taskCardElement(task));
    }
    col.appendChild(list);

    grid.appendChild(col);
    attachSortable(list);
  }

  calendarEl.appendChild(grid);
}

async function loadAndRenderCalendar() {
  const days = getVisibleDays(currentView, anchorDate);
  const start = isoDateTime(days[0]);
  const end = isoDateTime(addDays(days[days.length - 1], 1));
  const tasks = await fetchJSON(`/api/tasks?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
  renderGrid(days, bucketTasksByDate(tasks));
  updateNavTitle(days);
}

function renderBacklog(tasks) {
  const list = document.getElementById("backlog-list");
  list.innerHTML = "";
  for (const task of tasks) {
    list.appendChild(taskCardElement(task));
  }
  attachSortable(list);
}

async function refreshBacklog() {
  const tasks = await fetchJSON("/api/tasks/backlog");
  renderBacklog(tasks);
}

// --- jobs ---

function jobCardElement(job) {
  const card = document.createElement("div");
  card.className = "job-card" + (job.applied ? " applied" : "");
  card.dataset.jobId = job.id;

  const title = document.createElement("div");
  title.className = "job-title";
  title.textContent = job.name;
  card.appendChild(title);

  if (job.company) {
    const companyLine = document.createElement("div");
    companyLine.className = "job-company";
    companyLine.appendChild(companyNode(job));
    card.appendChild(companyLine);
  }

  const meta = document.createElement("div");
  meta.className = "job-meta";

  const link = document.createElement("a");
  link.className = "job-link";
  link.href = job.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = job.url;
  link.addEventListener("click", (e) => e.stopPropagation());
  meta.appendChild(link);

  const toggleLabel = document.createElement("label");
  toggleLabel.className = "applied-toggle";
  const toggleInput = document.createElement("input");
  toggleInput.type = "checkbox";
  toggleInput.checked = job.applied;
  toggleInput.addEventListener("click", (e) => e.stopPropagation());
  toggleInput.addEventListener("change", async () => {
    await fetchJSON(`/api/jobs/${job.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ applied: toggleInput.checked }),
    });
    refreshJobs();
  });
  toggleLabel.appendChild(toggleInput);
  toggleLabel.appendChild(document.createTextNode("Applied"));
  meta.appendChild(toggleLabel);

  card.appendChild(meta);

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "job-delete";
  deleteBtn.textContent = "✕";
  deleteBtn.title = "Delete job";
  deleteBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await fetchJSON(`/api/jobs/${job.id}`, { method: "DELETE" });
      refreshJobs();
    } catch (err) {
      alert(err.message);
    }
  });
  card.appendChild(deleteBtn);

  card.addEventListener("click", () => openJobModal(job));

  return card;
}

function renderJobs(jobsData) {
  jobs = jobsData;
  jobsById = Object.fromEntries(jobs.map((j) => [j.id, j]));
  const list = document.getElementById("jobs-list");
  list.innerHTML = "";
  for (const job of jobs) {
    list.appendChild(jobCardElement(job));
  }
  attachJobsSortable(list);
}

async function refreshJobs() {
  const jobsData = await fetchJSON("/api/jobs");
  renderJobs(jobsData);
}

function initAddJobForm() {
  document.getElementById("add-job-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("job-name").value.trim();
    const url = document.getElementById("job-url").value.trim();
    const company = document.getElementById("job-company").value.trim();
    const companyUrl = document.getElementById("job-company-url").value.trim();
    if (!name || !url) return;
    await fetchJSON("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, url, company: company || null, company_url: companyUrl || null }),
    });
    e.target.reset();
    refreshJobs();
  });
}

// --- job modal ---

let activeJobId = null;

function openJobModal(job) {
  activeJobId = job.id;
  document.getElementById("job-modal-name").value = job.name;
  document.getElementById("job-modal-url").value = job.url;
  document.getElementById("job-modal-company").value = job.company || "";
  document.getElementById("job-modal-company-url").value = job.company_url || "";
  document.getElementById("job-modal-applied").checked = !!job.applied;
  document.getElementById("job-modal").classList.remove("hidden");
}

function closeJobModal() {
  activeJobId = null;
  document.getElementById("job-modal").classList.add("hidden");
}

function initJobModal() {
  document.getElementById("job-modal-close").addEventListener("click", closeJobModal);

  document.getElementById("job-modal-save").addEventListener("click", async () => {
    const name = document.getElementById("job-modal-name").value.trim();
    const url = document.getElementById("job-modal-url").value.trim();
    const company = document.getElementById("job-modal-company").value.trim();
    const companyUrl = document.getElementById("job-modal-company-url").value.trim();
    if (!name || !url) return;
    try {
      await fetchJSON(`/api/jobs/${activeJobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          url,
          company: company || null,
          company_url: companyUrl || null,
          applied: document.getElementById("job-modal-applied").checked,
        }),
      });
      closeJobModal();
      refreshAll();
    } catch (err) {
      alert(err.message);
    }
  });

  document.getElementById("job-modal-delete").addEventListener("click", async () => {
    try {
      await fetchJSON(`/api/jobs/${activeJobId}`, { method: "DELETE" });
      closeJobModal();
      refreshJobs();
    } catch (err) {
      alert(err.message);
    }
  });
}

async function refreshAll() {
  await Promise.all([loadAndRenderCalendar(), refreshBacklog(), refreshJobs()]);
}

// --- view toggle + nav ---

function setActiveViewButton(view) {
  document.querySelectorAll("#view-toggle button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
}

function initViewToggle() {
  document.querySelectorAll("#view-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentView = btn.dataset.view;
      setActiveViewButton(currentView);
      loadAndRenderCalendar();
    });
  });
  setActiveViewButton(currentView);
}

function initNavControls() {
  document.getElementById("nav-prev").addEventListener("click", () => shiftAnchor(-1));
  document.getElementById("nav-next").addEventListener("click", () => shiftAnchor(1));
  document.getElementById("nav-today").addEventListener("click", () => {
    anchorDate = new Date();
    anchorDate.setHours(0, 0, 0, 0);
    loadAndRenderCalendar();
  });
}

// --- modal ---

function openModal(task) {
  activeTaskId = task.id;
  document.getElementById("modal-title").textContent = task.title;
  document.getElementById("modal-task-title").value = task.title;
  document.getElementById("modal-task-category").value = task.category_id;
  document.getElementById("modal-task-description").value = task.description || "";
  document.getElementById("modal-task-estimate").value = task.estimate_minutes ?? "";
  document.getElementById("modal-task-actual").value = task.actual_minutes ?? "";
  document.getElementById("modal-task-important").checked = !!task.is_important;
  document.getElementById("modal-task-status").textContent = task.status;

  const repeatCheckbox = document.getElementById("modal-task-repeat");
  const repeatUntilRow = document.getElementById("modal-repeat-until-row");
  const isScheduled = !!task.scheduled_date;
  repeatCheckbox.disabled = !isScheduled;
  repeatCheckbox.checked = isScheduled && !!task.repeat_daily;
  document.getElementById("modal-task-repeat-until").value = task.repeat_until ? task.repeat_until.slice(0, 10) : "";
  repeatUntilRow.classList.toggle("hidden", !repeatCheckbox.checked);
  document.getElementById("modal-repeat-disabled-hint").classList.toggle("hidden", isScheduled);

  const linkedJobEl = document.getElementById("modal-linked-job");
  if (task.job) {
    linkedJobEl.classList.remove("hidden");
    const link = document.getElementById("modal-linked-job-link");
    link.textContent = task.job.name;
    link.href = task.job.url;

    const companyEl = document.getElementById("modal-linked-job-company");
    companyEl.innerHTML = "";
    const company = companyNode(task.job);
    if (company) {
      companyEl.appendChild(document.createTextNode(" at "));
      companyEl.appendChild(company);
    }

    document.getElementById("modal-linked-job-applied").innerHTML = task.job.applied
      ? '<span class="applied-badge">Applied</span>'
      : '<span class="not-applied-badge">Not applied yet</span>';
  } else {
    linkedJobEl.classList.add("hidden");
  }

  document.getElementById("modal-mark-done").classList.toggle("hidden", task.status === "done");
  document.getElementById("modal-reopen").classList.toggle("hidden", task.status !== "done");

  document.getElementById("task-modal").classList.remove("hidden");
}

function closeModal() {
  activeTaskId = null;
  document.getElementById("task-modal").classList.add("hidden");
}

function initModal() {
  document.getElementById("modal-close").addEventListener("click", closeModal);

  document.getElementById("modal-task-repeat").addEventListener("change", (e) => {
    document.getElementById("modal-repeat-until-row").classList.toggle("hidden", !e.target.checked);
  });

  document.getElementById("modal-save").addEventListener("click", async () => {
    const repeatUntil = document.getElementById("modal-task-repeat-until").value;
    await fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: document.getElementById("modal-task-title").value,
        category_id: Number(document.getElementById("modal-task-category").value),
        description: document.getElementById("modal-task-description").value,
        estimate_minutes: document.getElementById("modal-task-estimate").value
          ? Number(document.getElementById("modal-task-estimate").value)
          : null,
        actual_minutes: document.getElementById("modal-task-actual").value
          ? Number(document.getElementById("modal-task-actual").value)
          : null,
        is_important: document.getElementById("modal-task-important").checked,
        repeat_daily: document.getElementById("modal-task-repeat").checked,
        repeat_until: repeatUntil ? `${repeatUntil}T00:00:00` : null,
      }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-mark-done").addEventListener("click", async () => {
    await fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "done" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-reopen").addEventListener("click", async () => {
    await fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "open" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-toggle-hold").addEventListener("click", async () => {
    await fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "on_hold" }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-to-backlog").addEventListener("click", async () => {
    await fetchJSON(`/api/tasks/${activeTaskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "open", scheduled_date: null }),
    });
    closeModal();
    refreshAll();
  });

  document.getElementById("modal-delete").addEventListener("click", async () => {
    await fetchJSON(`/api/tasks/${activeTaskId}`, { method: "DELETE" });
    closeModal();
    refreshAll();
  });
}

function initAddTaskForm() {
  document.getElementById("add-task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("task-title").value.trim();
    if (!title) return;
    await fetchJSON("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        category_id: Number(document.getElementById("task-category").value),
        estimate_minutes: document.getElementById("task-estimate").value
          ? Number(document.getElementById("task-estimate").value)
          : null,
        description: document.getElementById("task-description").value,
        is_important: document.getElementById("task-important").checked,
      }),
    });
    e.target.reset();
    refreshBacklog();
  });
}

async function init() {
  await loadCategories();
  initViewToggle();
  initNavControls();
  initModal();
  initAddTaskForm();
  initAddJobForm();
  initJobModal();
  await refreshAll();
}

init();
