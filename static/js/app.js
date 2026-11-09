// CampusCare Interactive Prototype Controller

let currentUser = null;
let metadata = { departments: [], categories: [], locations: [], sla_rules: [], staff_users: [], settings: {} };
let complaintsList = [];
let activeComplaint = null;
let currentFeedbackRating = 5;
let charts = {};

// ----------------- INITIALIZATION -----------------

document.addEventListener('DOMContentLoaded', async () => {
  await loadMetadata();
  await checkAuth();
  setupEventListeners();
});

async function loadMetadata() {
  try {
    const res = await fetch('/api/metadata');
    if (res.ok) {
      metadata = await res.json();
      populateMetadataDropdowns();
    }
  } catch (err) {
    console.error("Error loading metadata:", err);
  }
}

function populateMetadataDropdowns() {
  // Categories in New Complaint Form
  const catSelect = document.getElementById('cmp-category');
  if (catSelect) {
    catSelect.innerHTML = '<option value="">Select Problem Category (16 Categories)</option>' +
      metadata.categories.map(c => `<option value="${c.id}" data-dept="${c.department_name}">${c.name} (${c.department_name})</option>`).join('');
  }

  // Routing Table in Admin
  const routingTbody = document.getElementById('routing-tbody');
  if (routingTbody) {
    routingTbody.innerHTML = metadata.categories.map(c => `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-5 py-3 font-mono font-bold text-slate-700">${c.id}</td>
        <td class="px-5 py-3 font-bold text-slate-900">${c.name}</td>
        <td class="px-5 py-3 text-slate-600">${c.description}</td>
        <td class="px-5 py-3 font-semibold text-blue-700 flex items-center space-x-1.5">
          <i class="fa-solid fa-arrow-turn-down text-blue-400 text-xs"></i>
          <span>${c.department_name || 'Central Administration'}</span>
        </td>
        <td class="px-5 py-3">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">Active</span>
        </td>
      </tr>
    `).join('');
  }

  // Reassign Modal Dropdowns
  const reassignDept = document.getElementById('reassign-dept');
  if (reassignDept) {
    reassignDept.innerHTML = metadata.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
  }
  const reassignStaff = document.getElementById('reassign-staff');
  if (reassignStaff) {
    reassignStaff.innerHTML = '<option value="">-- Unassigned Staff Queue --</option>' +
      metadata.staff_users.map(s => `<option value="${s.id}">${s.full_name} (${s.role})</option>`).join('');
  }
}

function setupEventListeners() {
  // Real-time duplicate check when title or building changes
  const titleInput = document.getElementById('cmp-title');
  const buildingSelect = document.getElementById('cmp-building');
  if (titleInput && buildingSelect) {
    const triggerDuplicateCheck = debounce(checkDuplicatesRealtime, 400);
    titleInput.addEventListener('input', triggerDuplicateCheck);
    buildingSelect.addEventListener('change', triggerDuplicateCheck);
  }
}

// ----------------- AUTHENTICATION -----------------

async function checkAuth() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.authenticated && data.user) {
      setUserState(data.user);
    } else {
      setUserState(null);
    }
  } catch (err) {
    console.error("Auth check failed:", err);
    setUserState(null);
  }
}

function setUserState(user) {
  currentUser = user;
  
  const landing = document.getElementById('view-landing');
  const studentView = document.getElementById('view-student');
  const deptView = document.getElementById('view-department');
  const adminView = document.getElementById('view-admin');
  const userPill = document.getElementById('user-profile-pill');
  const loginBtn = document.getElementById('nav-login-btn');
  const demoBar = document.getElementById('demo-role-bar');
  const emergencyBar = document.getElementById('emergency-alert-bar');

  // Hide all views first
  landing.classList.add('hidden');
  studentView.classList.add('hidden');
  deptView.classList.add('hidden');
  adminView.classList.add('hidden');
  demoBar.classList.remove('hidden');

  if (!user) {
    landing.classList.remove('hidden');
    userPill.classList.add('hidden');
    userPill.classList.remove('flex');
    loginBtn.classList.remove('hidden');
    emergencyBar.classList.add('hidden');
    return;
  }

  // User is logged in
  loginBtn.classList.add('hidden');
  userPill.classList.remove('hidden');
  userPill.classList.add('flex');
  document.getElementById('nav-user-name').textContent = user.full_name;
  document.getElementById('nav-user-role').textContent = user.role.replace('_', ' ');

  // Highlight active role button in top bar
  document.querySelectorAll('.demo-btn').forEach(btn => {
    if (btn.dataset.role === user.role) {
      btn.classList.add('bg-white', 'text-blue-700', 'shadow-xs');
    } else {
      btn.classList.remove('bg-white', 'text-blue-700', 'shadow-xs');
    }
  });

  if (user.role === 'student') {
    studentView.classList.remove('hidden');
    document.getElementById('student-name-display').textContent = user.full_name;
    document.getElementById('student-branch-year').textContent = `Student Portal • College ID: ${user.college_id || 'DEMO-CSE-001'}`;
    loadComplaints();
    loadNotifications();
  } else if (user.role === 'staff' || user.role === 'department_head') {
    deptView.classList.remove('hidden');
    const deptObj = metadata.departments.find(d => d.id === user.department_id);
    document.getElementById('dept-assigned-name').textContent = deptObj ? deptObj.name : 'Department Maintenance';
    document.getElementById('dept-badge-role').textContent = user.role === 'department_head' ? 'Department Head' : 'Staff Technician';
    loadComplaints();
    loadNotifications();
  } else if (user.role === 'admin' || user.role === 'system_admin') {
    adminView.classList.remove('hidden');
    loadComplaints();
    loadAdminAnalytics();
    loadNotifications();
  }
}

