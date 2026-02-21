from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/patch")

class KernelVerifyReply(BaseModel):
    status: str
    source: str

@router.get("/verify", response_model=KernelVerifyReply)
async def kernel_verify():
    return KernelVerifyReply(status="ok", source="chat")
