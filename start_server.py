"""Start script for Anubis dashboard - sets env vars and runs uvicorn."""
import os
import sys

# Load GROQ_API_KEY from Windows user environment if not already set
if not os.environ.get("GROQ_API_KEY"):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            val, _ = winreg.QueryValueEx(key, "GROQ_API_KEY")
            os.environ["GROQ_API_KEY"] = val
    except FileNotFoundError:
        pass

import uvicorn
uvicorn.run("anubis.api.app:app", host="127.0.0.1", port=8484)