async function demoLogin(role) {
  try {
    const res = await fetch('/api/auth/demo-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Switched role to ${role.toUpperCase()}`, 'success');
      setUserState(data.user);
      closeAuthModal();
    } else {
      showToast(data.error || 'Login failed', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to server', 'error');
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const identifier = document.getElementById('login-identifier').value;
  const password = document.getElementById('login-password').value;
  
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Login successful', 'success');
      setUserState(data.user);
      closeAuthModal();
    } else {
      showToast(data.error || 'Invalid credentials', 'error');
    }
  } catch (err) {
    showToast('Login request failed', 'error');
  }
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  const full_name = document.getElementById('reg-name').value;
  const college_id = document.getElementById('reg-college-id').value;
  const year_of_study = document.getElementById('reg-year').value;
  const email = document.getElementById('reg-email').value;
  const password = document.getElementById('reg-password').value;
  const parent_consent = document.getElementById('reg-consent').checked;

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name, college_id, year_of_study, email, password, parent_consent })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Account registered successfully', 'success');
      setUserState(data.user);
      closeAuthModal();
    } else {
      showToast(data.error || 'Registration failed', 'error');
    }
  } catch (err) {
    showToast('Registration request failed', 'error');
  }
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  showToast('Logged out', 'info');
  setUserState(null);
}

// ----------------- COMPLAINTS LOADING & DISPLAY -----------------

async function loadComplaints() {
  if (!currentUser) return;
  
  let url = '/api/complaints?';
  if (currentUser.role === 'student') {
    const status = document.getElementById('filter-student-status')?.value;
    const search = document.getElementById('filter-student-search')?.value;
    if (status) url += `status=${encodeURIComponent(status)}&`;
    if (search) url += `search=${encodeURIComponent(search)}&`;
  } else if (currentUser.role === 'staff' || currentUser.role === 'department_head') {
    const status = document.getElementById('filter-dept-status')?.value;
    if (status) url += `status=${encodeURIComponent(status)}&`;
  } else if (currentUser.role === 'admin' || currentUser.role === 'system_admin') {
    const status = document.getElementById('filter-admin-status')?.value;
    const priority = document.getElementById('filter-admin-priority')?.value;
    const search = document.getElementById('filter-admin-search')?.value;
    if (status) url += `status=${encodeURIComponent(status)}&`;
    if (priority) url += `priority=${encodeURIComponent(priority)}&`;
    if (search) url += `search=${encodeURIComponent(search)}&`;
  }

  try {
    const res = await fetch(url);
    const data = await res.json();
    complaintsList = data.complaints || [];

    if (currentUser.role === 'student') {
      renderStudentComplaints(complaintsList);
    } else if (currentUser.role === 'staff' || currentUser.role === 'department_head') {
      renderDepartmentComplaints(complaintsList);
    } else if (currentUser.role === 'admin' || currentUser.role === 'system_admin') {
      renderAdminComplaints(complaintsList);
    }
  } catch (err) {
    console.error("Failed to load complaints:", err);
  }
}

