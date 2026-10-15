from iris.ui.desktop.backend import IrisWorker


def test_stop_before_start_is_safe():
    worker = IrisWorker()
    worker.stop()
    assert worker._stop_event.is_set()


def test_stop_sets_event_without_forcing_loop_stop():
    class LoopStub:
        def __init__(self):
            self.stop_requested = False

        def is_running(self):
            return True

        def call_soon_threadsafe(self, callback):
            self.stop_requested = True

    worker = IrisWorker()
    loop = LoopStub()
    worker._loop = loop

    worker.stop()

    assert worker._stop_event.is_set()
    assert not loop.stop_requested
