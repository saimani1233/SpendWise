"""SpendWise API backed by a local SQLite database."""
from calendar import monthrange
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.database.connection import Base, SessionLocal, engine, get_db
from app.database.migrations import migrate_nullable_income_categories
from app.database.models import Budget, Category, RecurringTransaction, Transaction, User, utcnow

EXPENSE_CATEGORIES = ['Food', 'Shopping', 'Transportation', 'Rent', 'Bills', 'Healthcare', 'Entertainment', 'Education', 'Travel', 'Other']
bearer = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(_app):
    migrate_nullable_income_categories(engine)
    Base.metadata.create_all(bind=engine)
    if settings.demo_email and settings.demo_password:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == settings.demo_email))
            if user is None:
                user = User(name='Demo User', email=settings.demo_email, password_hash=hash_password(settings.demo_password))
                db.add(user)
                db.flush()
            existing = {(category.name, category.type) for category in db.scalars(select(Category).where(Category.user_id == user.id))}
            for name in EXPENSE_CATEGORIES:
                if (name, 'expense') not in existing:
                    db.add(Category(user_id=user.id, name=name, type='expense', is_system=True))
            db.commit()
    yield

app = FastAPI(title='SpendWise API', description='Personal finance API. Money amounts use integer paise.', version='2.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origins, allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['Authorization', 'Content-Type'])

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
class Register(Credentials):
    name: str = Field(min_length=2, max_length=80)
class ProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    preferred_currency: Literal['INR'] = 'INR'
    theme: Literal['light', 'dark'] = 'light'
class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
class TransactionInput(BaseModel):
    description: str = Field(min_length=1, max_length=120)
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    type: Literal['income', 'expense']
    category_id: Optional[str] = None
    transaction_date: date
    payment_method: Literal['card', 'cash', 'upi', 'bank_transfer', 'other'] = 'other'
    notes: Optional[str] = Field(default=None, max_length=500)
    merchant: Optional[str] = Field(default=None, max_length=120)
    @field_validator('description')
    @classmethod
    def clean_description(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Description is required')
        return value
    @model_validator(mode='after')
    def validate_expense_category(self):
        if self.type == 'expense' and not self.category_id:
            raise ValueError('Choose a category for an expense')
        if self.type == 'income':
            self.category_id = None
        return self
class BudgetInput(BaseModel):
    category_id: str
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    period_month: int = Field(ge=1, le=12)
    period_year: int = Field(ge=2020, le=2100)
class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    type: Literal['expense'] = 'expense'
    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Category name is required')
        return value
class RecurringInput(BaseModel):
    description: str = Field(min_length=1, max_length=120)
    amount_paise: int = Field(gt=0, le=100_000_000_000)
    type: Literal['income', 'expense']
    category_id: Optional[str] = None
    frequency: Literal['weekly', 'monthly', 'yearly']
    start_date: date
    next_due_date: date
    end_date: Optional[date] = None
    is_active: bool = True
    @model_validator(mode='after')
    def validate_expense_category(self):
        if self.type == 'expense' and not self.category_id:
            raise ValueError('Choose a category for an expense')
        if self.type == 'income':
            self.category_id = None
        return self


def public_user(user):
    return {'_id': str(user.id), 'name': user.name, 'email': user.email, 'preferred_currency': user.preferred_currency, 'theme': user.theme}
def as_date(value):
    return value.isoformat() if value else None
def category_out(category):
    return {'_id': str(category.id), 'user_id': str(category.user_id), 'name': category.name, 'type': category.type, 'is_system': category.is_system}
def transaction_out(item):
    return {'_id': str(item.id), 'description': item.description, 'amount_paise': item.amount_paise, 'type': item.type, 'category_id': str(item.category_id) if item.category_id is not None else None, 'category_name': item.category.name if item.category else 'Uncategorized', 'transaction_date': as_date(item.transaction_date), 'payment_method': item.payment_method, 'notes': item.notes, 'merchant': item.merchant}
def category_owned(db, user, category_id, kind=None):
    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        raise HTTPException(422, 'Choose a valid category')
    category = db.scalar(select(Category).where(Category.id == category_id, Category.user_id == user.id))
    if category is None or (kind and category.type != kind):
        raise HTTPException(422, 'Choose a category of the matching type')
    return category
def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials:
        raise HTTPException(401, 'Sign in to continue', headers={'WWW-Authenticate': 'Bearer'})
    subject = decode_access_token(credentials.credentials)
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise HTTPException(401, 'Your session is invalid or expired', headers={'WWW-Authenticate': 'Bearer'})
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, 'Your account could not be found')
    return user
def tx_query(db, user, kind=None, category_id=None, start_date=None, end_date=None, search=None):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if kind:
        stmt = stmt.where(Transaction.type == kind)
    if category_id:
        try:
            stmt = stmt.where(Transaction.category_id == int(category_id))
        except ValueError:
            raise HTTPException(422, 'Choose a valid category')
    if start_date:
        stmt = stmt.where(Transaction.transaction_date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.transaction_date <= end_date)
    if search:
        needle = f'%{search.strip()}%'
        stmt = stmt.outerjoin(Category).where(or_(Transaction.description.ilike(needle), Transaction.merchant.ilike(needle), Category.name.ilike(needle)))
    return stmt

def transaction_data(db, payload, user):
    category = category_owned(db, user, payload.category_id, 'expense') if payload.type == 'expense' else None
    data = payload.model_dump(exclude={'category_id'})
    return data | {'category_id': category.id if category else None}
def summary_for(db, user_id, start, end):
    rows = db.execute(select(Transaction.type, func.sum(Transaction.amount_paise), func.count(Transaction.id)).where(Transaction.user_id == user_id, Transaction.transaction_date >= start, Transaction.transaction_date < end).group_by(Transaction.type)).all()
    values = {'income_paise': 0, 'expenses_paise': 0, 'transaction_count': 0}
    for kind, amount, count in rows:
        values['income_paise' if kind == 'income' else 'expenses_paise'] = amount or 0
        values['transaction_count'] += count
    values['balance_paise'] = values['income_paise'] - values['expenses_paise']
    return values

@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': 'sqlite'}

@app.post('/api/auth/register', status_code=201)
def register(payload: Register, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'An account with this email already exists')
    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.flush()
        db.add_all([Category(user_id=user.id, name=name, type='expense', is_system=True) for name in EXPENSE_CATEGORIES])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with this email already exists')
    db.refresh(user)
    return {'access_token': create_access_token(str(user.id)), 'token_type': 'bearer', 'user': public_user(user)}

@app.post('/api/auth/login')
def login(payload: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, 'Email or password is incorrect')
    return {'access_token': create_access_token(str(user.id)), 'token_type': 'bearer', 'user': public_user(user)}

@app.get('/api/auth/me')
@app.get('/api/users/me')
def me(user=Depends(current_user)):
    return public_user(user)

@app.put('/api/users/me')
def update_profile(payload: ProfileUpdate, user=Depends(current_user), db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email, User.id != user.id)):
        raise HTTPException(409, 'That email address is already in use')
    user.name, user.email, user.preferred_currency, user.theme = payload.name.strip(), email, payload.preferred_currency, payload.theme
    db.commit()
    return public_user(user)

