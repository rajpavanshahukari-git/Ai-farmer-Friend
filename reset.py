"""Reset to a clean demo state: python -m app.database.reset  (run from backend/, with the server stopped).

Deletes the database, generated audio and uploaded photos; the demo farmer is re-seeded on next start.
"""
import shutil

from app.config.settings import AUDIO_DIR, DATABASE_URL, STORAGE_DIR, UPLOAD_DIR

if __name__ == "__main__":
    if DATABASE_URL.startswith("sqlite"):
        db_file = STORAGE_DIR / "farmer.db"
        db_file.unlink(missing_ok=True)
        print(f"removed {db_file}")
    else:
        print("Non-SQLite database: drop the tables yourself.")
    for d in (AUDIO_DIR, UPLOAD_DIR):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        print(f"cleared {d}")
    print("Done. Start the server to re-seed the demo farmer (Ravi, chilli, Guntur, Telugu).")
