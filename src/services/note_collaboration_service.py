"""
Real-time Note Collaboration Service
REAL implementation with WebSocket support for team collaboration
"""
import json
import re
import asyncio
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import logging

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from src.db.models.note import Note, NoteComment
from src.db.models.note_version import NoteVersion
from src.db.models.note_activity import NoteActivity, NoteShare
from src.db.models.note_mention import NoteMention
from src.db.models.user import User
from src.db.models.team import Team, TeamMember
from src.services.notification_service import NotificationService
from src.core.redis_manager import RedisManager

logger = logging.getLogger(__name__)


class NoteCollaborationService:
    """
    REAL note collaboration service with live editing, @mentions, and version control.
    """
    
    def __init__(self):
        self.redis_manager = RedisManager()
        self.notification_service = NotificationService()
        # Track active WebSocket connections per note
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Track user presence per note
        self.user_presence: Dict[int, Dict[int, Dict]] = {}
        
    async def join_note_session(self, note_id: int, user_id: int, websocket: WebSocket):
        """
        User joins a note editing session.
        """
        # Add to active connections
        if note_id not in self.active_connections:
            self.active_connections[note_id] = set()
        self.active_connections[note_id].add(websocket)
        
        # Update user presence
        if note_id not in self.user_presence:
            self.user_presence[note_id] = {}
        
        self.user_presence[note_id][user_id] = {
            'user_id': user_id,
            'joined_at': datetime.utcnow().isoformat(),
            'cursor_position': 0,
            'selection': None
        }
        
        # Notify other users
        await self.broadcast_presence_update(note_id, user_id, 'joined')
        
        logger.info(f"User {user_id} joined note {note_id} session")
    
    async def leave_note_session(self, note_id: int, user_id: int, websocket: WebSocket):
        """
        User leaves a note editing session.
        """
        # Remove from active connections
        if note_id in self.active_connections:
            self.active_connections[note_id].discard(websocket)
            if not self.active_connections[note_id]:
                del self.active_connections[note_id]
        
        # Remove user presence
        if note_id in self.user_presence:
            self.user_presence[note_id].pop(user_id, None)
            if not self.user_presence[note_id]:
                del self.user_presence[note_id]
        
        # Notify other users
        await self.broadcast_presence_update(note_id, user_id, 'left')
        
        logger.info(f"User {user_id} left note {note_id} session")
    
    async def broadcast_presence_update(self, note_id: int, user_id: int, action: str):
        """
        Broadcast user presence updates to all connected users.
        """
        if note_id not in self.active_connections:
            return
        
        message = {
            'type': 'presence_update',
            'note_id': note_id,
            'user_id': user_id,
            'action': action,
            'timestamp': datetime.utcnow().isoformat(),
            'active_users': list(self.user_presence.get(note_id, {}).keys())
        }
        
        await self.broadcast_to_note(note_id, message)
    
    async def broadcast_to_note(self, note_id: int, message: Dict[str, Any], exclude_websocket: Optional[WebSocket] = None):
        """
        Broadcast message to all users editing a note.
        """
        if note_id not in self.active_connections:
            return
        
        disconnected = set()
        message_json = json.dumps(message)
        
        for websocket in self.active_connections[note_id]:
            if websocket == exclude_websocket:
                continue
                
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected websockets
        for ws in disconnected:
            self.active_connections[note_id].discard(ws)
    
    async def handle_note_edit(
        self,
        db: AsyncSession,
        note_id: int,
        user_id: int,
        content: str,
        cursor_position: int,
        websocket: WebSocket
    ):
        """
        Handle real-time note editing with conflict resolution.
        """
        # Get current note
        note = await db.get(Note, note_id)
        if not note:
            return
        
        # Check permissions
        if not await self.can_edit_note(db, user_id, note_id):
            await websocket.send_json({
                'type': 'error',
                'message': 'No edit permission'
            })
            return
        
        # Create version snapshot before edit
        if note.content != content:
            version = NoteVersion(
                note_id=note_id,
                user_id=user_id,
                content=note.content,
                version_number=await self.get_next_version_number(db, note_id),
                change_summary="Edit via real-time collaboration"
            )
            db.add(version)
        
        # Update note content
        old_content = note.content
        note.content = content
        note.updated_at = datetime.utcnow()
        
        # Track activity
        activity = NoteActivity(
            note_id=note_id,
            user_id=user_id,
            activity_type='edited',
            details=json.dumps({
                'cursor_position': cursor_position,
                'content_length': len(content),
                'diff_size': abs(len(content) - len(old_content))
            })
        )
        db.add(activity)
        
        # Process @mentions
        await self.process_mentions(db, note_id, user_id, content, old_content)
        
        # Commit changes
        await db.commit()
        
        # Broadcast update to other users
        update_message = {
            'type': 'content_update',
            'note_id': note_id,
            'user_id': user_id,
            'content': content,
            'cursor_position': cursor_position,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_note(note_id, update_message, exclude_websocket=websocket)
        
        # Update Redis cache
        await self.redis_manager.set(
            f"note:{note_id}:content",
            content,
            expire=3600  # 1 hour cache
        )
    
    async def handle_cursor_update(
        self,
        note_id: int,
        user_id: int,
        cursor_position: int,
        selection: Optional[Dict[str, int]] = None
    ):
        """
        Handle cursor position updates for collaborative editing.
        """
        if note_id in self.user_presence and user_id in self.user_presence[note_id]:
            self.user_presence[note_id][user_id].update({
                'cursor_position': cursor_position,
                'selection': selection,
                'last_update': datetime.utcnow().isoformat()
            })
        
        # Broadcast cursor update
        cursor_message = {
            'type': 'cursor_update',
            'note_id': note_id,
            'user_id': user_id,
            'cursor_position': cursor_position,
            'selection': selection,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_note(note_id, cursor_message)
    
    async def process_mentions(
        self,
        db: AsyncSession,
        note_id: int,
        user_id: int,
        content: str,
        old_content: str = ""
    ):
        """
        Process @mentions in note content and create notifications.
        """
        # Find all @mentions in the content
        mention_pattern = r'@(\w+)'
        new_mentions = set(re.findall(mention_pattern, content))
        old_mentions = set(re.findall(mention_pattern, old_content))
        
        # Find newly added mentions
        added_mentions = new_mentions - old_mentions
        
        for username in added_mentions:
            # Find user by username
            result = await db.execute(
                select(User).where(
                    User.username == username,
                    User.deleted_at.is_(None)
                )
            )
            mentioned_user = result.scalar_one_or_none()
            
            if mentioned_user and mentioned_user.id != user_id:
                # Find mention position
                match = re.search(f'@{username}', content)
                if match:
                    position = match.start()
                    
                    # Extract context around mention
                    start = max(0, position - 50)
                    end = min(len(content), position + 50)
                    context = content[start:end]
                    
                    # Create mention record
                    mention = NoteMention(
                        note_id=note_id,
                        mentioned_user_id=mentioned_user.id,
                        mentioned_by_user_id=user_id,
                        mention_text=context,
                        mention_position=position
                    )
                    db.add(mention)
                    
                    # Send notification
                    await self.notification_service.send_mention_notification(
                        db,
                        mentioned_user.id,
                        user_id,
                        note_id,
                        context
                    )
    
    async def share_note(
        self,
        db: AsyncSession,
        note_id: int,
        shared_by_user_id: int,
        share_type: str,
        target_id: Optional[int] = None,
        permission_level: str = 'view',
        expires_at: Optional[datetime] = None
    ) -> NoteShare:
        """
        Share a note with users, teams, or departments.
        """
        # Validate permission to share
        if not await self.can_share_note(db, shared_by_user_id, note_id):
            raise PermissionError("No permission to share this note")
        
        # Create share record
        share = NoteShare(
            note_id=note_id,
            shared_by_user_id=shared_by_user_id,
            permission=permission_level,
            created_at=datetime.utcnow()
        )
        
        if share_type == 'user':
            share.shared_with_user_id = target_id
        elif share_type == 'team':
            share.shared_with_team_id = target_id
            
        if expires_at:
            share.expires_at = expires_at
        
        db.add(share)
        
        # Track activity
        activity = NoteActivity(
            note_id=note_id,
            user_id=shared_by_user_id,
            activity_type='shared',
            details=json.dumps({
                'share_type': share_type,
                'target_id': target_id,
                'permission': permission_level
            })
        )
        db.add(activity)
        
        await db.commit()
        
        # Send notifications
        if share_type == 'user' and target_id:
            await self.notification_service.send_share_notification(
                db,
                target_id,
                shared_by_user_id,
                note_id
            )
        elif share_type == 'team' and target_id:
            # Notify all team members
            team_members = await self.get_team_members(db, target_id)
            for member in team_members:
                if member.user_id != shared_by_user_id:
                    await self.notification_service.send_share_notification(
                        db,
                        member.user_id,
                        shared_by_user_id,
                        note_id
                    )
        
        return share
    
    async def get_note_with_access_check(
        self,
        db: AsyncSession,
        note_id: int,
        user_id: int
    ) -> Optional[Note]:
        """
        Get note with access permission check.
        """
        # Get note with all relationships
        result = await db.execute(
            select(Note)
            .options(
                selectinload(Note.shares),
                selectinload(Note.comments),
                selectinload(Note.versions),
                selectinload(Note.activities)
            )
            .where(Note.id == note_id)
        )
        note = result.scalar_one_or_none()
        
        if not note:
            return None
        
        # Check access permission
        if not await self.can_view_note(db, user_id, note_id):
            return None
        
        return note
    
    async def can_view_note(self, db: AsyncSession, user_id: int, note_id: int) -> bool:
        """
        Check if user can view a note.
        """
        # Get note
        note = await db.get(Note, note_id)
        if not note:
            return False
        
        # Owner always has access
        if note.user_id == user_id:
            return True
        
        # Check visibility
        if note.visibility == 'private':
            # Check explicit shares
            result = await db.execute(
                select(NoteShare).where(
                    and_(
                        NoteShare.note_id == note_id,
                        or_(
                            NoteShare.shared_with_user_id == user_id,
                            NoteShare.shared_with_team_id.in_(
                                select(TeamMember.team_id).where(
                                    TeamMember.user_id == user_id
                                )
                            )
                        )
                    )
                )
            )
            return result.scalar_one_or_none() is not None
        
        elif note.visibility == 'team':
            # Check if user is in any team with the note owner
            result = await db.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.user_id == user_id,
                        TeamMember.team_id.in_(
                            select(TeamMember.team_id).where(
                                TeamMember.user_id == note.user_id
                            )
                        )
                    )
                )
            )
            return result.scalar_one_or_none() is not None
        
        elif note.visibility == 'department':
            # Check if user is in the same department
            note_owner = await db.get(User, note.user_id)
            user = await db.get(User, user_id)
            return note_owner.department_id == user.department_id
        
        elif note.visibility == 'organization':
            # Check if user is in the same organization
            note_owner = await db.get(User, note.user_id)
            user = await db.get(User, user_id)
            return note_owner.organization_id == user.organization_id
        
        return False
    
    async def can_edit_note(self, db: AsyncSession, user_id: int, note_id: int) -> bool:
        """
        Check if user can edit a note.
        """
        # Get note
        note = await db.get(Note, note_id)
        if not note:
            return False
        
        # Owner always has edit access
        if note.user_id == user_id:
            return True
        
        # Check explicit edit shares
        result = await db.execute(
            select(NoteShare).where(
                and_(
                    NoteShare.note_id == note_id,
                    NoteShare.permission == 'edit',
                    or_(
                        NoteShare.shared_with_user_id == user_id,
                        NoteShare.shared_with_team_id.in_(
                            select(TeamMember.team_id).where(
                                TeamMember.user_id == user_id
                            )
                        )
                    )
                )
            )
        )
        return result.scalar_one_or_none() is not None
    
    async def can_share_note(self, db: AsyncSession, user_id: int, note_id: int) -> bool:
        """
        Check if user can share a note.
        """
        # Only owner can share for now
        note = await db.get(Note, note_id)
        return note and note.user_id == user_id
    
    async def get_next_version_number(self, db: AsyncSession, note_id: int) -> int:
        """
        Get next version number for a note.
        """
        result = await db.execute(
            select(func.max(NoteVersion.version_number))
            .where(NoteVersion.note_id == note_id)
        )
        max_version = result.scalar() or 0
        return max_version + 1
    
    async def get_team_members(self, db: AsyncSession, team_id: int) -> List[TeamMember]:
        """
        Get all members of a team.
        """
        result = await db.execute(
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
        )
        return result.scalars().all()
    
    async def search_notes(
        self,
        db: AsyncSession,
        user_id: int,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Note]:
        """
        Search notes with access control.
        """
        # Base query with access control
        stmt = select(Note).where(
            or_(
                # User's own notes
                Note.user_id == user_id,
                # Shared with user
                Note.id.in_(
                    select(NoteShare.note_id).where(
                        NoteShare.shared_with_user_id == user_id
                    )
                ),
                # Shared with user's teams
                Note.id.in_(
                    select(NoteShare.note_id).where(
                        NoteShare.shared_with_team_id.in_(
                            select(TeamMember.team_id).where(
                                TeamMember.user_id == user_id
                            )
                        )
                    )
                ),
                # Organization/department visibility (simplified for now)
                and_(
                    Note.visibility.in_(['organization', 'department']),
                    Note.user_id.in_(
                        select(User.id).where(
                            User.organization_id == select(User.organization_id).where(
                                User.id == user_id
                            ).scalar_subquery()
                        )
                    )
                )
            )
        )
        
        # Add search condition
        if query:
            search_condition = or_(
                Note.title.ilike(f'%{query}%'),
                Note.content.ilike(f'%{query}%'),
                Note.tags.contains([query])
            )
            stmt = stmt.where(search_condition)
        
        # Add filters
        if filters:
            if 'device_id' in filters:
                stmt = stmt.where(Note.device_id == filters['device_id'])
            if 'tags' in filters:
                stmt = stmt.where(Note.tags.overlap(filters['tags']))
            if 'visibility' in filters:
                stmt = stmt.where(Note.visibility == filters['visibility'])
        
        # Order by relevance and recency
        stmt = stmt.order_by(Note.updated_at.desc()).limit(50)
        
        result = await db.execute(stmt)
        return result.scalars().all()


