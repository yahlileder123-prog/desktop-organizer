"""A quiet window for teaching the organizer and tidying the desktop."""

from __future__ import annotations

import ctypes
import sys
from collections import OrderedDict
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from desktop_organizer import engine, shortcut, storage
from desktop_organizer.paths import desktop, known_folder, pretty_path

BG = "#f3f1ec"
CARD = "#fffcf8"
INK = "#1c1b19"
MUTED = "#5e594f"
LINE = "#e4ddd2"
ACCENT = "#1f6b4a"
ACCENT_HOVER = "#184e36"
SOFT = "#e5f2eb"
SOFT_INK = "#184e36"
WARN_BG = "#f8efe6"
WARN_INK = "#6d4c2a"
TRACK = "#e7e2d9"

WIZARD = [
    {
        "kind": "type",
        "key": "pdf",
        "suggest": "documents",
        "title": "Where should PDFs go?",
        "body": "Readings, forms, and other PDFs that land on your desktop.",
    },
    {
        "kind": "type",
        "key": "images",
        "suggest": "pictures",
        "title": "Where should pictures go?",
        "body": "Photos and screenshots.",
    },
    {
        "kind": "type",
        "key": "audio",
        "suggest": "music",
        "title": "Where should audio go?",
        "body": "Music, voice notes, and other sound files.",
    },
    {
        "kind": "type",
        "key": "video",
        "suggest": "videos",
        "title": "Where should videos go?",
        "body": "Clips and recordings.",
    },
    {
        "kind": "type",
        "key": "documents",
        "suggest": "documents",
        "title": "Where should documents go?",
        "body": "Word files, text, and other writing that is not a PDF.",
    },
    {
        "kind": "rules",
        "title": "Send a subject to its own folder",
        "body": "A file about literature can go straight to your literature folder. Add a word you expect in the name, then choose the folder.",
    },
    {
        "kind": "shortcut",
        "title": "Put a button on your desktop",
        "body": "Press Organize Desktop whenever downloads pile up. It files whatever is loose on the desktop, using what you just taught it.",
    },
]


