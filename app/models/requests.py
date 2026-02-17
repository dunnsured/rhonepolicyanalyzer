from pydantic import BaseModel


class ClientInfo(BaseModel):
    client_name: str = ""
    industry: str = ""
    annual_revenue: str = ""
    employee_count: str = ""
    is_msp: bool = False
    notes: str = ""
