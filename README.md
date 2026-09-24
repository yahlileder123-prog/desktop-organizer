# Desktop Organizer

Desktop Organizer files the loose downloads that pile up on your Windows desktop. You teach it once, then one press puts each file in the folder where it belongs.

A literature essay can go straight to your literature folder. A song with no special word goes with the rest of your audio. Anything you have not taught it yet stays on the desktop.

## Install

1. Open [Releases](../../releases).
2. Download `DesktopOrganizerSetup.exe`.
3. Run it. It installs for your Windows user and does not ask for an administrator account.
4. Open **Desktop Organizer** from the Start menu.

## Use it

The first launch asks where common files should go: PDFs, pictures, audio, videos, and documents. Accept the suggested folder, choose a different one, or skip that kind of file.

Then teach a subject. Type a word you expect in the file name, such as `literature`, and choose the folder for it. A matching name is filed there even when the file is also a PDF.

Add the **Organize Desktop** shortcut when the setup offers it. Press that shortcut whenever downloads pile up. It files the desktop immediately and shows what moved. **Undo** puts that batch back.

You can keep teaching later:

- **Organize** shows what will move, and what is still waiting.
- **Teach** is the list of words and folders.
- **File types** is the general sorting used when no word matches.

Only loose files on the desktop are moved. Files that are already inside a folder stay there. Shortcuts stay put. The app does not read what is inside a file. It only looks at the file name.

## Privacy

Everything stays on this computer. Folder choices are saved under your Windows profile so the shortcut can use them later. Nothing is sent to a server.

## Run from source

Python 3.13 is required.

```bat
python -m pip install -r requirements.txt
python main.py
```

Or double-click `Run Organizer.bat`.
