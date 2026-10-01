from app.services.chat_service import ChatService


def test_current_attachment_does_not_inherit_thread_files():
    files = [{"id": "criminal", "name": "Criminal Appeal - Vadivel.pdf", "status": "indexed"},
             {"id": "divorce", "name": "Divorce Petition - Umapathy.pdf", "status": "indexed"}]
    scope, ids = ChatService._resolve_file_scope("Give me a draft of this case.", ["criminal"], files)
    assert (scope, ids) == ("current_message", ["criminal"])
    scope, ids = ChatService._resolve_file_scope("Give me a draft.", [], files)
    assert (scope, ids) == ("current_message", [])


def test_explicit_filename_and_all_files_intent_expand_scope_only_on_request():
    files = [{"id": "criminal", "name": "Criminal Appeal - Vadivel.pdf", "status": "indexed"},
             {"id": "divorce", "name": "Divorce Petition - Umapathy.pdf", "status": "indexed"}]
    assert ChatService._resolve_file_scope("Compare this with the Divorce Petition Umapathy.", [], files) == ("explicit_selected", ["divorce"])
    assert ChatService._resolve_file_scope("Use all uploaded files.", [], files) == ("thread", ["criminal", "divorce"])
