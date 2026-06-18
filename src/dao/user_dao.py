from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.exc import IntegrityError
from loguru import logger

from src.models.sql.workflow.user import User


class UserDAOError(Exception):
    """Base exception for User DAO operations."""
    pass


class UserNotFoundError(UserDAOError):
    """Raised when user is not found."""
    pass


class DuplicateEmailError(UserDAOError):
    """Raised when email already exists."""
    pass


class UserDAO:
    """
    Data Access Object for Users.

    Features:
    - CRUD operations with validation
    - Secure password handling
    - Login tracking
    - Activity monitoring
    - Batch operations
    - Search and filtering
    - Account management
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============================================================
    # CREATE
    # ============================================================

    async def create(self, user: User) -> User:
        """
        Creates a new user.

        Args:
            user: User instance to create

        Returns:
            Created user with ID

        Raises:
            DuplicateEmailError: If email already exists
        """
        try:
            # Normalize email
            user.email = user.email.lower().strip()

            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)

            logger.info(
                f"User created: {user.id}",
                extra={"email": user.email}
            )

            return user

        except IntegrityError as e:
            await self.db.rollback()
            if "email" in str(e).lower():
                raise DuplicateEmailError(f"Email '{user.email}' already registered")
            raise

    # ============================================================
    # READ
    # ============================================================

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """
        Gets user by ID.

        Args:
            user_id: User UUID

        Returns:
            User or None if not found
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalars().first()

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Gets user by email (case-insensitive).

        Args:
            email: User email

        Returns:
            User or None if not found
        """
        email = email.lower().strip()

        result = await self.db.execute(
            select(User).where(func.lower(User.email) == email)
        )
        return result.scalars().first()

    async def get_active_by_email(self, email: str) -> Optional[User]:
        """
        Gets active user by email.

        Args:
            email: User email

        Returns:
            Active user or None
        """
        email = email.lower().strip()

        result = await self.db.execute(
            select(User).where(
                and_(
                    func.lower(User.email) == email,
                    User.is_active == True
                )
            )
        )
        return result.scalars().first()

    async def exists_by_email(self, email: str) -> bool:
        """
        Checks if email is already registered.

        Args:
            email: Email to check

        Returns:
            True if exists, False otherwise
        """
        email = email.lower().strip()

        result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(func.lower(User.email) == email)
        )
        return (result.scalar() or 0) > 0

    async def get_all(
            self,
            skip: int = 0,
            limit: int = 100,
            active_only: bool = False,
            search: Optional[str] = None,
            sort_by: str = "created_at",
            sort_desc: bool = True
    ) -> List[User]:
        """
        Gets all users with filtering and pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
            active_only: Only return active users
            search: Search in email and full_name
            sort_by: Field to sort by
            sort_desc: Sort descending

        Returns:
            List of users
        """
        # Validate pagination
        skip = max(0, skip)
        limit = min(max(1, limit), 1000)

        # Build query
        query = select(User)

        # Apply active filter
        if active_only:
            query = query.where(User.is_active == True)

        # Apply search
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    User.email.ilike(search_term),
                    User.full_name.ilike(search_term)
                )
            )

        # Apply sorting
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_desc:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(self, active_only: bool = False) -> int:
        """
        Counts total users.

        Args:
            active_only: Only count active users

        Returns:
            User count
        """
        query = select(func.count()).select_from(User)

        if active_only:
            query = query.where(User.is_active == True)

        result = await self.db.execute(query)
        return result.scalar() or 0

    # ============================================================
    # UPDATE
    # ============================================================

    async def update(self, user: User) -> User:
        """
        Updates a user.

        Args:
            user: User with updated fields

        Returns:
            Updated user
        """
        user.updated_at = datetime.now(timezone.utc)

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def update_fields(
            self,
            user_id: UUID,
            updates: Dict[str, Any]
    ) -> Optional[User]:
        """
        Updates specific fields for a user.

        Args:
            user_id: User UUID
            updates: Dictionary of fields to update

        Returns:
            Updated user or None if not found
        """
        # Get user
        user = await self.get_by_id(user_id)
        if not user:
            return None

        # Restricted fields that cannot be updated this way
        restricted = {"id", "hashed_password", "created_at"}

        # Apply updates
        for key, value in updates.items():
            if key not in restricted and hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def update_password(
            self,
            user_id: UUID,
            hashed_password: str
    ) -> bool:
        """
        Updates user password securely.

        Args:
            user_id: User UUID
            hashed_password: New hashed password

        Returns:
            True if updated, False if user not found
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                hashed_password=hashed_password,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        if result.rowcount > 0:
            logger.info(
                f"Password updated for user: {user_id}",
                extra={"user_id": str(user_id)}
            )
            return True

        return False

    async def update_email(
            self,
            user_id: UUID,
            new_email: str
    ) -> Optional[User]:
        """
        Updates user email with validation.

        Args:
            user_id: User UUID
            new_email: New email address

        Returns:
            Updated user or None

        Raises:
            DuplicateEmailError: If email already exists
        """
        new_email = new_email.lower().strip()

        # Check for duplicate
        if await self.exists_by_email(new_email):
            existing = await self.get_by_email(new_email)
            if existing and existing.id != user_id:
                raise DuplicateEmailError(f"Email '{new_email}' already registered")

        # Update email
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.email = new_email
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def record_login(self, user_id: UUID) -> bool:
        """
        Records successful login.

        Args:
            user_id: User UUID

        Returns:
            True if updated
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.now(timezone.utc))
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount > 0

    # ============================================================
    # ACCOUNT STATUS
    # ============================================================

    async def activate(self, user_id: UUID) -> bool:
        """
        Activates a user account.

        Args:
            user_id: User UUID

        Returns:
            True if activated
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                is_active=True,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        if result.rowcount > 0:
            logger.info(f"User activated: {user_id}")
            return True
        return False

    async def deactivate(self, user_id: UUID) -> bool:
        """
        Deactivates a user account.

        Args:
            user_id: User UUID

        Returns:
            True if deactivated
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                is_active=False,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        if result.rowcount > 0:
            logger.info(f"User deactivated: {user_id}")
            return True
        return False

    async def set_superuser(self, user_id: UUID, is_superuser: bool) -> bool:
        """
        Sets superuser status.

        Args:
            user_id: User UUID
            is_superuser: Superuser flag

        Returns:
            True if updated
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                is_superuser=is_superuser,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount > 0

    # ============================================================
    # DELETE
    # ============================================================

    async def delete(self, user_id: UUID) -> bool:
        """
        Hard deletes a user.

        Args:
            user_id: User UUID

        Returns:
            True if deleted
        """
        stmt = delete(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()

        if result.rowcount > 0:
            logger.info(f"User deleted: {user_id}")
            return True
        return False

    async def soft_delete(self, user_id: UUID) -> bool:
        """
        Soft deletes a user by deactivating.

        Args:
            user_id: User UUID

        Returns:
            True if deactivated
        """
        return await self.deactivate(user_id)

    # ============================================================
    # BATCH OPERATIONS
    # ============================================================

    async def get_batch(self, user_ids: List[UUID]) -> List[User]:
        """
        Gets multiple users by IDs.

        Args:
            user_ids: List of user UUIDs

        Returns:
            List of found users
        """
        if not user_ids:
            return []

        result = await self.db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        return list(result.scalars().all())

    async def deactivate_batch(self, user_ids: List[UUID]) -> int:
        """
        Deactivates multiple users.

        Args:
            user_ids: List of user UUIDs

        Returns:
            Number of deactivated users
        """
        if not user_ids:
            return 0

        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(
                is_active=False,
                updated_at=datetime.now(timezone.utc)
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount

    # ============================================================
    # ANALYTICS / REPORTING
    # ============================================================

    async def get_inactive_users(
            self,
            days_inactive: int = 30,
            limit: int = 100
    ) -> List[User]:
        """
        Gets users who haven't logged in recently.

        Args:
            days_inactive: Days since last login
            limit: Maximum users to return

        Returns:
            List of inactive users
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_inactive)

        query = (
            select(User)
            .where(
                or_(
                    User.last_login < cutoff,
                    User.last_login.is_(None)
                )
            )
            .where(User.is_active == True)
            .order_by(User.last_login.asc().nullsfirst())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent_signups(
            self,
            days: int = 7,
            limit: int = 100
    ) -> List[User]:
        """
        Gets recently registered users.

        Args:
            days: Number of days to look back
            limit: Maximum users to return

        Returns:
            List of recent users
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(User)
            .where(User.created_at >= cutoff)
            .order_by(User.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_stats(self) -> Dict[str, int]:
        """
        Gets user statistics.

        Returns:
            Dictionary with user stats
        """
        total = await self.count()
        active = await self.count(active_only=True)

        # Count superusers
        result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(User.is_superuser == True)
        )
        superusers = result.scalar() or 0

        # Count recent logins (last 24h)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(User.last_login >= recent_cutoff)
        )
        recent_logins = result.scalar() or 0

        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "superusers": superusers,
            "recent_logins_24h": recent_logins
        }