from fastapi import APIRouter

from app.api.v1.routes.checkout import router as checkout_router
from app.api.v1.routes.contacts import router as contact_router
from app.api.v1.routes.customers import router as customer_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.leads import router as lead_router
from app.api.v1.routes.messaging import router as messaging_router
from app.api.v1.routes.organizations import router as organization_router
from app.api.v1.routes.pricing import router as pricing_router
from app.api.v1.routes.product_config import router as product_config_router
from app.api.v1.routes.sales import router as sales_router
from app.api.v1.routes.sales_admin import router as sales_desk_router
from app.api.v1.routes.widget import router as widget_router
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
api_router.include_router(pricing_router)
api_router.include_router(product_config_router)
api_router.include_router(checkout_router)
api_router.include_router(widget_router)
api_router.include_router(messaging_router)
api_router.include_router(health_router)
