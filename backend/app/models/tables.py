from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserRole(str, Enum):
    employee = "employee"
    manager = "manager"
    hr = "hr"
    admin = "admin"


class DocumentSource(str, Enum):
    slack = "slack"
    drive = "drive"
    gmail = "gmail"
    teams = "teams"
    whatsapp_upload = "whatsapp_upload"
    desktop_agent = "desktop_agent"
    manual_upload = "manual_upload"


class DocumentStatus(str, Enum):
    pending = "pending"
    parsed = "parsed"
    failed = "failed"


class EntityType(str, Enum):
    person = "person"
    project = "project"
    document = "document"
    client = "client"


class ConversationChannel(str, Enum):
    slack = "slack"
    whatsapp = "whatsapp"
    teams = "teams"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class ConnectorType(str, Enum):
    slack = "slack"
    teams = "teams"
    gmail = "gmail"
    drive = "drive"
    whatsapp = "whatsapp"


class ConnectorStatus(str, Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.employee.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    created_projects = relationship("Project", back_populates="created_by_user", cascade="all, delete-orphan")
    assigned_projects = relationship(
    "ProjectAssignment",
    back_populates="user",
    cascade="all, delete-orphan",
    foreign_keys="[ProjectAssignment.user_id]",
)
    uploaded_documents = relationship("Document", back_populates="uploaded_by_user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    audit_log = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    connector_credentials = relationship("ConnectorCredential", back_populates="connected_by_user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    created_by_user = relationship("User", back_populates="created_projects")
    assignments = relationship("ProjectAssignment", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    graph_nodes = relationship("GraphNode", back_populates="project", cascade="all, delete-orphan")
    graph_edges = relationship("GraphEdge", back_populates="project", cascade="all, delete-orphan")


class ProjectAssignment(Base):
    __tablename__ = "project_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id], back_populates="assigned_projects")
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DocumentStatus.pending.value)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="documents")
    uploaded_by_user = relationship("User", back_populates="uploaded_documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    contextual_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document = relationship("Document", back_populates="chunks")
    graph_nodes = relationship("GraphNode", back_populates="source_chunk", cascade="all, delete-orphan")
    graph_edges = relationship("GraphEdge", back_populates="source_chunk", cascade="all, delete-orphan")


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    source_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id"), nullable=True)

    project = relationship("Project", back_populates="graph_nodes")
    source_chunk = relationship("DocumentChunk", back_populates="graph_nodes")
    outgoing_edges = relationship("GraphEdge", foreign_keys="GraphEdge.from_node_id", back_populates="from_node", cascade="all, delete-orphan")
    incoming_edges = relationship("GraphEdge", foreign_keys="GraphEdge.to_node_id", back_populates="to_node", cascade="all, delete-orphan")


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("document_chunks.id"), nullable=True)

    project = relationship("Project", back_populates="graph_edges")
    from_node = relationship("GraphNode", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node = relationship("GraphNode", foreign_keys=[to_node_id], back_populates="incoming_edges")
    source_chunk = relationship("DocumentChunk", back_populates="graph_edges")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cited_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    sources_retrieved: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_log")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    model_used: Mapped[str] = mapped_column(String(255), nullable=False)
    precision: Mapped[float | None] = mapped_column(nullable=True)
    recall: Mapped[float | None] = mapped_column(nullable=True)
    faithfulness_score: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectorCredential(Base):
    __tablename__ = "connector_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    connected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    connected_by_user = relationship("User", back_populates="connector_credentials")
