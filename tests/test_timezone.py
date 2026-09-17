import unittest
import datetime
from datetime import timezone
from app import create_app
from app.utils.timezone import to_ist, format_ist, now_ist, to_ist_iso, IST

class TimezoneTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_utc_to_ist_conversion(self):
        # 16 Sep 2026 17:41:19 UTC should be 16 Sep 2026 23:11:19 IST (+5:30)
        utc_dt = datetime.datetime(2026, 9, 16, 17, 41, 19, tzinfo=timezone.utc)
        ist_dt = to_ist(utc_dt)
        self.assertEqual(ist_dt.year, 2026)
        self.assertEqual(ist_dt.month, 9)
        self.assertEqual(ist_dt.day, 16)
        self.assertEqual(ist_dt.hour, 23)
        self.assertEqual(ist_dt.minute, 11)
        self.assertEqual(ist_dt.second, 19)

    def test_naive_utc_datetime_conversion(self):
        # DB naive UTC datetime
        naive_dt = datetime.datetime(2026, 9, 16, 17, 41, 19)
        formatted_date = to_ist(naive_dt, '%d %b %Y')
        formatted_time = to_ist(naive_dt, '%I:%M %p')
        self.assertEqual(formatted_date, '16 Sep 2026')
        self.assertEqual(formatted_time, '11:11 PM')

    def test_format_ist_helper(self):
        naive_dt = datetime.datetime(2026, 9, 16, 17, 41, 19)
        res = format_ist(naive_dt, '%d %b %Y, %I:%M:%S %p IST')
        self.assertEqual(res, '16 Sep 2026, 11:11:19 PM IST')

    def test_to_ist_iso(self):
        naive_dt = datetime.datetime(2026, 9, 16, 17, 41, 19)
        iso_str = to_ist_iso(naive_dt)
        self.assertTrue(iso_str.startswith('2026-09-16T23:11:19+05:30'))

    def test_jinja_filters(self):
        with self.app.test_request_context():
            from flask import render_template_string
            tmpl = "{{ dt|to_ist('%d %b %Y') }} - {{ dt|to_ist('%I:%M %p') }}"
            rendered = render_template_string(tmpl, dt=datetime.datetime(2026, 9, 16, 17, 41, 19))
            self.assertEqual(rendered, '16 Sep 2026 - 11:11 PM')


if __name__ == '__main__':
    unittest.main()
