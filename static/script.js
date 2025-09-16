const form = document.getElementById('employeeForm');
const result = document.getElementById('result');
const loadBtn = document.getElementById('loadUsersBtn');
const tbody = document.getElementById('usersList');

let editingId = null; // when not null we are in edit mode

// small spinner HTML used in various places
const spinnerHTML = '<span class="spinner" style="display:inline-block;width:18px;height:18px;border:3px solid rgba(0,0,0,.1);border-top-color:#007aff;border-radius:50%;animation:spin 1s linear infinite;margin-right:8px"></span>';

// helpers
function formatSalary(n) {
  if (n == null || n === '') return '';
  const num = Number(n);
  if (isNaN(num)) return n;
  return '₹ ' + new Intl.NumberFormat('en-IN').format(num);
}


function toInputDate(val) {
  if (!val) return '';
  // if already ISO-ish (YYYY-MM-DD) return directly
  if (/^\d{4}-\d{2}-\d{2}$/.test(val)) return val;

  // try Date parse
  const dt = new Date(val);
  if (!isNaN(dt)) return dt.toISOString().split('T')[0];

  // try dd-MMM-YYYY
  const m = val.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
  if (m) {
    const [ , dd, mon, yyyy ] = m;
    const map = {Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
    const mm = map[mon] || '01';
    return `${yyyy}-${mm}-${dd.padStart(2,'0')}`;
  }

  return '';
}

// submit
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  result.style.color = 'black';
  result.innerHTML = `${spinnerHTML}Saving...`;

  const payload = {
    emp_id: document.getElementById('emp_id').value.trim(),
    name: document.getElementById('name').value.trim(),
    salary: document.getElementById('salary').value,
    email: document.getElementById('email').value.trim(),
    department: document.getElementById('department').value.trim(),
    join_date: document.getElementById('join_date').value || null
  };

  try {
    let url = '/create_user';
    let method = 'POST';

    if (editingId) {
      url = `/update_user/${editingId}`;
      method = 'PUT';
    }

    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const json = await res.json();

    if (!res.ok || (json && json.status === 'error')) {
      const msg = (json && json.message) ? json.message : `HTTP ${res.status}`;
      result.style.color = 'red';
      result.textContent = `Error: ${msg}`;
      return;
    }

    // success
    result.style.color = 'green';
    result.textContent = json.message || (editingId ? 'Updated' : 'Created');
    form.reset();
    editingId = null;
    document.getElementById('emp_id').disabled = false; // re-enable emp_id after edit
    loadUsers();
  } catch (err) {
    result.style.color = 'red';
    result.textContent = 'Network error: ' + err.message;
  }
});

// load users
loadBtn.addEventListener('click', loadUsers);

async function loadUsers() {
  tbody.innerHTML = `<tr><td colspan="8" class="text-center">${spinnerHTML}Loading...</td></tr>`;

  try {
    const res = await fetch('/get_users');
    // try to parse json even if !res.ok to get message from backend
    const json = await res.json().catch(() => null);

    if (!res.ok) {
      const msg = (json && json.message) ? json.message : `HTTP ${res.status}`;
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Error loading data: ${msg}</td></tr>`;
      return;
    }
    let users = Array.isArray(json) ? json : (json && Array.isArray(json.data) ? json.data : []);

    if (!users || users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No employees found</td></tr>';
      return;
    }

    // build rows safely
    tbody.innerHTML = '';
    users.forEach(u => {
      const tr = document.createElement('tr');

      // create cells
      const idCell = document.createElement('td'); idCell.textContent = u.id ?? '';
      const empCell = document.createElement('td'); empCell.textContent = u.emp_id ?? '';
      const nameCell = document.createElement('td'); nameCell.textContent = u.name ?? '';
      const salaryCell = document.createElement('td'); salaryCell.textContent = formatSalary(u.salary);
      const emailCell = document.createElement('td'); emailCell.textContent = u.email ?? '';
      const deptCell = document.createElement('td');
      // department badge
      const badge = document.createElement('span');
      badge.className = 'badge bg-info text-dark';
      badge.textContent = u.department ?? '';
      deptCell.appendChild(badge);

      const joinCell = document.createElement('td'); joinCell.textContent = u.join_date ?? '';

      const actionsCell = document.createElement('td');
      // Edit button
      const editBtn = document.createElement('button');
      editBtn.className = 'btn btn-sm btn-warning me-2';
      editBtn.innerHTML = '<i class="fas fa-edit"></i>';
      editBtn.addEventListener('click', () => {
        // populate form; convert date to yyyy-mm-dd for input
        document.getElementById('emp_id').value = u.emp_id || '';
        document.getElementById('name').value = u.name || '';
        document.getElementById('salary').value = u.salary ?? '';
        document.getElementById('email').value = u.email || '';
        document.getElementById('department').value = u.department || '';
        document.getElementById('join_date').value = toInputDate(u.join_date);
        editingId = u.id;
        result.style.color = '#0d6efd';
        result.textContent = `Editing employee #${u.id} — edit fields and click Save`;
        // disable emp_id when editing (backend update does not change emp_id)
        document.getElementById('emp_id').disabled = true;
      });

      // Delete button
      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm btn-danger';
      delBtn.innerHTML = '<i class="fas fa-trash"></i>';
      delBtn.addEventListener('click', async () => {
        if (!confirm(`Delete ${u.name} (${u.emp_id})?`)) return;
        try {
          const r = await fetch(`/delete_user/${u.id}`, { method: 'DELETE' });
          const j = await r.json().catch(() => null);
          if (!r.ok || (j && j.status === 'error')) {
            alert(`Delete failed: ${j && j.message ? j.message : `HTTP ${r.status}`}`);
            return;
          }
          // removed
          loadUsers();
        } catch (err) {
          alert('Network error: ' + err.message);
        }
      });

      actionsCell.appendChild(editBtn);
      actionsCell.appendChild(delBtn);

      // append cells
      tr.appendChild(idCell);
      tr.appendChild(empCell);
      tr.appendChild(nameCell);
      tr.appendChild(salaryCell);
      tr.appendChild(emailCell);
      tr.appendChild(deptCell);
      tr.appendChild(joinCell);
      tr.appendChild(actionsCell);

      tbody.appendChild(tr);
    });

  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Failed to load users: ${err.message}</td></tr>`;
  }
}

// initial load
loadUsers();

/* small keyframe for the spinner */
const style = document.createElement('style');
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
