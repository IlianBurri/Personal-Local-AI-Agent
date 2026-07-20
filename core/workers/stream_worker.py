"""QThread worker for streaming LLM responses with stop support."""

from PyQt6 import QtCore


class StreamWorker(QtCore.QObject):
    token = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, client, messages, kwargs=None):
        super().__init__()
        self.client = client
        self.messages = messages
        self.kwargs = kwargs or {}
        self._stopped = False

    def stop(self):
        """Signal the worker to stop processing as soon as possible."""
        self._stopped = True

    @QtCore.pyqtSlot()
    def run(self):
        try:
            for tok in self.client.stream_chat(
                self.messages, **self.kwargs
            ):
                if self._stopped:
                    break
                if tok:
                    self.token.emit(str(tok))
        except Exception as e:
            # Don't report errors caused by user stopping
            if not self._stopped:
                self.error.emit(str(e))
        finally:
            self.finished.emit()
