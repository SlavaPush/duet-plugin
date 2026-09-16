class DuetError(Exception):
    """An actionable failure; the message is shown to the user."""


class LimitReached(DuetError):
    """The per-run call limit for a stage is exhausted."""


class ProcessLimitError(DuetError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result