function renderStudentComplaints(items) {
  const tbody = document.getElementById('student-complaints-tbody');
  
  // Calculate quick stats
  const total = items.length;
  const review = items.filter(c => ['SUBMITTED', 'UNDER_REVIEW'].includes(c.status)).length;
  const progress = items.filter(c => ['ASSIGNED', 'IN_PROGRESS', 'ON_HOLD'].includes(c.status)).length;
  const resolved = items.filter(c => ['RESOLVED', 'CLOSED'].includes(c.status)).length;
  
  document.getElementById('stat-student-total').textContent = total;
  document.getElementById('stat-student-review').textContent = review;
  document.getElementById('stat-student-progress').textContent = progress;
  document.getElementById('stat-student-resolved').textContent = resolved;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">You have not submitted any complaints yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(c => `
    <tr class="hover:bg-slate-50 transition cursor-pointer" onclick="viewComplaintDetail(${c.id})">
      <td class="px-5 py-3 font-mono font-bold text-blue-600">${c.complaint_code}</td>
      <td class="px-5 py-3">
        <div class="font-bold text-slate-800">${escapeHtml(c.title)}</div>
        <div class="text-[11px] text-slate-400 truncate max-w-xs">${escapeHtml(c.description)}</div>
      </td>
      <td class="px-5 py-3 font-medium text-slate-600">${c.category_name || 'General'}</td>
      <td class="px-5 py-3 text-slate-500">${escapeHtml(c.location_description || c.building)}</td>
      <td class="px-5 py-3">
        <span class="px-2 py-0.5 rounded-full text-[10px] uppercase font-bold badge-priority-${c.priority}">${c.priority}</span>
      </td>
      <td class="px-5 py-3">
        <span class="px-2.5 py-0.5 rounded-full text-[10px] uppercase font-bold badge-status-${c.status}">${c.status.replace('_', ' ')}</span>
      </td>
      <td class="px-5 py-3 text-right">
        <button onclick="event.stopPropagation(); viewComplaintDetail(${c.id})" class="px-2.5 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50 rounded-lg transition">
          View Timeline &rarr;
        </button>
      </td>
    </tr>
  `).join('');
}

function renderDepartmentComplaints(items) {
  const tbody = document.getElementById('dept-complaints-tbody');
  const countEl = document.getElementById('dept-queue-count');
  const emergencyContainer = document.getElementById('dept-emergency-container');
  
  if (countEl) countEl.textContent = `${items.length} complaints`;

  // Render emergency callout banner if any
  const emergencyItems = items.filter(c => c.priority === 'EMERGENCY' && c.status !== 'CLOSED');
  if (emergencyItems.length > 0) {
    emergencyContainer.innerHTML = emergencyItems.map(em => `
      <div class="p-4 rounded-2xl bg-red-600 text-white shadow-lg flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center text-xl shrink-0">
            <i class="fa-solid fa-triangle-exclamation animate-bounce"></i>
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <span class="font-mono font-bold text-xs bg-white text-red-700 px-2 py-0.5 rounded-md">${em.complaint_code}</span>
              <span class="text-xs font-extrabold uppercase tracking-wider">EMERGENCY DISPATCH TICKET</span>
            </div>
            <h4 class="text-sm font-bold mt-0.5">${escapeHtml(em.title)}</h4>
            <p class="text-xs text-red-100">Location: ${escapeHtml(em.location_description || em.building)}</p>
          </div>
        </div>
        <button onclick="viewComplaintDetail(${em.id})" class="px-4 py-2 bg-white text-red-700 hover:bg-red-50 font-bold text-xs rounded-xl shadow-xs transition shrink-0">
          Act Immediately &rarr;
        </button>
      </div>
    `).join('');
    document.getElementById('emergency-alert-bar')?.classList.remove('hidden');
  } else {
    emergencyContainer.innerHTML = '';
    document.getElementById('emergency-alert-bar')?.classList.add('hidden');
  }

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No complaints currently in this queue.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(c => `
    <tr class="hover:bg-slate-50 transition">
      <td class="px-5 py-3">
        <div class="font-mono font-bold text-blue-600">${c.complaint_code}</div>
        <span class="px-2 py-0.5 rounded-full text-[10px] uppercase font-bold badge-priority-${c.priority}">${c.priority}</span>
      </td>
      <td class="px-5 py-3 max-w-xs">
        <div class="font-bold text-slate-800">${escapeHtml(c.title)}</div>
        <div class="text-[11px] text-slate-400 truncate">${escapeHtml(c.description)}</div>
      </td>
      <td class="px-5 py-3 text-slate-600">${escapeHtml(c.location_description || c.building)}</td>
      <td class="px-5 py-3">
        <span class="font-semibold text-slate-700">${c.staff_name || '<em class="text-slate-400">Unassigned</em>'}</span>
      </td>
      <td class="px-5 py-3 text-[11px] font-mono text-slate-500">${c.due_at ? c.due_at.substring(0, 16) : 'N/A'}</td>
      <td class="px-5 py-3">
        <span class="px-2.5 py-0.5 rounded-full text-[10px] uppercase font-bold badge-status-${c.status}">${c.status.replace('_', ' ')}</span>
      </td>
      <td class="px-5 py-3 text-right space-x-1">
        <button onclick="openStatusModal(${c.id}, '${c.status}')" title="Change Status" class="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg transition">
          <i class="fa-solid fa-pen-to-square"></i>
        </button>
        ${currentUser.role === 'department_head' ? `
          <button onclick="openReassignModal(${c.id}, '${c.assigned_department_id}', '${c.assigned_staff_id || ''}')" title="Assign Staff" class="p-1.5 text-indigo-600 hover:bg-indigo-50 rounded-lg transition">
            <i class="fa-solid fa-user-plus"></i>
          </button>
        ` : ''}
        ${c.status !== 'RESOLVED' && c.status !== 'CLOSED' ? `
          <button onclick="openResolutionModal(${c.id})" title="Mark Resolved" class="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded-lg transition">
            <i class="fa-solid fa-circle-check"></i>
          </button>
        ` : ''}
        <button onclick="viewComplaintDetail(${c.id})" title="Details" class="p-1.5 text-slate-500 hover:bg-slate-100 rounded-lg transition">
          <i class="fa-solid fa-eye"></i>
        </button>
      </td>
    </tr>
  `).join('');
}

function renderAdminComplaints(items) {
  const tbody = document.getElementById('admin-complaints-tbody');
  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400">No complaints found.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(c => `
    <tr class="hover:bg-slate-50 transition">
      <td class="px-5 py-3">
        <div class="font-mono font-bold text-blue-600">${c.complaint_code}</div>
        <span class="px-2 py-0.5 rounded-full text-[10px] uppercase font-bold badge-priority-${c.priority}">${c.priority}</span>
      </td>
      <td class="px-5 py-3 max-w-xs">
        <div class="font-bold text-slate-800">${escapeHtml(c.title)}</div>
        <div class="text-[11px] text-slate-400">By: ${escapeHtml(c.student_name || 'Anonymous')}</div>
      </td>
      <td class="px-5 py-3 text-slate-600 font-medium">${c.category_name || 'General'}</td>
      <td class="px-5 py-3 text-slate-500">${escapeHtml(c.location_description || c.building)}</td>
      <td class="px-5 py-3 font-semibold text-slate-700">${c.department_name || 'Unassigned'}</td>
      <td class="px-5 py-3">
        <span class="px-2.5 py-0.5 rounded-full text-[10px] uppercase font-bold badge-status-${c.status}">${c.status.replace('_', ' ')}</span>
      </td>
      <td class="px-5 py-3 text-right space-x-1">
        <button onclick="openReassignModal(${c.id}, '${c.assigned_department_id}', '${c.assigned_staff_id || ''}')" title="Reassign Department" class="p-1.5 text-indigo-600 hover:bg-indigo-50 rounded-lg transition">
          <i class="fa-solid fa-arrows-split-up-and-left"></i>
        </button>
        <button onclick="openStatusModal(${c.id}, '${c.status}')" title="Override Status" class="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg transition">
          <i class="fa-solid fa-pen-to-square"></i>
        </button>
        <button onclick="viewComplaintDetail(${c.id})" title="Audit Timeline" class="p-1.5 text-slate-500 hover:bg-slate-100 rounded-lg transition">
          <i class="fa-solid fa-eye"></i>
        </button>
      </td>
    </tr>
  `).join('');
}

// ----------------- COMPLAINT DETAIL & TIMELINE -----------------

async function viewComplaintDetail(id) {
  try {
    const res = await fetch(`/api/complaints/${id}`);
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Failed to load details', 'error');
      return;
    }

    activeComplaint = data.complaint;
    const timeline = data.timeline || [];
    const resolution = data.resolution;
    const feedback = data.feedback;

    document.getElementById('detail-code-badge').textContent = activeComplaint.complaint_code;
    document.getElementById('detail-status-badge').textContent = activeComplaint.status.replace('_', ' ');
    document.getElementById('detail-status-badge').className = `text-xs font-bold px-2.5 py-0.5 rounded-full badge-status-${activeComplaint.status}`;
    document.getElementById('detail-title').textContent = activeComplaint.title;
    document.getElementById('detail-desc').textContent = activeComplaint.description;
    document.getElementById('detail-category').textContent = activeComplaint.category_name || 'General';
    document.getElementById('detail-priority').textContent = activeComplaint.priority;
    document.getElementById('detail-priority').className = `font-bold badge-priority-${activeComplaint.priority} px-2 py-0.5 rounded-full text-[10px] inline-block`;
    document.getElementById('detail-dept').textContent = activeComplaint.department_name || 'Central Administration';
    document.getElementById('detail-student').textContent = activeComplaint.is_anonymous ? 'Anonymous Student' : (activeComplaint.student_name || 'Student');
    document.getElementById('detail-location').textContent = activeComplaint.location_description || `${activeComplaint.building}, Floor: ${activeComplaint.floor}, Room: ${activeComplaint.room}`;

    // Render Timeline
    const timelineContainer = document.getElementById('timeline-container');
    timelineContainer.innerHTML = timeline.map(t => `
      <div class="timeline-item">
        <div class="timeline-dot"></div>
        <div class="flex items-center space-x-2 text-[11px] font-semibold text-slate-500">
          <span class="font-bold text-slate-800 uppercase px-2 py-0.5 rounded-md badge-status-${t.new_status}">${t.new_status.replace('_', ' ')}</span>
          <span>•</span>
          <span>${t.changed_at}</span>
          ${t.changed_by_name ? `<span>• by ${escapeHtml(t.changed_by_name)}</span>` : ''}
        </div>
        <p class="text-xs text-slate-700 mt-1 font-medium">${escapeHtml(t.public_message || '')}</p>
        ${t.internal_note ? `<p class="text-[11px] text-amber-800 bg-amber-50 p-2 rounded-lg mt-1 border border-amber-200"><strong>Internal Note:</strong> ${escapeHtml(t.internal_note)}</p>` : ''}
      </div>
    `).join('');

    // Resolution Box
    const resBox = document.getElementById('detail-resolution-box');
    if (resolution) {
      resBox.classList.remove('hidden');
      document.getElementById('detail-resolution-summary').textContent = resolution.resolution_summary;
      document.getElementById('detail-resolution-work').textContent = resolution.work_performed ? `Work Performed: ${resolution.work_performed}` : '';
      document.getElementById('detail-resolution-meta').textContent = `Resolved by ${resolution.resolved_by_name || 'Staff Specialist'} on ${resolution.resolved_at}`;
    } else {
      resBox.classList.add('hidden');
    }

    // Feedback Section
    const fbSection = document.getElementById('detail-feedback-section');
    const fbForm = document.getElementById('feedback-form-content');
    const fbDisplay = document.getElementById('feedback-display-content');
    const reopenBox = document.getElementById('detail-reopen-box');

    if (feedback) {
      fbSection.classList.remove('hidden');
      fbForm.classList.add('hidden');
      fbDisplay.classList.remove('hidden');
      document.getElementById('fb-stars-display').textContent = '★'.repeat(feedback.rating) + '☆'.repeat(5 - feedback.rating);
      document.getElementById('fb-comment-display').textContent = feedback.comment || 'No written feedback provided.';
      reopenBox.classList.add('hidden');
    } else if (currentUser && currentUser.role === 'student' && ['RESOLVED', 'CLOSED'].includes(activeComplaint.status)) {
      fbSection.classList.remove('hidden');
      fbForm.classList.remove('hidden');
      fbDisplay.classList.add('hidden');
      reopenBox.classList.remove('hidden');
    } else {
      fbSection.classList.add('hidden');
      reopenBox.classList.add('hidden');
    }

    document.getElementById('modal-complaint-detail').classList.remove('hidden');
  } catch (err) {
    showToast('Failed to load complaint details', 'error');
  }
}

function closeDetailModal() {
  document.getElementById('modal-complaint-detail').classList.add('hidden');
}

// ----------------- COMPLAINT SUBMISSION -----------------

function openComplaintModal() {
  document.getElementById('modal-new-complaint').classList.remove('hidden');
  onCategorySelectChange();
}

function closeComplaintModal() {
  document.getElementById('modal-new-complaint').classList.add('hidden');
  document.getElementById('form-complaint').reset();
  document.getElementById('duplicate-warning-box').classList.add('hidden');
  document.getElementById('emergency-form-warning').classList.add('hidden');
}

function onCategorySelectChange() {
  const catSelect = document.getElementById('cmp-category');
  const selectedOpt = catSelect.options[catSelect.selectedIndex];
  const deptBox = document.getElementById('routing-preview-box');
  const deptNameEl = document.getElementById('routing-dept-name');
  
  if (selectedOpt && selectedOpt.dataset.dept) {
    deptBox.classList.remove('hidden');
    deptNameEl.textContent = selectedOpt.dataset.dept;
  } else {
    deptBox.classList.add('hidden');
  }
}

function onPriorityChange() {
  const priority = document.getElementById('cmp-priority').value;
  const warning = document.getElementById('emergency-form-warning');
  if (priority === 'EMERGENCY') {
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }
}

function handleFileSelected(input) {
  const file = input.files[0];
  if (file) {
    document.getElementById('file-label').textContent = `Attached: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
  }
}