@app.put('/api/users/me/password')
def change_password(payload: PasswordUpdate, user=Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, 'Current password is incorrect')
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {'message': 'Password updated'}

@app.get('/api/transactions')
def get_transactions(type: Optional[Literal['income', 'expense']] = None, category_id: Optional[str] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, search: Optional[str] = Query(None, max_length=100), sort: Literal['date', 'amount'] = 'date', page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=100), user=Depends(current_user), db: Session = Depends(get_db)):
    stmt = tx_query(db, user, type, category_id, start_date, end_date, search)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    sort_col = Transaction.amount_paise if sort == 'amount' else Transaction.transaction_date
    items = db.scalars(stmt.order_by(sort_col.desc(), Transaction.id.desc()).offset((page - 1) * limit).limit(limit)).all()
    return {'items': [transaction_out(item) for item in items], 'total': total, 'page': page, 'limit': limit}

@app.post('/api/transactions', status_code=201)
def add_transaction(payload: TransactionInput, user=Depends(current_user), db: Session = Depends(get_db)):
    item = Transaction(user_id=user.id, **transaction_data(db, payload, user))
    db.add(item); db.commit(); db.refresh(item)
    return transaction_out(item)
@app.get('/api/transactions/{record_id}')
def get_transaction(record_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Transaction).where(Transaction.id == record_id, Transaction.user_id == user.id))
    if not item: raise HTTPException(404, 'Transaction not found')
    return transaction_out(item)
