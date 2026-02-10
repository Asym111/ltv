#!/usr/bin/env python
"""Диагностика приложения"""
import main

print("✅ main file:", main.__file__)
print("✅ routes:", [r.path for r in main.app.routes])
print("✅ Total routes:", len(main.app.routes))
