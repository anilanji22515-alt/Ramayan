import sqlite3
import os
import hashlib
from datetime import datetime, timezone
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def log_audit(actor_id, action, entity_type, entity_id, details, ip=None):
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO audit_logs (actor_user_id, action, entity_type, entity_id, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (actor_id, action, entity_type, str(entity_id), details, ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to write audit log: {e}")

def init_db():
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Enable Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # 1. Departments
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        contact_phone TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 2. Categories
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        default_department_id TEXT,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (default_department_id) REFERENCES departments(id)
    )
    ''')
    
    # 3. Users
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        college_id TEXT UNIQUE,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student', 'staff', 'department_head', 'admin', 'system_admin')),
        department_id TEXT,
        year_of_study INTEGER,
        section TEXT,
        is_email_verified INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    ''')
    
    # 4. Campus Locations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campus_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campus_name TEXT NOT NULL,
        building TEXT NOT NULL,
        block TEXT,
        floor TEXT,
        room_or_area TEXT,
        landmark TEXT,
        is_active INTEGER DEFAULT 1
    )
    ''')
    
    # 5. Complaints
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_code TEXT UNIQUE NOT NULL,
        student_id INTEGER,
        category_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        building TEXT NOT NULL,
        block TEXT,
        floor TEXT,
        room TEXT,
        landmark TEXT,
        location_description TEXT,
        priority TEXT NOT NULL CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'EMERGENCY')),
        status TEXT NOT NULL CHECK(status IN ('SUBMITTED', 'UNDER_REVIEW', 'ASSIGNED', 'IN_PROGRESS', 'ON_HOLD', 'RESOLVED', 'CLOSED', 'REJECTED', 'REOPENED')),
        is_anonymous INTEGER DEFAULT 0,
        assigned_department_id TEXT,
        assigned_staff_id INTEGER,
        parent_complaint_id INTEGER,
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        acknowledged_at TEXT,
        due_at TEXT,
        resolved_at TEXT,
        closed_at TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES users(id),
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (assigned_department_id) REFERENCES departments(id),
        FOREIGN KEY (assigned_staff_id) REFERENCES users(id),
        FOREIGN KEY (parent_complaint_id) REFERENCES complaints(id)
    )
    ''')
    
    # 6. Complaint Attachments
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaint_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        uploaded_by INTEGER,
        file_name TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        mime_type TEXT,
        file_size INTEGER,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (uploaded_by) REFERENCES users(id)
    )
    ''')
    
    # 7. Status History
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS complaint_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        changed_by INTEGER,
        public_message TEXT,
        internal_note TEXT,
        changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (changed_by) REFERENCES users(id)
    )
    ''')
    
    # 8. Resolution Records
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS resolution_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER UNIQUE NOT NULL,
        resolved_by INTEGER NOT NULL,
        resolution_summary TEXT NOT NULL,
        work_performed TEXT,
        proof_attachment_id INTEGER,
        resolved_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (resolved_by) REFERENCES users(id)
    )
    ''')
    
    # 9. Feedback
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER UNIQUE NOT NULL,
        student_id INTEGER NOT NULL,
        rating INTEGER CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        problem_fixed INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES users(id)
    )
    ''')
    
    # 10. Email Outbox & Delivery State
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS email_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER,
        event_type TEXT NOT NULL,
        recipient_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT,
        delivery_status TEXT NOT NULL CHECK(delivery_status IN ('PENDING', 'PROCESSING', 'SENT', 'SIMULATED', 'FAILED', 'RETRY_SCHEDULED')),
        retry_count INTEGER DEFAULT 0,
        provider_message_id TEXT,
        last_error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        sent_at TEXT,
        FOREIGN KEY (complaint_id) REFERENCES complaints(id)
    )
    ''')
    
    # 11. In-App Notifications
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        complaint_id INTEGER,
        channel TEXT DEFAULT 'in_app',
        recipient TEXT,
        event_type TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (complaint_id) REFERENCES complaints(id)
    )
    ''')
    
    # 12. SLA Rules
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sla_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        priority TEXT UNIQUE NOT NULL,
        acknowledge_minutes INTEGER NOT NULL,
        resolve_minutes INTEGER NOT NULL,
        working_hours_only INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1
    )
    ''')
    
    # 13. System Settings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 14. Audit Logs (Section 14 Specification)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        details TEXT,
        ip_address TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (actor_user_id) REFERENCES users(id)
    )
    ''')
    
    # Seed Initial Data if empty
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)
        
    conn.commit()
    conn.close()