async function checkDuplicatesRealtime() {
  const cat = document.getElementById('cmp-category').value;
  const building = document.getElementById('cmp-building').value;
  const title = document.getElementById('cmp-title').value;
  
  if (!title || title.length < 4) {
    document.getElementById('duplicate-warning-box').classList.add('hidden');
    return;
  }

  try {
    const res = await fetch('/api/complaints/check-duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category_id: cat, building, title })
    });
    const data = await res.json();
    const dupBox = document.getElementById('duplicate-warning-box');
    const dupList = document.getElementById('duplicate-list');
    
    if (data.duplicates && data.duplicates.length > 0) {
      dupBox.classList.remove('hidden');
      dupList.innerHTML = data.duplicates.map(d => `<li><strong>${d.complaint_code}</strong>: ${escapeHtml(d.title)} (${d.status})</li>`).join('');
    } else {
      dupBox.classList.add('hidden');
    }
  } catch (err) {
    console.error("Duplicate check error:", err);
  }
}

async function submitComplaint(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-complaint');
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Submitting...`;

  const payload = {
    title: document.getElementById('cmp-title').value.strip ? document.getElementById('cmp-title').value.strip() : document.getElementById('cmp-title').value.trim(),
    category_id: document.getElementById('cmp-category').value,
    priority: document.getElementById('cmp-priority').value,
    building: document.getElementById('cmp-building').value,
    block: document.getElementById('cmp-block').value,
    floor: document.getElementById('cmp-floor').value,
    room: document.getElementById('cmp-room').value,
    landmark: document.getElementById('cmp-landmark').value,
    description: document.getElementById('cmp-desc').value.trim(),
    is_anonymous: document.getElementById('cmp-anonymous').checked
  };

  try {
    const res = await fetch('/api/complaints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `<span>Confirm & Submit Report</span> <i class="fa-solid fa-paper-plane text-xs"></i>`;

    if (res.ok) {
      closeComplaintModal();
      showToast(`Complaint ${data.complaint_code} submitted! Parent notification dispatched to anilanji22515@gmail.com`, 'success');
      await loadComplaints();
      await loadNotifications();
      viewComplaintDetail(data.complaint_id);
    } else {
      showToast(data.error || 'Failed to submit complaint', 'error');
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<span>Confirm & Submit Report</span> <i class="fa-solid fa-paper-plane text-xs"></i>`;
    showToast('Network error while submitting complaint', 'error');
  }
}

