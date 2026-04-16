"""Enterprise invitation service.

Imported by OSS as:

    from amprealize.enterprise.multi_tenant.invitation_service import InvitationService
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Optional

from amprealize.multi_tenant.contracts import (
    CreateInvitationRequest,
    Invitation,
    InvitationChannel,
    InvitationEvent,
    InvitationListResponse,
    InvitationStatus,
    InvitationWithOrg,
    MemberRole,
    OrgMembership,
)
from amprealize.storage.postgres_pool import PostgresPool
from amprealize.utils.dsn import resolve_postgres_dsn


class InvitationService:
    """Manages org membership invitations."""

    def __init__(
        self,
        *,
        pool: Optional[PostgresPool] = None,
        dsn: Optional[str] = None,
        base_url: str = "https://amprealize.dev",
        **_: Any,
    ) -> None:
        self._pool = pool or PostgresPool(
            dsn or resolve_postgres_dsn(
                service="ORG",
                explicit_dsn=None,
                env_var="AMPREALIZE_ORG_PG_DSN",
                default_dsn="postgresql://localhost:5432/amprealize",
            )
        )
        self._base_url = base_url.rstrip("/")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(48)

    def _get_accept_url(self, token: str) -> str:
        return f"{self._base_url}/invitations/{token}/accept"

    @staticmethod
    def _invitation_from_row(row: Any) -> Invitation:
        invitation_id, org_id, email, role, status, token, channel, invited_by, expires_at, accepted_at, accepted_by, message, metadata, created_at, updated_at = row[:15]
        return Invitation(
            id=invitation_id,
            org_id=org_id,
            email=email,
            role=MemberRole(role),
            status=InvitationStatus(status),
            token=token,
            channel=InvitationChannel(channel),
            invited_by=invited_by,
            expires_at=expires_at,
            accepted_at=accepted_at,
            accepted_by=accepted_by,
            message=message,
            metadata=metadata or {},
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _event_from_row(row: Any) -> InvitationEvent:
        event_id, invitation_id, event_type, actor_id, metadata, created_at = row[:6]
        return InvitationEvent(
            id=event_id,
            invitation_id=invitation_id,
            event_type=event_type,
            actor_id=actor_id,
            metadata=metadata or {},
            created_at=created_at,
        )

    def create_invitation(
        self,
        *,
        org_id: str,
        request: CreateInvitationRequest,
        invited_by: str,
        send: bool = True,
    ) -> Invitation:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM org_memberships WHERE org_id = %(org_id)s AND user_id IN (SELECT user_id FROM users WHERE email = %(email)s)",
                {"org_id": org_id, "email": request.email},
            )
            if cursor.fetchone():
                raise ValueError("User is already a member")

            cursor.execute(
                "SELECT invitation_id FROM invitations WHERE org_id = %(org_id)s AND email = %(email)s AND status = 'pending'",
                {"org_id": org_id, "email": request.email},
            )
            if cursor.fetchone():
                raise ValueError("Pending invitation already exists")

            invitation = Invitation(
                org_id=org_id,
                email=request.email,
                role=request.role,
                status=InvitationStatus.PENDING,
                token=self._generate_token(),
                channel=request.channel,
                invited_by=invited_by,
                expires_at=self._now() + timedelta(days=request.expires_in_days),
                accepted_at=None,
                accepted_by=None,
                message=request.message,
                metadata=request.metadata,
                created_at=self._now(),
                updated_at=self._now(),
            )

            cursor.execute(
                "INSERT INTO invitations (invitation_id, org_id, email, role, status, token, channel, invited_by, expires_at, accepted_at, accepted_by, message, metadata, created_at, updated_at) "
                "VALUES (%(invitation_id)s, %(org_id)s, %(email)s, %(role)s, %(status)s, %(token)s, %(channel)s, %(invited_by)s, %(expires_at)s, %(accepted_at)s, %(accepted_by)s, %(message)s, %(metadata)s, %(created_at)s, %(updated_at)s)",
                {
                    "invitation_id": invitation.id,
                    "org_id": invitation.org_id,
                    "email": invitation.email,
                    "role": invitation.role.value,
                    "status": invitation.status.value,
                    "token": invitation.token,
                    "channel": invitation.channel.value,
                    "invited_by": invitation.invited_by,
                    "expires_at": invitation.expires_at,
                    "accepted_at": invitation.accepted_at,
                    "accepted_by": invitation.accepted_by,
                    "message": invitation.message,
                    "metadata": invitation.metadata,
                    "created_at": invitation.created_at,
                    "updated_at": invitation.updated_at,
                },
            )

            cursor.execute(
                "INSERT INTO invitation_events (invitation_event_id, invitation_id, event_type, actor_id, metadata, created_at) "
                "VALUES (%(event_id)s, %(invitation_id)s, %(event_type)s, %(actor_id)s, %(metadata)s, %(created_at)s)",
                {
                    "event_id": f"iev-{secrets.token_hex(6)}",
                    "invitation_id": invitation.id,
                    "event_type": "created",
                    "actor_id": invited_by,
                    "metadata": {"send": send},
                    "created_at": self._now(),
                },
            )
            return invitation

    def get_invitation(self, invitation_id: str) -> Invitation | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invitation_id, org_id, email, role, status, token, channel, invited_by, expires_at, accepted_at, accepted_by, message, metadata, created_at, updated_at "
                "FROM invitations WHERE invitation_id = %(invitation_id)s",
                {"invitation_id": invitation_id},
            )
            row = cursor.fetchone()
            return self._invitation_from_row(row) if row else None

    def get_invitation_by_token(self, token: str) -> InvitationWithOrg | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invitation_id, org_id, email, role, status, token, channel, invited_by, expires_at, accepted_at, accepted_by, message, metadata, created_at, updated_at, org_name, org_slug, inviter_name "
                "FROM invitation_lookup WHERE token = %(token)s",
                {"token": token},
            )
            row = cursor.fetchone()
            if row is None:
                return None
            invitation = self._invitation_from_row(row[:15])
            return InvitationWithOrg(
                invitation=invitation,
                org_name=row[15],
                org_slug=row[16],
                inviter_name=row[17],
            )

    def list_org_invitations(
        self,
        *,
        org_id: str,
        status: InvitationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> InvitationListResponse:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            params = {"org_id": org_id, "status": status.value if status else None, "limit": limit, "offset": offset}
            cursor.execute("SELECT COUNT(*) FROM invitations WHERE org_id = %(org_id)s", params)
            total = (cursor.fetchone() or (0,))[0]
            cursor.execute(
                "SELECT COUNT(*) FROM invitations WHERE org_id = %(org_id)s AND status = 'pending'",
                params,
            )
            pending_count = (cursor.fetchone() or (0,))[0]
            cursor.execute(
                "SELECT invitation_id, org_id, email, role, status, token, channel, invited_by, expires_at, accepted_at, accepted_by, message, metadata, created_at, updated_at "
                "FROM invitations WHERE org_id = %(org_id)s ORDER BY created_at DESC LIMIT %(limit)s OFFSET %(offset)s",
                params,
            )
            rows = cursor.fetchall() or []
            return InvitationListResponse(
                invitations=[self._invitation_from_row(row) for row in rows],
                total=total,
                pending_count=pending_count,
                page_info=None,
            )

    def accept_invitation(self, *, token: str, user_id: str) -> OrgMembership:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invitation_id, org_id, email, role, status, expires_at FROM invitations WHERE token = %(token)s",
                {"token": token},
            )
            invitation_row = cursor.fetchone()
            if invitation_row is None:
                raise ValueError("Invalid invitation token")

            invitation_id, org_id, invited_email, role, status, expires_at = invitation_row
            if status != InvitationStatus.PENDING.value:
                raise ValueError("Invitation is not pending")
            if expires_at < self._now():
                cursor.execute(
                    "UPDATE invitations SET status = 'expired', updated_at = %(updated_at)s WHERE invitation_id = %(invitation_id)s",
                    {"invitation_id": invitation_id, "updated_at": self._now()},
                )
                raise ValueError("Invitation has expired")

            cursor.execute(
                "SELECT email FROM users WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )
            user_row = cursor.fetchone()
            user_email = user_row[0] if user_row else None
            if user_email != invited_email:
                raise ValueError("User email does not match invitation email")

            cursor.execute(
                "SELECT 1 FROM org_memberships WHERE org_id = %(org_id)s AND user_id = %(user_id)s",
                {"org_id": org_id, "user_id": user_id},
            )
            if cursor.fetchone():
                raise ValueError("User is already a member")

            membership = OrgMembership(
                org_id=org_id,
                user_id=user_id,
                role=MemberRole(role),
                invited_by=None,
                invited_at=None,
                created_at=self._now(),
                updated_at=self._now(),
            )
            cursor.execute(
                "INSERT INTO org_memberships (membership_id, org_id, user_id, role, invited_by, invited_at, created_at, updated_at) "
                "VALUES (%(membership_id)s, %(org_id)s, %(user_id)s, %(role)s, %(invited_by)s, %(invited_at)s, %(created_at)s, %(updated_at)s)",
                {
                    "membership_id": membership.id,
                    "org_id": membership.org_id,
                    "user_id": membership.user_id,
                    "role": membership.role.value,
                    "invited_by": membership.invited_by,
                    "invited_at": membership.invited_at,
                    "created_at": membership.created_at,
                    "updated_at": membership.updated_at,
                },
            )
            cursor.execute(
                "UPDATE invitations SET status = 'accepted', accepted_at = %(accepted_at)s, accepted_by = %(accepted_by)s, updated_at = %(updated_at)s WHERE invitation_id = %(invitation_id)s",
                {
                    "invitation_id": invitation_id,
                    "accepted_at": self._now(),
                    "accepted_by": user_id,
                    "updated_at": self._now(),
                },
            )
            return membership

    def revoke_invitation(self, *, invitation_id: str, revoked_by: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE invitations SET status = 'revoked', updated_at = %(updated_at)s WHERE invitation_id = %(invitation_id)s RETURNING invitation_id",
                {"invitation_id": invitation_id, "updated_at": self._now(), "revoked_by": revoked_by},
            )
            return cursor.fetchone() is not None

    def expire_invitations(self) -> int:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE invitations SET status = 'expired', updated_at = %(updated_at)s WHERE status = 'pending' AND expires_at < %(now)s RETURNING invitation_id",
                {"updated_at": self._now(), "now": self._now()},
            )
            rows = cursor.fetchall() or []
            return len(rows)

    def get_invitation_link(self, invitation_id: str) -> str | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT token FROM invitations WHERE invitation_id = %(invitation_id)s",
                {"invitation_id": invitation_id},
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._get_accept_url(row[0])

    def get_invitation_events(self, invitation_id: str) -> list[InvitationEvent]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT invitation_event_id, invitation_id, event_type, actor_id, metadata, created_at "
                "FROM invitation_events WHERE invitation_id = %(invitation_id)s ORDER BY created_at ASC",
                {"invitation_id": invitation_id},
            )
            return [self._event_from_row(row) for row in cursor.fetchall() or []]

    async def send_invitation(self, **kwargs: Any) -> dict[str, Any]:
        invitation = self.create_invitation(send=True, **kwargs)
        return invitation.model_dump()

    async def list_invitations(self, org_id: str) -> list[dict[str, Any]]:
        return [inv.model_dump() for inv in self.list_org_invitations(org_id=org_id).invitations]
