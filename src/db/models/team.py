from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from typing import TYPE_CHECKING

from src.db.base_class import Base

if TYPE_CHECKING:
    from src.db.models.organization import Organization
    from src.db.models.user import User


class Team(Base):
    """
    Cross-functional teams within an organization.
    Allows grouping users from different departments for collaboration.
    """
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    
    # Team details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    team_type = Column(String(50), nullable=False)  # permanent, temporary, project, shift
    
    # Team leader
    leader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Created by
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Configuration
    settings = Column(JSONB, default=dict, nullable=False)
    permissions = Column(JSONB, default=dict, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Time-based teams
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="teams")
    leader = relationship("User", foreign_keys=[leader_id])
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="created_teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="team")
    shared_notes = relationship("NoteShare", foreign_keys="NoteShare.shared_with_team_id", back_populates="shared_with_team")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('organization_id', 'name', name='uq_org_team_name'),
        CheckConstraint("team_type IN ('permanent', 'temporary', 'project', 'shift')", name='check_team_type'),
        Index('idx_team_org_active', 'organization_id', 'is_active'),
        Index('idx_team_type', 'team_type'),
    )
    
    @property
    def member_count(self) -> int:
        """Get number of active members"""
        return len([m for m in self.members if m.is_active])
    
    @property
    def is_temporary(self) -> bool:
        """Check if team is temporary"""
        return self.team_type == 'temporary' or self.end_date is not None
    
    @property
    def is_expired(self) -> bool:
        """Check if team has expired"""
        if not self.end_date:
            return False
        from datetime import datetime
        return self.end_date < datetime.utcnow()
    
    def add_member(self, user_id: int, role: str = 'member') -> 'TeamMember':
        """Add a member to the team"""
        from datetime import datetime
        member = TeamMember(
            team_id=self.id,
            user_id=user_id,
            role=role,
            joined_at=datetime.utcnow(),
            is_active=True
        )
        self.members.append(member)
        return member
    
    def remove_member(self, user_id: int):
        """Remove a member from the team"""
        from datetime import datetime
        for member in self.members:
            if member.user_id == user_id and member.is_active:
                member.is_active = False
                member.left_at = datetime.utcnow()
                break
    
    def __repr__(self):
        return f"<Team {self.id}: {self.name}>"


class TeamMember(Base):
    """
    Team membership tracking.
    Tracks users assigned to teams with their roles.
    """
    __tablename__ = 'team_members'
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Member details
    role = Column(String(50), nullable=True)  # member, co-lead, specialist
    joined_at = Column(DateTime(timezone=True), nullable=False)
    left_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Permissions override
    custom_permissions = Column(JSONB, nullable=True)
    
    # Relationships
    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint('team_id', 'user_id', name='uq_team_user'),
        CheckConstraint("role IN ('member', 'co-lead', 'specialist', 'admin')", name='check_member_role'),
        Index('idx_team_member_active', 'team_id', 'user_id', 'is_active'),
    )
    
    @property
    def duration_days(self) -> int:
        """Get membership duration in days"""
        from datetime import datetime
        end = self.left_at or datetime.utcnow()
        return (end - self.joined_at).days if self.joined_at else 0
    
    def __repr__(self):
        return f"<TeamMember {self.user_id} in Team {self.team_id}>"