// ----------------- STATUS UPDATES & RESOLUTION -----------------

function openStatusModal(id, currentStatus) {
  document.getElementById('status-complaint-id').value = id;
  document.getElementById('status-select').value = currentStatus || 'IN_PROGRESS';
  document.getElementById('status-public-msg').value = '';
  document.getElementById('status-internal-note').value = '';
  document.getElementById('modal-update-status').classList.remove('hidden');
}

function closeStatusModal() {
  document.getElementById('modal-update-status').classList.add('hidden');
}

async function submitStatusUpdate(e) {
  e.preventDefault();
  const id = document.getElementById('status-complaint-id').value;
  const status = document.getElementById('status-select').value;
  const public_message = document.getElementById('status-public-msg').value;
  const internal_note = document.getElementById('status-internal-note').value;

  try {
    const res = await fetch(`/api/complaints/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, public_message, internal_note })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Status updated to ${status}`, 'success');
      closeStatusModal();
      await loadComplaints();
      if (activeComplaint && activeComplaint.id == id) {
        viewComplaintDetail(id);
      }
    } else {
      showToast(data.error || 'Failed to update status', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to server', 'error');
  }
}

function openResolutionModal(id) {
  document.getElementById('res-complaint-id').value = id;
  document.getElementById('res-summary').value = '';
  document.getElementById('res-work').value = '';
  document.getElementById('modal-resolution').classList.remove('hidden');
}

function closeResolutionModal() {
  document.getElementById('modal-resolution').classList.add('hidden');
}

async function submitResolution(e) {
  e.preventDefault();
  const id = document.getElementById('res-complaint-id').value;
  const resolution_summary = document.getElementById('res-summary').value;
  const work_performed = document.getElementById('res-work').value;

  try {
    const res = await fetch(`/api/complaints/${id}/resolution`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_summary, work_performed })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Problem marked as Resolved!', 'success');
      closeResolutionModal();
      await loadComplaints();
      if (activeComplaint && activeComplaint.id == id) {
        viewComplaintDetail(id);
      }
    } else {
      showToast(data.error || 'Failed to submit resolution', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to server', 'error');
  }
}

function openReassignModal(id, currentDeptId, currentStaffId) {
  document.getElementById('reassign-complaint-id').value = id;
  if (currentDeptId) document.getElementById('reassign-dept').value = currentDeptId;
  if (currentStaffId) document.getElementById('reassign-staff').value = currentStaffId;
  document.getElementById('reassign-note').value = '';
  document.getElementById('modal-reassign').classList.remove('hidden');
}

function closeReassignModal() {
  document.getElementById('modal-reassign').classList.add('hidden');
}

async function submitReassign(e) {
  e.preventDefault();
  const id = document.getElementById('reassign-complaint-id').value;
  const department_id = document.getElementById('reassign-dept').value;
  const staff_id = document.getElementById('reassign-staff').value || null;
  const assignment_note = document.getElementById('reassign-note').value;

  try {
    const res = await fetch(`/api/complaints/${id}/assign`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ department_id, staff_id, assignment_note })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Assignment saved', 'success');
      closeReassignModal();
      await loadComplaints();
      if (activeComplaint && activeComplaint.id == id) {
        viewComplaintDetail(id);
      }
    } else {
      showToast(data.error || 'Failed to reassign', 'error');
    }
  } catch (err) {
    showToast('Failed to connect to server', 'error');
  }
}

