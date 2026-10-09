from pydantic import BaseModel, ConfigDict


class DistrictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name_th: str
    province_name_th: str
