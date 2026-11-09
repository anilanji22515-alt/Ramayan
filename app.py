from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for
import os
import io
import csv
from datetime import datetime, timedelta, timezone
from config import Config
from database import get_db, init_db, hash_password
from services.email_service import EmailService

app = Flask(__name__)
app.config.from_object(Config)

# Helper function to get current user from session
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute("SELECT id, college_id, full_name, email, role, department_id, year_of_study FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return dict(user)
    return None

# Web Route - Single Page Application Shell
@app.route('/')
def index():
    return render_template('index.html', campus_name=Config.CAMPUS_NAME)

# ----------------- AUTHENTICATION APIS -----------------

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_current_user()
    if not user:
        return jsonify({'authenticated': False}), 200
    return jsonify({'authenticated': True, 'user': user}), 200

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    password = data.get('password', '')
    
    if not identifier or not password:
        return jsonify({'error': 'College ID or Email and Password are required'}), 400
        
    conn = get_db()
    pwd_hash = hash_password(password)
    user = conn.execute(
        "SELECT id, college_id, full_name, email, role, department_id, year_of_study FROM users WHERE (email = ? OR college_id = ?) AND password_hash = ? AND is_active = 1",
        (identifier, identifier, pwd_hash)
    ).fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'Invalid credentials or inactive account'}), 401
        
    user_dict = dict(user)
    session['user_id'] = user_dict['id']
    session['role'] = user_dict['role']
    return jsonify({'message': 'Login successful', 'user': user_dict}), 200