// ----------------- STUDENT FEEDBACK & REOPEN -----------------

function setFeedbackRating(stars) {
  currentFeedbackRating = stars;
  const starIcons = document.querySelectorAll('#star-rating-box i');
  starIcons.forEach((icon, idx) => {
    if (idx < stars) {
      icon.className = 'fa-solid fa-star text-amber-400';
    } else {
      icon.className = 'fa-solid fa-star text-slate-300';
    }
  });
}

async function submitStudentFeedback() {
  if (!activeComplaint) return;
  const fixed = document.querySelector('input[name="fb_fixed"]:checked').value === '1';
  const comment = document.getElementById('fb-comment').value;

  try {
    const res = await fetch(`/api/complaints/${activeComplaint.id}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating: currentFeedbackRating, comment, problem_fixed: fixed })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Feedback submitted successfully. Thank you!', 'success');
      viewComplaintDetail(activeComplaint.id);
      loadComplaints();
    } else {
      showToast(data.error || 'Failed to submit feedback', 'error');
    }
  } catch (err) {
    showToast('Failed to submit feedback', 'error');
  }
}

async function promptReopen() {
  if (!activeComplaint) return;
  const reason = prompt("Please provide a reason why this complaint should be reopened:");
  if (!reason) return;

  try {
    const res = await fetch(`/api/complaints/${activeComplaint.id}/reopen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason })
    });
    const data = await res.json();
    if (res.ok) {
      showToast('Complaint reopened', 'info');
      viewComplaintDetail(activeComplaint.id);
      loadComplaints();
    } else {
      showToast(data.error || 'Failed to reopen complaint', 'error');
    }
  } catch (err) {
    showToast('Request failed', 'error');
  }
}

// ----------------- ADMIN ANALYTICS & CHARTS -----------------

async function loadAdminAnalytics() {
  try {
    const res = await fetch('/api/admin/analytics');
    const data = await res.json();
    if (!res.ok) return;

    // KPI values
    document.getElementById('kpi-total').textContent = data.kpi.total;
    document.getElementById('kpi-open').textContent = data.kpi.open;
    document.getElementById('kpi-progress').textContent = data.kpi.in_progress;
    document.getElementById('kpi-resolved').textContent = data.kpi.resolved;
    document.getElementById('kpi-emergency').textContent = data.kpi.emergency;
    document.getElementById('kpi-overdue').textContent = data.kpi.overdue;

    renderAnalyticsCharts(data);
  } catch (err) {
    console.error("Failed to load admin analytics:", err);
  }
}

