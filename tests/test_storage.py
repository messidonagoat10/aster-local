import os

import pytest

from assistant_core.storage import Store


def test_chat_history_persists_in_order_and_can_be_deleted(tmp_path):
    store = Store(tmp_path / "assistant.sqlite3")
    store.initialize()
    conversation_id = "5c2fd25e-3485-48bf-83f4-69fda53661fb"

    store.add_message(conversation_id, "user", "Remember this conversation.")
    store.add_message(conversation_id, "assistant", "I have the recent context.")

    history = store.get_context(conversation_id, 20)
    assert [(message.role, message.content) for message in history] == [
        ("user", "Remember this conversation."),
        ("assistant", "I have the recent context."),
    ]
    assert store.list_conversations()[0]["message_count"] == 2

    store.delete_conversation(conversation_id)
    assert store.get_messages(conversation_id) == []


def test_saved_memories_are_editable_searchable_and_fully_deletable(tmp_path):
    store = Store(tmp_path / "assistant.sqlite3")
    store.initialize()
    memory_id = store.save_memory("My preferred editor is Visual Studio Code.")

    assert store.search_memories("Which editor do I prefer?") == [
        "My preferred editor is Visual Studio Code."
    ]
    store.save_memory("My preferred editor is Neovim.", memory_id)
    assert store.search_memories("preferred editor") == ["My preferred editor is Neovim."]

    store.forget_everything()
    assert store.list_memories() == []
    assert store.list_conversations() == []


def test_local_notes_tasks_settings_and_approved_folders(tmp_path):
    store = Store(tmp_path / "assistant.sqlite3")
    store.initialize()
    folder = tmp_path / "documents"
    folder.mkdir()
    normalized = store.add_approved_folder(str(folder))
    assert store.list_approved_folders() == [normalized]

    item_id = store.create_item("todo", "Review draft", "Check the opening", "2026-06-01T12:00:00Z")
    assert store.search_items("todo", "draft")[0]["id"] == item_id
    assert store.complete_item(item_id) is True
    assert store.list_items()[0]["completed"] == 1

    store.set_setting("web_search_enabled", "false")
    assert store.get_setting("web_search_enabled") == "false"
    exported = store.export_data()
    assert exported["agenda"][0]["title"] == "Review draft"
    assert exported["approved_folders"][0]["path"] == normalized
    assert store.remove_approved_folder(normalized) is True
    store.forget_everything()
    assert store.list_items() == []
    assert store.list_approved_folders() == []
    assert store.get_setting("web_search_enabled") is None


def test_semantic_memory_embeddings_rank_by_cosine_similarity(tmp_path):
    store = Store(tmp_path / "assistant.sqlite3")
    store.initialize()
    first = store.save_memory("I prefer to write Python tools.")
    second = store.save_memory("I enjoy growing tomatoes.")
    store.save_memory_embedding(first, [1.0, 0.0, 0.0])
    store.save_memory_embedding(second, [0.0, 1.0, 0.0])

    assert store.search_memories_by_embedding([0.9, 0.1, 0.0]) == ["I prefer to write Python tools."]


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI database protection is Windows-only.")
def test_database_can_be_encrypted_disabled_and_reopened(tmp_path):
    path = tmp_path / "assistant.sqlite3"
    store = Store(path)
    store.initialize()
    conversation = "5c2fd25e-3485-48bf-83f4-69fda53661fb"
    store.add_message(conversation, "user", "private message payload")
    memory_id = store.save_memory("private remembered detail")
    store.save_memory_embedding(memory_id, [0.1, 0.2])

    store.enable_encryption()
    assert not path.exists()
    assert store.encrypted_path.exists()
    assert b"private message payload" not in store.encrypted_path.read_bytes()
    assert b"private remembered detail" not in store.encrypted_path.read_bytes()

    reopened = Store(path)
    reopened.initialize()
    assert reopened.encryption_status() == {"supported": True, "enabled": True}
    assert reopened.get_messages(conversation)[0]["content"] == "private message payload"
    assert reopened.search_memories_by_embedding([0.1, 0.2]) == ["private remembered detail"]
    reopened.disable_encryption()
    assert path.exists()
    assert not reopened.encrypted_path.exists()

