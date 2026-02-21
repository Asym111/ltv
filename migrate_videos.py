"""
migrate_videos.py
Запустить из корня проекта: python migrate_videos.py
Создаёт таблицу video_resources если её нет.
"""
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(__file__))

def migrate():
    from app.core.database import engine, Base
    import app.models.video_model  # регистрируем модель

    Base.metadata.create_all(bind=engine)
    print("✅ Таблица video_resources создана (или уже существует).")

if __name__ == "__main__":
    migrate()