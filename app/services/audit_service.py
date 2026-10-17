from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogCreate


class AuditService:
    """Service handling audit trail logging for security and compliance."""

    @staticmethod
    def log_event(
        db: Session,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        actor: str = "system",
        details: Optional[str] = None,
        commit: bool = True,
    ) -> AuditLog:
        audit_entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            actor=actor,
            details=details,
        )
        db.add(audit_entry)
        if commit:
            db.commit()
            db.refresh(audit_entry)
        else:
            db.flush()
        return audit_entry

    @staticmethod
    def list_logs(db: Session, skip: int = 0, limit: int = 50):
        stmt = select(AuditLog).offset(skip).limit(limit).order_by(AuditLog.id.desc())
        return list(db.scalars(stmt).all())
