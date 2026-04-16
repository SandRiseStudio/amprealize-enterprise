"""Enterprise organization service.

Imported by OSS as:

    from amprealize.enterprise.multi_tenant.organization_service import OrganizationService
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Optional
import uuid

from amprealize.multi_tenant.contracts import (
    BillingContext,
    MemberRole,
    OrgPlan,
    Project,
    ProjectCollaborator,
    ProjectMembership,
    ProjectRole,
    ProjectVisibility,
    Subscription,
    SubscriptionStatus,
    UpdateProjectRequest,
    UsageRecord,
)
from amprealize.storage.postgres_pool import PostgresPool
from amprealize.utils.dsn import resolve_postgres_dsn


class OrganizationService:
    """Multi-tenant project, membership, and billing operations.

    This implementation intentionally focuses on the synchronous CRUD surface
    exercised by the unit tests and by the API route wiring.
    """

    def __init__(
        self,
        *,
        pool: Optional[PostgresPool] = None,
        dsn: Optional[str] = None,
        board_service: Any | None = None,
        **_: Any,
    ) -> None:
        self._board_service = board_service
        self._pool = pool or PostgresPool(
            dsn or resolve_postgres_dsn(
                service="ORG",
                explicit_dsn=None,
                env_var="AMPREALIZE_ORG_PG_DSN",
                default_dsn="postgresql://localhost:5432/amprealize",
            )
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _project_from_row(row: Any) -> Project:
        if len(row) >= 11:
            project_id, org_id, owner_id, name, slug, description, visibility, settings, _archived_at, created_at, updated_at = row[:11]
        else:
            project_id, org_id, owner_id, name, slug, description, visibility, settings, created_at, updated_at = row[:10]
        return Project(
            id=project_id,
            org_id=org_id,
            owner_id=owner_id,
            name=name,
            slug=slug,
            description=description,
            visibility=ProjectVisibility(visibility),
            settings=settings or {},
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _project_membership_from_row(row: Any) -> ProjectMembership:
        membership_id, project_id, user_id, role, created_at, updated_at = row[:6]
        return ProjectMembership(
            id=membership_id,
            project_id=project_id,
            user_id=user_id,
            role=ProjectRole(role),
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _collaborator_from_row(row: Any) -> ProjectCollaborator:
        collaborator_id, project_id, user_id, role, invited_by, invited_at, accepted_at, created_at, updated_at = row[:9]
        return ProjectCollaborator(
            id=collaborator_id,
            project_id=project_id,
            user_id=user_id,
            role=ProjectRole(role),
            invited_by=invited_by,
            invited_at=invited_at,
            accepted_at=accepted_at,
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _subscription_from_row(row: Any) -> Subscription:
        subscription_id, user_id, stripe_subscription_id, stripe_customer_id, plan, status, current_period_start, current_period_end, cancel_at, created_at, updated_at = row[:11]
        return Subscription(
            id=subscription_id,
            user_id=user_id,
            org_id=None,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            plan=OrgPlan(plan),
            status=SubscriptionStatus(status),
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at=cancel_at,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_project(self, project_id: str, org_id: str | None = None) -> Project | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            query = (
                "SELECT project_id, org_id, owner_id, name, slug, description, visibility, settings, "
                "archived_at, created_at, updated_at "
                "FROM projects WHERE project_id = %(project_id)s AND archived_at IS NULL"
            )
            params: dict[str, Any] = {"project_id": project_id}
            if org_id is not None:
                query += " AND org_id = %(org_id)s"
                params["org_id"] = org_id
            cursor.execute(query, params)
            row = cursor.fetchone()
            return self._project_from_row(row) if row else None

    def get_project_by_slug(self, org_id: str, slug: str) -> Project | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT project_id, org_id, owner_id, name, slug, description, visibility, settings, archived_at, created_at, updated_at "
                "FROM projects WHERE org_id = %(org_id)s AND slug = %(slug)s AND archived_at IS NULL",
                {"org_id": org_id, "slug": slug},
            )
            row = cursor.fetchone()
            return self._project_from_row(row) if row else None

    def update_project(self, project_id: str, request: UpdateProjectRequest) -> Project | None:
        changes = request.model_dump(exclude_none=True)
        if not changes:
            return self.get_project(project_id)

        with self._pool.connection() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join(f"{field} = %({field})s" for field in changes)
            params = {**changes, "project_id": project_id, "updated_at": self._now()}
            cursor.execute(
                f"UPDATE projects SET {set_clause}, updated_at = %(updated_at)s WHERE project_id = %(project_id)s AND archived_at IS NULL",
                params,
            )
            if getattr(cursor, "rowcount", 0) <= 0:
                return None
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE agents SET project_id = NULL WHERE project_id = %(project_id)s",
                {"project_id": project_id},
            )
            cursor.execute(
                "UPDATE projects SET archived_at = %(archived_at)s, updated_at = %(updated_at)s "
                "WHERE project_id = %(project_id)s AND archived_at IS NULL",
                {"project_id": project_id, "archived_at": self._now(), "updated_at": self._now()},
            )
            return getattr(cursor, "rowcount", 0) > 0

    def restore_project(self, project_id: str) -> Project | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE projects SET archived_at = NULL, updated_at = %(updated_at)s WHERE project_id = %(project_id)s",
                {"project_id": project_id, "updated_at": self._now()},
            )
            if getattr(cursor, "rowcount", 0) <= 0:
                return None
        return self.get_project(project_id)

    def add_project_member(self, project_id: str, user_id: str, role: ProjectRole = ProjectRole.CONTRIBUTOR) -> ProjectMembership:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT membership_id, project_id, user_id, role, created_at, updated_at FROM project_memberships "
                "WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            existing = cursor.fetchone()
            if existing:
                raise ValueError("User is already a project member")

            membership = ProjectMembership(
                id=f"pmem-{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                user_id=user_id,
                role=role,
                created_at=self._now(),
                updated_at=self._now(),
            )
            cursor.execute(
                "INSERT INTO project_memberships (membership_id, project_id, user_id, role, created_at, updated_at) "
                "VALUES (%(membership_id)s, %(project_id)s, %(user_id)s, %(role)s, %(created_at)s, %(updated_at)s)",
                {
                    "membership_id": membership.id,
                    "project_id": membership.project_id,
                    "user_id": membership.user_id,
                    "role": membership.role.value,
                    "created_at": membership.created_at,
                    "updated_at": membership.updated_at,
                },
            )
            return membership

    def remove_project_member(self, project_id: str, user_id: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM project_memberships WHERE project_id = %(project_id)s AND role = 'owner'",
                {"project_id": project_id},
            )
            owner_count_row = cursor.fetchone() or (0,)
            owner_count = owner_count_row[0]
            cursor.execute(
                "SELECT role = 'owner' FROM project_memberships WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            is_owner_row = cursor.fetchone()
            is_owner = bool(is_owner_row[0]) if is_owner_row else False
            if is_owner and owner_count <= 1:
                raise ValueError("Cannot remove the last owner")
            cursor.execute(
                "DELETE FROM project_memberships WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            return getattr(cursor, "rowcount", 0) > 0

    def list_project_members(self, project_id: str) -> list[ProjectMembership]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT membership_id, project_id, user_id, role, created_at, updated_at FROM project_memberships WHERE project_id = %(project_id)s",
                {"project_id": project_id},
            )
            return [self._project_membership_from_row(row) for row in cursor.fetchall() or []]

    def update_project_member_role(self, project_id: str, user_id: str, new_role: ProjectRole) -> ProjectMembership | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM project_memberships WHERE project_id = %(project_id)s AND role = 'owner'",
                {"project_id": project_id},
            )
            owner_count_row = cursor.fetchone() or (0,)
            owner_count = owner_count_row[0]
            cursor.execute(
                "SELECT role = 'owner' FROM project_memberships WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            is_owner_row = cursor.fetchone()
            is_owner = bool(is_owner_row[0]) if is_owner_row else False
            if is_owner and owner_count <= 1 and new_role != ProjectRole.OWNER:
                raise ValueError("Cannot demote the last owner")
            cursor.execute(
                "UPDATE project_memberships SET role = %(role)s, updated_at = %(updated_at)s "
                "WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {
                    "project_id": project_id,
                    "user_id": user_id,
                    "role": new_role.value,
                    "updated_at": self._now(),
                },
            )
            if getattr(cursor, "rowcount", 0) <= 0:
                return None
            row = cursor.fetchone()
            return self._project_membership_from_row(row) if row else None

    def create_project(
        self,
        *,
        owner_id: str,
        name: str,
        slug: str,
        description: str | None = None,
        visibility: ProjectVisibility = ProjectVisibility.PRIVATE,
        settings: dict[str, Any] | None = None,
        org_id: str | None = None,
    ) -> Project:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT project_id FROM projects WHERE owner_id = %(owner_id)s AND slug = %(slug)s AND archived_at IS NULL",
                {"owner_id": owner_id, "slug": slug},
            )
            if cursor.fetchone():
                raise ValueError("Project slug is already taken")
            project = Project(
                id=f"proj-{uuid.uuid4().hex[:12]}",
                org_id=org_id,
                owner_id=owner_id,
                name=name,
                slug=slug,
                description=description,
                visibility=visibility,
                settings=settings or {},
                created_at=self._now(),
                updated_at=self._now(),
            )
            cursor.execute(
                "INSERT INTO projects (project_id, org_id, owner_id, name, slug, description, visibility, settings, created_at, updated_at) "
                "VALUES (%(project_id)s, %(org_id)s, %(owner_id)s, %(name)s, %(slug)s, %(description)s, %(visibility)s, %(settings)s, %(created_at)s, %(updated_at)s)",
                {
                    "project_id": project.id,
                    "org_id": project.org_id,
                    "owner_id": project.owner_id,
                    "name": project.name,
                    "slug": project.slug,
                    "description": project.description,
                    "visibility": project.visibility.value,
                    "settings": json.dumps(project.settings),
                    "created_at": project.created_at,
                    "updated_at": project.updated_at,
                },
            )
            return project

    def list_projects(self, *, owner_id: str, org_id: str | None = None) -> list[Project]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            conditions = ["owner_id = %(owner_id)s", "archived_at IS NULL"]
            params: dict[str, Any] = {"owner_id": owner_id}
            if org_id is None:
                conditions.append("org_id IS NULL")
            else:
                conditions.append("org_id = %(org_id)s")
                params["org_id"] = org_id
            cursor.execute(
                "SELECT project_id, org_id, owner_id, name, slug, description, visibility, settings, created_at, updated_at "
                f"FROM projects WHERE {' AND '.join(conditions)}",
                params,
            )
            return [self._project_from_row(row) for row in cursor.fetchall() or []]

    def add_collaborator(
        self,
        *,
        project_id: str,
        user_id: str,
        invited_by: str,
        role: ProjectRole = ProjectRole.CONTRIBUTOR,
    ) -> ProjectCollaborator:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT owner_id FROM projects WHERE project_id = %(project_id)s AND org_id IS NULL",
                {"project_id": project_id},
            )
            owner_row = cursor.fetchone()
            if owner_row is None:
                raise ValueError("Project is not a user-owned project")
            owner_id = owner_row[0]
            if owner_id != invited_by:
                raise ValueError("Only the project owner can add collaborators")
            cursor.execute(
                "SELECT collaborator_id FROM project_collaborators WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            if cursor.fetchone():
                raise ValueError("User is already a collaborator")
            collaborator = ProjectCollaborator(
                id=f"collab-{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                user_id=user_id,
                role=role,
                invited_by=invited_by,
                invited_at=self._now(),
                accepted_at=None,
                created_at=self._now(),
                updated_at=self._now(),
            )
            cursor.execute(
                "INSERT INTO project_collaborators (collaborator_id, project_id, user_id, role, invited_by, invited_at, accepted_at, created_at, updated_at) "
                "VALUES (%(collaborator_id)s, %(project_id)s, %(user_id)s, %(role)s, %(invited_by)s, %(invited_at)s, %(accepted_at)s, %(created_at)s, %(updated_at)s)",
                {
                    "collaborator_id": collaborator.id,
                    "project_id": collaborator.project_id,
                    "user_id": collaborator.user_id,
                    "role": collaborator.role.value,
                    "invited_by": collaborator.invited_by,
                    "invited_at": collaborator.invited_at,
                    "accepted_at": collaborator.accepted_at,
                    "created_at": collaborator.created_at,
                    "updated_at": collaborator.updated_at,
                },
            )
            return collaborator

    def accept_collaboration(self, *, collaborator_id: str, user_id: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE project_collaborators SET accepted_at = %(accepted_at)s, updated_at = %(updated_at)s "
                "WHERE collaborator_id = %(collaborator_id)s AND user_id = %(user_id)s",
                {
                    "collaborator_id": collaborator_id,
                    "user_id": user_id,
                    "accepted_at": self._now(),
                    "updated_at": self._now(),
                },
            )
            return getattr(cursor, "rowcount", 0) > 0

    def list_project_collaborators(self, *, project_id: str) -> list[ProjectCollaborator]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT collaborator_id, project_id, user_id, role, invited_by, invited_at, accepted_at, created_at, updated_at "
                "FROM project_collaborators WHERE project_id = %(project_id)s",
                {"project_id": project_id},
            )
            return [self._collaborator_from_row(row) for row in cursor.fetchall() or []]

    def list_user_collaborations(self, *, user_id: str) -> list[Project]:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT p.project_id, p.org_id, p.owner_id, p.name, p.slug, p.description, p.visibility, p.settings, p.created_at, p.updated_at "
                "FROM projects p JOIN project_collaborators pc ON pc.project_id = p.project_id WHERE pc.user_id = %(user_id)s",
                {"user_id": user_id},
            )
            return [self._project_from_row(row) for row in cursor.fetchall() or []]

    def remove_collaborator(self, *, project_id: str, user_id: str, removed_by: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT owner_id FROM projects WHERE project_id = %(project_id)s AND org_id IS NULL",
                {"project_id": project_id},
            )
            owner_row = cursor.fetchone()
            owner_id = owner_row[0] if owner_row else None
            if owner_id is not None and removed_by not in {owner_id, user_id}:
                raise ValueError("Only the project owner can remove collaborators")
            cursor.execute(
                "DELETE FROM project_collaborators WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {"project_id": project_id, "user_id": user_id},
            )
            return getattr(cursor, "rowcount", 0) > 0

    def update_collaborator_role(
        self,
        *,
        project_id: str,
        user_id: str,
        new_role: ProjectRole,
        updated_by: str,
    ) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT owner_id FROM projects WHERE project_id = %(project_id)s AND org_id IS NULL",
                {"project_id": project_id},
            )
            owner_row = cursor.fetchone()
            owner_id = owner_row[0] if owner_row else None
            if owner_id != updated_by:
                raise ValueError("Only the project owner can update collaborator roles")
            cursor.execute(
                "UPDATE project_collaborators SET role = %(role)s, updated_at = %(updated_at)s "
                "WHERE project_id = %(project_id)s AND user_id = %(user_id)s",
                {
                    "project_id": project_id,
                    "user_id": user_id,
                    "role": new_role.value,
                    "updated_at": self._now(),
                },
            )
            return getattr(cursor, "rowcount", 0) > 0

    def create_user_subscription(self, *, user_id: str, plan: OrgPlan) -> Subscription:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT subscription_id FROM subscriptions WHERE user_id = %(user_id)s AND org_id IS NULL",
                {"user_id": user_id},
            )
            if cursor.fetchone():
                raise ValueError("User already has a subscription")
            return Subscription(
                id=f"sub-{uuid.uuid4().hex[:12]}",
                user_id=user_id,
                org_id=None,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                created_at=self._now(),
                updated_at=self._now(),
            )

    def get_user_subscription(self, *, user_id: str) -> Subscription | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT subscription_id, user_id, stripe_subscription_id, stripe_customer_id, plan, status, "
                "current_period_start, current_period_end, cancel_at, created_at, updated_at "
                "FROM subscriptions WHERE user_id = %(user_id)s AND org_id IS NULL",
                {"user_id": user_id},
            )
            row = cursor.fetchone()
            return self._subscription_from_row(row) if row else None

    def resolve_billing_context(
        self,
        *,
        user_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> BillingContext | None:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            if org_id is not None:
                cursor.execute(
                    "SELECT role FROM org_memberships WHERE org_id = %(org_id)s AND user_id = %(user_id)s",
                    {"org_id": org_id, "user_id": user_id},
                )
                if cursor.fetchone() is None:
                    return None
                cursor.execute(
                    "SELECT subscription_id, plan, status, token_budget, tokens_used FROM subscriptions WHERE org_id = %(org_id)s",
                    {"org_id": org_id},
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return BillingContext(
                    subscription_id=row[0],
                    subscription_type="org",
                    org_id=org_id,
                    user_id=user_id,
                    plan=OrgPlan(row[1]),
                    status=SubscriptionStatus(row[2]),
                    token_budget=row[3],
                    tokens_used=row[4],
                    is_within_budget=row[4] <= row[3],
                )

            if project_id is not None:
                cursor.execute(
                    "SELECT org_id, owner_id FROM projects WHERE project_id = %(project_id)s",
                    {"project_id": project_id},
                )
                project_row = cursor.fetchone()
                if project_row is None:
                    return None
                project_org_id = project_row[0]
                if project_org_id is not None:
                    cursor.execute(
                        "SELECT subscription_id, plan, status, token_budget, tokens_used FROM subscriptions WHERE org_id = %(org_id)s",
                        {"org_id": project_org_id},
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return BillingContext(
                        subscription_id=row[0],
                        subscription_type="org",
                        org_id=project_org_id,
                        user_id=user_id,
                        plan=OrgPlan(row[1]),
                        status=SubscriptionStatus(row[2]),
                        token_budget=row[3],
                        tokens_used=row[4],
                        is_within_budget=row[4] <= row[3],
                    )

            cursor.execute(
                "SELECT subscription_id, plan, status FROM subscriptions WHERE user_id = %(user_id)s AND org_id IS NULL",
                {"user_id": user_id},
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM usage_records WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )
            usage_row = cursor.fetchone() or (0,)
            return BillingContext(
                subscription_id=row[0],
                subscription_type="user",
                org_id=None,
                user_id=user_id,
                plan=OrgPlan(row[1]),
                status=SubscriptionStatus(row[2]),
                token_budget=100000,
                tokens_used=usage_row[0],
                is_within_budget=usage_row[0] <= 100000,
            )

    def record_user_usage(
        self,
        *,
        user_id: str,
        metric_name: str,
        quantity: int,
        org_id: str | None = None,
    ) -> UsageRecord:
        return UsageRecord(
            user_id=user_id,
            org_id=org_id,
            metric_name=metric_name,
            quantity=quantity,
            recorded_at=self._now(),
            metadata={},
        )

    def get_user_usage_summary(
        self,
        *,
        user_id: str,
        metric_name: str,
        start_date: datetime,
        include_org_usage: bool = False,
    ) -> int:
        with self._pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM usage_records WHERE user_id = %(user_id)s AND metric_name = %(metric_name)s AND recorded_at >= %(start_date)s",
                {
                    "user_id": user_id,
                    "metric_name": metric_name,
                    "start_date": start_date,
                    "include_org_usage": include_org_usage,
                },
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0
