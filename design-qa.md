# Workspace execution transcript QA

final result: passed

## Scope and source visual truth

User references:
- `/tmp/codex-clipboard-4e68b399-6b91-4fc1-b1b7-185b0ca7e861.png`: progress prose interleaved with collapsible action groups.
- `/tmp/codex-clipboard-a5c9f337-6d06-4f5a-9867-cae92bbacd17.png`: expanded Shell panel and success footer.

The requested scope is the Workspace conversation's processing messages and execution rows. Existing Harness branding, navigation, project explorer, routes, and backend permissions are retained; this is not a clone of unrelated Codex account and project controls.

## Evidence and normalization

- Desktop implementation: `docs/qa/workspace-execution/desktop.png`, 1679 × 903 CSS/pixel viewport, density 1.
- Final desktop capture after the mobile composer refinement: `docs/qa/workspace-execution/desktop-final.png`, same 1679 × 903 viewport.
- Mobile implementation: `docs/qa/workspace-execution/mobile.png`, 390 × 844 CSS/pixel viewport, density 1.
- Full desktop comparison: `docs/qa/workspace-execution/full-comparison.png`, source and implementation at equal 1679 × 903 dimensions.
- Final focused Shell comparison after composer refinement: `docs/qa/workspace-execution/command-comparison-final.png`.
- Focused Shell comparison: `docs/qa/workspace-execution/command-comparison.png`; implementation command region scaled proportionally to the 763px-wide source crop. Full-resolution source and implementation were opened before comparison.
- State: completed execution, final action group expanded and command output visible.
- Test data is isolated in a temporary local SQLite harness. Model decisions are scripted; folder/file mutations, protected patching, terminal execution, persistence, SSE, and React rendering are real.

## Comparison history

1. Initial desktop capture `/tmp/harness-transcript-preview/screenshots/desktop.png` exposed a P2 layout problem: expanded execution pushed the composer below the viewport.
2. Fixed the Workspace shell height and made the conversation scroll independently. Added scroll-follow behavior that stops when the user scrolls back.
3. Re-captured at the same desktop viewport and expanded command state (`desktop.png`), and compared the source and implementation together (`full-comparison.png` and `command-comparison.png`). The composer is visible and the expanded Shell panel retains its output and result footer.

4. Mobile capture exposed an overlong composer placeholder and a bright native textarea scrollbar. Shortened the placeholder, applied dark native-control colors, and removed the resize handle. Re-captured the 390 × 844 viewport after the fix.

## Fidelity surfaces

- Typography: neutral 14px sans-serif progress/actions; 12px monospace command/output. Text hierarchy and truncation match the reference pattern. Hidden full commands remain readable in expanded panels and title text.
- Spacing/layout: flat assistant turns, grouped compact actions, readable paragraph gaps, rounded bordered command panel, and persistent composer. No horizontal viewport overflow at desktop or mobile.
- Colors/tokens: charcoal conversation background, muted action labels, slightly lighter Shell surface and subdued result text. Existing product branding outside the transcript is intentional.
- Asset quality: no raster assets are required by this UI. Execution icons use the Phosphor icon library; no bespoke drawn icons or imitation raster assets.
- Copy/content: actual commands, selected relative file paths, real stdout/stderr and exit codes. Commentary is public progress text; hidden thought parts are filtered out. Final responses follow completion validation.

## Interactions and console

Verified in the Codex in-app browser:
- Submitted a new Workspace request; saw live progress before the final response.
- Created a folder, wrote and patched its README, and ran `python -m pytest -q` through the controlled terminal tool; expanded output showed two real tests passing.
- Expanded/collapsed action groups and the Shell panel.
- Reloaded the conversation and verified both runs' commentary and action history returned.
- Opened the command by keyboard on mobile; checked overflow and composer visibility.
- Browser console warning/error check: no entries.

Automated coverage checks running-to-completed action updates, ordering around commentary, replay deduplication, failed commands, automatic build lifecycle pairing, cancellation, and exclusion of hidden model thoughts.

## Findings and follow-up polish

No unresolved P0/P1/P2 findings in the requested transcript scope. Existing sidebar branding and the optional diagnostic metadata/exit-code line are intentional differences. Command stdout/stderr is delivered when the controlled process returns; incremental terminal output is not implemented by this change. Live Gemini prose wording is not tested by the scripted preview.

## Implementation checklist

- [x] Inline progress and collapsible actions
- [x] Shell output, timing, exit code and result states
- [x] File/folder actions and sanitized diffs
- [x] SSE updates and persisted history
- [x] Keyboard/mobile controls and visible composer
- [x] Browser comparison and regression coverage
