# VyapaarAI

> **"Python does the math and verification. The LLM only chooses tools and explains. A screenshot alone never proves a payment."**

VyapaarAI is an AI business partner designed for small shopkeepers (e.g., Sharma Tea Stall, Gupta Kirana Store) to manage, understand, and protect their digital collections.

---

## 1. Honest Scope Statement

- **Synthetic Data**: All transaction records, merchants, customer names, and UTRs are synthetic and generated for demonstration purposes.
- **Stand-in API**: The internal ledger lookup (`get_transaction`) stands in for a real Paytm merchant API. There is no live external Paytm API integration.
- **Internal Demo Cases**: Cases created in the app are internal demo tracking cases; nothing is submitted to Paytm, banks, or external payment gateways.
- **Stand-in Auth**: The merchant switcher in the header stands in for user authentication and provides cross-merchant data isolation.
- **Digital Collections Scope**: All numbers reflect recorded digital payments only. Cash collections and external business takings are outside this scope.

---

## 2. Key Capabilities

1. **Digital Collections Dashboard**: 4 key metric cards, 14-day Recharts trendline, recent transactions with status chips, and an ingestion quarantine report.
2. **AI Business Partner (Assistant)**: Natural language Q&A driven by tool-calling (`get_daily_summary`, `compare_periods`, `get_hourly_activity`, `get_payment_status`, `create_followup_case`). Python computes numbers and exact-sum volume vs. ticket effects. Fully resilient with a deterministic rule-based fallback if the LLM is unavailable.
3. **Screenshot Payment Verification**: Upload customer payment screenshots. OpenCV pre-processing and Tesseract OCR extract details, followed by an auditable 9-step deterministic decision table. No AI confidence scores or hallucinations.
4. **Dispute Cases & Daily Reports**: Track payment mismatches as internal cases with optimistic status updates, and generate pre-formatted daily business reports with downloadable `.txt` exports.

---

## 3. Windows Setup & Installation

### Prerequisites
- **Windows 10 / 11**
- **Python 3.12+**
- **Node.js 18+ & npm**
- **Tesseract OCR**:
  - Install Tesseract from the official UB-Mannheim installer: [UB-Mannheim Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
  - Default install directory: `C:\Program Files\Tesseract-OCR\tesseract.exe`

---

### Step 1: Clone & Create Python Virtual Environment
Open PowerShell in the project directory:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1
```

---

### Step 2: Install Python Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

Ensure `.env` contains the required settings:
```env
LLM_API_KEY=your_groq_api_key_here
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
DATABASE_URL=sqlite:///./vyapaar.db
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```
*(Note: If no LLM API key is provided, the assistant automatically and transparently operates in deterministic rule-based mode).*

---

### Step 4: Seed the Database
Generate 30 days of synthetic transaction history with intentional dirty rows to test validation and quarantine logging:

```powershell
python scripts/seed.py
```

---

### Step 5: Generate Test Screenshot Images
Generate synthetic test payment receipts across all verification test branches (clean match, wrong amount, unknown UTR, pending row, blur/rotation, prompt injection):

```powershell
python scripts/make_test_images.py
```

---

### Step 6: Run Tests & Verification
Run the backend pytest suite (all 56 tests):
```powershell
pytest backend/tests -q
```

Run OCR pipeline evaluation against the test images and database:
```powershell
python scripts/eval_ocr.py
```

---

### Step 7: Run Backend API Server
Start the FastAPI server on port 8000:

```powershell
python -m uvicorn backend.main:app --port 8000 --reload
```
API docs will be available at `http://localhost:8000/docs`.

---

### Step 8: Run Frontend Application
In a separate terminal window:

```powershell
cd frontend
npm install
npm run dev
```

Open your browser at `http://localhost:5173`.
To build for production:
```powershell
npm run build
```

---

## 4. Architectural Safeguards

- **Integer Paise Everywhere**: Floating-point types are strictly forbidden for currency. All arithmetic uses integer paise with Indian numbering formatting (`₹1,25,000.50`).
- **No Hallucinated Math**: The LLM is strictly prohibited from doing arithmetic. Volume vs. ticket size decomposition is computed in Python with an exact-sum guarantee.
- **Rule 8 Grounding**: *"A screenshot alone cannot prove payment. Verification is against the transaction record."*
- **Cross-Merchant Isolation**: Every SQL query and API route validates and filters by `merchant_id`. Merchant 1 cannot access or view Merchant 2's transactions, cases, or UTRs.

