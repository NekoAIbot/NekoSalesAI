from fastapi import APIRouter

router = APIRouter(
    prefix="/leads",
    tags=["Leads"],
)


@router.get("/")
def list_leads():
    return {"message": "List Leads"}


@router.post("/")
def create_lead():
    return {"message": "Create Lead"}


@router.get("/{lead_id}")
def get_lead(lead_id: int):
    return {"id": lead_id}


@router.put("/{lead_id}")
def update_lead(lead_id: int):
    return {"message": "Updated", "id": lead_id}


@router.delete("/{lead_id}")
def delete_lead(lead_id: int):
    return {"message": "Deleted", "id": lead_id}
