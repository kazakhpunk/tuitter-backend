"""
FastAPI backend for Social.vim application
"""
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import uvicorn

import models
import schemas
import crud
from database import engine, get_db

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Social.vim API",
    description="Backend API for Social.vim TUI application",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== UTILITY FUNCTIONS ==========

def get_current_user_from_handle(db: Session, handle: str) -> models.User:
    """Get current user by handle (username)"""
    user = crud.get_user_by_username(db, handle)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{handle}' not found")
    return user


# ========== USER ENDPOINTS ==========

@app.get("/me", response_model=schemas.UserResponse)
def get_current_user(
    handle: str = Query(..., description="Username/handle of the current user"),
    db: Session = Depends(get_db)
):
    """
    Get current user profile.
    For demo purposes, uses query parameter to identify user.
    """
    user = get_current_user_from_handle(db, handle)
    return schemas.UserResponse.from_orm(user)


# ========== POST ENDPOINTS ==========

@app.get("/timeline", response_model=List[schemas.PostResponse])
def get_timeline(
    limit: int = Query(50, ge=1, le=100),
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Get timeline posts (recent posts from all users)"""
    posts = crud.get_timeline_posts(db, limit)
    
    # Get current user to check interactions
    user = crud.get_user_by_username(db, handle)
    user_id = user.id if user else None
    
    # Build response with user interaction status
    result = []
    for post in posts:
        liked = crud.check_user_liked_post(db, post.id, user_id) if user_id else False
        reposted = crud.check_user_reposted(db, post.id, user_id) if user_id else False
        result.append(schemas.PostResponse.from_orm(post, user_id, liked, reposted))
    
    return result


@app.get("/discover", response_model=List[schemas.PostResponse])
def get_discover(
    limit: int = Query(50, ge=1, le=100),
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Get discover posts (trending/popular posts)"""
    posts = crud.get_discover_posts(db, limit)
    
    # Get current user to check interactions
    user = crud.get_user_by_username(db, handle)
    user_id = user.id if user else None
    
    # Build response with user interaction status
    result = []
    for post in posts:
        liked = crud.check_user_liked_post(db, post.id, user_id) if user_id else False
        reposted = crud.check_user_reposted(db, post.id, user_id) if user_id else False
        result.append(schemas.PostResponse.from_orm(post, user_id, liked, reposted))
    
    return result


@app.post("/posts", response_model=schemas.PostResponse)
def create_post(
    post_data: schemas.PostCreate,
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Create a new post"""
    user = get_current_user_from_handle(db, handle)
    post = crud.create_post(db, user.id, user.username, post_data.content)
    return schemas.PostResponse.from_orm(post, user.id, False, False)


@app.post("/posts/{post_id}/like")
def like_post(
    post_id: int,
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Toggle like on a post"""
    user = get_current_user_from_handle(db, handle)
    success = crud.toggle_like(db, post_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True}


@app.post("/posts/{post_id}/repost")
def repost_post(
    post_id: int,
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Toggle repost on a post"""
    user = get_current_user_from_handle(db, handle)
    success = crud.toggle_repost(db, post_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"success": True}


# ========== COMMENT ENDPOINTS ==========

@app.get("/posts/{post_id}/comments", response_model=List[schemas.CommentResponse])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db)
):
    """Get all comments for a post"""
    comments = crud.get_comments(db, post_id)
    return [schemas.CommentResponse(user=c.username, text=c.text) for c in comments]


@app.post("/posts/{post_id}/comments", response_model=schemas.CommentResponse)
def add_comment(
    post_id: int,
    comment_data: schemas.CommentCreate,
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Add a comment to a post"""
    user = get_current_user_from_handle(db, handle)
    comment = crud.add_comment(db, post_id, user.id, user.username, comment_data.text)
    return schemas.CommentResponse(user=comment.username, text=comment.text)


# ========== CONVERSATION & MESSAGE ENDPOINTS ==========

@app.get("/conversations", response_model=List[schemas.ConversationResponse])
def get_conversations(
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Get all conversations for the current user"""
    user = get_current_user_from_handle(db, handle)
    conversations = crud.get_conversations_for_user(db, user.id)
    
    result = []
    for conv in conversations:
        # Get participant handles
        user_a = crud.get_user_by_id(db, conv.participant_a_id)
        user_b = crud.get_user_by_id(db, conv.participant_b_id)
        
        handles = []
        if user_a:
            handles.append(user_a.username)
        if user_b:
            handles.append(user_b.username)
        
        result.append(schemas.ConversationResponse(
            id=conv.id,
            participant_handles=handles,
            last_message_preview=conv.last_message_preview,
            last_message_at=conv.last_message_at,
            unread=False  # TODO: implement unread logic
        ))
    
    return result


@app.get("/conversations/{conversation_id}/messages", response_model=List[schemas.MessageResponse])
def get_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """Get all messages in a conversation"""
    messages = crud.get_messages_for_conversation(db, conversation_id)
    return [schemas.MessageResponse.from_orm(m) for m in messages]


@app.post("/conversations/{conversation_id}/messages", response_model=schemas.MessageResponse)
def send_message(
    conversation_id: int,
    message_data: schemas.MessageCreate,
    db: Session = Depends(get_db)
):
    """Send a message in a conversation"""
    sender = crud.get_user_by_username(db, message_data.sender_handle)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")
    
    message = crud.create_message(
        db, 
        conversation_id, 
        sender.id, 
        sender.username, 
        message_data.content
    )
    return schemas.MessageResponse.from_orm(message)


@app.post("/dm", response_model=schemas.ConversationResponse)
def get_or_create_dm(
    conversation_data: schemas.ConversationCreate,
    db: Session = Depends(get_db)
):
    """Get or create a direct message conversation between two users"""
    user_a = crud.get_user_by_username(db, conversation_data.user_a_handle)
    user_b = crud.get_user_by_username(db, conversation_data.user_b_handle)
    
    if not user_a:
        raise HTTPException(status_code=404, detail=f"User '{conversation_data.user_a_handle}' not found")
    if not user_b:
        raise HTTPException(status_code=404, detail=f"User '{conversation_data.user_b_handle}' not found")
    
    conversation = crud.get_or_create_conversation(db, user_a.id, user_b.id)
    
    return schemas.ConversationResponse(
        id=conversation.id,
        participant_handles=[user_a.username, user_b.username],
        last_message_preview=conversation.last_message_preview,
        last_message_at=conversation.last_message_at,
        unread=False
    )


# ========== NOTIFICATION ENDPOINTS ==========

@app.get("/notifications", response_model=List[schemas.NotificationResponse])
def get_notifications(
    unread: bool = Query(False, description="Get only unread notifications"),
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Get notifications for the current user"""
    user = get_current_user_from_handle(db, handle)
    notifications = crud.get_notifications_for_user(db, user.id, unread)
    return [schemas.NotificationResponse.from_orm(n) for n in notifications]


@app.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db)
):
    """Mark a notification as read"""
    success = crud.mark_notification_read(db, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


# ========== SETTINGS ENDPOINTS ==========

@app.get("/settings", response_model=schemas.SettingsResponse)
def get_settings(
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Get user settings"""
    user = get_current_user_from_handle(db, handle)
    settings = crud.get_user_settings(db, user.id)
    
    if not settings:
        # Return default settings with user info
        return schemas.SettingsResponse(
            username=user.username,
            display_name=user.display_name,
            bio=user.bio,
            email_notifications=True,
            show_online_status=True,
            private_account=False,
            github_connected=False,
            gitlab_connected=False,
            google_connected=False,
            discord_connected=False,
            ascii_pic=user.ascii_pic
        )
    
    return schemas.SettingsResponse(
        username=user.username,
        display_name=user.display_name,
        bio=user.bio,
        email_notifications=settings.email_notifications,
        show_online_status=settings.show_online_status,
        private_account=settings.private_account,
        github_connected=settings.github_connected,
        gitlab_connected=settings.gitlab_connected,
        google_connected=settings.google_connected,
        discord_connected=settings.discord_connected,
        ascii_pic=user.ascii_pic
    )


@app.put("/settings")
def update_settings(
    settings_update: schemas.SettingsUpdate,
    handle: str = Query("yourname", description="Current user handle"),
    db: Session = Depends(get_db)
):
    """Update user settings"""
    user = get_current_user_from_handle(db, handle)
    crud.update_user_settings(db, user.id, settings_update)
    return {"success": True}


# ========== HEALTH CHECK ==========

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "social.vim API"}


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "service": "Social.vim API",
        "version": "1.0.0",
        "docs": "/docs"
    }


# ========== RUN SERVER ==========

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

