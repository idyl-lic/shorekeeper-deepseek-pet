"""完成通知必须告诉用户是哪个会话（本 fork 新增行为）。"""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')

from PySide6.QtWidgets import QApplication
from shorekeeper_pet.pet import Pet

_app = QApplication.instance() or QApplication([])


class NotificationTitleTests(unittest.TestCase):
    def setUp(self):
        self.pet = Pet(offline=True)
        self.pet.timer.stop()

    def tearDown(self):
        self.pet.close()

    def notify(self, state, title):
        self.pet.notification = {'state': state, 'title': title, 'thread_id': 'x', 'message': ''}
        self.pet.state = state
        self.pet.override = state

    def test_heading_names_the_conversation(self):
        for state, label in (('done', '已完成'), ('error', '出错了'), ('paused', '已暂停')):
            self.notify(state, '检查连接是否正常')
            heading = self.pet.notification_heading()
            self.assertIn('检查连接是否正常', heading)
            self.assertIn(label, heading)

    def test_headline_is_prepended_to_the_bubble_body(self):
        self.notify('done', '检查连接是否正常')
        text = self.pet.bubble_text()
        self.assertTrue(text.startswith('「检查连接是否正常」已完成'), text)

    def test_long_title_is_truncated(self):
        self.notify('done', '这是一个特别特别长的会话标题用来测试截断逻辑是否生效')
        heading = self.pet.notification_heading()
        self.assertLessEqual(len(heading), 30)
        self.assertIn('…', heading)

    def test_notification_forces_the_bubble_even_when_off(self):
        self.notify('done', '检查连接是否正常')
        binding = dict(self.pet.binding('done'))
        binding['bubble_mode'] = 'off'
        original = self.pet.binding

        def patched(state):
            value = dict(original(state))
            if state == 'done':
                value['bubble_mode'] = 'off'
            return value

        self.pet.binding = patched
        self.assertTrue(self.pet.bubble_visible())
        self.assertIn('检查连接是否正常', self.pet.bubble_text())

    def test_no_notification_means_no_heading(self):
        self.pet.notification = None
        self.assertEqual(self.pet.notification_heading(), '')


if __name__ == '__main__':
    unittest.main()
