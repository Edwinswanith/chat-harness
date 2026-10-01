ALLOWED = {
    "created": {"planning", "cancelled", "failed"},
    "planning": {"context_building", "inspecting_workspace", "failed", "cancelled"},
    "inspecting_workspace": {"designing", "coding", "failed", "cancelled"},
    "designing": {"coding", "failed", "cancelled"},
    "coding": {"model_running", "building", "failed", "cancelled"},
    "context_building": {"model_running", "inspecting_workspace", "failed", "cancelled"},
    "model_running": {"tool_running", "subagent_running", "validating", "failed", "cancelled"},
    "tool_running": {"validating", "failed", "cancelled"},
    "subagent_running": {"model_running", "failed", "cancelled"},
    "validating": {"model_running", "building", "repairing", "completed", "failed", "cancelled"},
    "building": {"rendering", "repairing", "failed", "cancelled"},
    "rendering": {"visual_validating", "repairing", "failed", "cancelled"},
    "visual_validating": {"model_running", "repairing", "final_review", "failed", "cancelled"},
    "final_review": {"completed", "failed", "cancelled"},
    "repairing": {"model_running", "coding", "failed", "cancelled"},
}


def transition_allowed(current: str, target: str) -> bool:
    return current not in {"completed", "failed", "cancelled"} and target in ALLOWED.get(current, set())
