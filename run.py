# run.py
import sys
from pathlib import Path

# Wir sagen Python explizit, dass es im Hauptverzeichnis suchen darf
root_dir = Path(__file__).parent.absolute()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    print("==================================================")
    print("        ARCA CORE CORE PIPELINE INITIALIZED   ")
    print("==================================================")
    
    from ui.web_app import start_web_ui
    
    print("\n[LAUNCH] Spin up Server on http://127.0.0.1:8765 ...")
    server = start_web_ui(host="127.0.0.1", port=8765, open_browser=True)
    
    print("[ONLINE] Odysseus Studio is now fully operational.\n")
    server.serve_forever()

except KeyboardInterrupt:
    print("\n[SHUTDOWN] Shutting down Odysseus gracefully.")
except Exception as e:
    print(f"\n[CRITICAL ERROR] Launch failed: {e}")
    import traceback
    traceback.print_exc()
    input("\nPress Enter to exit...")