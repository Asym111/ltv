# scripts/make_branch.py
"""
Превращает существующий отдельный аккаунт (tenant) в филиал другой сети.

Что делает:
 1. Ставит branch.parent_tenant_id = root.id
 2. Переносит клиентов филиала на корень сети (общая база):
    - если клиента с таким phone_hash на корне нет — просто меняем tenant_id
    - если есть дубль — сливаем: транзакции и бонусы переезжают на клиента корня,
      дубль удаляется, баланс пересчитывается
 3. Транзакции НЕ трогаем — они остаются помечены филиалом (точка продажи)

Запуск (из корня проекта):
    python scripts/make_branch.py --branch 4 --root 3            # dry-run (по умолчанию)
    python scripts/make_branch.py --branch 4 --root 3 --apply    # применить

ВАЖНО: сделайте бэкап БД перед --apply.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from app.core.database import SessionLocal  # noqa: E402
from app.models.auth import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.models.bonus_grant import BonusGrant  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Сделать тенант филиалом сети (с переносом клиентов на корень)")
    ap.add_argument("--branch", type=int, required=True, help="id тенанта, который станет филиалом")
    ap.add_argument("--root", type=int, required=True, help="id головного тенанта (корня сети)")
    ap.add_argument("--apply", action="store_true", help="применить изменения (без флага — dry-run)")
    args = ap.parse_args()

    if args.branch == args.root:
        print("branch и root не могут совпадать")
        return 1

    db = SessionLocal()
    try:
        branch = db.get(Tenant, args.branch)
        root = db.get(Tenant, args.root)
        if not branch or not root:
            print("Тенант не найден")
            return 1
        if root.parent_tenant_id is not None:
            print(f"Корень #{root.id} сам является филиалом — нельзя")
            return 1
        if branch.parent_tenant_id not in (None, args.root):
            print(f"Тенант #{branch.id} уже филиал сети #{branch.parent_tenant_id}")
            return 1

        print(f"Сеть: «{root.name}» (#{root.id})  ←  филиал: «{branch.name}» (#{branch.id})")

        branch_users = db.query(User).filter(User.tenant_id == branch.id).all()
        root_hashes = {
            u.phone_hash: u.id
            for u in db.query(User).filter(User.tenant_id == root.id).all()
            if u.phone_hash
        }

        moved, merged = 0, 0
        for u in branch_users:
            dup_id = root_hashes.get(u.phone_hash) if u.phone_hash else None
            if dup_id:
                merged += 1
                print(f"  [merge] клиент #{u.id} → дубль на корне #{dup_id} (переносим транзакции/бонусы)")
                if args.apply:
                    db.query(Transaction).filter(Transaction.user_id == u.id).update(
                        {"user_id": dup_id}, synchronize_session=False
                    )
                    db.query(BonusGrant).filter(BonusGrant.user_id == u.id).update(
                        {"user_id": dup_id}, synchronize_session=False
                    )
                    db.delete(u)
            else:
                moved += 1
                if args.apply:
                    u.tenant_id = root.id

        print(f"Клиентов перенесено: {moved}, слито дублей: {merged}")

        if args.apply:
            branch.parent_tenant_id = root.id
            db.commit()

            # Пересчёт кэша баланса у слитых клиентов
            from app.services.loyalty_engine import get_balances
            for uid in set(root_hashes.values()):
                try:
                    b = get_balances(db, user_id=uid)
                    db.query(User).filter(User.id == uid).update({"bonus_balance": int(b["total"])})
                except Exception:
                    pass
            db.commit()
            print("✓ Применено. Не забудьте: сотрудники филиала входят как раньше, "
                  "владелец сети видит филиал в переключателе.")
        else:
            print("DRY-RUN: ничего не изменено. Добавьте --apply чтобы применить.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
