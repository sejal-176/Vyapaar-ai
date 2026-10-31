"""SQLAlchemy models for Growth Insights preview (growth_demo.db).
Kept completely isolated from core VyapaarAI models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship

GrowthBase = declarative_base()


class GDCustomer(GrowthBase):
    __tablename__ = "gd_customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payer_token = Column(String, nullable=False, unique=True, index=True)
    consent_status = Column(String, nullable=False, default="NONE")  # NONE, OPTED_IN

    invoices = relationship("GDInvoice", back_populates="customer")
    outreach = relationship("GDOutreach", back_populates="customer")


class GDProduct(GrowthBase):
    __tablename__ = "gd_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False)
    price_paise = Column(Integer, nullable=False)
    cost_price_paise = Column(Integer, nullable=True)
    stock_on_hand = Column(Integer, nullable=False, default=0)
    stock_updated_on = Column(String, nullable=False)

    invoice_items = relationship("GDInvoiceItem", back_populates="product")


class GDInvoice(GrowthBase):
    __tablename__ = "gd_invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("gd_customers.id"), nullable=True, index=True)
    invoice_date = Column(String, nullable=False, index=True)
    total_paise = Column(Integer, nullable=False)

    customer = relationship("GDCustomer", back_populates="invoices")
    items = relationship("GDInvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class GDInvoiceItem(GrowthBase):
    __tablename__ = "gd_invoice_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("gd_invoices.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("gd_products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price_paise = Column(Integer, nullable=False)

    invoice = relationship("GDInvoice", back_populates="items")
    product = relationship("GDProduct", back_populates="invoice_items")


class GDOutreach(GrowthBase):
    __tablename__ = "gd_outreach"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("gd_customers.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="DRAFT")  # DRAFT, APPROVED, MARKED_SENT, DISMISSED
    language = Column(String, nullable=False, default="en")    # en, hi, mr
    offer_type = Column(String, nullable=False, default="NONE") # NONE, LOYALTY_STAMP, PERCENT
    offer_pct = Column(Integer, nullable=False, default=0)
    message_text = Column(String, nullable=False)
    evidence_json = Column(String, nullable=False, default="{}")
    created_at = Column(String, nullable=False)
    approved_at = Column(String, nullable=True)
    marked_sent_at = Column(String, nullable=True)

    customer = relationship("GDCustomer", back_populates="outreach")

