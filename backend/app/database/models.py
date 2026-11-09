from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.connection import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_currency: Mapped[str] = mapped_column(String(3), default='INR', nullable=False)
    theme: Mapped[str] = mapped_column(String(8), default='light', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    categories: Mapped[list['Category']] = relationship(back_populates='user', cascade='all, delete-orphan')

class Category(Base):
    __tablename__ = 'categories'
    __table_args__ = (UniqueConstraint('user_id', 'type', 'name', name='uq_category_user_type_name'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user: Mapped[User] = relationship(back_populates='categories')

class Transaction(Base):
    __tablename__ = 'transactions'
    __table_args__ = (Index('ix_tx_user_date', 'user_id', 'transaction_date'), CheckConstraint("(type = 'income' AND category_id IS NULL) OR (type = 'expense' AND category_id IS NOT NULL)", name='ck_transaction_type_category'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='RESTRICT'), index=True, nullable=True)
    description: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), default='other', nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    merchant: Mapped[str | None] = mapped_column(String(120))
    occurrence_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    category: Mapped[Category | None] = relationship()

class Budget(Base):
    __tablename__ = 'budgets'
    __table_args__ = (UniqueConstraint('user_id', 'category_id', 'period_year', 'period_month', name='uq_budget_user_category_period'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id', ondelete='RESTRICT'), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    category: Mapped[Category] = relationship()

class RecurringTransaction(Base):
    __tablename__ = 'recurring_transactions'
    __table_args__ = (CheckConstraint("(type = 'income' AND category_id IS NULL) OR (type = 'expense' AND category_id IS NOT NULL)", name='ck_recurring_type_category'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='RESTRICT'), nullable=True)
    description: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    frequency: Mapped[str] = mapped_column(String(8), nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    next_due_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    category: Mapped[Category | None] = relationship()
