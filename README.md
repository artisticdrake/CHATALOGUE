# 🎓 Chatalogue — University Course Assistant Chatbot



<p align="center">
  <b>A Local, ML-Powered, Multi-Stage NLP System for University Course Queries</b><br/>
  9-Stage Pipeline • Custom spaCy NER • ML Intent Classification • Deterministic SQL • RAG + LLM
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-black.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Platform-Windows%20-black" alt="Cross-platform" />
  <img src="https://img.shields.io/badge/NLP-spaCy%20%7C%20SentenceTransformers-black" alt="NLP Stack" />
  <img src="https://img.shields.io/badge/Database-SQLite-black" alt="SQLite" />
  <img src="https://img.shields.io/badge/LLM-GPT--4.1--mini%20-black" alt="GPT-4.1-mini" />
</p>

---

## 🌟 Overview

**Chatalogue** is a complete, local-first university course chatbot built around a sophisticated **9-stage modular NLP pipeline**. It answers student questions about courses, instructors, schedules, locations, and more through an intuitive conversational interface.

### What can Chatalogue do?

- **"Who teaches Data Mining?"** → Instructor lookup
- **"When does CS 521 meet and in which room?"** → Schedule + location retrieval
- **"Where does that class meet?"** → Contextual follow-up handling
- **"Who teaches Algorithms and when does Machine Learning meet?"** → Multi-course queries

### Key Features

✅ **Local-first architecture** — runs entirely offline except optional LLM enhancement  
✅ **Custom ML models** — trained spaCy NER + SentenceTransformers intent classifier  
✅ **Deterministic SQL generation** — safe, structured database queries  
✅ **Context-aware** — remembers conversation history for follow-up questions  
✅ **RAG-enhanced responses** — combines database results with LLM generation  
✅ **Tkinter GUI** — clean, responsive chat interface  

---

## 🧠 The 9-Stage NLP Pipeline

Chatalogue processes every query through a sophisticated 9-stage pipeline:

<p align="center">
  <img src="pipeline.png" width="100%" alt="Pipeline Diagram" />
</p>

### 🔵 NLP & Understanding (Stages 1–3)

**Stage 1: Intent Classification**
- ML-based classification using Logistic Regression + SentenceTransformers
- Determines user goal (course info, instructor lookup, schedule, location, etc.)
- Returns confidence scores and top-k predictions

**Stage 2: Semantic Parsing**
- Custom-trained spaCy NER model extracts entities
- Recognized entities: `COURSE_NAME`, `COURSE_CODE`, `INSTRUCTOR`, `BUILDING`, `TIME`, `WEEKDAY`, `SECTION`
- Multi-clause splitting: handles compound questions like "Who teaches DS and when does ML meet?"

**Stage 3: Context Handling**
- `ConversationContext` stores previous turns
- Resolves implicit references ("it", "that class", "the professor")
- Enables natural follow-up questions

### 🟠 Data Retrieval (Stages 4–7)

**Stage 4: Fuzzy Search**
- Maps course names → course codes using SQLite LIKE queries
- Handles variations: "deep learning" → "MET CS 767"

**Stage 5: SQL Generation**
- `process_semantic_query()` builds safe, parameterized SQL
- Handles multi-course and multi-attribute queries
- Packages queries into structured "subqueries"

**Stage 6: Database Execution**
- `run_query.handle_request()` executes SQL on SQLite database
- Supports fuzzy search mode and structured multi-subquery mode
- Returns results as lists of dictionaries

**Stage 7: Context Update**
- New results stored in conversation state
- Enables chained queries: "Who teaches it?" → "Where does it meet?"

### 🟢 Response Generation (Stages 8–9)

**Stage 8: RAG Prompt Construction**
- `chatalogue.rag_answer_with_db()` merges DB results with prompt template
- Produces context-enriched query for LLM
- Structures data for optimal LLM comprehension

**Stage 9: LLM Response**
- Uses OpenAI API with GPT-4.1-mini
- Generates natural, conversational answers
- **Fully optional** — system works without API key (SQL-only mode)

---

## 📁 Project Structure
```
project_root/
│
├── README.md                        # This file
├── requirements.txt                 # Python dependencies
├── mac_run.sh                       # macOS/Linux launch script
├── win_run.bat                      # Windows launch script
│
├── data/
│   ├── processed/                   # Processed data files
│   ├── raw/                         # Raw scraped data
│   └── courses_metcs.sqlite         # SQLite database with course data
│
├── db_info.py                       # Database inspection utility
│
├── debug/
│   ├── debug_query.py               # Query debugging tool
│   ├── debug.py                     # General debugging utilities
│   └── str.py                       # String processing helpers
│
├── models/
│   ├── intent/                      # Intent classification model files
│   └── ner/                         # Custom spaCy NER model files
│
├── src/
│   └── chatalogue/
│       ├── __init__.py
│       ├── chat_window.py           # Tkinter GUI
│       ├── chatalogue.py            # Main NLP engine & RAG
│       ├── semantic_parser.py       # NER + intent override logic
│       ├── intent_classifier.py     # ML classifier
│       ├── db_interface.py          # SQL generation layer
│       ├── run_query.py             # Database execution layer
│       ├── bu_scraper.py            # Course web scraper
│       ├── config.py                # Paths & constants
│       └── tempCodeRunnerFile.py    # Temporary execution file
│
├── testing/
│   └── test/
│       ├── full_test.py             # Full integration tests
│       ├── semantic_parser_test.py  # Parser unit tests
│       ├── test_bot_result.txt      # Test result logs
│       ├── test_chat.py             # Chat functionality tests
│       ├── test_chatalogue.py       # Core engine tests
│       ├── test_db_int.py           # Database interface tests
│       ├── TEST_EDGE_CASES.py       # Edge case testing
│       ├── test_intent.py           # Intent classifier tests
│       ├── test_run_q.py            # Query execution tests
│       ├── test_scraper.py          # Scraper tests
│       └── test_semantic_parser.py  # Additional parser tests
│
├── training/
│   └── utils/
│       ├── ner_augment.py           # NER data augmentation
│       ├── intent_train_model.py    # Intent model training script
│       └── ner_train_model.py       # NER model training script
│
└── pipeline.png                     # Pipeline diagram
```
---

