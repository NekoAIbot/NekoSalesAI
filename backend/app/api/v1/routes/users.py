from fastapi import APIRouter

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.get("/")
def list_users():
    return {"message": "List Users"}


@router.post("/")
def create_user():
    return {"message": "Create User"}


@router.get("/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}


@router.put("/{user_id}")
def update_user(user_id: int):
    return {"message": "Updated", "id": user_id}


@router.delete("/{user_id}")
def delete_user(user_id: int):
    return {"message": "Deleted", "id": user_id}
