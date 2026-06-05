from fastapi import HTTPException, status


class UnauthorizedGoogleAccess(HTTPException):
    def __init__(
        self, detail: str = "Not authorized with Google. Please re-authenticate."
    ):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class GoogleAPICallError(HTTPException):
    def __init__(
        self,
        detail: str = "Failed to call Google API.",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ):
        super().__init__(status_code=status_code, detail=detail)


class ItemNotFound(HTTPException):
    def __init__(self, detail: str = "Item not found."):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
