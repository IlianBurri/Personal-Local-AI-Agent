from core.database.sqlite_manager import SQLiteManager


class ChatRepository:

    def __init__(
        self,
        db: SQLiteManager
    ):
        self.db = db

    # --------------------
    # Chats
    # --------------------

    def create_chat(
        self,
        title="New Chat"
    ):
        return self.db.create_chat(
            title
        )

    def get_all_chats(self):
        return self.db.get_chats()

    def delete_chat(
        self,
        chat_id
    ):
        self.db.delete_chat(
            chat_id
        )

    def rename_chat(
        self,
        chat_id,
        title
    ):
        self.db.rename_chat(
            chat_id,
            title
        )

    # --------------------
    # Messages
    # --------------------

    def add_user_message(
        self,
        chat_id,
        content
    ):
        self.db.add_message(
            chat_id,
            "user",
            content
        )

    def add_assistant_message(
        self,
        chat_id,
        content
    ):
        self.db.add_message(
            chat_id,
            "assistant",
            content
        )

    def get_chat_messages(self, chat_id):
        return self.db.get_messages(chat_id)

    def delete_last_assistant_message(self, chat_id):
        return self.db.delete_last_assistant_message(chat_id)
