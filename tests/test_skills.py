from datetime import UTC, datetime

import pytest

from assistant_core.skills import (
    ParsedToolCall,
    SkillContext,
    SkillError,
    SkillRegistry,
    _calculate,
    create_builtin_registry,
    parse_tool_call,
)
from assistant_core.storage import Store


def _context(tmp_path):
    store = Store(tmp_path / "aster.sqlite3")
    store.initialize()
    return SkillContext(store=store, data_dir=tmp_path, clock=lambda: datetime(2026, 1, 2, tzinfo=UTC))


def test_registry_exposes_declared_permissions_and_omits_web_by_default(tmp_path):
    context = _context(tmp_path)
    registry = create_builtin_registry(context)

    assert "calculator" in registry.names()
    assert "files_search" in registry.names()
    assert "files_delete" in registry.names()
    assert "web_search" not in registry.names()
    skill, arguments, preview = registry.prepare(ParsedToolCall("note_create", {"title": "Plan", "content": "Call Alex"}))
    assert skill.permission == "confirm"
    assert preview == "Save note 'Plan' on this computer"
    with pytest.raises(SkillError, match="confirmation"):
        registry.execute(skill, context, arguments)
    assert registry.get("brightness_set").permission == "confirm"
    assert registry.get("apps_close").permission == "dangerous"


def test_web_search_is_not_registered_until_user_opt_in_and_still_requires_confirmation(tmp_path):
    context = _context(tmp_path)
    opted_in = SkillContext(store=context.store, data_dir=tmp_path, web_search_enabled=True)
    registry = create_builtin_registry(opted_in)
    skill, arguments, preview = registry.prepare(ParsedToolCall("web_search", {"query": "local weather"}))
    assert skill.permission == "dangerous"
    assert preview == "Send this query to DuckDuckGo: local weather"
    with pytest.raises(SkillError):
        registry.execute(skill, opted_in, arguments)


def test_timer_is_persisted_as_a_local_reminder_and_requires_confirmation(tmp_path):
    context = _context(tmp_path)
    registry = create_builtin_registry(context)
    skill, arguments, preview = registry.prepare(ParsedToolCall("timer_start", {"duration_seconds": 30, "label": "Tea"}))
    assert skill.permission == "confirm"
    assert "30 second timer" in preview
    with pytest.raises(SkillError):
        registry.execute(skill, context, arguments)
    result = registry.execute_confirmed(skill, context, arguments, confirmed=True)
    assert result["active"] is True
    assert context.store.list_items()[0]["title"] == "Tea"


def test_confirmed_note_creation_and_dangerous_file_delete_require_confirmation(tmp_path):
    context = _context(tmp_path)
    registry = create_builtin_registry(context)
    note, note_args, _ = registry.prepare(ParsedToolCall("note_create", {"title": "Plan", "content": "Call Alex"}))
    result = registry.execute_confirmed(note, context, note_args, confirmed=True)
    assert result["saved"] is True
    assert context.store.search_items("note", "Plan")

    root = tmp_path / "approved"
    root.mkdir()
    file_path = root / "draft.txt"
    file_path.write_text("draft", encoding="utf-8")
    context = SkillContext(store=context.store, data_dir=tmp_path, approved_roots=(root,))
    registry = create_builtin_registry(context)
    delete, arguments, preview = registry.prepare(ParsedToolCall("files_delete", {"path": str(file_path)}))
    assert delete.permission == "dangerous"
    assert str(file_path) in preview
    with pytest.raises(SkillError):
        registry.execute(delete, context, arguments)
    registry.execute_confirmed(delete, context, arguments, confirmed=True)
    assert not file_path.exists()


def test_file_access_rejects_unapproved_paths_and_symlink_escape(tmp_path):
    context = _context(tmp_path)
    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    link = inside / "link.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("Symlinks are unavailable in this Windows test environment.")
    context = SkillContext(store=context.store, data_dir=tmp_path, approved_roots=(inside,))
    registry = create_builtin_registry(context)
    with pytest.raises(SkillError, match="outside"):
        registry.prepare(ParsedToolCall("files_open", {"path": str(secret)}))
    with pytest.raises(SkillError, match="outside"):
        registry.prepare(ParsedToolCall("files_delete", {"path": str(link)}))
    assert secret.read_text(encoding="utf-8") == "private"


def test_tool_call_parser_rejects_duplicate_keys_and_unsupported_shell_tool(tmp_path):
    with pytest.raises(SkillError):
        parse_tool_call('{"name":"calculator","name":"shell","arguments":{}}')
    request = parse_tool_call('<tool_call>{"tool":"calculator","arguments":{"expression":"2+2"}}</tool_call>')
    assert request == ParsedToolCall("calculator", {"expression": "2+2"})
    with pytest.raises(SkillError, match="not available"):
        create_builtin_registry(_context(tmp_path)).get("shell_run")


def test_calculator_is_ast_limited_and_prompt_injection_is_not_executable():
    assert _calculate("sqrt(81) + 2 ** 3") == 17
    for expression in ["__import__('os').system('whoami')", "open('secret.txt').read()", "2 ** 100"]:
        with pytest.raises(SkillError):
            _calculate(expression)
