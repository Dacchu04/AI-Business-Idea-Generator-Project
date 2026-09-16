# AI Business Idea Generator — Project 21 (Gemini)

Uses Google's Gemini API with the stable `gemini-3.1-flash-lite` model.

## Install
```powershell
pip install -r requirements.txt
```

## Run
```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_KEY"
python -m streamlit run app.py
```

Optional:
```powershell
$env:GEMINI_MODEL="gemini-3.1-flash-lite"
```

If the Gemini free-tier rate limit is reached, the app automatically falls back to Demo Mode.
Never commit or share a real API key.
