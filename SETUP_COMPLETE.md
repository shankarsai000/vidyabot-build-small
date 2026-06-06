# 🚀 VidyaBot Quick Launch Guide

## One-Click Setup Complete ✅

Your VidyaBot project is now fully configured with a fresh virtual environment and all dependencies installed!

---

## 📋 What Was Setup

### ✅ Virtual Environment (venv)
- **Path**: `./venv`
- **Python**: 3.14.2
- **Status**: Fresh, clean installation
- **All packages installed** from `backend/requirements.txt`

### ✅ VS Code Configuration
1. **Auto-Activation**: Terminal automatically activates venv when you open the project
2. **Python Interpreter**: Set to `venv/Scripts/python.exe`
3. **Launch Configurations**: Ready for debugging FastAPI backend
4. **Tasks**: Configured for common development tasks

---

## 🎯 Getting Started

### **Option 1: Start Backend Server (Recommended)**

**Method A - Using Tasks:**
1. Open Command Palette (`Ctrl+Shift+P`)
2. Search for: `Tasks: Run Task`
3. Select: **"Start Backend Server"**
4. Server runs on `http://localhost:8000`

**Method B - Using Run/Debug:**
1. Press `F5` or go to Run → Start Debugging
2. Select configuration: **"Python: FastAPI Backend"**
3. Server launches in debug mode

**Method C - Manual:**
```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### **Option 2: Run Tests**

```powershell
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_ingestion.py -v

# With coverage
pytest tests/ --cov=backend
```

### **Option 3: Access the Application**

After starting the backend:
- **Web App**: `http://localhost:8000`
- **API Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## 📁 Project Structure Reference

```
vidyabot/
├── venv/                    # ← Virtual environment (fresh!)
├── backend/
│   ├── main.py             # FastAPI app entry point
│   ├── requirements.txt     # Updated for Python 3.14
│   ├── ingestion/          # PDF parsing & chunking
│   ├── retrieval/          # 3-stage pruning pipeline
│   ├── llm/                # Claude API wrapper
│   ├── cache/              # Semantic cache
│   └── api/                # API routes
├── frontend/               # HTML/CSS/JS app
├── tests/                  # Unit tests
├── .vscode/
│   ├── settings.json       # ← VS Code settings (updated!)
│   ├── tasks.json         # ← Task definitions (NEW!)
│   └── launch.json        # ← Debug configs (NEW!)
└── .env                    # Environment variables
```

---

## ⚙️ Configuration Notes

### Environment Variables (`.env`)
Required keys:
```
ANTHROPIC_API_KEY=sk-your-key-here
```

Optional:
```
DATABASE_URL=sqlite:///data/vidyabot.db
PDF_UPLOAD_DIR=./data/textbooks
```

### Updated Requirements (`backend/requirements.txt`)
- **PyMuPDF**: Updated to 1.24.14 (latest compatible)
- **Numpy**: Flexible versioning (2.0+) for Python 3.14
- **Removed**: OpenAI Whisper (Python 3.14 incompatibility)

---

## 🔧 Troubleshooting

### Terminal not auto-activating venv?
→ Open new terminal or run: `.venv\Scripts\Activate.ps1`

### Python not recognized?
→ Restart VS Code. Settings should point to `venv/Scripts/python.exe`

### Port 8000 already in use?
→ Change in `backend/main.py` or run: `uvicorn main:app --port 8001`

### Package import errors?
→ Verify venv is active: Look for `(venv)` in terminal prompt

---

## 📚 Development Commands Cheat Sheet

```powershell
# Activate venv manually
.\venv\Scripts\Activate.ps1

# Install additional packages
pip install package-name

# Freeze current dependencies
pip freeze > backend/requirements.txt

# Run specific test file
pytest tests/test_cache.py -v

# Run with print statements visible
pytest tests/ -v -s

# Generate coverage report
pytest tests/ --cov=backend --cov-report=html
```

---

## 🎓 Next Steps

1. **Update `.env`**: Add your `ANTHROPIC_API_KEY`
2. **Add Textbooks**: Place PDFs in `data/textbooks/` or upload via UI
3. **Start Server**: Run "Start Backend Server" task (F5)
4. **Test It**: Open `http://localhost:8000` in browser
5. **Check API**: Visit `http://localhost:8000/docs` for interactive API explorer

---

## 📞 Support

For issues:
- Check `.vscode/settings.json` is properly configured
- Verify Python version: `python --version` (should be 3.14+)
- Check venv is activated: Should see `(venv)` in terminal
- Review backend logs for detailed error messages

**Happy coding! 🚀**