@app.put('/api/transactions/{record_id}')
def update_transaction(record_id: int, payload: TransactionInput, user=Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Transaction).where(Transaction.id == record_id, Transaction.user_id == user.id))
    if not item: raise HTTPException(404, 'Transaction not found')
    for key, value in transaction_data(db, payload, user).items(): setattr(item, key, value)
    db.commit(); db.refresh(item)
    return transaction_out(item)
@app.delete('/api/transactions/{record_id}')
def delete_transaction(record_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Transaction).where(Transaction.id == record_id, Transaction.user_id == user.id))
    if not item: raise HTTPException(404, 'Transaction not found')
    db.delete(item); db.commit()
    return {'message': 'Transaction deleted'}

@app.get('/api/categories')
def get_categories(user=Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Category).where(Category.user_id == user.id, Category.type == 'expense').order_by(Category.name)).all()
    return {'items': [category_out(item) for item in items]}
@app.post('/api/categories', status_code=201)
def add_category(payload: CategoryInput, user=Depends(current_user), db: Session = Depends(get_db)):
    item = Category(user_id=user.id, name=payload.name, type='expense')
    db.add(item)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'A category with this name and type already exists')
    db.refresh(item)
    return category_out(item)
@app.put('/api/categories/{record_id}')
def update_category(record_id: int, payload: CategoryInput, user=Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Category).where(Category.id == record_id, Category.user_id == user.id, Category.is_system.is_(False)))
    if not item: raise HTTPException(404, 'Custom category not found')
    item.name = payload.name
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'A category with this name and type already exists')
    return category_out(item)
@app.delete('/api/categories/{record_id}')
def delete_category(record_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    item = db.scalar(select(Category).where(Category.id == record_id, Category.user_id == user.id, Category.is_system.is_(False)))
    if not item: raise HTTPException(404, 'Custom category not found')
    in_use = db.scalar(select(Transaction.id).where(Transaction.category_id == item.id).limit(1)) or db.scalar(select(Budget.id).where(Budget.category_id == item.id).limit(1)) or db.scalar(select(RecurringTransaction.id).where(RecurringTransaction.category_id == item.id).limit(1))
    if in_use: raise HTTPException(409, 'This category is in use. Remove its associated records first.')
    db.delete(item); db.commit()
    return {'message': 'Category deleted'}

@app.get('/api/budgets')
def get_budgets(user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Budget).where(Budget.user_id == user.id).order_by(Budget.period_year.desc(), Budget.period_month.desc())).all()
    return {'items': [budget_out(db, row) for row in rows]}
def budget_out(db, row):
    start = date(row.period_year, row.period_month, 1)
    end = date(row.period_year + (row.period_month == 12), row.period_month % 12 + 1, 1)
    spent = db.scalar(select(func.sum(Transaction.amount_paise)).where(Transaction.user_id == row.user_id, Transaction.category_id == row.category_id, Transaction.type == 'expense', Transaction.transaction_date >= start, Transaction.transaction_date < end)) or 0
    return {'_id': str(row.id), 'category_id': str(row.category_id), 'category_name': row.category.name, 'amount_paise': row.amount_paise, 'period_month': row.period_month, 'period_year': row.period_year, 'spent_paise': spent, 'remaining_paise': row.amount_paise - spent, 'utilization_percent': round(spent / row.amount_paise * 100, 1)}
def budget_data(payload, user, db):
    cat = category_owned(db, user, payload.category_id, 'expense')
    return {'user_id': user.id, 'category_id': cat.id, 'amount_paise': payload.amount_paise, 'period_month': payload.period_month, 'period_year': payload.period_year}
