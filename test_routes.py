from main import app

routes = [r.path for r in app.router.routes]
print("Routes:", routes)
