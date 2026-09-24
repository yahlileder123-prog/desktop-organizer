import os
import tempfile
import unittest
from pathlib import Path

from desktop_organizer import engine, shortcut, storage


def _config_with(folder: Path, *, keyword: str | None = None, pdf: str | None = None) -> storage.Config:
    config = storage.fresh_config()
    if keyword:
        config.add_keywords([keyword], str(folder))
    if pdf:
        config.set_type("pdf", folder=pdf, enabled=True)
    return config


class OrganizeTests(unittest.TestCase):
    def test_literature_goes_to_the_study_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / "Desktop"
            literature = root / "Studying" / "Literature"
            desktop.mkdir()
            essay = desktop / "literature essay final.pdf"
            essay.write_text("notes", encoding="utf-8")
            picture = desktop / "holiday.png"
            picture.write_text("img", encoding="utf-8")

            config = storage.fresh_config()
            config.add_keywords(["literature"], str(literature))
            config.set_type("images", folder=str(root / "Pictures"), enabled=True)

            actions, staying = engine.plan(desktop, config)
            done, errors = engine.apply(actions, desktop)

            self.assertEqual(errors, [])
            self.assertEqual(staying, [])
            moved = {item.src.name: item.dst for item in done}
            self.assertEqual(moved["literature essay final.pdf"], literature / "literature essay final.pdf")
            self.assertEqual(moved["holiday.png"].parent, root / "Pictures")
            self.assertTrue((literature / "literature essay final.pdf").read_text(encoding="utf-8") == "notes")
            self.assertFalse(essay.exists())

    def test_keyword_beats_file_type_and_short_words_do_not_overmatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / "Desktop"
            desktop.mkdir()
            (desktop / "party invite.pdf").write_text("x", encoding="utf-8")
            (desktop / "art history chapter.pdf").write_text("x", encoding="utf-8")
            (desktop / "notes.pdf").write_text("x", encoding="utf-8")
            (desktop / "Stuff").mkdir()
            (desktop / "Stuff" / "literature.pdf").write_text("hidden", encoding="utf-8")
            (desktop / "desktop.ini").write_text("x", encoding="utf-8")
            (desktop / "Keep.lnk").write_text("x", encoding="utf-8")

            config = storage.fresh_config()
            config.add_keywords(["art"], str(root / "Art"))
            config.add_keywords(["art history"], str(root / "History"))
            config.set_type("pdf", folder=str(root / "PDFs"), enabled=True)

            actions, staying = engine.plan(desktop, config)
            by_name = {item.src.name: item.dest_dir for item in actions}

            self.assertEqual(by_name["art history chapter.pdf"], root / "History")
            self.assertEqual(by_name["party invite.pdf"], root / "PDFs")
            self.assertEqual(by_name["notes.pdf"], root / "PDFs")
            self.assertNotIn("literature.pdf", by_name)
            self.assertNotIn("desktop.ini", by_name)
            self.assertEqual([path.name for path in staying], [])

    def test_unknown_files_stay_and_collisions_get_a_new_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / "Desktop"
            docs = root / "Docs"
            desktop.mkdir()
            docs.mkdir()
            (docs / "notes.txt").write_text("old", encoding="utf-8")
            (desktop / "notes.txt").write_text("new", encoding="utf-8")
            (desktop / "mystery.xyz").write_text("?", encoding="utf-8")

            config = _config_with(docs, pdf=str(docs))
            config.set_type("documents", folder=str(docs), enabled=True)
            actions, staying = engine.plan(desktop, config)
            done, errors = engine.apply(actions, desktop)

            self.assertEqual(errors, [])
            self.assertEqual([path.name for path in staying], ["mystery.xyz"])
            self.assertTrue((docs / "notes (2).txt").read_text(encoding="utf-8") == "new")
            self.assertEqual(done[0].dst.name, "notes (2).txt")

    def test_undo_puts_the_file_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / "Desktop"
            docs = root / "Docs"
            desktop.mkdir()
            original = desktop / "reading.pdf"
            original.write_text("chapter", encoding="utf-8")
            config = storage.fresh_config()
            config.set_type("pdf", folder=str(docs), enabled=True)
            actions, _staying = engine.plan(desktop, config)
            done, errors = engine.apply(actions, desktop)
            self.assertEqual(errors, [])

            moves = [{"src": str(item.src), "dst": str(item.dst)} for item in done]
            restored, pending, _notes = engine.undo_moves(moves, desktop)

            self.assertEqual(pending, [])
            self.assertEqual(len(restored), 1)
            self.assertEqual(original.read_text(encoding="utf-8"), "chapter")
            self.assertFalse((docs / "reading.pdf").exists())

    def test_desktop_itself_is_not_a_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            desktop = Path(temporary)
            (desktop / "song.mp3").write_text("a", encoding="utf-8")
            config = storage.fresh_config()
            config.add_keywords(["song"], str(desktop))
            config.set_type("audio", folder=str(desktop), enabled=True)
            actions, staying = engine.plan(desktop, config)
            self.assertEqual(actions, [])
            self.assertEqual([path.name for path in staying], ["song.mp3"])

    def test_rules_roundtrip_and_a_word_has_one_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            config = storage.fresh_config()
            config.add_keywords(["literature", "poetry"], str(Path(temporary) / "Lit"))
            config.add_keywords(["literature"], str(Path(temporary) / "Books"))
            config.set_type("pdf", folder=str(Path(temporary) / "PDFs"), enabled=True)
            config.wizard_done = True
            storage.save_config(config, path)

            loaded = storage.load_config(path)
            self.assertTrue(loaded.wizard_done)
            self.assertEqual(len(loaded.rules), 2)
            literature = next(rule for rule in loaded.rules if any(word.casefold() == "literature" for word in rule.keywords))
            self.assertTrue(literature.folder.endswith("Books"))
            poetry = next(rule for rule in loaded.rules if "poetry" in [word.casefold() for word in rule.keywords])
            self.assertTrue(poetry.folder.endswith("Lit"))
            pdf = loaded.type_by_key("pdf")
            self.assertIsNotNone(pdf)
            assert pdf is not None
            self.assertTrue(pdf.enabled)
            self.assertTrue(pdf.folder.endswith("PDFs"))
            self.assertTrue(loaded.has_destination())


    def test_refuses_windows_the_project_folder_and_a_forged_undo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            desktop = root / "Desktop"
            desktop.mkdir()
            report = desktop / "report.pdf"
            report.write_text("private", encoding="utf-8")
            windows = Path(os.environ["SystemRoot"])
            project = Path(__file__).resolve().parents[1]

            for folder in (windows, project):
                config = storage.fresh_config()
                config.add_keywords(["report"], str(folder))
                actions, staying = engine.plan(desktop, config)
                self.assertEqual(actions, [])
                self.assertEqual([path.name for path in staying], ["report.pdf"])

            kept = root / "kept"
            kept.mkdir()
            secret = kept / "secret.pdf"
            secret.write_text("secret", encoding="utf-8")
            forged = [{"src": str(root / "elsewhere" / "secret.pdf"), "dst": str(secret)}]
            restored, pending, _notes = engine.undo_moves(forged, desktop)
            self.assertEqual(restored, [])
            self.assertEqual(pending, [])
            self.assertEqual(secret.read_text(encoding="utf-8"), "secret")
            self.assertTrue(report.exists())


class ShortcutTests(unittest.TestCase):
    def test_shortcut_points_at_organize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            error = shortcut.create_shortcut(folder)
            self.assertIsNone(error)
            link = folder / "Organize Desktop.lnk"
            self.assertTrue(link.exists())
            command = (
                "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
                + shortcut._ps(str(link))
                + "); Write-Output $s.TargetPath; Write-Output $s.Arguments"
            )
            import subprocess

            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            self.assertTrue(lines[0].lower().endswith("pythonw.exe") or lines[0].lower().endswith("python.exe"))
            self.assertIn("--organize", lines[1])
            self.assertIn("main.py", lines[1])


if __name__ == "__main__":
    unittest.main()
