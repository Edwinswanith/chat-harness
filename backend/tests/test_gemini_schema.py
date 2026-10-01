from app.model_clients.gemini_client import GeminiModelClient
from app.tools.calculator import Calculator
from app.tools.tool_registry import ToolRegistry


def test_tool_schema_is_accepted_by_gemini_function_declaration():
    from google.genai import types

    tool = ToolRegistry([Calculator()]).describe()[0]
    schema = GeminiModelClient._gemini_schema(tool["parameters"])
    assert "additionalProperties" not in schema
    assert schema["properties"]["expression"] == {"type": "string"}
    declaration = types.FunctionDeclaration(name=tool["name"], description=tool["description"], parameters=schema)
    assert declaration.name == "calculator"


def test_workspace_tool_commentary_excludes_hidden_thoughts():
    from types import SimpleNamespace
    from app.schemas.contracts import ModelContext, MemoryBundle, RagContext
    model = GeminiModelClient('test-key', 'test-model')
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
        SimpleNamespace(text='Hidden reasoning', thought=True, function_call=None),
        SimpleNamespace(text='I’ll update the README and run tests.', thought=False, function_call=None),
        SimpleNamespace(text=None, thought=False, function_call=SimpleNamespace(name='workspace_patch_file', args={'relative_path': 'README.md'})),
    ]))], usage_metadata=None)
    model._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: response))
    context = ModelContext(request={'text': 'Edit README', 'mode': 'workspace'}, plan='Inspect, edit, test', memory=MemoryBundle(), rag=RagContext())
    decision = model._call_sync(context)
    assert decision.text == 'I’ll update the README and run tests.'
    assert 'Hidden reasoning' not in decision.text
    assert decision.kind == 'tool'