@app.route('/api/auth/demo-login', methods=['POST'])
def auth_demo_login():
    data = request.get_json() or {}
    role = data.get('role', 'student')
    
    conn = get_db()
    user = conn.execute("SELECT id, college_id, full_name, email, role, department_id, year_of_study FROM users WHERE role = ? LIMIT 1", (role,)).fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': f'Demo account for role {role} not found'}), 404
        
    user_dict = dict(user)
    session['user_id'] = user_dict['id']
    session['role'] = user_dict['role']
    return jsonify({'message': f'Logged in as demo {role}', 'user': user_dict}), 200

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    college_id = data.get('college_id', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    department = data.get('department', '').strip()
    year_of_study = data.get('year_of_study', 1)
    phone = data.get('phone', '').strip()
    consent = data.get('parent_consent', False)
    
    if not full_name or not college_id or not email or not password:
        return jsonify({'error': 'All required fields must be filled'}), 400
        
    if not consent:
        return jsonify({'error': 'Consent to campus problem notification policy is required'}), 400
        
    conn = get_db()
    # Check uniqueness
    existing = conn.execute("SELECT id FROM users WHERE college_id = ? OR email = ?", (college_id, email)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'College ID or Email address already registered'}), 409
        
    pwd_hash = hash_password(password)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (college_id, full_name, email, phone, password_hash, role, year_of_study, section, is_email_verified)
        VALUES (?, ?, ?, ?, ?, 'student', ?, 'A', 1)
    ''', (college_id, full_name, email, phone, pwd_hash, year_of_study))
    new_id = cursor.lastrowid
    conn.commit()
    
    user = conn.execute("SELECT id, college_id, full_name, email, role, department_id, year_of_study FROM users WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    
    user_dict = dict(user)
    session['user_id'] = user_dict['id']
    session['role'] = user_dict['role']
    return jsonify({'message': 'Registration successful', 'user': user_dict}), 201

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

# ----------------- METADATA & CONFIG APIS -----------------

@app.route('/api/metadata', methods=['GET'])
def get_metadata():
    conn = get_db()
    departments = [dict(r) for r in conn.execute("SELECT * FROM departments WHERE is_active = 1 ORDER BY name").fetchall()]
    categories = [dict(r) for r in conn.execute("SELECT c.*, d.name as department_name FROM categories c LEFT JOIN departments d ON c.default_department_id = d.id WHERE c.is_active = 1 ORDER BY c.name").fetchall()]
    locations = [dict(r) for r in conn.execute("SELECT * FROM campus_locations WHERE is_active = 1 ORDER BY building, floor, room_or_area").fetchall()]
    sla_rules = [dict(r) for r in conn.execute("SELECT * FROM sla_rules WHERE is_active = 1").fetchall()]
    staff_users = [dict(r) for r in conn.execute("SELECT id, full_name, email, role, department_id FROM users WHERE role IN ('staff', 'department_head')").fetchall()]
    settings = {r['setting_key']: r['setting_value'] for r in conn.execute("SELECT setting_key, setting_value FROM system_settings").fetchall()}
    conn.close()
    
    return jsonify({
        'departments': departments,
        'categories': categories,
        'locations': locations,
        'sla_rules': sla_rules,
        'staff_users': staff_users,
        'settings': settings
    }), 200

# ----------------- COMPLAINTS APIS -----------------

@app.route('/api/complaints/check-duplicate', methods=['POST'])
def check_duplicate():
    data = request.get_json() or {}
    category_id = data.get('category_id')
    building = data.get('building', '')
    title = data.get('title', '').strip().lower()
    
    if not category_id and not building:
        return jsonify({'duplicates': []}), 200
        
    conn = get_db()
    query = """
        SELECT id, complaint_code, title, building, floor, room, priority, status, submitted_at
        FROM complaints
        WHERE status NOT IN ('CLOSED', 'REJECTED')
        AND (category_id = ? OR building = ?)
        ORDER BY submitted_at DESC LIMIT 5
    """
    rows = conn.execute(query, (category_id, building)).fetchall()
    conn.close()
    
    duplicates = []
    for r in rows:
        d = dict(r)
        # Simple similarity check
        r_title = d['title'].lower()
        if any(w in r_title for w in title.split() if len(w) > 3) or (d['building'] == building):
            duplicates.append(d)
            
    return jsonify({'duplicates': duplicates[:3]}), 200

@app.route('/api/complaints', methods=['GET', 'POST'])
def handle_complaints():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db()
    
    if request.method == 'POST':
        data = request.get_json() or {}
        title = data.get('title', '').strip()
        category_id = data.get('category_id')
        description = data.get('description', '').strip()
        building = data.get('building', '').strip()
        block = data.get('block', '').strip()
        floor = data.get('floor', '').strip()
        room = data.get('room', '').strip()
        landmark = data.get('landmark', '').strip()
        priority = data.get('priority', 'MEDIUM').upper()
        is_anonymous = 1 if data.get('is_anonymous') else 0
        
        # Server-side validations
        if not title or len(title) < 5 or len(title) > 120:
            conn.close()
            return jsonify({'error': 'Title must be between 5 and 120 characters'}), 400
        if not category_id:
            conn.close()
            return jsonify({'error': 'Category is required'}), 400
        if not description or len(description) < 15:
            conn.close()
            return jsonify({'error': 'Description must be at least 15 characters'}), 400
        if not building:
            conn.close()
            return jsonify({'error': 'Building / Location is required'}), 400
        if priority not in ('LOW', 'MEDIUM', 'HIGH', 'EMERGENCY'):
            priority = 'MEDIUM'
            
        # Determine responsible department via routing rules
        cat_row = conn.execute("SELECT name, default_department_id FROM categories WHERE id = ?", (category_id,)).fetchone()
        if cat_row:
            category_name = cat_row['name']
            assigned_department_id = cat_row['default_department_id']
        else:
            category_name = 'General'
            assigned_department_id = 'D001' # Fallback to admin/facilities
            
        dept_row = conn.execute("SELECT name FROM departments WHERE id = ?", (assigned_department_id,)).fetchone()
        department_name = dept_row['name'] if dept_row else "Central Administration"
        
        # Generate Unique Complaint Reference CMP-YYYY-XXXXXX
        year = datetime.now(timezone.utc).year
        count_row = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()
        next_num = count_row[0] + 1
        complaint_code = f"CMP-{year}-{next_num:06d}"
        
        location_desc = f"{building}"
        if block: location_desc += f", {block}"
        if floor: location_desc += f", {floor}"
        if room: location_desc += f", {room}"
        if landmark: location_desc += f" (Near: {landmark})"
        
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate Due SLA
        sla_hours = 24
        if priority == 'EMERGENCY': sla_hours = 4
        elif priority == 'HIGH': sla_hours = 24
        elif priority == 'MEDIUM': sla_hours = 72
        elif priority == 'LOW': sla_hours = 168
        due_at = (datetime.now(timezone.utc) + timedelta(hours=sla_hours)).strftime("%Y-%m-%d %H:%M:%S")
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO complaints (
                complaint_code, student_id, category_id, title, description,
                building, block, floor, room, landmark, location_description,
                priority, status, is_anonymous, assigned_department_id,
                submitted_at, due_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?, ?, ?, ?, ?)
        ''', (
            complaint_code, user['id'], category_id, title, description,
            building, block, floor, room, landmark, location_desc,
            priority, is_anonymous, assigned_department_id,
            now_str, due_at, now_str
        ))
        complaint_id = cursor.lastrowid
        
        # Record Initial Status History
        cursor.execute('''
            INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, changed_at)
            VALUES (?, NULL, 'SUBMITTED', ?, 'Complaint submitted and assigned to ' || ?, ?)
        ''', (complaint_id, user['id'], department_name, now_str))
        
        # Notification to Student
        cursor.execute('''
            INSERT INTO notifications (user_id, complaint_id, event_type, title, message)
            VALUES (?, ?, 'SUBMISSION_CONFIRMATION', 'Complaint Submitted Successfully', 'Your complaint ' || ? || ' has been assigned to ' || ?)
        ''', (user['id'], complaint_id, complaint_code, department_name))
        
        # MANDATORY EMAIL NOTIFICATION REQUIREMENT
        # Backend queues / sends email notification to: anilanji22515@gmail.com
        recipient_email = Config.PARENT_NOTIFICATION_EMAIL
        summary_snippet = description[:150] + ("..." if len(description) > 150 else "")
        subject, body_text, body_html = EmailService.format_complaint_email(
            complaint_code=complaint_code,
            category=category_name,
            priority=priority,
            location=location_desc,
            summary=summary_snippet,
            submitted_at=now_str
        )
        
        # Send or Simulate delivery
        email_result = EmailService.send_notification(recipient_email, subject, body_text, body_html)
        delivery_status = email_result['status']
        provider_msg_id = email_result.get('message_id')
        error_msg = email_result.get('error')
        
        cursor.execute('''
            INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, provider_message_id, last_error, sent_at)
            VALUES (?, 'COMPLAINT_SUBMISSION', ?, ?, ?, ?, ?, ?, ?)
        ''', (complaint_id, recipient_email, subject, body_text, delivery_status, provider_msg_id, error_msg, now_str if delivery_status in ('SENT', 'SIMULATED') else None))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Complaint successfully submitted',
            'complaint_id': complaint_id,
            'complaint_code': complaint_code,
            'status': 'SUBMITTED',
            'assigned_department': department_name,
            'email_notification': {
                'recipient': recipient_email,
                'status': delivery_status,
                'provider_message_id': provider_msg_id,
                'is_simulated': email_result.get('is_simulated', False),
                'note': email_result.get('note')
            }
        }), 201

    # GET complaints with role-based filtering
    role = user['role']
    status_filter = request.args.get('status')
    priority_filter = request.args.get('priority')
    category_filter = request.args.get('category')
    search = request.args.get('search', '').strip()
    
    query = """
        SELECT c.*, cat.name as category_name, d.name as department_name,
               u.full_name as student_name, u.college_id as student_college_id,
               staff.full_name as staff_name,
               f.rating as feedback_rating, f.problem_fixed as feedback_fixed
        FROM complaints c
        LEFT JOIN categories cat ON c.category_id = cat.id
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        LEFT JOIN users u ON c.student_id = u.id
        LEFT JOIN users staff ON c.assigned_staff_id = staff.id
        LEFT JOIN feedback f ON c.id = f.complaint_id
        WHERE 1=1
    """
    params = []
    
    if role == 'student':
        query += " AND c.student_id = ?"
        params.append(user['id'])
    elif role in ('staff', 'department_head') and user.get('department_id'):
        query += " AND (c.assigned_department_id = ? OR c.priority = 'EMERGENCY')"
        params.append(user['department_id'])
    # admin sees all
    
    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)
    if priority_filter:
        query += " AND c.priority = ?"
        params.append(priority_filter)
    if category_filter:
        query += " AND c.category_id = ?"
        params.append(category_filter)
    if search:
        query += " AND (c.complaint_code LIKE ? OR c.title LIKE ? OR c.location_description LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
        
    query += " ORDER BY CASE WHEN c.priority = 'EMERGENCY' THEN 1 WHEN c.priority = 'HIGH' THEN 2 ELSE 3 END, c.submitted_at DESC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    complaints = []
    for r in rows:
        d = dict(r)
        # Protect anonymous student identities for department staff
        if d['is_anonymous'] and role != 'admin' and d['student_id'] != user['id']:
            d['student_name'] = 'Anonymous Student'
            d['student_college_id'] = 'ANONYMOUS'
        complaints.append(d)
        
    return jsonify({'complaints': complaints}), 200

