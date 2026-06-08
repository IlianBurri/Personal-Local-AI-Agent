from core.database.sqlite_manager import SQLiteManager

db = SQLiteManager()

print("DB PATH:")
print(db.db_path)

print("Chats:")
print(db.get_chats())