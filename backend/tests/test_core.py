from datetime import date
import pytest
from pydantic import ValidationError

from app.main import BudgetInput, RecurringInput, TransactionInput, add_frequency


def test_amount_must_be_positive_integer_paise():
    with pytest.raises(ValidationError):
        TransactionInput(description="Lunch", amount_paise=0, type="expense", category_id="012345678901234567890123", transaction_date=date.today())


def test_transaction_requires_valid_type_and_date():
    with pytest.raises(ValidationError):
        TransactionInput(description="Lunch", amount_paise=1250, type="transfer", category_id="012345678901234567890123", transaction_date="not-a-date")


def test_budget_month_is_validated():
    with pytest.raises(ValidationError):
        BudgetInput(category_id="012345678901234567890123", amount_paise=10000, period_month=13, period_year=2025)


def test_recurring_month_end_advances_without_invalid_date():
    assert add_frequency(date(2025, 1, 31), "monthly") == date(2025, 2, 28)


def test_weekly_and_yearly_recurring_dates():
    assert add_frequency(date(2025, 2, 1), "weekly") == date(2025, 2, 8)
    assert add_frequency(date(2024, 2, 29), "yearly") == date(2025, 2, 28)