@app.route('/api/complaints/<int:complaint_id>', methods=['GET'])
def get_complaint_detail(complaint_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db()
    c = conn.execute("""
        SELECT c.*, cat.name as category_name, d.name as department_name,
               u.full_name as student_name, u.college_id as student_college_id, u.email as student_email,
               staff.full_name as staff_name, staff.email as staff_email
        FROM complaints c
        LEFT JOIN categories cat ON c.category_id = cat.id
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        LEFT JOIN users u ON c.student_id = u.id
        LEFT JOIN users staff ON c.assigned_staff_id = staff.id
        WHERE c.id = ?
    """, (complaint_id,)).fetchone()
    
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
        
    complaint_data = dict(c)
    
    # Permission check
    if user['role'] == 'student' and complaint_data['student_id'] != user['id']:
        conn.close()
        return jsonify({'error': 'Forbidden access to this complaint'}), 403
        
    if complaint_data['is_anonymous'] and user['role'] != 'admin' and complaint_data['student_id'] != user['id']:
        complaint_data['student_name'] = 'Anonymous Student'
        complaint_data['student_college_id'] = 'ANONYMOUS'
        complaint_data['student_email'] = 'protected@privacy.campuscare.edu'
        
    # Status Timeline History
    history_query = """
        SELECT h.*, u.full_name as changed_by_name, u.role as changed_by_role
        FROM complaint_status_history h
        LEFT JOIN users u ON h.changed_by = u.id
        WHERE h.complaint_id = ?
        ORDER BY h.changed_at ASC
    """
    history_rows = conn.execute(history_query, (complaint_id,)).fetchall()
    timeline = []
    for h in history_rows:
        hd = dict(h)
        # CRITICAL PRIVACY: Hide internal notes from students!
        if user['role'] == 'student':
            hd['internal_note'] = None
        timeline.append(hd)
        
    # Resolution Record
    res_row = conn.execute("""
        SELECT r.*, u.full_name as resolved_by_name
        FROM resolution_records r
        LEFT JOIN users u ON r.resolved_by = u.id
        WHERE r.complaint_id = ?
    """, (complaint_id,)).fetchone()
    resolution = dict(res_row) if res_row else None
    
    # Student Feedback
    fb_row = conn.execute("SELECT * FROM feedback WHERE complaint_id = ?", (complaint_id,)).fetchone()
    feedback = dict(fb_row) if fb_row else None
    
    # Email Logs for this complaint (visible to Admin and Department Head)
    email_logs = []
    if user['role'] in ('admin', 'system_admin', 'department_head'):
        email_rows = conn.execute("SELECT * FROM email_outbox WHERE complaint_id = ? ORDER BY created_at DESC", (complaint_id,)).fetchall()
        email_logs = [dict(e) for e in email_rows]
        
    conn.close()
    
    return jsonify({
        'complaint': complaint_data,
        'timeline': timeline,
        'resolution': resolution,
        'feedback': feedback,
        'email_logs': email_logs
    }), 200

# ----------------- STATUS & WORKFLOW UPDATES -----------------

@app.route('/api/complaints/<int:complaint_id>/status', methods=['PATCH'])
def update_complaint_status(complaint_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    if user['role'] not in ('staff', 'department_head', 'admin', 'system_admin'):
        return jsonify({'error': 'Only staff or admin can update status'}), 403
        
    data = request.get_json() or {}
    new_status = data.get('status', '').upper()
    public_message = data.get('public_message', '').strip()
    internal_note = data.get('internal_note', '').strip()
    
    valid_statuses = ('UNDER_REVIEW', 'ASSIGNED', 'IN_PROGRESS', 'ON_HOLD', 'RESOLVED', 'CLOSED', 'REJECTED', 'REOPENED')
    if new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Allowed: {valid_statuses}'}), 400
        
    if new_status in ('ON_HOLD', 'REJECTED') and not public_message:
        return jsonify({'error': f'A message or reason is required when placing on hold or rejecting'}), 400
        
    conn = get_db()
    c = conn.execute("SELECT id, complaint_code, status, student_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
        
    old_status = c['status']
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor = conn.cursor()
    cursor.execute("UPDATE complaints SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_str, complaint_id))
    
    cursor.execute("""
        INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (complaint_id, old_status, new_status, user['id'], public_message or f"Status changed to {new_status}", internal_note, now_str))
    
    # Notify student
    cursor.execute("""
        INSERT INTO notifications (user_id, complaint_id, event_type, title, message)
        VALUES (?, ?, 'STATUS_UPDATE', 'Complaint Update: ' || ?, ?)
    """, (c['student_id'], complaint_id, c['complaint_code'], public_message or f"Your complaint is now {new_status}"))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'old_status': old_status, 'new_status': new_status}), 200

@app.route('/api/complaints/<int:complaint_id>/assign', methods=['PATCH'])
def assign_complaint(complaint_id):
    user = get_current_user()
    if not user or user['role'] not in ('department_head', 'admin', 'system_admin'):
        return jsonify({'error': 'Unauthorized to assign staff or departments'}), 403
        
    data = request.get_json() or {}
    department_id = data.get('department_id')
    staff_id = data.get('staff_id')
    note = data.get('assignment_note', 'Assigned by administrator')
    
    conn = get_db()
    c = conn.execute("SELECT id, complaint_code, assigned_department_id, status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    
    if department_id and staff_id:
        cursor.execute("UPDATE complaints SET assigned_department_id = ?, assigned_staff_id = ?, status = 'ASSIGNED', updated_at = ? WHERE id = ?", (department_id, staff_id, now_str, complaint_id))
    elif department_id:
        cursor.execute("UPDATE complaints SET assigned_department_id = ?, status = 'ASSIGNED', updated_at = ? WHERE id = ?", (department_id, now_str, complaint_id))
    elif staff_id:
        cursor.execute("UPDATE complaints SET assigned_staff_id = ?, status = 'ASSIGNED', updated_at = ? WHERE id = ?", (staff_id, now_str, complaint_id))
        
    cursor.execute("""
        INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
        VALUES (?, ?, 'ASSIGNED', ?, 'Complaint assigned to department specialist for action.', ?, ?)
    """, (complaint_id, c['status'], user['id'], note, now_str))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Complaint reassigned successfully'}), 200

@app.route('/api/complaints/<int:complaint_id>/resolution', methods=['POST'])
def add_resolution(complaint_id):
    user = get_current_user()
    if not user or user['role'] not in ('staff', 'department_head', 'admin'):
        return jsonify({'error': 'Unauthorized to submit resolution'}), 403
        
    data = request.get_json() or {}
    summary = data.get('resolution_summary', '').strip()
    work_performed = data.get('work_performed', '').strip()
    
    if not summary:
        return jsonify({'error': 'Resolution summary is required'}), 400
        
    conn = get_db()
    c = conn.execute("SELECT id, complaint_code, student_id FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    
    # Upsert resolution record
    cursor.execute("""
        INSERT INTO resolution_records (complaint_id, resolved_by, resolution_summary, work_performed, resolved_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(complaint_id) DO UPDATE SET
            resolved_by = excluded.resolved_by,
            resolution_summary = excluded.resolution_summary,
            work_performed = excluded.work_performed,
            resolved_at = excluded.resolved_at
    """, (complaint_id, user['id'], summary, work_performed, now_str))
    
    cursor.execute("UPDATE complaints SET status = 'RESOLVED', resolved_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, complaint_id))
    
    cursor.execute("""
        INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, changed_at)
        VALUES (?, 'IN_PROGRESS', 'RESOLVED', ?, ?, ?)
    """, (complaint_id, user['id'], f"Problem resolved: {summary}", now_str))
    
    # Notify student
    cursor.execute("""
        INSERT INTO notifications (user_id, complaint_id, event_type, title, message)
        VALUES (?, ?, 'RESOLVED', 'Complaint Resolved: ' || ?, 'Your complaint has been marked as resolved. Please provide your feedback.')
    """, (c['student_id'], complaint_id, c['complaint_code']))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Resolution recorded successfully'}), 200

@app.route('/api/complaints/<int:complaint_id>/feedback', methods=['POST'])
def add_feedback(complaint_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json() or {}
    rating = int(data.get('rating', 5))
    comment = data.get('comment', '').strip()
    problem_fixed = 1 if data.get('problem_fixed', True) else 0
    
    conn = get_db()
    c = conn.execute("SELECT id, complaint_code, student_id, status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
    if c['student_id'] != user['id']:
        conn.close()
        return jsonify({'error': 'Only the student who submitted the complaint can provide feedback'}), 403
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (complaint_id, student_id, rating, comment, problem_fixed, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(complaint_id) DO UPDATE SET
            rating = excluded.rating,
            comment = excluded.comment,
            problem_fixed = excluded.problem_fixed,
            created_at = excluded.created_at
    """, (complaint_id, user['id'], rating, comment, problem_fixed, now_str))
    
    if problem_fixed == 1:
        cursor.execute("UPDATE complaints SET status = 'CLOSED', closed_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, complaint_id))
        cursor.execute("""
            INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, changed_at)
            VALUES (?, 'RESOLVED', 'CLOSED', ?, 'Student satisfied with resolution. Complaint closed.', ?)
        """, (complaint_id, user['id'], now_str))
    else:
        # Reopen complaint if problem is not fixed
        cursor.execute("UPDATE complaints SET status = 'REOPENED', updated_at = ? WHERE id = ?", (now_str, complaint_id))
        cursor.execute("""
            INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, changed_at)
            VALUES (?, 'RESOLVED', 'REOPENED', ?, 'Student indicated problem is not fixed: ' || ?, ?)
        """, (complaint_id, user['id'], comment or "Reopened by student", now_str))
        
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Feedback recorded'}), 200

@app.route('/api/complaints/<int:complaint_id>/reopen', methods=['POST'])
def reopen_complaint(complaint_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'error': 'A reason for reopening is required'}), 400
        
    conn = get_db()
    c = conn.execute("SELECT id, complaint_code, student_id, status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not c:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
    if user['role'] == 'student' and c['student_id'] != user['id']:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
        
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("UPDATE complaints SET status = 'REOPENED', updated_at = ? WHERE id = ?", (now_str, complaint_id))
    cursor.execute("""
        INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, changed_at)
        VALUES (?, ?, 'REOPENED', ?, 'Complaint reopened: ' || ?, ?)
    """, (complaint_id, c['status'], user['id'], reason, now_str))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Complaint reopened successfully'}), 200

# ----------------- ADMIN, ANALYTICS & OUTBOX APIS -----------------

@app.route('/api/admin/analytics', methods=['GET'])
def admin_analytics():
    user = get_current_user()
    if not user or user['role'] not in ('admin', 'system_admin', 'department_head'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db()
    
    total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    open_count = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('SUBMITTED', 'UNDER_REVIEW')").fetchone()[0]
    in_progress = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('ASSIGNED', 'IN_PROGRESS', 'ON_HOLD')").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM complaints WHERE status IN ('RESOLVED', 'CLOSED')").fetchone()[0]
    emergency = conn.execute("SELECT COUNT(*) FROM complaints WHERE priority = 'EMERGENCY' AND status != 'CLOSED'").fetchone()[0]
    
    # Overdue count
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    overdue = conn.execute("SELECT COUNT(*) FROM complaints WHERE due_at < ? AND status NOT IN ('RESOLVED', 'CLOSED', 'REJECTED')", (now_str,)).fetchone()[0]
    
    # Category Breakdown
    cat_rows = conn.execute("""
        SELECT cat.name, COUNT(c.id) as count
        FROM categories cat
        LEFT JOIN complaints c ON cat.id = c.category_id
        GROUP BY cat.id, cat.name
        ORDER BY count DESC
    """).fetchall()
    categories_data = [{'name': r['name'], 'count': r['count']} for r in cat_rows]
    
    # Status Breakdown
    status_rows = conn.execute("""
        SELECT status, COUNT(id) as count
        FROM complaints
        GROUP BY status
    """).fetchall()
    status_data = [{'status': r['status'], 'count': r['count']} for r in status_rows]
    
    # Department Workload
    dept_rows = conn.execute("""
        SELECT d.name, COUNT(c.id) as total,
               SUM(CASE WHEN c.status IN ('RESOLVED', 'CLOSED') THEN 1 ELSE 0 END) as resolved
        FROM departments d
        LEFT JOIN complaints c ON d.id = c.assigned_department_id
        GROUP BY d.id, d.name
        ORDER BY total DESC
    """).fetchall()
    departments_data = [{'name': r['name'], 'total': r['total'], 'resolved': r['resolved'] or 0} for r in dept_rows]
    
    conn.close()
    
    return jsonify({
        'kpi': {
            'total': total,
            'open': open_count,
            'in_progress': in_progress,
            'resolved': resolved,
            'emergency': emergency,
            'overdue': overdue
        },
        'categories': categories_data,
        'statuses': status_data,
        'departments': departments_data
    }), 200

@app.route('/api/admin/outbox', methods=['GET'])
def get_email_outbox():
    user = get_current_user()
    if not user or user['role'] not in ('admin', 'system_admin', 'department_head'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db()
    rows = conn.execute("""
        SELECT o.*, c.complaint_code, c.title as complaint_title
        FROM email_outbox o
        LEFT JOIN complaints c ON o.complaint_id = c.id
        ORDER BY o.created_at DESC LIMIT 50
    """).fetchall()
    conn.close()
    
    return jsonify({
        'outbox': [dict(r) for r in rows],
        'configured_recipient': Config.PARENT_NOTIFICATION_EMAIL
    }), 200

@app.route('/api/admin/test-email', methods=['POST'])
def send_test_email():
    user = get_current_user()
    if not user or user['role'] not in ('admin', 'system_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.get_json() or {}
    recipient = data.get('recipient') or Config.PARENT_NOTIFICATION_EMAIL
    
    subject = "CampusCare: Administrator Diagnostic Test Email"
    body_text = f"This is a test notification dispatched from CampusCare administration console by {user['full_name']}."
    body_html = f"<p>{body_text}</p>"
    
    res = EmailService.send_notification(recipient, subject, body_text, body_html)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, provider_message_id, last_error, sent_at)
        VALUES (NULL, 'ADMIN_TEST', ?, ?, ?, ?, ?, ?, ?)
    """, (recipient, subject, body_text, res['status'], res.get('message_id'), res.get('error'), now_str if res['status'] in ('SENT', 'SIMULATED') else None))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'recipient': recipient,
        'result': res
    }), 200

@app.route('/api/admin/outbox/<int:outbox_id>/retry', methods=['POST'])
def retry_outbox_email(outbox_id):
    user = get_current_user()
    if not user or user['role'] not in ('admin', 'system_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db()
    msg = conn.execute("SELECT * FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()
    if not msg:
        conn.close()
        return jsonify({'error': 'Outbox message not found'}), 404
        
    res = EmailService.send_notification(msg['recipient_email'], msg['subject'], msg['body'])
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE email_outbox
        SET delivery_status = ?, retry_count = retry_count + 1, provider_message_id = ?, last_error = ?, sent_at = ?
        WHERE id = ?
    """, (res['status'], res.get('message_id'), res.get('error'), now_str if res['status'] in ('SENT', 'SIMULATED') else None, outbox_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'result': res}), 200

@app.route('/api/admin/export', methods=['GET'])
def export_complaints_csv():
    user = get_current_user()
    if not user or user['role'] not in ('admin', 'system_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
        
    conn = get_db()
    rows = conn.execute("""
        SELECT c.complaint_code, c.title, cat.name as category, c.location_description,
               c.priority, c.status, d.name as department, u.full_name as student_name,
               c.submitted_at, c.resolved_at
        FROM complaints c
        LEFT JOIN categories cat ON c.category_id = cat.id
        LEFT JOIN departments d ON c.assigned_department_id = d.id
        LEFT JOIN users u ON c.student_id = u.id
        ORDER BY c.submitted_at DESC
    """).fetchall()
    conn.close()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Complaint ID', 'Title', 'Category', 'Location', 'Priority', 'Status', 'Department', 'Student', 'Submitted At', 'Resolved At'])
    
    for r in rows:
        cw.writerow([r['complaint_code'], r['title'], r['category'], r['location_description'], r['priority'], r['status'], r['department'], r['student_name'], r['submitted_at'], r['resolved_at']])
        
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    filename = f"CampusCare_Complaints_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

# ----------------- NOTIFICATIONS API -----------------

@app.route('/api/notifications', methods=['GET'])
def get_user_notifications():
    user = get_current_user()
    if not user:
        return jsonify({'notifications': []}), 200
        
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 20
    """, (user['id'],)).fetchall()
    conn.close()
    
    return jsonify({'notifications': [dict(r) for r in rows]}), 200

@app.route('/api/notifications/<int:notif_id>/read', methods=['PATCH'])
def mark_notification_read(notif_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, user['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True}), 200

# Initialize Database on import/startup
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
