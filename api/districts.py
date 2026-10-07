from fastapi import APIRouter

from core.db import SessionLocal
from schemas.district import DistrictResponse
from services.districts import list_districts

router = APIRouter()


@router.get("/districts", response_model=list[DistrictResponse])
async def get_districts() -> list[DistrictResponse]:
    async with SessionLocal() as session:
        districts = await list_districts(session)
    return [DistrictResponse.model_validate(district) for district in districts]
