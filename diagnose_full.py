#!/usr/bin/env python
"""Диагностика всех маршрутов"""
import main

print("=" * 60)
print("ДИАГНОСТИКА МАРШРУТОВ")
print("=" * 60)
print()

routes = [r.path for r in main.app.routes]
print(f"✅ Всего маршрутов: {len(routes)}")
print()

# Группировка маршрутов
api_routes = [r for r in routes if r.startswith('/api')]
admin_routes = [r for r in routes if r.startswith('/admin')]
static_routes = [r for r in routes if r in ['/docs', '/openapi.json', '/redoc', '/docs/oauth2-redirect']]
other_routes = [r for r in routes if r not in api_routes + admin_routes + static_routes]

print("📊 API маршруты:")
for r in sorted(api_routes):
    print(f"  - {r}")

print()
print("💼 Admin UI маршруты:")
for r in sorted(admin_routes):
    print(f"  - {r}")

print()
print("📚 Документация маршруты:")
for r in sorted(static_routes):
    print(f"  - {r}")

print()
print("🔧 Другие маршруты:")
for r in sorted(other_routes):
    print(f"  - {r}")

print()
print("=" * 60)
print("✨ Приложение готово к работе!")
print("=" * 60)
