
function categoryRowElement(category) {
  const row = document.createElement("div");
  row.className = "category-row";
  row.dataset.categoryId = category.id;

  const colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.value = category.color;

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = category.name;

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    try {
      await Global.fetchJSON(`/api/categories/${category.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
      });
      Global.showMessage(`Saved "${nameInput.value}".`, "success");
      loadCategories();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete category "${category.name}"?`)) return;
    try {
      await Global.fetchJSON(`/api/categories/${category.id}`, { method: "DELETE" });
      Global.showMessage(`Deleted "${category.name}".`, "success");
      loadCategories();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  row.appendChild(colorInput);
  row.appendChild(nameInput);
  row.appendChild(saveBtn);
  row.appendChild(deleteBtn);
  return row;
}

async function loadCategories() {
  const categories = await Global.fetchJSON("/api/categories");
  const container = document.getElementById("category-rows");
  container.innerHTML = "";
  for (const category of categories) {
    container.appendChild(categoryRowElement(category));
  }
}

function initAddForm() {
  document.getElementById("add-category-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("new-category-name");
    const colorInput = document.getElementById("new-category-color");
    try {
      await Global.fetchJSON("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
      });
      nameInput.value = "";
      Global.showMessage("Category added.", "success");
      loadCategories();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

function personRowElement(person, resumePeople) {
  const row = document.createElement("div");
  row.className = "category-row";
  row.dataset.personId = person.id;

  const colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.value = person.color;

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = person.name;

  const resumeSelect = document.createElement("select");
  const defaultPerson = resumePeople.find((p) => p.is_default);
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = defaultPerson ? `Default (${defaultPerson.name})` : "Default";
  resumeSelect.appendChild(defaultOption);
  // If this person's saved slug isn't in the resume app's current list
  // (resume app was unreachable when this loaded, or that person was
  // renamed/deleted there since), include it anyway so Save doesn't
  // silently wipe their choice back to the default the moment they click
  // it.
  const knownSlugs = resumePeople.map((p) => p.slug);
  const extraSlug =
    person.resume_person_slug && !knownSlugs.includes(person.resume_person_slug) ? person.resume_person_slug : null;
  for (const p of resumePeople) {
    const opt = document.createElement("option");
    opt.value = p.slug;
    opt.textContent = p.name;
    resumeSelect.appendChild(opt);
  }
  if (extraSlug) {
    const opt = document.createElement("option");
    opt.value = extraSlug;
    opt.textContent = `${extraSlug} (not found in resume app)`;
    resumeSelect.appendChild(opt);
  }
  resumeSelect.value = person.resume_person_slug || "";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    try {
      await Global.fetchJSON(`/api/people/${person.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: nameInput.value,
          color: colorInput.value,
          resume_person_slug: resumeSelect.value || null,
        }),
      });
      Global.showMessage(`Saved "${nameInput.value}".`, "success");
      loadPeople();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete "${person.name}"?`)) return;
    try {
      await Global.fetchJSON(`/api/people/${person.id}`, { method: "DELETE" });
      Global.showMessage(`Deleted "${person.name}".`, "success");
      loadPeople();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });

  row.appendChild(colorInput);
  row.appendChild(nameInput);
  row.appendChild(resumeSelect);
  row.appendChild(saveBtn);
  row.appendChild(deleteBtn);
  return row;
}

async function loadPeople() {
  const people = await Global.fetchJSON("/api/people");

  // The resume app owns every person and their resume content - this just
  // asks it who's available rather than storing/uploading anything
  // resume-related here. Degrades gracefully (empty list, not a
  // page-breaking error) if the resume app happens to be unreachable when
  // Settings loads.
  let resumePeople = [];
  try {
    const data = await Global.fetchJSON("/api/people/resume-people");
    resumePeople = data.people;
  } catch (err) {
    Global.showMessage(`Couldn't load people from the resume app: ${err.message}`, "error");
  }

  const container = document.getElementById("person-rows");
  container.innerHTML = "";
  for (const person of people) {
    container.appendChild(personRowElement(person, resumePeople));
  }
}

function initAddPersonForm() {
  document.getElementById("add-person-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("new-person-name");
    const colorInput = document.getElementById("new-person-color");
    try {
      await Global.fetchJSON("/api/people", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
      });
      nameInput.value = "";
      Global.showMessage("Person added.", "success");
      loadPeople();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function refreshPushStatus() {
  const statusEl = document.getElementById("push-status");
  const btn = document.getElementById("push-subscribe-btn");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    statusEl.textContent = "This browser doesn't support push notifications.";
    btn.disabled = true;
    return;
  }
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing) {
    statusEl.textContent = "Reminders are enabled on this device.";
    btn.textContent = "Disable reminders on this device";
  } else {
    statusEl.textContent = "Reminders are not enabled on this device yet.";
    btn.textContent = "Enable reminders on this device";
  }
}

function initPushSubscribe() {
  document.getElementById("push-subscribe-btn").addEventListener("click", async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    try {
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();

      if (existing) {
        await Global.fetchJSON("/api/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: existing.endpoint }),
        });
        await existing.unsubscribe();
        Global.showMessage("Reminders disabled on this device.", "success");
        refreshPushStatus();
        return;
      }

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        Global.showMessage("Notification permission was not granted.", "error");
        return;
      }

      const { key } = await Global.fetchJSON("/api/push/vapid-public-key");
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
      await Global.fetchJSON("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(subscription.toJSON()),
      });
      Global.showMessage("Reminders enabled on this device.", "success");
      refreshPushStatus();
    } catch (err) {
      Global.showMessage(err.message, "error");
    }
  });
  refreshPushStatus();
}

initAddForm();
initAddPersonForm();
initPushSubscribe();
loadCategories();
loadPeople();