def seed_data(cursor):
    # 1. Departments
    departments = [
        ('D001', 'Facilities and Civil Maintenance', 'facilities@college.edu', 'ext. 101'),
        ('D002', 'Electrical Maintenance', 'electrical@college.edu', 'ext. 102'),
        ('D003', 'IT and Network Support', 'itsupport@college.edu', 'ext. 103'),
        ('D004', 'Plumbing and Water', 'plumbing@college.edu', 'ext. 104'),
        ('D005', 'Sanitation and Housekeeping', 'housekeeping@college.edu', 'ext. 105'),
        ('D006', 'Mess and Food Services', 'mess@college.edu', 'ext. 106'),
        ('D007', 'Campus Security', 'security@college.edu', 'ext. 911'),
        ('D008', 'Medical and Health Services', 'health@college.edu', 'ext. 108'),
        ('D009', 'Library Services', 'library@college.edu', 'ext. 109'),
        ('D010', 'Hostel Administration', 'hostel@college.edu', 'ext. 110'),
        ('D011', 'Transport and Parking', 'transport@college.edu', 'ext. 111'),
        ('D012', 'Sports and Recreation', 'sports@college.edu', 'ext. 112')
    ]
    cursor.executemany(
        "INSERT INTO departments (id, name, contact_email, contact_phone) VALUES (?, ?, ?, ?)",
        departments
    )
    
    # 2. Categories
    categories = [
        ('CAT001', 'Classrooms', 'Desks, blackboards, podiums, and classroom infrastructure', 'D001'),
        ('CAT002', 'Water and Sanitation', 'Drinking water, leakages, pipeline issues, water coolers', 'D004'),
        ('CAT003', 'Electricity and Lighting', 'Fans, lights, wiring, power outages, switches', 'D002'),
        ('CAT004', 'Wi-Fi and Internet', 'Campus Wi-Fi connectivity, LAN ports, network speed', 'D003'),
        ('CAT005', 'Furniture', 'Damaged chairs, benches, tables, cupboards', 'D001'),
        ('CAT006', 'Washrooms', 'Cleanliness, running water, soap dispensers, mirrors', 'D005'),
        ('CAT007', 'Roads and Infrastructure', 'Footpaths, parking lots, potholes, street lights', 'D001'),
        ('CAT008', 'Mess/Food', 'Food quality, hygiene, mess timings, menu adherence', 'D006'),
        ('CAT009', 'Health and Medical Facilities', 'First aid kits, health center equipment, medical attention', 'D008'),
        ('CAT010', 'Security', 'Unauthorized access, lighting in dim areas, lost & found', 'D007'),
        ('CAT011', 'Laboratories and Equipment', 'Lab computers, test equipment, chemicals, safety gear', 'D003'),
        ('CAT012', 'Library', 'AC, book availability, study carrels, noise control', 'D009'),
        ('CAT013', 'Hostel and Accommodation', 'Room maintenance, hot water, corridor lighting, pest control', 'D010'),
        ('CAT014', 'Sports and Recreation', 'Gym equipment, playground turf, basketball hoops', 'D012'),
        ('CAT015', 'Transport and Parking', 'College bus schedules, parking permits, congestion', 'D011'),
        ('CAT016', 'Other', 'General campus grievances and unspecified matters', 'D001')
    ]
    cursor.executemany(
        "INSERT INTO categories (id, name, description, default_department_id) VALUES (?, ?, ?, ?)",
        categories
    )
    
    # 3. Campus Locations
    locations = [
        ('Main Campus', 'Main Block', 'Reception', 'Ground Floor', 'Reception / Admin Office', 'Near Entrance Lobby'),
        ('Main Campus', 'Main Block', 'Block A', 'First Floor', 'Room 101 - Lecture Hall', 'Opposite Staff Room'),
        ('Main Campus', 'Main Block', 'Block B', 'Second Floor', 'Room 204 - Classroom', 'Near Staircase 2'),
        ('Main Campus', 'Engineering Block', 'CS Wing', 'First Floor', 'Computer Lab 1', 'Beside Server Room'),
        ('Main Campus', 'Engineering Block', 'EC Wing', 'Second Floor', 'Electronics Lab', 'Near Elevator'),
        ('Main Campus', 'Central Library', 'East Wing', 'Ground Floor', 'Main Reading Hall', 'Near Circulation Desk'),
        ('Main Campus', 'Central Library', 'West Wing', 'First Floor', 'Digital Library / Computer Section', 'Adjacent to Reference Section'),
        ('Main Campus', 'Hostel A', 'Boys Block', 'Ground Floor', 'Dining Hall', 'Near Central Kitchen'),
        ('Main Campus', 'Hostel B', 'Girls Block', 'First Floor', 'Corridor North', 'Near Water Dispenser'),
        ('Main Campus', 'Main Canteen', 'Central Area', 'Ground Floor', 'Dining Area', 'Beside Juice Counter'),
        ('Main Campus', 'Sports Complex', 'Stadium', 'Ground Floor', 'Pavilion & Indoor Court', 'Next to Gymnasium'),
        ('Main Campus', 'Main Gate', 'Checkpost 1', 'Ground Floor', 'Security Office', 'Beside Visitor Gate'),
        ('Main Campus', 'Parking Area', 'East Lot', 'Ground Floor', 'Two-Wheeler Section', 'Behind Cafeteria')
    ]
    cursor.executemany(
        "INSERT INTO campus_locations (campus_name, building, block, floor, room_or_area, landmark) VALUES (?, ?, ?, ?, ?, ?)",
        locations
    )
    
    # 4. Users (Demo Accounts)
    pwd_hash = hash_password('demo1234')
    users = [
        ('DEMO-CSE-001', 'Rahul Kumar', 'rahul.demo@example.com', '9876543210', pwd_hash, 'student', None, 2, 'A'),
        (None, 'Priya Sharma', 'staff.demo@example.com', '9876543211', pwd_hash, 'staff', 'D004', None, None),
        (None, 'Arun Head', 'head.demo@example.com', '9876543212', pwd_hash, 'department_head', 'D004', None, None),
        (None, 'Campus Administrator', 'admin.demo@example.com', '9876543213', pwd_hash, 'admin', None, None, None)
    ]
    cursor.executemany(
        "INSERT INTO users (college_id, full_name, email, phone, password_hash, role, department_id, year_of_study, section) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        users
    )
    
    # 5. SLA Rules
    sla = [
        ('EMERGENCY', 5, 240, 0),       # 5 min acknowledge, 4 hours resolve, 24/7
        ('HIGH', 120, 1440, 1),          # 2 working hours, 24 working hours
        ('MEDIUM', 480, 4320, 1),        # 1 working day (8h), 3 days (72h)
        ('LOW', 960, 10080, 1)           # 2 working days (16h), 7 days
    ]
    cursor.executemany(
        "INSERT INTO sla_rules (priority, acknowledge_minutes, resolve_minutes, working_hours_only) VALUES (?, ?, ?, ?)",
        sla
    )
    
    # 6. System Settings
    cursor.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('PARENT_NOTIFICATION_EMAIL', ?)", (Config.PARENT_NOTIFICATION_EMAIL,))
    cursor.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('ALLOW_ANONYMOUS', 'true')")
    cursor.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('CAMPUS_NAME', ?)", (Config.CAMPUS_NAME,))

    # 7. Seed Sample Complaints with Full Real-World Lifecycle Data
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # Complaint 1 (Rahul Kumar's complaint - CMP-2026-000001)
    cursor.execute('''
    INSERT INTO complaints (
        complaint_code, student_id, category_id, title, description,
        building, block, floor, room, landmark, location_description,
        priority, status, is_anonymous, assigned_department_id, assigned_staff_id,
        submitted_at, acknowledged_at, due_at, resolved_at, closed_at, updated_at
    ) VALUES (
        'CMP-2026-000001', 1, 'CAT002', 'Water leakage near classroom',
        'Water is leaking steadily from the ceiling joint right in front of classroom 204 entrance, causing slippery floor hazards.',
        'Main Block', 'Block B', 'Second Floor', 'Room 204', 'Near Staircase 2',
        'Main Block, Block B, 2nd Floor, Room 204 (Near Staircase 2)',
        'HIGH', 'CLOSED', 0, 'D004', 2,
        '2026-11-08 10:30:00', '2026-11-08 10:45:00', '2026-11-09 10:45:00', '2026-11-09 09:30:00', '2026-11-09 11:00:00', ?
    )
    ''', (now,))
    
    # Status Timeline for CMP-2026-000001
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, NULL, 'SUBMITTED', 1, 'Complaint submitted and verified by system.', NULL, '2026-11-08 10:30:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, 'SUBMITTED', 'UNDER_REVIEW', 4, 'Complaint validated by campus administration; auto-routed to Plumbing and Water.', 'Valid report; high priority due to slip hazard.', '2026-11-08 10:35:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, 'UNDER_REVIEW', 'ASSIGNED', 3, 'Assigned to Staff Specialist Priya Sharma for immediate inspection.', 'Assigned tool kit #4.', '2026-11-08 10:45:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, 'ASSIGNED', 'IN_PROGRESS', 2, 'Technician on-site. Ceiling panel inspected and leak traced to pipe joint.', 'Replaced seal and tightened elbow fitting.', '2026-11-08 11:10:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, 'IN_PROGRESS', 'RESOLVED', 2, 'Damaged pipe joint replaced and overhead tank valve pressure normalized. Floor dried.', 'Work completed satisfactorily.', '2026-11-09 09:30:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (1, 'RESOLVED', 'CLOSED', 1, 'Student confirmed issue is fully resolved and rated service.', 'Closed after positive feedback.', '2026-11-09 11:00:00')
    ''')
    
    # Resolution record for CMP-2026-000001
    cursor.execute('''
    INSERT INTO resolution_records (complaint_id, resolved_by, resolution_summary, work_performed, resolved_at)
    VALUES (1, 2, 'Defective PVC elbow joint replaced with heavy-duty brass fitting. Water pressure tested and overhead leak sealed.', 'Replaced joint, secured false ceiling tile, wiped floor dry.', '2026-11-09 09:30:00')
    ''')
    
    # Student Feedback for CMP-2026-000001
    cursor.execute('''
    INSERT INTO feedback (complaint_id, student_id, rating, comment, problem_fixed, created_at)
    VALUES (1, 1, 5, 'Quick response! The leak was fixed completely within 24 hours. Great job by plumbing team.', 1, '2026-11-09 11:00:00')
    ''')
    
    # Outbox Email record for CMP-2026-000001
    cursor.execute('''
    INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, retry_count, provider_message_id, sent_at)
    VALUES (1, 'COMPLAINT_SUBMISSION', 'anilanji22515@gmail.com', 'CampusCare: New campus complaint submitted - CMP-2026-000001', 'Automated parent notification for CMP-2026-000001', 'SENT', 0, 'MSG-CC89A019B4', '2026-11-08 10:30:02')
    ''')
    
    # Complaint 2 (Wi-Fi issue - IN_PROGRESS)
    cursor.execute('''
    INSERT INTO complaints (
        complaint_code, student_id, category_id, title, description,
        building, block, floor, room, landmark, location_description,
        priority, status, is_anonymous, assigned_department_id, assigned_staff_id,
        submitted_at, acknowledged_at, due_at, updated_at
    ) VALUES (
        'CMP-2026-000002', 1, 'CAT004', 'Wi-Fi gateway timeout in computer lab 1',
        'Students are unable to access internal college portals and repositories due to repeated 504 gateway timeout on Lab Access Point AP-04.',
        'Engineering Block', 'CS Wing', 'First Floor', 'Computer Lab 1', 'Beside Server Room',
        'Engineering Block, CS Wing, 1st Floor, Computer Lab 1',
        'MEDIUM', 'IN_PROGRESS', 0, 'D003', NULL,
        '2026-11-09 08:15:00', '2026-11-09 08:45:00', '2026-11-12 08:45:00', ?
    )
    ''', (now,))
    
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (2, NULL, 'SUBMITTED', 1, 'Complaint submitted.', NULL, '2026-11-09 08:15:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (2, 'SUBMITTED', 'IN_PROGRESS', 4, 'Assigned to IT Network team. Network switch diagnostic underway.', 'Access point firmware upgrade scheduled.', '2026-11-09 08:45:00')
    ''')
    
    cursor.execute('''
    INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, retry_count, provider_message_id, sent_at)
    VALUES (2, 'COMPLAINT_SUBMISSION', 'anilanji22515@gmail.com', 'CampusCare: New campus complaint submitted - CMP-2026-000002', 'Automated parent notification for CMP-2026-000002', 'SENT', 0, 'MSG-CC89A019B5', '2026-11-09 08:15:02')
    ''')
    
    # Complaint 3 (Broken Light - RESOLVED)
    cursor.execute('''
    INSERT INTO complaints (
        complaint_code, student_id, category_id, title, description,
        building, block, floor, room, landmark, location_description,
        priority, status, is_anonymous, assigned_department_id, assigned_staff_id,
        submitted_at, acknowledged_at, due_at, resolved_at, updated_at
    ) VALUES (
        'CMP-2026-000003', 1, 'CAT003', 'Flickering and broken tube light near library entrance',
        'The main entrance tube light is flickering heavily and humming, making nighttime studying uncomfortable.',
        'Central Library', 'East Wing', 'Ground Floor', 'Main Entrance', 'Near Circulation Desk',
        'Central Library, Ground Floor, Main Entrance',
        'LOW', 'RESOLVED', 1, 'D002', NULL,
        '2026-11-07 14:00:00', '2026-11-07 15:00:00', '2026-11-14 15:00:00', '2026-11-08 16:30:00', ?
    )
    ''', (now,))
    
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (3, NULL, 'SUBMITTED', 1, 'Anonymous complaint submitted.', NULL, '2026-11-07 14:00:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (3, 'SUBMITTED', 'RESOLVED', 4, 'Replaced failed ballast and fitted new 20W LED fixture.', 'LED installed with 2-year warranty.', '2026-11-08 16:30:00')
    ''')
    
    cursor.execute('''
    INSERT INTO resolution_records (complaint_id, resolved_by, resolution_summary, work_performed, resolved_at)
    VALUES (3, 4, 'Installed modern LED batten light in place of defective fluorescent tube.', 'Replaced fixture and checked voltage rating.', '2026-11-08 16:30:00')
    ''')
    
    cursor.execute('''
    INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, retry_count, provider_message_id, sent_at)
    VALUES (3, 'COMPLAINT_SUBMISSION', 'anilanji22515@gmail.com', 'CampusCare: New campus complaint submitted - CMP-2026-000003', 'Automated parent notification for CMP-2026-000003', 'SENT', 0, 'MSG-CC89A019B6', '2026-11-07 14:00:03')
    ''')

    # Complaint 4 (Emergency Complaint Example)
    cursor.execute('''
    INSERT INTO complaints (
        complaint_code, student_id, category_id, title, description,
        building, block, floor, room, landmark, location_description,
        priority, status, is_anonymous, assigned_department_id, assigned_staff_id,
        submitted_at, acknowledged_at, due_at, updated_at
    ) VALUES (
        'CMP-2026-000004', 1, 'CAT003', 'Severe sparking and burning smell from corridor main fuse box',
        'Visible sparks and burning wire smell emitting from the main distribution fuse box on 2nd floor corridor.',
        'Engineering Block', 'EC Wing', 'Second Floor', 'Electronics Lab Corridor', 'Near Elevator',
        'Engineering Block, EC Wing, 2nd Floor, Corridor near elevator',
        'EMERGENCY', 'UNDER_REVIEW', 0, 'D002', NULL,
        '2026-11-09 12:00:00', '2026-11-09 12:02:00', '2026-11-09 16:00:00', ?
    )
    ''', (now,))

    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (4, NULL, 'SUBMITTED', 1, 'EMERGENCY priority report submitted. Emergency alert dispatched.', NULL, '2026-11-09 12:00:00')
    ''')
    cursor.execute('''
    INSERT INTO complaint_status_history (complaint_id, old_status, new_status, changed_by, public_message, internal_note, changed_at)
    VALUES (4, 'SUBMITTED', 'UNDER_REVIEW', 4, 'Electrical emergency team notified. Circuit isolator engaged.', 'Urgent: Safety breaker tripped.', '2026-11-09 12:02:00')
    ''')

    cursor.execute('''
    INSERT INTO email_outbox (complaint_id, event_type, recipient_email, subject, body, delivery_status, retry_count, provider_message_id, sent_at)
    VALUES (4, 'COMPLAINT_SUBMISSION', 'anilanji22515@gmail.com', 'CampusCare: New campus complaint submitted - CMP-2026-000004', 'Automated parent notification for CMP-2026-000004', 'SENT', 0, 'MSG-CC89A019B7', '2026-11-09 12:00:02')
    ''')
