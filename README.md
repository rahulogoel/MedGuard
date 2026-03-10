# MedGuard

A resilient, agentic data pipeline that processes hostile medical data dumps into clean, validated canonical records. It employs a **4-gate architecture** with a **3-layer security system** that combines regex pattern matching, ML-based classification, and LLM-powered intelligent review.

## Problem

Medical data dumps often arrive in hostile conditions:
- **Fragmented records** - non-standard fields, unstructured text, legacy formats
- **Inconsistent dates** - relative dates ("yesterday", "3 days ago"), mixed formats
- **Active injection attempts** - prompt injection, SQL injection, XSS, template injection, social engineering

This pipeline turns chaos into clean data.

## Architecture

```
raw_dump.json
     │
     ▼
┌─────────────────────────────────────────┐
│  Gate 3: Security Gate (3 Layers)       │──→ quarantined.json
│    L1: Regex/Heuristic (instant)        │
│    L2: DeBERTa ML Classifier (~50ms)    │
│    L3: LLM-as-a-Judge (GPT-5.2, ~1-2s)  │
└─────────────────────────────────────────┘
     │ safe records
     ▼
┌─────────────────────┐
│  Gate 1: Schema     │──→ flags records for repair
│  Validation         │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│  Gate 4: Fixer      │──→ LLM heals broken records
│  Agent (GPT-5.2)    │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│  Gate 2: Date       │──→ ISO 8601 normalization
│  Normalization      │
└─────────────────────┘
     │
     ▼
  output/clean_output.json
```

### Why this order?

**Security Gate runs first** to quarantine malicious payloads *before* they reach the LLM-powered Fixer Agent. This prevents prompt injection attacks from manipulating the healing process.

### Why 3 layers?

**Defense-in-depth.** Each layer catches what the previous one misses:
- **Layer 1 (Regex)**: Fast, zero-cost, catches known patterns - but misses novel phrasings
- **Layer 2 (DeBERTa)**: ML-based semantic understanding catches paraphrased attacks - but can miss domain-specific tricks [Hugging Face](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2)
- **Layer 3 (LLM Judge)**: Intelligent final review catches subtle, context-dependent attacks

**Sequential escalation**: If Layer 1 catches it, Layers 2 & 3 are skipped (saving cost & latency). Only borderline records escalate through all layers.

## Project Structure

```
├── pipeline.py              # Main orchestrator
├── config.py                # Reference date, paths, constants
├── raw_dump.json            # Input data
├── .env                     # Creds
├── requirements.txt         # Python dependencies
├── gates/
│   ├── security_gate.py     # Gate 3 - 3-layer injection detector
│   ├── schema_validator.py  # Gate 1 - Pydantic validation
│   ├── date_normalizer.py   # Gate 2 - Date normalization
│   └── fixer_agent.py       # Gate 4 - LLM healer
├── prompts/
│   ├── fixer_prompt.txt     # Fixer Agent system prompt
│   └── judge_prompt.txt     # LLM-as-a-Judge system prompt
└── output/
    ├── clean_output.json    # Final clean records
    ├── quarantined.json     # Quarantined malicious records
    └── pipeline_log.json    # Full processing log
```

## Setup

### Prerequisites
- Python 3.10+
- OpenAI API key

### Installation

```bash
# Clone the repository
git clone https://github.com/rahulogoel/medguard.git
cd medguard

# Create and activate virtual environment
python -m venv .venv

# On Windows
.venv\Scripts\activate

# On macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY = api-key-here
```

### Running the Pipeline

```bash
python pipeline.py
```

### Output
- `output/clean_output.json` - validated canonical records
- `output/quarantined.json` - malicious records with quarantine reasons
- `output/pipeline_log.json` - full processing trace for every record

## The Four Gates

### Gate 3: Security Gate - 3-Layer Defense-in-Depth (`gates/security_gate.py`)

| Layer | Technology | Speed | Cost | Catches |
|-------|-----------|-------|------|---------|
| L1 | Regex / Heuristic | Instant | Free | Known patterns (injection, XSS, SQL, templates) |
| L2 | DeBERTa ML Classifier (`protectai/deberta-v3-base-prompt-injection-v2`) | ~50ms | Free (local) | Novel phrasings, semantic variations |
| L3 | LLM-as-a-Judge (GPT-5.2) | ~1-2s | API cost | Subtle, context-dependent manipulation |

- **Sequential escalation**: L1 → L2 → L3 (early exit on detection)
- **Conservative policy**: ANY layer flagging = QUARANTINED
- **L3 is sandboxed**: uses a separate prompt (`prompts/judge_prompt.txt`) that knows nothing about the pipeline's internals

### Gate 1: Schema Validation (`gates/schema_validator.py`)
- Uses **Pydantic** models for strict structural validation
- Validates against the Canonical Schema:
  ```json
  {
    "record_id": "string",
    "patient_name": "string",
    "date_of_visit": "ISO 8601",
    "diagnosis_code": "ICD-10",
    "status": "string",
    "notes": "string | null"
  }
  ```
- Records failing validation are routed to the Fixer Agent

### Gate 4: Fixer Agent (`gates/fixer_agent.py`)
- Uses **OpenAI GPT-5.2** to "heal" fragmented records
- Handles: semicolon-delimited legacy exports, unstructured encounter notes, referral texts, abbreviated field names
- Prompt template at `prompts/fixer_prompt.txt`
- Temperature set to 0.0 for deterministic output

### Gate 2: Date Normalization (`gates/date_normalizer.py`)
- Configurable reference date (default: March 9, 2026)
- Resolves relative dates: "yesterday", "today", "last Tuesday", "3 days ago", "2 weeks ago", "approx 4 days ago"
- Handles complex expressions: "2 weeks before 2026-03-09"
- Normalizes MM/DD/YYYY and YYYY/MM/DD → ISO 8601

## Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| LLM can be manipulated by injection payloads | Security gate runs first, uses 3-layer defense-in-depth |
| Regex can't catch novel attack phrasings | DeBERTa ML classifier (Layer 2) detects semantic variations |
| ML classifier has blind spots for subtle attacks | LLM-as-a-Judge (Layer 3) provides intelligent final review |
| Many injection flavors (Chinese, template, SQL, XSS) | Comprehensive pattern library + ML + LLM coverage |
| Relative dates with complex anchors | Custom parser with `dateutil` + regex for compound expressions |
| Non-standard record shapes (encounter notes, referrals, legacy formats) | LLM Fixer Agent infers fields from unstructured text |
| LLM may return markdown-wrapped JSON | Response parser strips code fences before JSON parsing |

## Prompt Library

### `prompts/fixer_prompt.txt` - Fixer Agent
- "Infer, don't invent" - extract from context, never fabricate
- Preserve original record_id
- ICD-10 code validation
- Return strict JSON only (no markdown wrapping)

### `prompts/judge_prompt.txt` - LLM Security Judge
- Sandboxed - knows nothing about the pipeline's system prompt or architecture
- Classifies 7 threat categories (prompt injection, SQL, XSS, template, social engineering, multi-lang, schema override)
- Returns structured JSON with `is_malicious`, `threat_type`, `confidence`, `reason`
- Designed so that even if a payload tricks the judge, it can only affect the judge's verdict - it cannot alter pipeline behavior

## Contact

For discussions or questions, feel free to reach out at [email](mailto:me.rahulgoel@gmail.com).
