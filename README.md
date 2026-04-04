# 🧠 AI-Powered HR CV RAG System

A modern AI-driven HR platform that enables recruiters to **upload CVs, extract structured candidate data, perform semantic search, and ask intelligent questions** using LLMs and vector search.

---

## 🚀 Features

### 📤 CV Ingestion
- Upload **PDF or TXT resumes**
- Extract key information using AI:
  - Name, Email, Phone
  - Location
  - Years of Experience
  - Seniority Level
  - Role
  - Skills
- Automatically splits CVs into chunks for AI processing

### 🔍 Semantic Search
- Search candidates using **natural language job descriptions**
- Uses vector similarity (FAISS)
- Supports filters:
  - Seniority
  - Location
  - Role

### 💬 AI Q&A (RAG)
- Ask questions like:
  - *"Who has experience with AWS and Python?"*
- Answers are grounded in uploaded CVs
- Includes contextual references

### 📊 Dashboard
- View total candidates
- Monitor system activity
- Quick access to features

### 🎨 Modern UI
- Clean dashboard interface
- Sidebar navigation
- Drag & drop CV upload
- Real-time feedback

---

## 🏗️ Tech Stack

### Backend
- FastAPI
- FAISS (vector similarity search)
- OpenAI / OpenRouter API
- NumPy
- PyPDF

### Frontend
- HTML
- CSS
- JavaScript

---

## 📂 Project Structure

```
project/
│
├── main.py              # FastAPI backend
├── static/
│   └── index.html      # Frontend UI
├── requirements.txt
├── .env                # API keys
└── README.md
```

---

## ⚙️ Installation

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd project
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup environment variables

Create a `.env` file:

```env
OPENROUTER_API_KEY=your_api_key_here
```

---

## ▶️ Run the Application

```bash
uvicorn main:app --reload
```

### Access:
- API Docs: http://localhost:8000/docs
- Web App: http://localhost:8000

---

## 📡 API Endpoints

### 📤 Upload CVs
```http
POST /ingest
```
- Upload multiple CVs (max 20)

---

### 🔍 Search Candidates
```http
POST /search
```

Example:
```json
{
  "query": "Senior Python developer with AWS",
  "top_k": 5
}
```

---

### 💬 Ask Questions
```http
POST /qa
```

Example:
```json
{
  "question": "Who has machine learning experience?",
  "top_k": 5
}
```

---

## 🧠 How It Works

1. **Upload CVs**
   - Extract text
   - Parse structured data using AI

2. **Embedding**
   - Convert text into vector representations

3. **Storage**
   - Store vectors in FAISS index

4. **Search**
   - Convert query → vector → similarity search

5. **Q&A (RAG)**
   - Retrieve relevant data
   - Generate AI answer based on context

---

## ⚠️ Limitations

- Data stored in memory (resets on restart)
- No authentication system
- Depends on AI accuracy for parsing
- Not production-ready

---

## 🛠️ Future Improvements

- Add database (PostgreSQL / MongoDB)
- Persistent vector storage
- Authentication system
- Better CV parsing models
- Ranking improvements
- Docker & cloud deployment

---

## 👨‍💻 Author

Moamen Elsharkawy

---

## ⭐ Support

If you like this project, consider giving it a ⭐ on GitHub!