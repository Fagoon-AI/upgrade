class AppError(Exception):
    """
    Custom exception class for application-specific errors that need
    to be returned as HTTP responses.
    """
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.is_operational = True