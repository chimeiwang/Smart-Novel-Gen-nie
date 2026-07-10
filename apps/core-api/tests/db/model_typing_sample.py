from inkforge_core.db.models import User
from sqlalchemy import Select, select


def user_lookup(identifier: str, username: str) -> Select[tuple[User]]:
    return select(User).where(User.id == identifier, User.username == username)


def new_user() -> User:
    return User(username="静态类型示例", passwordHash="静态类型示例")
