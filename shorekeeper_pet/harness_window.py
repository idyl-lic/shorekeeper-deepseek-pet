"""把 DeepSeek Harness 主窗口切到前台（Windows），找不到就启动它。

只做窗口激活，不碰 Harness 的进程内状态：失败不影响桌宠本身。
"""
from __future__ import annotations
import os, subprocess, sys

EXE_NAME = 'deepseek harness.exe'


def _win32():
    return sys.platform == 'win32'


if _win32():
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.BringWindowToTop.restype = wintypes.BOOL
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.AttachThreadInput.restype = wintypes.BOOL
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class _FLASHWINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('hwnd', wintypes.HWND),
                    ('dwFlags', wintypes.DWORD), ('uCount', wintypes.UINT),
                    ('dwTimeout', wintypes.DWORD)]

    _user32.FlashWindowEx.argtypes = [ctypes.POINTER(_FLASHWINFO)]
    _user32.FlashWindowEx.restype = wintypes.BOOL

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _SW_RESTORE, _SW_SHOW = 9, 5


def _exe_of(pid: int) -> str:
    """进程映像文件名（小写，仅文件名）。"""
    if not _win32() or not pid:
        return ''
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ''
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ''
        return os.path.basename(buf.value).lower()
    finally:
        _kernel32.CloseHandle(handle)


def windows() -> list:
    """所有可见的 Harness 顶层窗口：[(hwnd, title, class), ...]。"""
    if not _win32():
        return []
    found = []

    def collect(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _exe_of(pid.value) != EXE_NAME:
            return True
        title = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, title, 512)
        if not title.value:
            return True
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        found.append((hwnd, title.value, cls.value))
        return True

    _user32.EnumWindows(_EnumWindowsProc(collect), 0)
    return found


def _force_foreground(hwnd) -> bool:
    """Windows 前台锁会拒绝 SetForegroundWindow，按强度依次降级尝试。"""
    if _user32.SetForegroundWindow(hwnd) and _user32.GetForegroundWindow() == hwnd:
        return True
    # 1) SwitchToThisWindow：Alt+Tab 同款路径，多数前台锁场景可用。
    try:
        _user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
        _user32.SwitchToThisWindow.restype = None
        _user32.SwitchToThisWindow(hwnd, True)
        if _user32.GetForegroundWindow() == hwnd:
            return True
    except AttributeError:
        pass
    # 2) 附加到当前前台线程，绕过前台锁。
    foreground = _user32.GetForegroundWindow()
    current_thread = _kernel32.GetCurrentThreadId()
    attached = False
    try:
        if foreground:
            source_thread = _user32.GetWindowThreadProcessId(foreground, None)
            attached = bool(_user32.AttachThreadInput(source_thread, current_thread, True))
        _user32.ShowWindow(hwnd, _SW_RESTORE)
        _user32.BringWindowToTop(hwnd)
        if _user32.SetForegroundWindow(hwnd) and _user32.GetForegroundWindow() == hwnd:
            return True
    finally:
        if attached:
            source_thread = _user32.GetWindowThreadProcessId(foreground, None)
            _user32.AttachThreadInput(source_thread, current_thread, False)
    # 3) 模拟一次 ALT 按键，解除前台激活锁后再试。
    try:
        _user32.keybd_event(0x12, 0, 0, 0)
        _user32.keybd_event(0x12, 0, 2, 0)
        _user32.ShowWindow(hwnd, _SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
    except AttributeError:
        pass
    return _user32.GetForegroundWindow() == hwnd


def bring_to_front() -> bool:
    """把 Harness 主窗口切到前台。返回是否成功找到并激活窗口。"""
    if not _win32():
        return False
    candidates = windows()
    if not candidates:
        return False
    # 优先 Chromium 主窗口，其次任意 Harness 窗口。
    candidates.sort(key=lambda item: 0 if item[2].startswith('Chrome_WidgetWin') else 1)
    hwnd = candidates[0][0]
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, _SW_RESTORE)
    else:
        _user32.ShowWindow(hwnd, _SW_SHOW)
    return _force_foreground(hwnd)


def _from_registry() -> str:
    """App Paths 与卸载项里记录的安装位置，覆盖非标准安装目录。"""
    try:
        import winreg
    except ImportError:
        return ''
    checks = [
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\DeepSeek Harness.exe', ''),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\DeepSeek Harness.exe', ''),
    ]
    for root, key, value_name in checks:
        try:
            with winreg.OpenKey(root, key) as handle:
                path = winreg.QueryValue(handle, value_name)
                if path and os.path.isfile(path):
                    return path
        except OSError:
            continue
    roots = [
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
    ]
    for root, key in roots:
        try:
            with winreg.OpenKey(root, key) as parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        name = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, name) as entry:
                            label = str(winreg.QueryValueEx(entry, 'DisplayName')[0])
                            if 'deepseek harness' not in label.lower():
                                continue
                            for field in ('InstallLocation', 'DisplayIcon'):
                                try:
                                    raw = str(winreg.QueryValueEx(entry, field)[0]).strip('"').split(',')[0]
                                except OSError:
                                    continue
                                candidate = raw if raw.lower().endswith('.exe') else os.path.join(raw, 'DeepSeek Harness.exe')
                                if candidate and os.path.isfile(candidate):
                                    return candidate
                    except OSError:
                        continue
        except OSError:
            continue
    return ''


def _from_paths() -> str:
    """常见安装根的兜底扫描。"""
    roots = [os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles', ''),
             os.environ.get('ProgramFiles(x86)', ''), os.environ.get('ProgramW6432', '')]
    seen = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        for folder in ('Programs/DeepSeek Harness', 'DeepSeek Harness', 'DeepSeekHarness'):
            candidate = os.path.join(root, *folder.split('/'), 'DeepSeek Harness.exe')
            if os.path.isfile(candidate):
                return candidate
    return ''


def locate_executable(explicit: str = '') -> str:
    """找到 DeepSeek Harness.exe 的完整路径。"""
    if explicit and os.path.isfile(explicit):
        return explicit
    for finder in (_from_registry, _from_paths):
        try:
            found = finder()
        except Exception:
            found = ''
        if found:
            return found
    try:
        from .bridge import discover_deepseek
        return discover_deepseek('') or ''
    except Exception:
        return ''


def flash() -> bool:
    """前台激活被系统拒绝时，至少让任务栏按钮闪一下。"""
    if not _win32():
        return False
    candidates = windows()
    if not candidates:
        return False
    info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), candidates[0][0], 3 | 12, 0, 0)  # FLASHW_ALL | FLASHW_TIMERNOFG
    try:
        return bool(_user32.FlashWindowEx(ctypes.byref(info)))
    except AttributeError:
        return False


def open_harness(executable: str = '') -> str:
    """返回 focused / launched / denied / missing。窗口在就只前置，绝不起新进程。"""
    if windows():
        if bring_to_front():
            return 'focused'
        flash()
        return 'denied'
    target = locate_executable(executable)
    if not target or not os.path.isfile(target):
        return 'missing'
    try:
        subprocess.Popen([target], close_fds=True)
        return 'launched'
    except OSError:
        return 'missing'
