"""离屏冒烟测试：验证状态按钮绘制与会话列表弹窗（不需要完整素材）。"""
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from types import SimpleNamespace
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

from shorekeeper_pet.renderer import PetRenderer, STATUS_COLORS
from shorekeeper_pet.pet import SessionListPopup, SessionRow

app = QApplication([])
out = os.path.join(ROOT, 'qa')
os.makedirs(out, exist_ok=True)

# 1) 状态按钮绘制
class FakeRenderer(PetRenderer):
    """只提供绘制状态钮所需的最小属性。"""
    def __init__(self):
        self.options = {'pet_size': 180, 'font_family': 'Microsoft YaHei'}
        self.pet_rect = QRectF(10, 4, 180, 180)
        self.thread_list = [{'active': True}, {'active': False}, {'active': False}]
        self.state = 'working'


img = QImage(200, 200, QImage.Format.Format_ARGB32)
img.fill(QColor(0, 0, 0, 0))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
btn = FakeRenderer()
btn.paint_status_button(p)
p.end()
img.save(os.path.join(out, 'status-button.png'))
rect = btn.status_button_rect()
assert rect.width() > 10 and rect.right() <= 200, rect
print('状态按钮 OK, 直径=%.1f' % rect.width())

# 2) 会话列表弹窗
rows = [
    {'id': 'b', 'title': '正在跑的对话', 'state': 'working', 'active': True, 'last_event': 1793123000},
    {'id': 'c', 'title': '空闲会话', 'state': 'idle', 'active': False, 'last_event': 1793122600},
    {'id': 'a', 'title': '完成的旧对话', 'state': 'done', 'active': False, 'last_event': 1793119000},
    {'id': 'd', 'title': '等你回应的对话', 'state': 'waiting', 'active': True, 'last_event': 1793123100},
]
stub = SimpleNamespace(
    thread_list=rows,
    monitor=SimpleNamespace(selected='auto'),
    picked=None,
    opened=None,
)
stub.select_thread = lambda tid: setattr(stub, 'picked', tid)
stub.follow_thread = lambda tid: setattr(stub, 'picked', tid)
stub.open_thread = lambda tid: setattr(stub, 'opened', tid)
stub.screen_area = lambda: QRect(0, 0, 1920, 1080)
stub.frameGeometry = lambda: QRect(1520, 640, 340, 438)

popup = SessionListPopup(stub)
popup.show_near()
app.processEvents()
popup.grab().save(os.path.join(out, 'session-list.png'))
count = popup.list.count()
print('弹窗 OK, 行数=%d, 高度=%d' % (count, popup.height()))
assert count == len(rows), count
assert '4' in popup.heading.text(), popup.heading.text()

# 两条路径必须分开：follow 只关注，open 才切窗口
popup.follow_thread('b')
assert stub.picked == 'b' and stub.opened is None, (stub.picked, stub.opened)
print('单击路径 -> 关注', stub.picked, '未触发打开')
popup.open_thread('a')
assert stub.opened == 'a', stub.opened
print('双击路径 -> 打开', stub.opened)

# 用真实鼠标事件验证单击/双击分流
from PySide6.QtTest import QTest
from shorekeeper_pet.pet import SessionRow
calls = []
row = SessionRow(None, rows[0], False, lambda: calls.append('follow'), lambda: calls.append('open'))
row.show()
QTest.mouseClick(row, Qt.MouseButton.LeftButton)
assert calls == [], calls
QTest.qWait(QApplication.doubleClickInterval() + 150)
assert calls == ['follow'], calls
print('单击事件 ->', calls)

calls.clear()
QTest.mouseDClick(row, Qt.MouseButton.LeftButton)
QTest.qWait(QApplication.doubleClickInterval() + 150)
assert calls == ['open'], calls
print('双击事件 ->', calls)
row.hide()

# 关注中的行必须真的画出底纹（普通 QWidget 的样式表背景不生效，曾整行无高亮）
followed_row = SessionRow(None, rows[0], True, lambda: None, lambda: None)
followed_row.resize(316, 52)
followed_row.show()
app.processEvents()
pixmap = followed_row.grab().toImage()
accent = pixmap.pixelColor(4, 26)
tint = pixmap.pixelColor(150, 26)
print('高亮 竖条=%s 底纹=%s' % (accent.name(), tint.name()))
assert accent.blue() > 180 and accent.red() < 120, accent.name()
assert tint.name() == '#e8f2fd', tint.name()
followed_row.hide()

# 右键菜单打开期间弹窗不能因失焦自动收起
popup.show()
app.processEvents()
popup.suspend_autohide(True)
popup.hide_if_unfocused()
assert popup.isVisible(), '菜单打开时弹窗被收起了'
popup.suspend_autohide(False)
print('右键期间不自动收起 OK')

print('全部通过')
