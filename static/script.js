document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("employeeForm");
  const result = document.getElementById("result");
  const loadBtn = document.getElementById("loadUsers");
  const tbody = document.getElementById("usersList");
  const searchBox = document.getElementById("searchBox");
  const exportBtn = document.getElementById("exportCSV");
  const saveButton = form.querySelector('button[type="submit"]');

  const passwordModalEl = document.getElementById('resetPasswordModal');
  const passwordModal = new bootstrap.Modal(passwordModalEl);
  const passwordForm = document.getElementById('passwordChangeForm');
  const resetMsg = document.getElementById('resetPasswordMsg');
  const changePasswordLink = document.getElementById('changePasswordLink');
  const submitPasswordBtn = document.getElementById('submitPasswordBtn');

  let editingId = null;
  let currentSort = { column: "id", order: "asc" };
  let searchTimeout = null;

  function formatSalary(n) {
    if (!n) return "";
    const num = Number(n);
    if (isNaN(num)) return n;
    return "₹ " + new Intl.NumberFormat("en-IN").format(num);
  }

  function toInputDate(val) {
    if (!val) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(val)) return val;
    const date = new Date(val);
    if (!isNaN(date)) {
      return date.toISOString().split("T")[0];
    }
    return "";
  }

  async function loadUsers() {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center">Loading...</td></tr>`;
    try {
      const q = searchBox.value.trim();
      const url = `/get_users?search=${encodeURIComponent(q)}&sort_by=${currentSort.column}&order=${currentSort.order}&page=1&limit=1000`;
      const res = await fetch(url);
      const json = await res.json();

      if (!res.ok || json.status === "error") {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Failed to load data.</td></tr>`;
        return;
      }

      renderUsers(json.data);
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Error: ${err.message}</td></tr>`;
    }
  }

  function renderUsers(users) {
    tbody.innerHTML = "";
    if (!users || users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No employees found</td></tr>`;
      return;
    }

    users.forEach(user => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="align-middle">${user.id ?? ""}</td>
        <td class="align-middle">${user.emp_id ?? ""}</td>
        <td class="align-middle">${user.name ?? ""}</td>
        <td class="align-middle">${user.email ?? ""}</td>
        <td class="align-middle"><span class="badge bg-info">${user.department ?? ""}</span></td>
        <td class="align-middle">${formatSalary(user.salary)}</td>
        <td class="align-middle">${user.join_date ?? ""}</td>
        <td class="align-middle">
          <button class="btn btn-sm btn-warning me-2" title="Edit"><i class="fas fa-edit"></i></button>
          <button class="btn btn-sm btn-danger" title="Delete"><i class="fas fa-trash"></i></button>
        </td>
      `;
      tr.querySelector(".btn-warning").addEventListener("click", e => {
        e.stopPropagation();
        editUser(user.id);
      });
      tr.querySelector(".btn-danger").addEventListener("click", e => {
        e.stopPropagation();
        deleteUser(user.id);
      });
      tbody.appendChild(tr);
    });
  }

  form.addEventListener("submit", async e => {
    e.preventDefault();
    result.style.color = "black";
    result.textContent = "Saving...";

    const payload = {
      emp_id: form.emp_id.value.trim(),
      name: form.name.value.trim(),
      email: form.email.value.trim(),
      department: form.department.value.trim(),
      salary: form.salary.value,
      join_date: form.join_date.value || null,
    };

    try {
      let url = "/create_user";
      let method = "POST";

      if (editingId) {
        url = `/update_user/${editingId}`;
        method = "PUT";
      }

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const json = await res.json();

      if (!res.ok || json.status === "error") {
        throw new Error(json.message || "Failed to save user");
      }

      result.style.color = "green";
      result.textContent = json.message || "Saved successfully";

      form.reset();
      editingId = null;
      form.emp_id.disabled = false;
      saveButton.textContent = "Save Employee";

      loadUsers();
    } catch (error) {
      result.style.color = "red";
      result.textContent = error.message;
    }
  });

  window.editUser = function (id) {
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const user = rows
      .map(row => {
        const cells = row.children;
        return {
          id: Number(cells[0].textContent),
          emp_id: cells[1].textContent,
          name: cells[2].textContent,
          email: cells[3].textContent,
          department: cells[4].textContent,
          salary: cells[5].textContent.replace(/[\s₹,]/g, ""),
          join_date: cells[6].textContent,
        };
      })
      .find(u => u.id === id);

    if (!user) return;

    form.emp_id.value = user.emp_id;
    form.name.value = user.name;
    form.email.value = user.email;
    form.department.value = user.department;
    form.salary.value = user.salary;
    form.join_date.value = toInputDate(user.join_date);

    editingId = user.id;
    result.style.color = "blue";
    result.textContent = `Editing employee ${user.id}`;

    form.emp_id.disabled = true;
    saveButton.textContent = "Update Employee";
  };

  window.deleteUser = async function (id) {
    if (!confirm(`Delete employee ${id}?`)) return;
    try {
      const res = await fetch(`/delete_user/${id}`, { method: "DELETE" });
      const json = await res.json();
      if (!res.ok || json.status === "error") {
        alert(json.message || "Delete failed");
        return;
      }
      loadUsers();
    } catch (error) {
      alert("Error: " + error.message);
    }
  };

  loadBtn.addEventListener("click", () => loadUsers());

  searchBox.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadUsers, 350);
  });

  exportBtn.addEventListener("click", () => {
    let csv = "ID,Emp ID,Name,Email,Department,Salary,Join Date\n";
    Array.from(tbody.querySelectorAll("tr")).forEach(row => {
      const rowData = Array.from(row.children)
        .slice(0, 7)
        .map(td => td.textContent.replace(/,/g, ""))
        .join(",");
      csv += rowData + "\n";
    });
    const blob = new Blob([csv], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "employees.csv";
    link.click();
  });

  changePasswordLink.addEventListener("click", e => {
    e.preventDefault();
    resetMsg.textContent = "";
    passwordForm.reset();
    passwordModal.show();
  });

  submitPasswordBtn.addEventListener("click", async () => {
    resetMsg.textContent = "";
    const current = passwordForm.current_password.value.trim();
    const newPass = passwordForm.new_password.value.trim();
    const confirmPass = passwordForm.confirm_password.value.trim();

    if (!current || !newPass || !confirmPass) {
      resetMsg.innerHTML = '<div class="alert alert-danger">All fields are required.</div>';
      return;
    }

    if (newPass !== confirmPass) {
      resetMsg.innerHTML = '<div class="alert alert-danger">Passwords do not match.</div>';
      return;
    }

    try {
      const res = await fetch('/api/change_password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: current,
          new_password: newPass,
        }),
      });

      const json = await res.json();

      if (!res.ok || json.status === "error") {
        resetMsg.innerHTML = `<div class="alert alert-danger">${json.message || "Failed to change password."}</div>`;
        return;
      }

      resetMsg.innerHTML = `<div class="alert alert-success">${json.message || "Password changed successfully."}</div>`;
      passwordForm.reset();

      setTimeout(() => {
        passwordModal.hide();
      }, 2000);
    } catch (error) {
      resetMsg.innerHTML = '<div class="alert alert-danger">Network error occurred.</div>';
    }
  });

  // Initial loading
  loadUsers();
});