@app.post('/api/budgets', status_code=201)
def add_budget(payload: BudgetInput, user=Depends(current_user), db: Session = Depends(get_db)):
    row = Budget(**budget_data(payload, user, db)); db.add(row)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'A budget already exists for this category and month')
    db.refresh(row)
    return budget_out(db, row)
@app.put('/api/budgets/{record_id}')
def update_budget(record_id: int, payload: BudgetInput, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(Budget).where(Budget.id == record_id, Budget.user_id == user.id))
    if not row: raise HTTPException(404, 'Budget not found')
    for key, value in budget_data(payload, user, db).items():
        if key != 'user_id': setattr(row, key, value)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'A budget already exists for this category and month')
    return budget_out(db, row)
@app.delete('/api/budgets/{record_id}')
def delete_budget(record_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(Budget).where(Budget.id == record_id, Budget.user_id == user.id))
    if not row: raise HTTPException(404, 'Budget not found')
    db.delete(row); db.commit(); return {'message': 'Budget deleted'}

@app.get('/api/recurring')
def get_recurring(user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(RecurringTransaction).where(RecurringTransaction.user_id == user.id).order_by(RecurringTransaction.next_due_date)).all()
    return {'items': [recurring_out(row) for row in rows]}
def recurring_out(row):
    return {'_id': str(row.id), 'category_id': str(row.category_id) if row.category_id is not None else None, 'category_name': row.category.name if row.category else 'Uncategorized', 'description': row.description, 'amount_paise': row.amount_paise, 'type': row.type, 'frequency': row.frequency, 'start_date': as_date(row.start_date), 'next_due_date': as_date(row.next_due_date), 'end_date': as_date(row.end_date), 'is_active': row.is_active}
def recurring_data(payload, user, db):
    cat = category_owned(db, user, payload.category_id, 'expense') if payload.type == 'expense' else None
    return payload.model_dump(exclude={'category_id'}) | {'user_id': user.id, 'category_id': cat.id if cat else None}
@app.post('/api/recurring', status_code=201)
def add_recurring(payload: RecurringInput, user=Depends(current_user), db: Session = Depends(get_db)):
    row = RecurringTransaction(**recurring_data(payload, user, db)); db.add(row); db.commit(); db.refresh(row); return recurring_out(row)
@app.put('/api/recurring/{record_id}')
def update_recurring(record_id: int, payload: RecurringInput, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(RecurringTransaction).where(RecurringTransaction.id == record_id, RecurringTransaction.user_id == user.id))
    if not row: raise HTTPException(404, 'Recurring transaction not found')
    for key, value in recurring_data(payload, user, db).items():
        if key != 'user_id': setattr(row, key, value)
    db.commit(); db.refresh(row); return recurring_out(row)
@app.delete('/api/recurring/{record_id}')
def delete_recurring(record_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(RecurringTransaction).where(RecurringTransaction.id == record_id, RecurringTransaction.user_id == user.id))
    if not row: raise HTTPException(404, 'Recurring transaction not found')
    db.delete(row); db.commit(); return {'message': 'Recurring transaction deleted'}

def add_frequency(d: date, frequency: str):
    if frequency == 'weekly': return d + timedelta(days=7)
    if frequency == 'yearly':
        year = d.year + 1
        return date(year, d.month, min(d.day, monthrange(year, d.month)[1]))
    month = d.month % 12 + 1; year = d.year + (d.month == 12)
    return date(year, month, min(d.day, monthrange(year, month)[1]))
