# Writing the user manual: rules and decisions

Read this before you touch `docs/manual`. It holds the rules and the user's decisions for the manual, not facts about the program: the facts of a chapter come from the code (menus, dialogs, messages), never from memory and never copied from the developer documents. The manual is a separate product from the program, so its requirements are not in `wop_02_requirements.md`.

## Decided with the user
- For the users in the workshop (the developer documents are the `wop_0*.md` files). Language: English, plain words, short sentences (the user writes English with typos; the manual must not).
- A4, light theme in the pictures (the Windows theme must be on light when the pictures are made).
- LaTeX in `docs/manual` (`scrbook`), built by `tools/make_manual.py` with MiKTeX. The `build` folder is not in the repository.
- Pictures are taken from the real window by `tools/make_screenshots.py` and copied to `docs/manual/images` by `python tools/make_manual.py --pictures`. A picture with a menu, a dropdown or a hover text open, with the white mouse pointer and red callouts, comes from `tools/manual_scenes.py` and `tools/picture_marks.py` (the real mouse and screen are not used). A drag cannot be shown as a movement: show the pointer at the end and an arrow. All of this is in `tools/TOOLS.md`.
- What is not confirmed on a real machine (G-code on the lathe, a controller other than LinuxCNC) is marked as such in the text.

## Status
- Written: the preface, the File menu chapter, the shortcuts appendix (the user has read these and accepted the way of working, 2026-10-21), and, written 2026-10-29 in one go for the user to read and make notes: the main window, the project and the Setup (with the drawn raw part), contours and the sketch editor, blocks (every type, the styles, the custom path with the locked outline and the stepping). Written the same day, the rest: introduction, installing, the Edit, Tools, Workholding and Materials menus (the Check menu is gone, the checks run by themselves), tools, workholding, machines, postprocessors, checking, exporting, and the appendices (files, glossary, troubleshooting). No chapter has a draft box now. These are for the user to read and correct.
- Facts of the new chapters were taken from the code (form labels from `form_for`, hints and messages from the sketch editor). Things that are not confirmed on a real machine are marked in the text (the thread cycle in material, the drilling cycles in material, cutter compensation in material).
- Guesses made while writing (the user corrects them): the efficiency and the power wording, the advice for the first run on a machine, the order of the posts pages, the order of the chapters is that of use; each block section lists its fields with a short explanation and has a picture of its form; the style pictures are the ones of the program (hover pictures).

## Still to do
- Waiting for the user's notes (tone, detail, errors); then they are worked in.
- All pictures were made fresh on 2026-11-02 (light theme). No pictures yet for the Tools view, the workholding view, the toolboxes window, the materials window.
- Guessed: the first-run advice (Exporting), the power wording, the troubleshooting list.
- Some pictures are small when a wide dialog is scaled to the page (crop, or take them at a higher resolution); an index; a better title page.
- A drag cannot be shown as a movement: show the pointer at the end with an arrow. The pictures with a menu, a dropdown, a hover text, numbered parts or a cropped form are made by `tools/manual_scenes.py`.

## Structure
- Parts and chapters are in `docs/manual/main.tex`: Getting started (introduction, installing, the window), The menus (one chapter per menu), Making a program (project, blocks, contours and the sketch editor, tools, workholding, machines, postprocessors, checking, exporting), Reference (shortcuts, files, glossary, troubleshooting).
- Write in the order of use: the main window, Setup, blocks, contours and the sketch editor first.
- `docs/manual/chapters/file_menu.tex` is the model chapter (complete): every entry of the menu, the questions asked before something is lost, what the user sees. A chapter that is not written has its sections as an outline and a `draftbox`; remove the box when the chapter is written.
- Macros are in `docs/manual/preamble.tex`: `\menu`, `\menupath`, `\button`, `\key`, `\shot`, `notebox`, `draftbox`. Use them; do not format by hand.
- A chapter says what the user wants to do first, then which button or menu does it, then what he sees. No code names, no file names of the program unless the user has to know them.
- `tests/test_manual.py` checks the sources without LaTeX. The pages can be looked at without extra software: `QtPdf` of PySide6 renders a page to a picture.

## Advice for chapters (the user's, keep adding)
- Blocks (turning along a contour and simple turning): roughing stays off the finished part (it is cut only as far as the tool reaches, and the note names what stays), but the finishing pass always follows the contour, whatever the tool can reach. For a contour the tool cannot do (a cavity behind a narrow mouth, an undercut) the user turns the finishing pass off; otherwise the checker reports a collision. Say this plainly in the chapter and show it with a picture.
- Contours and the sketch editor: dimension and constrain a sketch inside itself (relations and dimensions between its own parts) and fix its position to the origin last, so that its position and orientation are easy to change later.
- The sketch editor has no File menu entry: it opens from the Sketch editor button of a contour, tool and workholding item, and by itself when a contour is added. Say what the old Edit shape did not do any more: no offset, no rotate, no mirror of a whole shape (the design notes list these limits in section 5).
- Custom path and the part outline (the user's, 2026-10-29): use as few dimensions to the green outline of the part as you can; they are easier to redo when the part changes. When an earlier block changes the shape of the part (the number of pieces of the outline), every dimension and relation to the part is dropped and the block says so; the path itself stays, and a warning shows that it is not fully constrained any more. A dimension that no longer fits is dropped too.
- Machine-written note (the user's, 2026-11-09): the title page (`main.tex`) and the preface (`chapters/preface.tex`, "Status of this draft") say only that the manual is machine generated, nothing else (no word on tests or on the lathe). Keep both.
- Workholding and threads (the user's, 2026-10-30): for now recommend only the clamping plane (stick-out); the workholding works but is not recommended yet. A multi-start thread is made by repeating the threading block with the start Z moved by the lead divided by the number of starts (Tr40x14 P7: lead 14, shift 7; the depth typed by hand, a designation with P is refused). The user checks the flat of a trapezoid tool against the thread root himself.
