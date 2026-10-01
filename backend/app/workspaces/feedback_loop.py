"""Workspace failures are model feedback; failed mutations cannot be delivered."""
import json


MUTATIONS = {'generate_image', 'workspace_create_file', 'workspace_write_file', 'workspace_patch_file',
             'workspace_create_directory', 'workspace_rename_path', 'workspace_delete_path'}
COMMANDS = {'terminal_run_command', 'workspace_run_build', 'workspace_run_tests', 'workspace_run_lint'}


class WorkspaceFeedbackLoop:
    def __init__(self):
        self.attempts = 0
        self.pending = {}

    @staticmethod
    def target(name, arguments, result):
        if name in COMMANDS:
            command = result.data.get('command') or arguments.get('command') or {'workspace_run_build': 'npm run build', 'workspace_run_tests': 'npm test', 'workspace_run_lint': 'npm run lint'}.get(name, name)
            return (arguments.get('cwd_relative', '.'), command.strip())
        return result.data.get('path') or arguments.get('relative_path') or arguments.get('path') or '.'

    def failed(self, name, arguments, result):
        self.attempts += 1
        target = self.target(name, arguments, result)
        if name == 'generate_image' or result.data.get('code') in {'invalid_tool_arguments', 'command_not_allowed'}:
            self.pending[('arguments', name)] = result.error
        elif name in MUTATIONS:
            self.pending[('mutation', target)] = result.error
        elif name in COMMANDS:
            self.pending[('command', target)] = result.error
        return (f"Failed action {name}: {result.error or 'Tool validation failed'}. "
                "Correct the cause and continue the original task. Preserve completed work. "
                "For blocked operations choose an approved alternative; never bypass workspace restrictions. "
                "Use the latest read result and its sha256 for each edit. A failure is not a completed action.")

    def accepted(self, name, arguments, result):
        target = self.target(name, arguments, result)
        if name in MUTATIONS: self.pending.pop(('mutation', target), None)
        if name in COMMANDS:
            self.pending.pop(('command', target), None)
            # Both wrappers implement the same approved command capability.
            for alias in COMMANDS: self.pending.pop(('arguments', alias), None)
        self.pending.pop(('arguments', name), None)

    def final_feedback(self):
        if not self.pending: return ''
        return ('Final response rejected: failed actions remain unresolved. Repair them with tools before finalizing. '
                + json.dumps([{'kind': key[0], 'target': key[1], 'error': value} for key, value in self.pending.items()]))