## ⚙️ Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- SQLite (included with Python)

### Setup Steps

1. **Clone the repository**
```bash
   git clone https://github.com/artisticdrake/Chatalogue.git
   cd Chatalogue
```

2. **Install dependencies**
```bash
   pip install -r requirements.txt
```

3. **Verify required files exist**
   - `data/courses_metcs.sqlite` — Course database
   - `models/intent/intent_model.joblib` — Intent classifier
   - `models/ner/course_ner_model/` — Custom NER model

4. **Configure OpenAI API**
```bash
   Set your environmental variable in your powershell using this command

   '$env:OPENAI_API_KEY = "your_api_key_here"'

```
   Without this, Chatalogue runs in SQL-only mode.

---

## 🚀 How to Run

### Windows (PowerShell)
```powershell
cd path/to/Chatalogue
$env:PYTHONPATH="src"
python -m chatalogue.chat_window
```

### macOS / Linux
```bash
chmod +x run.sh
./run.sh
```

**run.sh contents:**
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src"
python3 -m chatalogue.chat_window
```

---

## 💬 Example Queries

| User Query | System Action |
|------------|---------------|
| "Who teaches Data Mining?" | Intent → NER → SQL → Instructor name |
| "When does that class meet?" | Context resolution → SQL → Time & days |
| "Where does CS 544 meet?" | SQL lookup → Room & building |
| "Who teaches ML and when does DS meet?" | Multi-course split → iterative SQL → merged output |

---

## 🔍 Key Technical Components

### 🔹 Intent Classifier

**Location:** `src/chatalogue/intent_classifier.py`

- Uses **SentenceTransformers** (`all-MiniLM-L6-v2`) for text embeddings
- Trained **Logistic Regression** model
- Stored in: `models/intent_model.joblib`
- Outputs: predicted class, confidence score, top-k probabilities

### 🔹 Custom spaCy NER Model

**Location:** `models/course_ner_model/`

Recognizes the following entities:
- `COURSE_NAME` — "Data Mining", "Machine Learning"
- `COURSE_CODE` — "CS 521", "MET CS 767"
- `INSTRUCTOR` — "Prof. Smith", "Dr. Johnson"
- `BUILDING` — "CAS", "PSY", "MCS"
- `TIME` — "10:00", "18:00-20:45"
- `WEEKDAY` — "Monday", "Tue", "Wed"
- `SECTION` — "A1", "B2"

### 🔹 SQL Engine

**Components:**
- `db_interface.py` — Generates safe, parameterized SQL queries
- `run_query.py` — Executes queries against SQLite database
- Supports multi-subquery structures for complex multi-course questions
- Handles fuzzy matching and exact lookups

### 🔹 Tkinter GUI

**Location:** `src/chatalogue/chat_window.py`

Features:
- Clean, responsive chat interface
- Threaded message processing (non-blocking UI)
- Scrollable conversation history
- Action buttons: Save Chat, Clear, Test Query
- Real-time typing indicators

---

## 🧪 Testing

You can test individual components programmatically:
```python
from chatalogue.chatalogue import chat_loop

ctx = None
answer, ctx = chat_loop("Who teaches Data Mining?", ctx)
print(answer)

# Follow-up question
answer, ctx = chat_loop("When does it meet?", ctx)
print(answer)
```

---

## 🤖 RAG + LLM (Optional)

### With OpenAI API Key
If you configure an API key:
```bash
API_KEY = os.environ.get("OPENAI_API_KEY")
```

The system enhances database results with GPT-4.1-mini generated explanations for natural, conversational responses.

### Without API Key (SQL-Only Mode)
The system returns structured database results directly without LLM enhancement. Fully functional for all queries.

---

## 📦 Dependencies
```txt
openai>=1.0.0
requests
beautifulsoup4
numpy
spacy>=3.7.0
sentence-transformers>=2.2.0
joblib
tqdm
lxml
```

**Note:** Tkinter is included with Python on Windows/macOS. PyTorch installs automatically with `sentence-transformers`.

---

## 🛠️ Development Notes

### Running the Application
Always use the package entrypoint:
```bash
python -m chatalogue.chat_window
```
**Do not** run `.py` files directly.

### Code Structure
- Relative imports (`from . import ...`) are used throughout
- Database and model paths are centralized in `config.py`
- All modules are under `src/chatalogue/` package

### Extending the System
The modular architecture makes it easy to:
- Add new intents (modify `intent_classifier.py`)
- Expand NER entities (retrain `course_ner_model`)
- Add new database tables (update `db_interface.py`)
- Integrate new data sources (extend `bu_scraper.py`)

---


## 👨‍💻 Authors

**CS673 A1 Software Engineering (Fall 25) - GROUP 1**  


---

## 📄 Contributors

Repository and project content are maintained by the Chatalogue contributor.

---



<p align="center">
  <b>Built with ❤️ by students, for students</b><br/>
  <i>Making university information accessible through conversation</i>
</p>