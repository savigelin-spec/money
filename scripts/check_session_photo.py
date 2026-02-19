"""
Скрипт для проверки статуса фото в сессии модерации
"""
import asyncio
import sys
from pathlib import Path

# Настройка кодировки для Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import get_session
from database.queries import get_moderation_session_by_id, get_application_by_id
from sqlalchemy import select
from database.models import ModerationSession


async def check_session_photo(application_id: int = None, session_id: int = None):
    """Проверить статус фото в сессии модерации"""
    
    async for db_session in get_session():
        try:
            if application_id:
                # Ищем по application_id
                application = await get_application_by_id(db_session, application_id)
                if not application:
                    print(f"❌ Заявка #{application_id} не найдена")
                    return
                
                # Ищем сессию по application_id
                from sqlalchemy import select
                result = await db_session.execute(
                    select(ModerationSession).where(
                        ModerationSession.application_id == application_id
                    )
                )
                sessions = result.scalars().all()
                
                if not sessions:
                    print(f"❌ Сессия модерации для заявки #{application_id} не найдена")
                    return
                
                moderation_session = sessions[0]
                
            elif session_id:
                moderation_session = await get_moderation_session_by_id(db_session, session_id)
                if not moderation_session:
                    print(f"❌ Сессия #{session_id} не найдена")
                    return
                application_id = moderation_session.application_id
            else:
                print("❌ Укажите application_id или session_id")
                return
            
            await db_session.commit()
            
            print(f"\n📋 Информация о сессии модерации:")
            print(f"   ID сессии: {moderation_session.id}")
            print(f"   Заявка: #{application_id}")
            print(f"   Пользователь: {moderation_session.user_id}")
            print(f"   Модератор: {moderation_session.moderator_id}")
            print(f"   Статус: {moderation_session.status}")
            print(f"   Создана: {moderation_session.created_at}")
            
            print(f"\n📸 Статус фото:")
            if moderation_session.user_photo_file_id:
                print(f"   ✅ Фото пользователя: есть (file_id: {moderation_session.user_photo_file_id[:30]}...)")
            else:
                print(f"   ❌ Фото пользователя: отсутствует")
            
            if moderation_session.moderator_photo_file_id:
                print(f"   ✅ Фото модератора: есть (file_id: {moderation_session.moderator_photo_file_id[:30]}...)")
                print(f"\n⚠️  Фото модератора сохранено в БД, но могло не дойти до пользователя.")
                print(f"   Проверьте логи бота на наличие ошибок отправки.")
            else:
                print(f"   ❌ Фото модератора: отсутствует")
                print(f"\n⚠️  Модератор не отправил фото перед подтверждением заявки!")
                print(f"   Фото должно быть отправлено ДО подтверждения заявки.")
            
            # Проверяем статус заявки
            application = await get_application_by_id(db_session, application_id)
            if application:
                print(f"\n📝 Статус заявки: {application.status}")
                if application.status == "completed" and not moderation_session.moderator_photo_file_id:
                    print(f"   ⚠️  Заявка подтверждена без отправки фото модератора!")
            
        except Exception as e:
            await db_session.rollback()
            print(f"❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python scripts/check_session_photo.py --application <application_id>")
        print("  python scripts/check_session_photo.py --session <session_id>")
        print("\nПримеры:")
        print("  python scripts/check_session_photo.py --application 2")
        print("  python scripts/check_session_photo.py --session 1")
        sys.exit(1)
    
    try:
        if sys.argv[1] == "--application" and len(sys.argv) == 3:
            application_id = int(sys.argv[2])
            asyncio.run(check_session_photo(application_id=application_id))
        elif sys.argv[1] == "--session" and len(sys.argv) == 3:
            session_id = int(sys.argv[2])
            asyncio.run(check_session_photo(session_id=session_id))
        else:
            print("❌ Неверные аргументы")
            print("Используйте --application <id> или --session <id>")
            sys.exit(1)
    except ValueError:
        print("❌ ID должен быть целым числом")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
