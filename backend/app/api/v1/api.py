from fastapi import APIRouter

from app.api.v1.routes.ai import router as ai_router
from app.api.v1.routes.contacts import router as contact_router
from app.api.v1.routes.customers import router as customer_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.leads import router as lead_router
from app.api.v1.routes.organizations import router as organization_router
from app.api.v1.routes.sales import router as sales_router
from app.api.v1.routes.sales_admin import router as sales_desk_router
from app.api.v1.routes.tasks import router as task_router
from app.auth.router import router as auth_router

# Versioned prefix, matching the endpoint paths documented in README.md.
api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(organization_router)
api_router.include_router(customer_router)
api_router.include_router(contact_router)
api_router.include_router(lead_router)
api_router.include_router(sales_router)
api_router.include_router(sales_desk_router)
api_router.include_router(ai_router)
api_router.include_router(task_router)
api_router.include_router(dashboard_router)
api_router.include_router(health_router)