function renderAnalyticsCharts(data) {
  // Chart 1: Categories (Donut)
  const ctxCat = document.getElementById('chart-categories');
  if (ctxCat) {
    if (charts.categories) charts.categories.destroy();
    const topCats = data.categories.slice(0, 5);
    charts.categories = new Chart(ctxCat, {
      type: 'doughnut',
      data: {
        labels: topCats.map(c => c.name),
        datasets: [{
          data: topCats.map(c => c.count),
          backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } }
      }
    });
  }

  // Chart 2: Status Distribution (Pie)
  const ctxStatus = document.getElementById('chart-status');
  if (ctxStatus) {
    if (charts.status) charts.status.destroy();
    charts.status = new Chart(ctxStatus, {
      type: 'pie',
      data: {
        labels: data.statuses.map(s => s.status.replace('_', ' ')),
        datasets: [{
          data: data.statuses.map(s => s.count),
          backgroundColor: ['#0284c7', '#7c3aed', '#4f46e5', '#d97706', '#059669', '#475569', '#dc2626']
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } }
      }
    });
  }

  // Chart 3: Department Workload (Bar)
  const ctxDept = document.getElementById('chart-departments');
  if (ctxDept) {
    if (charts.departments) charts.departments.destroy();
    const topDepts = data.departments.slice(0, 5);
    charts.departments = new Chart(ctxDept, {
      type: 'bar',
      data: {
        labels: topDepts.map(d => d.name.split(' ')[0]),
        datasets: [
          { label: 'Total', data: topDepts.map(d => d.total), backgroundColor: '#94a3b8' },
          { label: 'Resolved', data: topDepts.map(d => d.resolved), backgroundColor: '#10b981' }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } }
      }
    });
  }
}

function switchAdminTab(tab) {
  document.querySelectorAll('.admin-tab-btn').forEach(btn => {
    btn.classList.remove('text-blue-600', 'border-b-2', 'border-blue-600');
    btn.classList.add('text-slate-500');
  });
  
  const activeBtn = document.getElementById(`tab-btn-${tab}`);
  if (activeBtn) {
    activeBtn.classList.add('text-blue-600', 'border-b-2', 'border-blue-600');
    activeBtn.classList.remove('text-slate-500');
  }

  document.getElementById('admin-tab-complaints').classList.add('hidden');
  document.getElementById('admin-tab-outbox').classList.add('hidden');
  document.getElementById('admin-tab-routing').classList.add('hidden');

  if (tab === 'complaints') {
    document.getElementById('admin-tab-complaints').classList.remove('hidden');
  } else if (tab === 'outbox') {
    document.getElementById('admin-tab-outbox').classList.remove('hidden');
    loadOutbox();
  } else if (tab === 'routing') {
    document.getElementById('admin-tab-routing').classList.remove('hidden');
  }
}

