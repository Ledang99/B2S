"""Tests for the drag-and-drop extractor window helpers."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from gui.app import (  # noqa: E402
    build_extract_command,
    load_metadata,
    output_dir_for,
    run_extract,
    supported_file,
)


def test_build_extract_command_matches_cli():
    script = Path("scripts/extract.py")
    book = Path(r"C:\books\My Book.pdf")
    command = build_extract_command("python", script, [book], "text")
    assert command == [
        "python",
        str(script),
        str(book),
        "--mode",
        "text",
        "--install-missing",
        "no",
    ]


def test_unknown_mode_falls_back_to_text():
    command = build_extract_command("python", Path("extract.py"), [Path("a.md")], "nope")
    assert "--mode" in command
    assert command[command.index("--mode") + 1] == "text"


def test_output_dir_uses_book_name():
    assert output_dir_for([Path(r"C:\books\Designing Data.pdf")]) == Path(
        r"C:\books\Designing Data-b2s"
    )
    assert output_dir_for([Path("a.pdf"), Path("b.epub")]) == Path("b2s-extract")


def test_supported_file_rejects_unknown_suffix(tmp_path: Path):
    note = tmp_path / "note.md"
    note.write_text("hello", encoding="utf-8")
    image = tmp_path / "cover.png"
    image.write_bytes(b"png")
    assert supported_file(note) is True
    assert supported_file(image) is False
    assert supported_file(tmp_path / "missing.pdf") is False


def test_run_extract_writes_text_and_metadata(tmp_path: Path):
    source = tmp_path / "note.md"
    source.write_text("# Backpressure\n\nChapter 1\nBounded queues prevent overload.\n", encoding="utf-8")
    work = tmp_path / "out"
    lines: list[str] = []

    code = run_extract([source], "text", work, lines.append)

    assert code == 0
    assert any("Extraction complete" in line for line in lines)
    text = (work / "full_text.txt").read_text(encoding="utf-8")
    assert "Backpressure" in text
    meta = load_metadata(work)
    assert meta is not None
    assert meta["words"] >= 5
    assert meta["extraction_mode"] == "text"
    assert json.loads((work / "metadata.json").read_text(encoding="utf-8"))["filename"] == "note.md"


def test_window_builds_and_drop_list_parses():
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except tkinter.TclError:
        pytest.skip("no display available")
    root.withdraw()
    try:
        data = "{C:/Users/Me/My Book.pdf} {C:/notes/a.md}"
        assert root.tk.splitlist(data) == ("C:/Users/Me/My Book.pdf", "C:/notes/a.md")
    finally:
        root.destroy()
