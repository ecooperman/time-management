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
      await fetchJSON(`/api/categories/${category.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
      });
      showMessage(`Saved "${nameInput.value}".`, "success");
      loadCategories();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.textContent = "Delete";
  deleteBtn.className = "danger";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete category "${category.name}"?`)) return;
    try {
      await fetchJSON(`/api/categories/${category.id}`, { method: "DELETE" });
      showMessage(`Deleted "${category.name}".`, "success");
      loadCategories();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });

  row.appendChild(colorInput);
  row.appendChild(nameInput);
  row.appendChild(saveBtn);
  row.appendChild(deleteBtn);
  return row;
}

async function loadCategories() {
  const categories = await fetchJSON("/api/categories");
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
      await fetchJSON("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
      });
      nameInput.value = "";
      showMessage("Category added.", "success");
      loadCategories();
    } catch (err) {
      showMessage(err.message, "error");
    }
  });
}

initAddForm();
loadCategories();