async function loadOutbox() {
  try {
    const res = await fetch('/api/admin/outbox');
    const data = await res.json();
    if (!res.ok) return;

    const tbody = document.getElementById('outbox-tbody');
    tbody.innerHTML = data.outbox.map(o => `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-mono font-bold text-slate-500">#${o.id}</td>
        <td class="px-4 py-3 font-mono font-bold text-blue-600">${o.complaint_code || 'N/A'}</td>
        <td class="px-4 py-3 font-medium text-slate-800">${escapeHtml(o.recipient_email)}</td>
        <td class="px-4 py-3 text-slate-600 truncate max-w-xs">${escapeHtml(o.subject)}</td>
        <td class="px-4 py-3">
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${o.delivery_status === 'SENT' ? 'bg-emerald-100 text-emerald-800' : (o.delivery_status === 'SIMULATED' ? 'bg-blue-100 text-blue-800' : 'bg-red-100 text-red-800')}">
            ${o.delivery_status}
          </span>
        </td>
        <td class="px-4 py-3 font-mono text-[10px] text-slate-500">${o.provider_message_id || 'N/A'}</td>
        <td class="px-4 py-3 text-[11px] text-slate-500">${o.created_at}</td>
        <td class="px-4 py-3 text-right">
          ${o.delivery_status === 'FAILED' ? `
            <button onclick="retryOutbox(${o.id})" class="px-2 py-1 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-md text-[11px] font-bold">Retry</button>
          ` : `<span class="text-emerald-600 text-xs"><i class="fa-solid fa-check"></i></span>`}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error("Failed to load outbox:", err);
  }
}

async function retryOutbox(id) {
  try {
    const res = await fetch(`/api/admin/outbox/${id}/retry`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast('Delivery retry triggered', 'info');
      loadOutbox();
    }
  } catch (err) {
    showToast('Retry request failed', 'error');
  }
}

function openTestEmailModal() {
  document.getElementById('modal-test-email').classList.remove('hidden');
  document.getElementById('test-email-status-box').classList.add('hidden');
}

function closeTestEmailModal() {
  document.getElementById('modal-test-email').classList.add('hidden');
}

async function sendDiagnosticEmail() {
  const btn = document.getElementById('btn-send-test-email');
  const recipient = document.getElementById('test-email-input').value;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-1"></i> Sending...`;

  try {
    const res = await fetch('/api/admin/test-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipient })
    });
    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `Dispatch Email Now`;

    const statusBox = document.getElementById('test-email-status-box');
    statusBox.classList.remove('hidden');
    
    if (res.ok) {
      statusBox.className = 'p-3 rounded-xl text-xs space-y-1 bg-emerald-50 border border-emerald-200 text-emerald-900';
      statusBox.innerHTML = `
        <div class="font-bold flex items-center space-x-1.5"><i class="fa-solid fa-circle-check text-emerald-600"></i><span>Outbox Delivery State: ${data.result.status}</span></div>
        <div class="text-[11px]">Provider Message ID: <code class="font-mono bg-emerald-100 px-1 rounded">${data.result.message_id}</code></div>
        <p class="text-[10px] text-emerald-700 mt-1">Logged in outbox table with recipient ${recipient}.</p>
      `;
      showToast('Diagnostic email recorded in outbox', 'success');
      loadOutbox();
    } else {
      statusBox.className = 'p-3 rounded-xl text-xs space-y-1 bg-red-50 border border-red-200 text-red-900';
      statusBox.textContent = `Error: ${data.error || 'Delivery failed'}`;
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `Dispatch Email Now`;
    showToast('Failed to dispatch test email', 'error');
  }
}

function exportCSV() {
  window.location.href = '/api/admin/export';
}

// ----------------- IN-APP NOTIFICATIONS -----------------

async function loadNotifications() {
  if (!currentUser) return;
  try {
    const res = await fetch('/api/notifications');
    const data = await res.json();
    const notifs = data.notifications || [];
    
    const badge = document.getElementById('notif-badge');
    const countText = document.getElementById('notif-count-text');
    const list = document.getElementById('notif-list');

    const unread = notifs.filter(n => !n.is_read);
    if (unread.length > 0) {
      badge.classList.remove('hidden');
      countText.textContent = `${unread.length} unread`;
    } else {
      badge.classList.add('hidden');
      countText.textContent = `${notifs.length} updates`;
    }

    if (notifs.length === 0) {
      list.innerHTML = `<div class="p-4 text-center text-xs text-slate-400">No new notifications</div>`;
      return;
    }

    list.innerHTML = notifs.map(n => `
      <div class="p-3 hover:bg-slate-50 transition cursor-pointer ${n.is_read ? 'opacity-70' : 'bg-blue-50/40'}" onclick="handleNotifClick(${n.id}, ${n.complaint_id})">
        <div class="flex items-center justify-between text-[10px] text-slate-400 mb-0.5">
          <span class="font-bold text-blue-700">${n.title}</span>
          <span>${n.created_at.substring(11, 16)}</span>
        </div>
        <p class="text-xs text-slate-700 font-medium">${escapeHtml(n.message)}</p>
      </div>
    `).join('');
  } catch (err) {
    console.error("Failed to load notifications:", err);
  }
}

function toggleNotifications() {
  const panel = document.getElementById('notif-dropdown');
  panel.classList.toggle('hidden');
}

async function handleNotifClick(notifId, complaintId) {
  await fetch(`/api/notifications/${notifId}/read`, { method: 'PATCH' });
  document.getElementById('notif-dropdown').classList.add('hidden');
  if (complaintId) {
    viewComplaintDetail(complaintId);
  }
  loadNotifications();
}

// ----------------- UI UTILITIES -----------------

function openAuthModal() {
  document.getElementById('modal-auth').classList.remove('hidden');
}

function closeAuthModal() {
  document.getElementById('modal-auth').classList.add('hidden');
}

function switchAuthTab(tab) {
  const loginBtn = document.getElementById('btn-tab-login');
  const regBtn = document.getElementById('btn-tab-register');
  const loginForm = document.getElementById('form-login');
  const regForm = document.getElementById('form-register');

  if (tab === 'login') {
    loginBtn.className = 'pb-2 px-4 text-blue-600 border-b-2 border-blue-600';
    regBtn.className = 'pb-2 px-4 text-slate-400 hover:text-slate-600';
    loginForm.classList.remove('hidden');
    regForm.classList.add('hidden');
  } else {
    regBtn.className = 'pb-2 px-4 text-blue-600 border-b-2 border-blue-600';
    loginBtn.className = 'pb-2 px-4 text-slate-400 hover:text-slate-600';
    regForm.classList.remove('hidden');
    loginForm.classList.add('hidden');
  }
}

function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toast-msg');
  const toastIcon = document.getElementById('toast-icon');

  toastMsg.textContent = message;
  if (type === 'success') {
    toastIcon.className = 'fa-solid fa-circle-check text-emerald-400 text-base';
  } else if (type === 'error') {
    toastIcon.className = 'fa-solid fa-circle-exclamation text-rose-400 text-base';
  } else {
    toastIcon.className = 'fa-solid fa-circle-info text-blue-400 text-base';
  }

  toast.classList.remove('hidden');
  setTimeout(() => {
    toast.classList.add('hidden');
  }, 4000);
}

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
