from core.database.sqlite_manager import SQLiteManager

db = SQLiteManager()

print("DB:", db.db_path)
print("Chats:", db.get_chats())
