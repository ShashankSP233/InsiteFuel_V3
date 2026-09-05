from sqlalchemy.orm import Session

from backend.models.audit_log import AuditLog


class AuditService:

    @staticmethod
    def log(
        db: Session,
        *,
        user_id: int | None,
        action: str,
        entity: str,
        entity_id: int | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        reason: str | None = None,
        details: str | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            reason=reason,
            details=details,
        )

        db.add(audit)
        db.flush()

        return audit