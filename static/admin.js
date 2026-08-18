
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

function personRowElement(person) {
  const row = document.createElement("div");
  row.className = "category-row";
  row.dataset.personId = person.id;

  const colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.value = person.color;

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = person.name;

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.addEventListener("click", async () => {
    try {
      await Global.fetchJSON(`/api/people/${person.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameInput.value, color: colorInput.value }),
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
  row.appendChild(saveBtn);
  row.appendChild(deleteBtn);
  return row;
}

async function loadPeople() {
  const people = await Global.fetchJSON("/api/people");
  const container = document.getElementById("person-rows");
  container.innerHTML = "";
  for (const person of people) {
    container.appendChild(personRowElement(person));
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

initAddForm();
initAddPersonForm();
loadCategories();
loadPeople();