def run(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    ctk.set_appearance_mode("light")
    app = App(organize_now="--organize" in args)
    app.mainloop()


def _count(amount: int, singular: str, plural: str | None = None) -> str:
    word = singular if amount == 1 else (plural or singular + "s")
    return f"{amount} {word}"


class App(ctk.CTk):
    def __init__(self, organize_now: bool = False) -> None:
        super().__init__()
        self.title("Desktop Organizer")
        self.configure(fg_color=BG)
        self._place_window(960, 720)
        self.config_data = storage.load_config()
        self.pending_organize = organize_now
        self.page_name = "Organize"
        self.notice = ""
        self.notice_kind = "good"
        self.form_error = ""
        self.folder_choice = ""
        self.teaching_name: str | None = None
        self.teach_folder = ""
        self.teach_error = ""
        self.draft_folder = ""
        self.step_index = min(self.config_data.wizard_step, len(WIZARD) - 1)
        self._suspend = False
        self._entered_step = -1

        self.font_title = ctk.CTkFont(family="Segoe UI", size=28, weight="bold")
        self.font_heading = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        self.font_body = ctk.CTkFont(family="Segoe UI", size=15)
        self.font_small = ctk.CTkFont(family="Segoe UI", size=13)
        self.keyword_var = ctk.StringVar()
        self.teach_word = ctk.StringVar()

        self.root_frame: ctk.CTkFrame | None = None
        if self.config_data.wizard_done:
            self._show_main()
            if organize_now:
                self.after(50, self._organize)
        else:
            if organize_now:
                self.notice = "Tell me where things go, and then I'll organize the desktop."
                self.notice_kind = "info"
            self._show_wizard()

    def _place_window(self, width: int, height: int) -> None:
        rect = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        work_w = max(640, rect.right - rect.left)
        work_h = max(480, rect.bottom - rect.top)
        scale = float(self._get_window_scaling() or 1)
        width = min(width, int((work_w - 80) / scale))
        height = min(height, int((work_h - 80) / scale))
        self.minsize(min(720, max(520, width - 80)), min(480, max(420, height - 40)))
        self.update_idletasks()
        pixel_w = int(width * scale)
        pixel_h = int(height * scale)
        x = rect.left + max(0, (work_w - pixel_w) // 2)
        y = rect.top + max(0, (work_h - pixel_h) // 2)
        # CustomTkinter scales the geometry numbers, so positions are passed unscaled.
        self.geometry(f"{width}x{height}+{int(x / scale)}+{int(y / scale)}")
        self.after(30, self._keep_on_screen)

    def _keep_on_screen(self) -> None:
        rect = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        self.update_idletasks()
        overflow = self.winfo_rooty() + self.winfo_height() - rect.bottom
        if overflow <= 0:
            return
        scale = float(self._get_window_scaling() or 1)
        width = max(520, int(self.winfo_width() / scale))
        height = max(420, int((self.winfo_height() - overflow - 16) / scale))
        self.geometry(f"{width}x{height}")

    def _reset(self) -> ctk.CTkFrame:
        if self.root_frame is not None:
            self.root_frame.destroy()
        self.root_frame = ctk.CTkFrame(self, fg_color=BG)
        self.root_frame.pack(fill="both", expand=True)
        return self.root_frame

    def _wipe(self, widget: ctk.CTkBaseClass) -> None:
        for child in widget.winfo_children():
            child.destroy()

    # ----- setup questions -------------------------------------------------

    def _show_wizard(self) -> None:
        shell = self._reset()
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        self.wizard_holder = ctk.CTkFrame(shell, fg_color=BG)
        self.wizard_holder.grid(row=0, column=0, sticky="nsew")
        self._render_wizard(enter=True)

    def _render_wizard(self, enter: bool = False) -> None:
        if enter:
            self._enter_step()
        self._wipe(self.wizard_holder)
        step = WIZARD[self.step_index]
        wrap = ctk.CTkScrollableFrame(
            self.wizard_holder,
            fg_color=BG,
            scrollbar_button_color=LINE,
            scrollbar_button_hover_color=MUTED,
        )
        wrap.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(wrap, fg_color=BG)
        inner.pack(fill="x", padx=72, pady=36)
        inner.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(inner, fg_color=BG)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        ctk.CTkLabel(top, text="Setup", text_color=ACCENT, font=self.font_small).pack(side="left")
        ctk.CTkLabel(
            top,
            text=f"{self.step_index + 1} of {len(WIZARD)}",
            text_color=MUTED,
            font=self.font_small,
        ).pack(side="right")

        dots = ctk.CTkFrame(inner, fg_color=BG)
        dots.grid(row=1, column=0, sticky="w", pady=(0, 18))
        for index in range(len(WIZARD)):
            color = ACCENT if index <= self.step_index else LINE
            mark = ctk.CTkFrame(dots, width=28 if index == self.step_index else 10, height=8, corner_radius=4, fg_color=color)
            mark.pack(side="left", padx=(0, 6))
            mark.pack_propagate(False)

        ctk.CTkLabel(inner, text=step["title"], font=self.font_title, text_color=INK, anchor="w", justify="left").grid(
            row=2, column=0, sticky="ew"
        )
        ctk.CTkLabel(
            inner,
            text=step["body"],
            font=self.font_body,
            text_color=MUTED,
            wraplength=560,
            justify="left",
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(10, 18))

        if self.notice and self.step_index == 0:
            self._banner(inner, 4)
        body_row = 5
        if step["kind"] == "type":
            self._wizard_type_body(inner, body_row)
        elif step["kind"] == "rules":
            self._keyword_form(inner, body_row, on_done=lambda: self._render_wizard(enter=False))
            self._rule_list(inner, body_row + 1)
        else:
            self._wizard_shortcut_body(inner, body_row)

        actions = ctk.CTkFrame(inner, fg_color=BG)
        actions.grid(row=20, column=0, sticky="ew", pady=(28, 0))
        if self.step_index > 0:
            self._ghost(actions, "Back", self._wizard_back).pack(side="left")
        if step["kind"] == "shortcut":
            self._ghost(actions, "Not now", self._finish_wizard).pack(side="right", padx=(8, 0))
            self._primary(actions, "Add shortcut", self._wizard_add_shortcut).pack(side="right")
        elif step["kind"] == "rules":
            self._primary(actions, "Continue", self._wizard_advance).pack(side="right")
        else:
            self._ghost(actions, "Skip", self._wizard_advance).pack(side="right", padx=(8, 0))
            label = "Use this folder" if self.draft_folder else "Choose folder"
            command = self._wizard_accept if self.draft_folder else self._pick_draft_folder
            self._primary(actions, label, command).pack(side="right")

    def _enter_step(self) -> None:
        if self._entered_step == self.step_index:
            return
        self._entered_step = self.step_index
        self.form_error = ""
        step = WIZARD[self.step_index]
        if step["kind"] != "type":
            return
        current = self.config_data.type_by_key(step["key"])
        if current and current.folder.strip():
            self.draft_folder = current.folder
            return
        suggested = known_folder(step["suggest"])
        self.draft_folder = str(suggested) if suggested and suggested.exists() else ""

    def _wizard_type_body(self, parent: ctk.CTkFrame, row: int) -> None:
        card = self._card(parent)
        card.grid(row=row, column=0, sticky="ew")
        if self.draft_folder:
            ctk.CTkLabel(card, text=Path(self.draft_folder).name, font=self.font_heading, text_color=INK, anchor="w").pack(
                fill="x", padx=18, pady=(16, 2)
            )
            ctk.CTkLabel(
                card,
                text=pretty_path(self.draft_folder),
                font=self.font_small,
                text_color=MUTED,
                anchor="w",
                wraplength=520,
                justify="left",
            ).pack(fill="x", padx=18, pady=(0, 8))
            self._ghost(card, "Change folder", self._pick_draft_folder).pack(anchor="w", padx=12, pady=(0, 12))
        else:
            ctk.CTkLabel(
                card,
                text="Choose a folder, or skip this kind of file.",
                font=self.font_body,
                text_color=MUTED,
                anchor="w",
            ).pack(fill="x", padx=18, pady=18)

    def _wizard_shortcut_body(self, parent: ctk.CTkFrame, row: int) -> None:
        card = self._card(parent)
        card.grid(row=row, column=0, sticky="ew")
        exists = shortcut.shortcut_path().exists()
        text = "Organize Desktop is already on your desktop. Adding it again just refreshes it." if exists else "The shortcut is named Organize Desktop."
        ctk.CTkLabel(card, text=text, font=self.font_body, text_color=INK, wraplength=520, justify="left", anchor="w").pack(
            fill="x", padx=18, pady=18
        )
        if self.form_error:
            ctk.CTkLabel(card, text=self.form_error, font=self.font_small, text_color=WARN_INK, anchor="w").pack(
                fill="x", padx=18, pady=(0, 14)
            )

    def _pick_draft_folder(self) -> None:
        chosen = self._browse(self.draft_folder)
        if not chosen:
            return
        self.draft_folder = chosen
        self._render_wizard(enter=False)

    def _wizard_accept(self) -> None:
        step = WIZARD[self.step_index]
        if step["kind"] == "type" and self.draft_folder:
            self.config_data.set_type(step["key"], folder=self.draft_folder, enabled=True)
        self._wizard_advance()

    def _wizard_back(self) -> None:
        if self.step_index == 0:
            return
        self.step_index -= 1
        self._entered_step = -1
        self.config_data.wizard_step = self.step_index
        storage.save_config(self.config_data)
        self._render_wizard(enter=True)

    def _wizard_advance(self) -> None:
        self.step_index += 1
        self._entered_step = -1
        self.config_data.wizard_step = self.step_index
        if self.step_index >= len(WIZARD):
            self._finish_wizard()
            return
        storage.save_config(self.config_data)
        self._render_wizard(enter=True)

    def _wizard_add_shortcut(self) -> None:
        error = shortcut.create_shortcut()
        if error:
            self.form_error = error
            self._render_wizard(enter=False)
            return
        self.notice = "Organize Desktop is on your desktop."
        self.notice_kind = "good"
        self._finish_wizard()

    def _finish_wizard(self) -> None:
        self.config_data.wizard_done = True
        self.config_data.wizard_step = 0
        storage.save_config(self.config_data)
        self._show_main()
        if self.pending_organize:
            self.pending_organize = False
            self.after(50, self._organize)

    def _reopen_wizard(self) -> None:
        self.config_data.wizard_done = False
        self.config_data.wizard_step = 0
        self.step_index = 0
        self._entered_step = -1
        storage.save_config(self.config_data)
        self._show_wizard()

    # ----- main window -----------------------------------------------------

    def _show_main(self) -> None:
        shell = self._reset()
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(shell, fg_color=BG)
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 4))
        ctk.CTkLabel(header, text="Desktop Organizer", font=self.font_title, text_color=INK, anchor="w").pack(fill="x")
        ctk.CTkLabel(
            header,
            text="Teach it which folder is for what. Then one press files the downloads sitting on your desktop.",
            font=self.font_body,
            text_color=MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

        tabs = ctk.CTkSegmentedButton(
            shell,
            values=["Organize", "Teach", "File types"],
            font=self.font_body,
            height=38,
            corner_radius=12,
            fg_color=TRACK,
            selected_color=CARD,
            selected_hover_color="#ffffff",
            unselected_color=TRACK,
            unselected_hover_color="#efeae3",
            text_color=INK,
            command=self._select_page,
        )
        tabs.set(self.page_name)
        tabs.grid(row=1, column=0, sticky="ew", padx=28, pady=(18, 8))
        self.tabs = tabs

        self.notice_frame = ctk.CTkFrame(shell, fg_color=BG)
        self.notice_frame.grid(row=2, column=0, sticky="ew", padx=28)
        self.notice_frame.grid_columnconfigure(0, weight=1)
        self.page = ctk.CTkFrame(shell, fg_color=BG)
        self.page.grid(row=3, column=0, sticky="nsew", padx=20, pady=(4, 0))
        self.page.grid_columnconfigure(0, weight=1)
        self.page.grid_rowconfigure(0, weight=1)
        self.footer = ctk.CTkFrame(shell, fg_color=BG)
        self.footer.grid(row=4, column=0, sticky="ew", padx=28, pady=(8, 18))
        self._render_page()

    def _select_page(self, name: str) -> None:
        self.page_name = name
        self.teaching_name = None
        self.form_error = ""
        self._render_page()

    def _render_page(self) -> None:
        if not hasattr(self, "page"):
            return
        self._wipe(self.notice_frame)
        self._wipe(self.page)
        self._wipe(self.footer)
        if self.notice:
            self.notice_frame.grid()
            self._banner(self.notice_frame, 0, pady=(0, 8))
        else:
            self.notice_frame.grid_remove()
        scroll = ctk.CTkScrollableFrame(self.page, fg_color=BG, scrollbar_button_color=LINE, scrollbar_button_hover_color=MUTED)
        scroll.grid(row=0, column=0, sticky="nsew")
        if self.page_name == "Organize":
            self._render_organize(scroll)
        elif self.page_name == "Teach":
            self._render_teach(scroll)
        else:
            self._render_types(scroll)

    def _render_organize(self, scroll: ctk.CTkScrollableFrame) -> None:
        actions, staying = self._safe_plan()
        self._shortcut_card(scroll)

        batch = storage.latest_batch()
        if batch and batch.get("moves"):
            card = self._card(scroll)
            card.pack(fill="x", pady=(0, 10))
            when = _when(str(batch.get("created", "")))
            title = "Last organize"
            if when:
                title += f" · {when}"
            ctk.CTkLabel(card, text=title, font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", padx=18, pady=(14, 2))
            ctk.CTkLabel(
                card,
                text=f"Moved {_count(len(batch['moves']), 'file')}.",
                font=self.font_body,
                text_color=MUTED,
                anchor="w",
            ).pack(fill="x", padx=18)
            self._ghost(card, "Undo", self._undo).pack(anchor="w", padx=12, pady=(4, 12))

        if actions:
            ctk.CTkLabel(scroll, text="Will move", font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", pady=(8, 8))
            groups: OrderedDict[Path, list[engine.Action]] = OrderedDict()
            for action in actions:
                groups.setdefault(action.dest_dir, []).append(action)
            for dest, items in groups.items():
                card = self._card(scroll)
                card.pack(fill="x", pady=(0, 8))
                ctk.CTkLabel(card, text=dest.name, font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", padx=18, pady=(14, 0))
                ctk.CTkLabel(card, text=pretty_path(dest), font=self.font_small, text_color=MUTED, anchor="w").pack(fill="x", padx=18, pady=(2, 4))
                reasons = {item.reason for item in items}
                detail = next(iter(reasons)) if len(reasons) == 1 else "mixed"
                if detail == "mixed":
                    line = _count(len(items), "file")
                elif detail[:1].isupper():
                    line = f"{_count(len(items), 'file')} · {detail}"
                else:
                    line = f"{_count(len(items), 'file')} · {detail}"
                ctk.CTkLabel(card, text=line, font=self.font_small, text_color=SOFT_INK, anchor="w").pack(fill="x", padx=18, pady=(0, 6))
                preview = ", ".join(item.src.name for item in items[:4])
                extra = len(items) - 4
                if extra > 0:
                    preview += f", and {_count(extra, 'more file')}"
                ctk.CTkLabel(card, text=preview, font=self.font_small, text_color=MUTED, anchor="w", wraplength=620, justify="left").pack(
                    fill="x", padx=18, pady=(0, 14)
                )
        elif not staying:
            self._empty_card(scroll, "Nothing loose on the desktop.", "Folders you already made are left alone.")

        if staying:
            ctk.CTkLabel(scroll, text="Still on the desktop", font=self.font_heading, text_color=INK, anchor="w").pack(
                fill="x", pady=(12, 4)
            )
            ctk.CTkLabel(
                scroll,
                text="These stay until you teach me where they belong.",
                font=self.font_small,
                text_color=MUTED,
                anchor="w",
            ).pack(fill="x", pady=(0, 8))
            for path in staying:
                self._stay_card(scroll, path)

        label = "Organize desktop"
        if actions:
            label = f"Organize desktop · {_count(len(actions), 'file')}"
        self._primary(self.footer, label, self._organize, height=48).pack(fill="x")
        ctk.CTkLabel(
            self.footer,
            text="Only loose files move. Folders, shortcuts, and anything you haven't taught stay put.",
            font=self.font_small,
            text_color=MUTED,
            wraplength=640,
        ).pack(pady=(8, 0))

    def _stay_card(self, parent: ctk.CTkScrollableFrame, path: Path) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 8))
        row = ctk.CTkFrame(card, fg_color=CARD)
        row.pack(fill="x", padx=8, pady=8)
        kind = engine.type_for_extension(self.config_data, path.suffix)
        if kind is not None:
            self._ghost(row, f"All {kind.label}", lambda key=kind.key: self._remember_type(key)).pack(side="right", padx=(8, 4))
        self._ghost(row, "Teach a word", lambda name=path.name: self._start_teach(name)).pack(side="right")
        ctk.CTkLabel(
            row,
            text=path.name,
            font=self.font_body,
            text_color=INK,
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(side="left", fill="x", expand=True, padx=(10, 8))
        if self.teaching_name == path.name:
            editor = ctk.CTkFrame(card, fg_color=CARD)
            editor.pack(fill="x", padx=16, pady=(0, 12))
            ctk.CTkLabel(editor, text="Word in the file name", font=self.font_small, text_color=MUTED, anchor="w").pack(fill="x")
            ctk.CTkEntry(
                editor,
                textvariable=self.teach_word,
                height=40,
                corner_radius=10,
                border_color=LINE,
                fg_color="#fff",
                text_color=INK,
                font=self.font_body,
                placeholder_text="literature",
            ).pack(fill="x", pady=(4, 8))
            picked = pretty_path(self.teach_folder) if self.teach_folder else "No folder chosen"
            ctk.CTkLabel(editor, text=picked, font=self.font_small, text_color=INK if self.teach_folder else MUTED, anchor="w").pack(fill="x")
            buttons = ctk.CTkFrame(editor, fg_color=CARD)
            buttons.pack(fill="x", pady=(8, 0))
            self._ghost(buttons, "Choose folder", self._pick_teach_folder).pack(side="left")
            self._primary(buttons, "Remember", self._remember_word, height=36).pack(side="right")
            if self.teach_error:
                ctk.CTkLabel(editor, text=self.teach_error, font=self.font_small, text_color=WARN_INK, anchor="w").pack(fill="x", pady=(8, 0))

    def _shortcut_card(self, parent: ctk.CTkScrollableFrame) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text="Desktop shortcut", font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        exists = shortcut.shortcut_path().exists()
        text = "Organize Desktop is already on your desktop. Press it whenever things pile up." if exists else "Add Organize Desktop. Pressing it tidies the desktop immediately."
        ctk.CTkLabel(card, text=text, font=self.font_small, text_color=MUTED, wraplength=620, justify="left", anchor="w").pack(fill="x", padx=18)
        self._ghost(card, "Add shortcut to desktop", self._add_shortcut).pack(anchor="w", padx=12, pady=(4, 12))

    def _render_teach(self, scroll: ctk.CTkScrollableFrame) -> None:
        ctk.CTkLabel(
            scroll,
            text="If a file name contains the word, it goes to that folder. This wins over the general file types.",
            font=self.font_body,
            text_color=MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 12))
        self._keyword_form(scroll, None, on_done=self._render_page)
        self._rule_list(scroll, None)
        if not self.config_data.rules:
            self._empty_card(
                scroll,
                "No special folders yet.",
                "Example: the word literature, and your Studying \\ Literature folder.",
            )

    def _render_types(self, scroll: ctk.CTkScrollableFrame) -> None:
        ctk.CTkLabel(
            scroll,
            text="If no special word matches, file it by the kind of file. Turn one off and that kind stays on the desktop.",
            font=self.font_body,
            text_color=MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 12))
        for item in self.config_data.types:
            card = self._card(scroll)
            card.pack(fill="x", pady=(0, 8))
            head = ctk.CTkFrame(card, fg_color=CARD)
            head.pack(fill="x", padx=16, pady=(12, 0))
            text = ctk.CTkFrame(head, fg_color=CARD)
            text.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(text, text=item.label, font=self.font_heading, text_color=INK, anchor="w").pack(fill="x")
            hint = ", ".join(ext.lstrip(".") for ext in item.extensions[:4])
            if len(item.extensions) > 4:
                hint += f" +{len(item.extensions) - 4}"
            ctk.CTkLabel(text, text=hint, font=self.font_small, text_color=MUTED, anchor="w").pack(fill="x")
            var = ctk.IntVar(value=1 if item.enabled and item.folder else 0)
            switch = ctk.CTkSwitch(
                head,
                text="",
                variable=var,
                onvalue=1,
                offvalue=0,
                progress_color=ACCENT,
                button_color="#ffffff",
                button_hover_color="#f4f4f4",
                fg_color=LINE,
                command=lambda key=item.key, variable=var: self._toggle_type(key, variable),
            )
            switch.pack(side="right", padx=(8, 4))
            path_text = pretty_path(item.folder) if item.folder else "No folder yet"
            ctk.CTkLabel(card, text=path_text, font=self.font_small, text_color=INK if item.folder else MUTED, anchor="w").pack(
                fill="x", padx=18, pady=(8, 0)
            )
            self._ghost(card, "Change folder" if item.folder else "Choose folder", lambda key=item.key: self._pick_type_folder(key)).pack(
                anchor="w", padx=12, pady=(2, 10)
            )
        self._ghost(scroll, "Review the setup questions", self._reopen_wizard).pack(anchor="w", pady=(12, 8))

    def _keyword_form(self, parent, row: int | None, on_done) -> None:
        card = self._card(parent)
        if row is None:
            card.pack(fill="x", pady=(0, 10))
        else:
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(card, text="Word in the file name", font=self.font_small, text_color=MUTED, anchor="w").pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkEntry(
            card,
            textvariable=self.keyword_var,
            height=42,
            corner_radius=10,
            border_color=LINE,
            fg_color="#fff",
            text_color=INK,
            font=self.font_body,
            placeholder_text="literature, poetry",
        ).pack(fill="x", padx=18)
        picked = pretty_path(self.folder_choice) if self.folder_choice else "No folder chosen"
        ctk.CTkLabel(card, text=picked, font=self.font_small, text_color=INK if self.folder_choice else MUTED, anchor="w").pack(
            fill="x", padx=18, pady=(8, 0)
        )
        buttons = ctk.CTkFrame(card, fg_color=CARD)
        buttons.pack(fill="x", padx=12, pady=(8, 8))
        self._ghost(buttons, "Choose folder", lambda: self._pick_rule_folder(on_done)).pack(side="left")
        self._primary(buttons, "Add", lambda: self._add_keyword(on_done), height=36).pack(side="right")
        if self.form_error:
            ctk.CTkLabel(card, text=self.form_error, font=self.font_small, text_color=WARN_INK, anchor="w").pack(
                fill="x", padx=18, pady=(0, 12)
            )

    def _rule_list(self, parent, row: int | None) -> None:
        rules = list(enumerate(self.config_data.rules))
        if not rules:
            return
        host = ctk.CTkFrame(parent, fg_color=BG)
        if row is None:
            host.pack(fill="x")
        else:
            host.grid(row=row, column=0, sticky="ew")
        for index, rule in reversed(rules):
            card = self._card(host)
            card.pack(fill="x", pady=(0, 8))
            words = ", ".join(rule.keywords)
            ctk.CTkLabel(card, text=words, font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", padx=18, pady=(14, 0))
            ctk.CTkLabel(card, text=pretty_path(rule.folder), font=self.font_small, text_color=MUTED, anchor="w", wraplength=620, justify="left").pack(
                fill="x", padx=18, pady=(2, 0)
            )
            self._ghost(card, "Remove", lambda i=index: self._remove_rule(i)).pack(anchor="w", padx=12, pady=(2, 10))

    # ----- actions ---------------------------------------------------------

    def _safe_plan(self) -> tuple[list[engine.Action], list[Path]]:
        try:
            folder = desktop()
            if not folder.exists():
                return [], []
            return engine.plan(folder, self.config_data)
        except OSError:
            return [], []

    def _organize(self) -> None:
        if not self.config_data.has_destination():
            self.notice = "Choose where at least one kind of file should go."
            self.notice_kind = "info"
            self.page_name = "File types"
            if hasattr(self, "tabs"):
                self.tabs.set("File types")
            self._render_page()
            return
        actions, staying = self._safe_plan()
        if not actions:
            if staying:
                self.notice = f"I left {_count(len(staying), 'file')} on the desktop. Teach me a word, or where that kind of file goes."
            else:
                self.notice = "The desktop is already tidy."
            self.notice_kind = "info"
            self._render_page()
            return
        done, errors = engine.apply(actions, desktop())
        if done:
            storage.record_moves([(str(item.src), str(item.dst)) for item in done])
            self.notice = f"Moved {_count(len(done), 'file')}."
            self.notice_kind = "good"
        else:
            self.notice = ""
        if errors:
            failed = f"Couldn't move {_count(len(errors), 'file')}. It may be open in another program."
            self.notice = f"{self.notice} {failed}".strip()
            self.notice_kind = "bad" if not done else "info"
        self.page_name = "Organize"
        if hasattr(self, "tabs"):
            self.tabs.set("Organize")
        self._render_page()

    def _undo(self) -> None:
        batch = storage.latest_batch()
        if not batch:
            return
        _restored, pending, notes = engine.undo_moves(list(batch["moves"]), desktop())
        batch["moves"] = pending
        batch["undone"] = not pending
        storage.mark_batch(batch)
        if pending and notes:
            self.notice = notes[0]
            self.notice_kind = "info"
        elif _restored:
            self.notice = f"Put {_count(len(_restored), 'file')} back on the desktop."
            self.notice_kind = "good"
        else:
            self.notice = notes[0] if notes else "Nothing to put back."
            self.notice_kind = "info"
        self._render_page()

    def _add_shortcut(self) -> None:
        error = shortcut.create_shortcut()
        self.notice = error or "Organize Desktop is on your desktop. Press it whenever things pile up."
        self.notice_kind = "bad" if error else "good"
        self._render_page()

    def _add_keyword(self, on_done) -> None:
        error = self._commit_keyword()
        self.form_error = error
        if not error:
            self.notice = "Remembered. The next organize will use it."
            self.notice_kind = "good"
        on_done()

    def _commit_keyword(self) -> str:
        if not self.folder_choice:
            return "Choose a folder first."
        words = [part.strip() for part in self.keyword_var.get().split(",") if part.strip()]
        saved = self.config_data.add_keywords(words, self.folder_choice)
        if not saved:
            return "Use a word of at least 2 letters."
        storage.save_config(self.config_data)
        self.keyword_var.set("")
        self.folder_choice = ""
        return ""

    def _remove_rule(self, index: int) -> None:
        self.config_data.remove_rule(index)
        storage.save_config(self.config_data)
        self._render_page() if self.config_data.wizard_done else self._render_wizard(enter=False)

    def _pick_rule_folder(self, on_done) -> None:
        chosen = self._browse(self.folder_choice)
        if not chosen:
            return
        self.folder_choice = chosen
        self.form_error = ""
        on_done()

    def _start_teach(self, filename: str) -> None:
        self.teaching_name = filename
        self.teach_word.set(engine.keyword_suggestion(filename))
        self.teach_folder = ""
        self.teach_error = ""
        self._render_page()

    def _pick_teach_folder(self) -> None:
        chosen = self._browse(self.teach_folder)
        if not chosen:
            return
        self.teach_folder = chosen
        self.teach_error = ""
        self._render_page()

    def _remember_word(self) -> None:
        if not self.teach_folder:
            self.teach_error = "Choose a folder first."
            self._render_page()
            return
        words = [part.strip() for part in self.teach_word.get().split(",") if part.strip()]
        saved = self.config_data.add_keywords(words, self.teach_folder)
        if not saved:
            self.teach_error = "Use a word of at least 2 letters."
            self._render_page()
            return
        storage.save_config(self.config_data)
        self.teaching_name = None
        self.notice = "Remembered. Press Organize desktop and I'll file it."
        self.notice_kind = "good"
        self._render_page()

    def _remember_type(self, key: str) -> None:
        chosen = self._browse()
        if not chosen:
            return
        self.config_data.set_type(key, folder=chosen, enabled=True)
        storage.save_config(self.config_data)
        item = self.config_data.type_by_key(key)
        label = item.label if item else "Those files"
        self.teaching_name = None
        self.notice = f"{label} will go to that folder. Press Organize desktop to file them."
        self.notice_kind = "good"
        self._render_page()

    def _toggle_type(self, key: str, variable: ctk.IntVar) -> None:
        if self._suspend:
            return
        item = self.config_data.type_by_key(key)
        if item is None:
            return
        enabled = bool(variable.get())
        if enabled and not item.folder:
            chosen = self._browse()
            if not chosen:
                self._suspend = True
                variable.set(0)
                self._suspend = False
                return
            self.config_data.set_type(key, folder=chosen, enabled=True)
        else:
            self.config_data.set_type(key, enabled=enabled)
        storage.save_config(self.config_data)
        self._render_page()

    def _pick_type_folder(self, key: str) -> None:
        item = self.config_data.type_by_key(key)
        chosen = self._browse(item.folder if item else "")
        if not chosen:
            return
        self.config_data.set_type(key, folder=chosen, enabled=True)
        storage.save_config(self.config_data)
        self._render_page()

    def _browse(self, initial: str = "") -> str:
        start = initial if initial and Path(initial).exists() else str(Path.home())
        chosen = filedialog.askdirectory(parent=self, initialdir=start, title="Choose a folder")
        return chosen or ""

    # ----- pieces ----------------------------------------------------------

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)

    def _empty_card(self, parent, title: str, body: str) -> None:
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text=title, font=self.font_heading, text_color=INK, anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        ctk.CTkLabel(card, text=body, font=self.font_body, text_color=MUTED, wraplength=620, justify="left", anchor="w").pack(
            fill="x", padx=18, pady=(0, 16)
        )

    def _banner(self, parent, row: int, pady: tuple[int, int] | int = 0) -> None:
        colors = {
            "good": (SOFT, SOFT_INK),
            "bad": ("#f8e8e4", "#7a332c"),
            "info": (WARN_BG, WARN_INK),
        }
        background, foreground = colors.get(self.notice_kind, colors["info"])
        banner = ctk.CTkFrame(parent, fg_color=background, corner_radius=12)
        banner.grid(row=row, column=0, sticky="ew", pady=pady)
        ctk.CTkLabel(banner, text=self.notice, font=self.font_body, text_color=foreground, wraplength=640, justify="left", anchor="w").pack(
            fill="x", padx=14, pady=10
        )

    def _primary(self, parent, text: str, command, height: int = 40) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=height,
            corner_radius=12,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#ffffff",
            font=self.font_body,
        )

    def _ghost(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#efeae3",
            text_color=INK,
            border_width=1,
            border_color=LINE,
            font=self.font_small,
        )
