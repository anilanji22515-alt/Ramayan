import unittest
import json
import os
from app import app
from database import init_db, get_db

class CampusCareTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['DATABASE_PATH'] = ':memory:'
        self.client = app.test_client()
        with app.app_context():
            init_db()

    def test_01_demo_login_student(self):
        """Test demo student login"""
        res = self.client.post('/api/auth/demo-login', json={'role': 'student'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['user']['role'], 'student')
        self.assertEqual(data['user']['email'], 'rahul.demo@example.com')

    def test_02_create_complaint_and_parent_email_outbox(self):
        """Test complaint submission, auto-routing, and parent notification outbox dispatch"""
        # Login as student
        self.client.post('/api/auth/demo-login', json={'role': 'student'})
        
        payload = {
            'title': 'Broken drinking water tap in Main Block',
            'category_id': 'CAT002', # Water and Sanitation -> D004 Plumbing and Water
            'priority': 'HIGH',
            'building': 'Main Block',
            'floor': '1st Floor',
            'room': 'Corridor Near Room 102',
            'description': 'Water tap is constantly dripping water on floor causing pooling.',
            'is_anonymous': False
        }
        res = self.client.post('/api/complaints', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data['complaint_code'].startswith('CMP-'))
        self.assertEqual(data['assigned_department'], 'Plumbing and Water')
        self.assertEqual(data['email_notification']['recipient'], 'anilanji22515@gmail.com')
        self.assertIn(data['email_notification']['status'], ('SENT', 'SIMULATED'))

    def test_03_privacy_internal_notes_hidden_from_students(self):
        """Verify that staff internal notes are protected and hidden from students"""
        # 1. Staff adds status update with public message and secret internal note
        self.client.post('/api/auth/demo-login', json={'role': 'staff'})
        update_res = self.client.patch('/api/complaints/1/status', json={
            'status': 'IN_PROGRESS',
            'public_message': 'Work is underway by field technician.',
            'internal_note': 'CONFIDENTIAL_NOTE_STAFF_ONLY_DO_NOT_LEAK'
        })
        self.assertEqual(update_res.status_code, 200)

        # 2. Student views complaint detail -> internal note MUST BE NULL
        self.client.post('/api/auth/demo-login', json={'role': 'student'})
        detail_res = self.client.get('/api/complaints/1')
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.get_json()
        for t in detail_data['timeline']:
            self.assertIsNone(t['internal_note'])

    def test_04_resolution_and_student_feedback(self):
        """Test staff marking complaint resolved and student submitting rating"""
        # Staff resolves
        self.client.post('/api/auth/demo-login', json={'role': 'staff'})
        res = self.client.post('/api/complaints/2/resolution', json={
            'resolution_summary': 'Replaced wireless access point AP-04',
            'work_performed': 'Configured DHCP and verified throughput'
        })
        self.assertEqual(res.status_code, 200)

        # Student rates
        self.client.post('/api/auth/demo-login', json={'role': 'student'})
        fb_res = self.client.post('/api/complaints/2/feedback', json={
            'rating': 5,
            'comment': 'Wi-Fi is super fast now, thanks!',
            'problem_fixed': True
        })
        self.assertEqual(fb_res.status_code, 200)

        # Check status is now CLOSED
        detail = self.client.get('/api/complaints/2').get_json()
        self.assertEqual(detail['complaint']['status'], 'CLOSED')

    def test_05_admin_analytics_and_outbox(self):
        """Test admin analytics KPI metrics and parent email outbox listing"""
        self.client.post('/api/auth/demo-login', json={'role': 'admin'})
        analytics = self.client.get('/api/admin/analytics').get_json()
        self.assertIn('kpi', analytics)
        self.assertGreaterEqual(analytics['kpi']['total'], 1)

        outbox = self.client.get('/api/admin/outbox').get_json()
        self.assertIn('outbox', outbox)
        self.assertEqual(outbox['configured_recipient'], 'anilanji22515@gmail.com')

if __name__ == '__main__':
    unittest.main()
