"""Shared enumerations used across the engine, the rule pack and the API.

Every member's value equals its name (``UPPER_SNAKE``), so YAML files and JSON payloads use the same
spelling as the code.
"""

from enum import StrEnum

__all__ = [
    "AccountType",
    "Appellant",
    "BasisStatus",
    "Channel",
    "DayBasis",
    "Deontic",
    "EntityType",
    "FactSource",
    "IssueType",
    "LiabilityFault",
    "Outcome",
    "RuleStatus",
    "Verification",
]


class DayBasis(StrEnum):
    """How days are counted for a regulatory duration."""

    CALENDAR = "CALENDAR"
    WORKING = "WORKING"


class BasisStatus(StrEnum):
    """Whether the instrument states the day basis or the research inferred it."""

    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"


class Verification(StrEnum):
    """Research verification grade of a rule or parameter (report grades P/S/U/C)."""

    PRIMARY_TEXT_READ = "PRIMARY_TEXT_READ"  # P: clause read in the primary text
    SECONDARY_ONLY = "SECONDARY_ONLY"  # S: secondary sources only
    UNVERIFIED = "UNVERIFIED"  # U: background knowledge, illegible source or single weak source
    CONFLICTING = "CONFLICTING"  # C: sources conflict


class RuleStatus(StrEnum):
    """Lifecycle status of an obligation. Only the owner sets ``IN_FORCE``."""

    DRAFT = "DRAFT"
    FUTURE_DATED = "FUTURE_DATED"
    IN_FORCE = "IN_FORCE"
    SUPERSEDED = "SUPERSEDED"
    REPEALED_BUT_SAVED = "REPEALED_BUT_SAVED"


class Deontic(StrEnum):
    """Deontic type of an obligation: must, must not, or may."""

    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"
    PERMISSION = "PERMISSION"


class Outcome(StrEnum):
    """The only three complaint outcomes allowed by IO Directions 2026 cl. 14(2) (report A14)."""

    FULLY_RESOLVED = "FULLY_RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    WHOLLY_REJECTED = "WHOLLY_REJECTED"


class EntityType(StrEnum):
    """Regulated-entity type, used for applicability profiles (report A12 and open question Q2)."""

    COMMERCIAL_BANK = "COMMERCIAL_BANK"
    SMALL_FINANCE_BANK = "SMALL_FINANCE_BANK"
    PAYMENTS_BANK = "PAYMENTS_BANK"
    LOCAL_AREA_BANK = "LOCAL_AREA_BANK"
    REGIONAL_RURAL_BANK = "REGIONAL_RURAL_BANK"
    COOPERATIVE_BANK = "COOPERATIVE_BANK"
    NBFC = "NBFC"
    PPI_ISSUER = "PPI_ISSUER"
    CREDIT_INFORMATION_COMPANY = "CREDIT_INFORMATION_COMPANY"
    OTHER = "OTHER"


class Channel(StrEnum):
    """Payment channel of a transaction, as in the failed-transaction TAT annex (report B1/B2)."""

    UPI_P2P = "UPI_P2P"
    UPI_MERCHANT = "UPI_MERCHANT"
    IMPS = "IMPS"
    ATM = "ATM"
    MICRO_ATM = "MICRO_ATM"
    CARD_TO_CARD = "CARD_TO_CARD"
    POS_CARD_PRESENT = "POS_CARD_PRESENT"
    CARD_NOT_PRESENT = "CARD_NOT_PRESENT"
    AEPS_MERCHANT = "AEPS_MERCHANT"
    """AePS at a merchant (shop) location; its own annex row (report B1)."""
    AEPS_BENEFICIARY = "AEPS_BENEFICIARY"
    """AePS fund transfer to a beneficiary; its own annex row (report B2)."""
    APBS = "APBS"
    NACH = "NACH"
    PPI_ON_US = "PPI_ON_US"
    PPI_OFF_US = "PPI_OFF_US"
    OTHER = "OTHER"


class AccountType(StrEnum):
    """Account categories that select the customer-liability cap (RBC-CB paras 67-71, report B5).

    The caps themselves are rule-pack parameters, never constants in code.
    """

    BSBD = "BSBD"
    """Basic savings bank deposit account."""
    OTHER_SAVINGS = "OTHER_SAVINGS"
    """Savings accounts other than BSBD."""
    PPI = "PPI"
    """Prepaid payment instruments."""
    GIFT_CARD = "GIFT_CARD"
    """Gift cards."""
    MSME_CURRENT_CASH_CREDIT_OD = "MSME_CURRENT_CASH_CREDIT_OD"
    """Current, cash-credit and overdraft accounts of MSMEs."""
    INDIVIDUAL_CURRENT_CASH_CREDIT_OD_SMALL = "INDIVIDUAL_CURRENT_CASH_CREDIT_OD_SMALL"
    """Individuals' current, cash-credit and overdraft accounts up to the ₹25 lakh limit (B5)."""
    CREDIT_CARD_SMALL_LIMIT = "CREDIT_CARD_SMALL_LIMIT"
    """Credit cards with a limit up to ₹5 lakh (B5)."""
    OTHER_CURRENT_CASH_CREDIT_OD = "OTHER_CURRENT_CASH_CREDIT_OD"
    """All other current, cash-credit and overdraft accounts."""
    CREDIT_CARD_LARGE_LIMIT = "CREDIT_CARD_LARGE_LIMIT"
    """Credit cards with a limit above ₹5 lakh (B5)."""


class FactSource(StrEnum):
    """Who asserted a fact: a person, a bank system feed, or an LLM extraction."""

    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    LLM = "LLM"


class IssueType(StrEnum):
    """What kind of transaction problem a complaint raises; selects the B-table rules that apply.

    Open to more members as the rule pack grows.
    """

    FAILED_TRANSACTION = "FAILED_TRANSACTION"
    """Failed or partly failed transaction (TAT circular, report B1/B2)."""
    UNAUTHORISED_TRANSACTION = "UNAUTHORISED_TRANSACTION"
    """Unauthorised electronic transaction (RBC-CB paras 66-73, report B5-B7)."""
    FRAUDULENT_TRANSACTION = "FRAUDULENT_TRANSACTION"
    """Other fraudulent transactions, as covered by report row B10."""
    OTHER = "OTHER"
    """Any other complaint; no transaction rule is selected by it."""


class LiabilityFault(StrEnum):
    """Whose fault an unauthorised transaction was (RBC-CB paras 67-70, report B5).

    Only a person sets this fact; an LLM never does (CLAUDE.md hard rule 4).
    """

    BANK = "BANK"
    THIRD_PARTY = "THIRD_PARTY"
    """Neither the bank nor the customer: the fault lies elsewhere in the system."""
    CUSTOMER = "CUSTOMER"


class Appellant(StrEnum):
    """Who filed an appeal against an Ombudsman award or decision (RB-IOS 2026 cl. 17, A8)."""

    BANK = "BANK"
    COMPLAINANT = "COMPLAINANT"