@app.post('/api/recurring/process-due')
def process_due(user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    rows = db.scalars(select(RecurringTransaction).where(RecurringTransaction.user_id == user.id, RecurringTransaction.is_active.is_(True), RecurringTransaction.next_due_date <= today)).all()
    created = 0
    for row in rows:
        while row.next_due_date <= today:
            due = row.next_due_date
            if row.end_date and due > row.end_date:
                row.is_active = False; break
            exists = db.scalar(select(Transaction.id).where(Transaction.occurrence_key == f'{row.id}:{due.isoformat()}'))
            if not exists:
                db.add(Transaction(user_id=user.id, category_id=row.category_id, description=row.description, amount_paise=row.amount_paise, type=row.type, transaction_date=due, payment_method='other', notes='Generated from recurring transaction', occurrence_key=f'{row.id}:{due.isoformat()}'))
                created += 1
            row.next_due_date = add_frequency(due, row.frequency)
            if row.end_date and row.next_due_date > row.end_date: row.is_active = False
    db.commit()
    return {'created': created, 'message': f'Processed {created} due occurrence(s).'}

@app.get('/api/analytics/summary')
def analytics_summary(user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); start = date(today.year, today.month, 1)
    pm = today.month - 1 or 12; py = today.year if today.month > 1 else today.year - 1
    previous = date(py, pm, 1); end = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    current = summary_for(db, user.id, start, end); prior = summary_for(db, user.id, previous, start)
    for metric, key in [('income', 'income_paise'), ('expense', 'expenses_paise')]:
        base = prior[key]; current[f'{metric}_change'] = round((current[key] - base) / base * 100) if base else None
    current['period'] = {'start': start.isoformat(), 'end': (end - timedelta(days=1)).isoformat()}
    return current
@app.get('/api/analytics/trends')
def analytics_trends(start_date: date | None = None, end_date: date | None = None, months: int = Query(6, ge=1, le=24), user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); end_day = end_date or today
    first_month = start_date or (date(today.year, today.month, 1) - timedelta(days=30 * (months - 1)))
    first = date(first_month.year, first_month.month, 1)
    rows = db.execute(select(Transaction.type, func.sum(Transaction.amount_paise), Transaction.transaction_date).where(Transaction.user_id == user.id, Transaction.transaction_date >= first, Transaction.transaction_date <= end_day).group_by(Transaction.type, Transaction.transaction_date)).all()
    buckets = {}
    for kind, amount, tx_date in rows:
        key = tx_date.strftime('%Y-%m'); bucket = buckets.setdefault(key, {'month': key, 'income_paise': 0, 'expenses_paise': 0})
        bucket['income_paise' if kind == 'income' else 'expenses_paise'] += amount or 0
    return {'items': [buckets[key] for key in sorted(buckets)]}
@app.get('/api/analytics/categories')
def analytics_categories(start_date: date | None = None, end_date: date | None = None, user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); start = start_date or date(today.year, today.month, 1); end = end_date or today
    rows = db.execute(select(Category.name, func.sum(Transaction.amount_paise)).join(Transaction, Transaction.category_id == Category.id).where(Transaction.user_id == user.id, Transaction.type == 'expense', Transaction.transaction_date >= start, Transaction.transaction_date <= end).group_by(Category.name).order_by(func.sum(Transaction.amount_paise).desc())).all()
    return {'items': [{'category': name, 'amount_paise': amount or 0} for name, amount in rows]}
@app.get('/api/reports/monthly')
def monthly_report(year: int | None = Query(None, ge=2000, le=2100), month: int | None = Query(None, ge=1, le=12), user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    selected_year, selected_month = year or today.year, month or today.month
    start = date(selected_year, selected_month, 1)
    end = date(selected_year + (selected_month == 12), selected_month % 12 + 1, 1)
    totals = summary_for(db, user.id, start, end)
    rows = db.execute(select(Category.name, func.sum(Transaction.amount_paise)).join(Transaction, Transaction.category_id == Category.id).where(Transaction.user_id == user.id, Transaction.type == 'expense', Transaction.transaction_date >= start, Transaction.transaction_date < end).group_by(Category.name).order_by(Category.name)).all()
    categories = [{'category': name, 'type': 'expense', 'amount_paise': amount or 0} for name, amount in rows]
    return {'period': {'year': selected_year, 'month': selected_month, 'start': start.isoformat(), 'end': (end - timedelta(days=1)).isoformat()}, 'summary': totals, 'categories': categories}
@app.get('/api/analytics/comparison')
def analytics_comparison(user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date(); start = date(today.year, today.month, 1)
    pm = today.month - 1 or 12; py = today.year if today.month > 1 else today.year - 1
    previous_start = date(py, pm, 1)
    return {'current': summary_for(db, user.id, start, today + timedelta(days=1)), 'previous': summary_for(db, user.id, previous_start, start)}
