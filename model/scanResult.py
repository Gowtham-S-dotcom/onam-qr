from pydantic import BaseModel


class ScanResult(BaseModel):
    qr_code: str
