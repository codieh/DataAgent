from app.infrastructure.persistence.repositories.artifacts import ArtifactRepository
from app.infrastructure.persistence.repositories.conversations import ConversationRepository
from app.infrastructure.persistence.repositories.events import EventRepository
from app.infrastructure.persistence.repositories.reviews import ReviewRepository
from app.infrastructure.persistence.repositories.runs import RunRepository


class Repository(
    ConversationRepository,
    RunRepository,
    ArtifactRepository,
    ReviewRepository,
    EventRepository,
):
    """Transactional facade composed from aggregate-specific repositories."""

