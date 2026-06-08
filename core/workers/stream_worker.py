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

    @QtCore.pyqtSlot()
    def run(self):
        try:
            for tok in self.client.stream_chat(
                self.messages,
                **self.kwargs
            ):
                if tok:
                    self.token.emit(str(tok))

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()