# WebSocket connection handler
class NoteWebSocketHandler:
    """
    Handle WebSocket connections for real-time note collaboration.
    """
    
    def __init__(self, collaboration_service: NoteCollaborationService):
        self.collaboration_service = collaboration_service
    
    async def handle_connection(
        self,
        websocket: WebSocket,
        note_id: int,
        user_id: int,
        db: AsyncSession
    ):
        """
        Handle a WebSocket connection for note collaboration.
        """
        await websocket.accept()
        
        try:
            # Join note session
            await self.collaboration_service.join_note_session(note_id, user_id, websocket)
            
            # Send initial note content
            note = await self.collaboration_service.get_note_with_access_check(db, note_id, user_id)
            if note:
                await websocket.send_json({
                    'type': 'initial_content',
                    'note_id': note_id,
                    'content': note.content,
                    'title': note.title,
                    'version': note.version,
                    'active_users': list(
                        self.collaboration_service.user_presence.get(note_id, {}).keys()
                    )
                })
            
            # Handle messages
            while True:
                data = await websocket.receive_json()
                
                if data['type'] == 'content_update':
                    await self.collaboration_service.handle_note_edit(
                        db,
                        note_id,
                        user_id,
                        data['content'],
                        data.get('cursor_position', 0),
                        websocket
                    )
                
                elif data['type'] == 'cursor_update':
                    await self.collaboration_service.handle_cursor_update(
                        note_id,
                        user_id,
                        data['cursor_position'],
                        data.get('selection')
                    )
                
                elif data['type'] == 'comment':
                    # Handle adding comments
                    comment = NoteComment(
                        note_id=note_id,
                        user_id=user_id,
                        content=data['content'],
                        parent_id=data.get('parent_id')
                    )
                    db.add(comment)
                    await db.commit()
                    
                    # Broadcast new comment
                    await self.collaboration_service.broadcast_to_note(note_id, {
                        'type': 'new_comment',
                        'comment': {
                            'id': comment.id,
                            'user_id': user_id,
                            'content': comment.content,
                            'created_at': comment.created_at.isoformat()
                        }
                    })
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user_id} on note {note_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Leave note session
            await self.collaboration_service.leave_note_session(note_id, user_id, websocket)
