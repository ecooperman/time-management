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
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function showMessage(text, kind) {
  const el = document.getElementById("admin-message");
  el.textContent = text;
  el.className = "admin-message " + kind;
  setTimeout(() => el.classList.add("hidden"), 4000);
}

function labeledInput(labelText, type, value) {
  const label = document.createElement("label");
  label.appendChild(document.createTextNode(labelText));
  const input = document.createElement("input");
  input.type = type;
  input.value = value || "";
  label.appendChild(input);
  return { label, input };
}

function jobAdminCardElement(job) {
  const card = document.createElement("div");
  card.className = "job-admin-card" + (job.applied ? " applied" : "");
  card.dataset.jobId = job.id;

  // Collapsed by default - just enough to identify the job at a glance.
  // Client-side only for now; if this needs to survive a reload later, it
  // becomes a persisted field on the job and an API call here instead.
  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "job-admin-summary";
  summary.setAttribute("aria-expanded", "false");

  const title = document.createElement("span");
  title.className = "job-admin-summary-title";
  title.textContent = job.name;
  summary.appendChild(title);

  if (job.applied) {
    const badge = document.createElement("span");
    badge.className = "job-admin-applied-badge";
    badge.textContent = "Applied";
    summary.appendChild(badge);
  }

  const chevron = document.createElement("span");
  chevron.className = "job-admin-chevron";
  chevron.textContent = "▸";
  chevron.setAttribute("aria-hidden", "true");
  summary.appendChild(chevron);

  const details = document.createElement("div");
  details.className = "job-admin-details hidden";

  summary.addEventListener("click", () => {
    const expanded = card.classList.toggle("expanded");
    details.classList.toggle("hidden", !expanded);
    summary.setAttribute("aria-expanded", String(expanded));
  });

  card.append(summary, details);

  const fields = document.createElement("div");
  fields.className = "job-admin-fields";

  const name = labeledInput("Name", "text", job.name);
  const company = labeledInput("Company", "text", job.company);
  const url = labeledInput("URL", "url", job.url);
  const companyUrl = labeledInput("Company URL", "url", job.company_url);
  fields.append(name.label, company.label, url.label, companyUrl.label);
  details.appendChild(fields);

  const actions = document.createElement("div");
  actions.className = "job-admin-actions";

  const appliedLabel = document.createElement("label");
  appliedLabel.className = "checkbox-label";
  const appliedInput = document.createElement("input");
  appliedInput.type = "checkbox";
  appliedInput.checked = !!job.applied;
  appliedLabel.append(appliedInput, document.createTextNode("Applied"));
  actions.appendChild(appliedLabel);

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    const nameVal = name.input.value.trim();
    const urlVal = url.input.value.trim();
    if (!nameVal || !urlVal) {
      showMessage("Name and URL are required.", "error");
      return;
    }
    try {
      await fetchJSON(`/api/jobs/${job.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nameVal,
          url: urlVal,
          company: company.input.value.trim() || null,
          company_url: companyUrl.input.value.trim() || null,
          applied: appliedInput.checked,
        }),
      });
      showMessage(`Saved "${nameVal}".`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
  actions.appendChild(saveBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete "${job.name}"?`)) return;
    try {
      await fetchJSON(`/api/jobs/${job.id}`, { method: "DELETE" });
      showMessage(`Deleted "${job.name}".`, "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
  actions.appendChild(deleteBtn);

  details.appendChild(actions);
  return card;
}

async function loadJobs() {
  const jobs = await fetchJSON("/api/jobs");
  const container = document.getElementById("job-rows");
  container.innerHTML = "";
  if (jobs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.textContent = "No jobs yet - add one above to get started.";
    container.appendChild(empty);
    return;
  }
  for (const job of jobs) {
    container.appendChild(jobAdminCardElement(job));
  }
}

function initAddJobForm() {
  const form = document.getElementById("add-job-form");
  const showBtn = document.getElementById("show-add-job");
  const cancelBtn = document.getElementById("cancel-add-job");

  showBtn.addEventListener("click", () => {
    form.classList.remove("hidden");
    showBtn.classList.add("hidden");
    document.getElementById("new-job-name").focus();
  });

  cancelBtn.addEventListener("click", () => {
    form.reset();
    form.classList.add("hidden");
    showBtn.classList.remove("hidden");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-job-name").value.trim();
    const url = document.getElementById("new-job-url").value.trim();
    const company = document.getElementById("new-job-company").value.trim();
    const companyUrl = document.getElementById("new-job-company-url").value.trim();
    if (!name || !url) return;
    try {
      await fetchJSON("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, url, company: company || null, company_url: companyUrl || null }),
      });
      form.reset();
      form.classList.add("hidden");
      showBtn.classList.remove("hidden");
      showMessage("Job added.", "success");
      loadJobs();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
}

initAddJobForm();
loadJobs();
