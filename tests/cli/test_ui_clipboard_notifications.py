from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.selection import Selection
from textual.widget import Widget

from hacxgent.cli.clipboard import copy_selection_to_clipboard
from hacxgent.cli.textual_ui.app import HacxgentApp


class ClipboardSelectionWidget(Widget):
    def __init__(self, selected_text: str) -> None:
        super().__init__()
        self._selected_text = selected_text

    @property
    def text_selection(self) -> Selection | None:
        return Selection(None, None)

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        return (self._selected_text, "\n")


@pytest.mark.asyncio
async def test_ui_clipboard_notification_does_not_crash_on_markup_text(
    monkeypatch: pytest.MonkeyPatch, hacxgent_app: HacxgentApp
) -> None:
    async with hacxgent_app.run_test(notifications=True) as pilot:
        await hacxgent_app.mount(ClipboardSelectionWidget("[/]"))
        with patch("hacxgent.cli.clipboard._copy_osc52"):
            copy_selection_to_clipboard(hacxgent_app)

        await pilot.pause(0.1)
        notifications = list(hacxgent_app._notifications)
        assert notifications
        notification = notifications[-1]
        assert notification.markup is False
        assert "copied to clipboard" in notification.message
