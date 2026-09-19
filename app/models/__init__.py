"""Import all models so Alembic can discover them."""

from app.models.user import User  # noqa: F401
from app.models.group import DocumentGroup  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.page import Page  # noqa: F401
from app.models.question import Question  # noqa: F401
from app.models.review import ReviewItem  # noqa: F401
from app.models.answer_key import AnswerKeyEntry  # noqa: F401
