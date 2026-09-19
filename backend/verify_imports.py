import sys
sys.path.insert(0, '/root/NekoSalesAI/backend')
from app.api.v1.routes.checkout import router as r1
from app.api.v1.routes.organizations import router as r2
print('All imports OK')
