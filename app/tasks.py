"""Arayüzü dondurmadan arka planda iş çalıştırmak için yardımcılar."""
import traceback

from .qt import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.signals.failed.emit(e)
        else:
            self.signals.done.emit(result)


_pool = QThreadPool.globalInstance()
_pool.setMaxThreadCount(max(4, _pool.maxThreadCount()))
_alive = set()


def run_async(fn, *args, on_done=None, on_error=None, **kwargs):
    """fn'i iş parçacığı havuzunda çalıştırır; geri çağrılar ana iş parçacığında çalışır."""
    task = _Task(fn, args, kwargs)
    sig = task.signals
    _alive.add(sig)

    def _finish(_=None):
        _alive.discard(sig)

    if on_done:
        sig.done.connect(on_done)
    if on_error:
        sig.failed.connect(on_error)
    sig.done.connect(_finish)
    sig.failed.connect(_finish)
    _pool.start(task)
    return sig
