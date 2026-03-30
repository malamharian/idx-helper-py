import asyncio
import re
import threading
from collections import Counter
from datetime import datetime

import flet as ft

import scraper

MAX_CONCURRENT_DOWNLOADS = 5


async def main(page: ft.Page):
    page.title = "IDX Helper"
    page.padding = 20
    page.window.width = 960
    page.window.height = 720

    session = scraper.create_session()
    download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    company_controls: dict[str, dict] = {}
    cancel_flags: dict[str, threading.Event] = {}
    company_attachments: dict[str, list[dict]] = {}

    # ── Log panel ──────────────────────────────────────────────

    log_column = ft.Column(spacing=1, scroll=ft.ScrollMode.AUTO, auto_scroll=True)
    log_container = ft.Container(
        content=log_column,
        height=100,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
        padding=8,
        visible=False,
    )

    def log(msg: str):
        log_column.controls.append(ft.Text(msg, size=11, selectable=True, no_wrap=False))
        if len(log_column.controls) > 500:
            log_column.controls.pop(0)
        log_container.visible = True
        page.update()

    # ── Year / Period ──────────────────────────────────────────

    current_year = datetime.now().year
    year_dd = ft.Dropdown(
        label="Tahun",
        editable=True,
        width=130,
        options=[ft.dropdown.Option(str(y)) for y in range(current_year, 2014, -1)],
        value=str(current_year),
    )

    period_dd = ft.Dropdown(
        label="Periode",
        editable=True,
        width=170,
        options=[
            ft.dropdown.Option("Tahunan"),
            ft.dropdown.Option("TW1"),
            ft.dropdown.Option("TW2"),
            ft.dropdown.Option("TW3"),
        ],
        value="Tahunan",
    )

    # ── File-type checkboxes ───────────────────────────────────

    cb_xlsx = ft.Checkbox(label=".xlsx", value=True)
    cb_pdf = ft.Checkbox(label=".pdf", value=False)
    cb_zip = ft.Checkbox(label=".zip", value=False)
    cb_all = ft.Checkbox(label="All", value=False)
    regex_field = ft.TextField(
        label="Custom regex",
        width=200,
        hint_text=r"e.g. Annual.*\.pdf",
        dense=True,
    )

    def on_all_changed(e):
        if cb_all.value:
            cb_xlsx.value = cb_pdf.value = cb_zip.value = True
        page.update()

    def on_type_changed(e):
        cb_all.value = cb_xlsx.value and cb_pdf.value and cb_zip.value
        page.update()

    cb_all.on_change = on_all_changed
    for cb in (cb_xlsx, cb_pdf, cb_zip):
        cb.on_change = on_type_changed

    # ── Emitens textarea ───────────────────────────────────────

    emitens_field = ft.TextField(
        label="Kode Emiten (opsional)",
        hint_text="One code per row. Leave empty to download for all (fetched from IDX).",
        multiline=True,
        min_lines=4,
        max_lines=12,
    )

    # ── Results section ────────────────────────────────────────

    results_column = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    results_container = ft.Container(
        content=results_column,
        expand=True,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
        padding=8,
    )

    download_dir_text = ft.Text(
        "No directory selected",
        italic=True,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    results_section = ft.Column(visible=False, expand=True)

    # ── File picker ────────────────────────────────────────────

    dir_picker = ft.FilePicker()

    async def pick_download_dir(e):
        path = await dir_picker.get_directory_path(dialog_title="Choose Download Directory")
        if path:
            download_dir_text.value = path
            download_dir_text.italic = False
            download_dir_text.color = None
            page.update()

    # ── Filtering helpers ──────────────────────────────────────

    def get_emitens_filter() -> set[str]:
        text = emitens_field.value or ""
        return {line.strip().upper() for line in text.splitlines() if line.strip()}

    def filter_attachments(attachments: list[dict]) -> list[dict]:
        if cb_all.value:
            return list(attachments)

        exts: set[str] = set()
        if cb_xlsx.value:
            exts.add(".xlsx")
        if cb_pdf.value:
            exts.add(".pdf")
        if cb_zip.value:
            exts.add(".zip")

        regex_pat = None
        raw = (regex_field.value or "").strip()
        if raw:
            try:
                regex_pat = re.compile(raw, re.IGNORECASE)
            except re.error:
                pass

        out: list[dict] = []
        for att in attachments:
            if att.get("File_Type", "") in exts:
                out.append(att)
            elif regex_pat and regex_pat.search(att.get("File_Name", "")):
                out.append(att)
        return out

    def summarize_atts(attachments: list[dict]) -> str:
        c = Counter(a.get("File_Type", "?") for a in attachments)
        return ", ".join(f"{v}x {k}" for k, v in sorted(c.items())) or "no files"

    def summarize_filters() -> str:
        if cb_all.value:
            return "all file types"
        parts: list[str] = []
        if cb_xlsx.value:
            parts.append(".xlsx")
        if cb_pdf.value:
            parts.append(".pdf")
        if cb_zip.value:
            parts.append(".zip")
        raw = (regex_field.value or "").strip()
        if raw:
            parts.append(f"regex:{raw}")
        return ", ".join(parts) or "no file types selected"

    # ── Row helpers ────────────────────────────────────────────

    def update_row(code: str, *, status=None, progress=None, running=None):
        ctrl = company_controls.get(code)
        if not ctrl:
            return
        if status is not None:
            ctrl["status"].value = status
        if progress is not None:
            ctrl["progress"].value = progress
        if running is not None:
            ctrl["running"] = running
            btn = ctrl["button"]
            if running:
                btn.text = "Cancel"
                btn.icon = ft.Icons.CANCEL
                btn.on_click = lambda e, c=code: on_cancel(c)
            else:
                btn.text = "Start"
                btn.icon = ft.Icons.DOWNLOAD
                btn.on_click = lambda e, c=code: on_start(c)
        page.update()

    def build_row(code: str, matched: list[dict]) -> ft.Container:
        pb = ft.ProgressBar(value=0, width=120, bar_height=6)
        st = ft.Text("Ready", size=12, width=150)
        btn = ft.Button(
            "Start",
            icon=ft.Icons.DOWNLOAD,
            height=32,
            on_click=lambda e, c=code: on_start(c),
        )

        company_controls[code] = {
            "progress": pb,
            "status": st,
            "button": btn,
            "running": False,
        }
        company_attachments[code] = matched
        cancel_flags[code] = threading.Event()

        file_list = ft.Column(
            [
                ft.Text(a.get("File_Name", "?"), size=11, color=ft.Colors.ON_SURFACE_VARIANT)
                for a in matched
            ],
            spacing=2,
        )

        header_row = ft.Row(
            [
                ft.Text(code, weight=ft.FontWeight.BOLD, width=60, size=13),
                ft.Text(f"{len(matched)} file(s)", size=12, color=ft.Colors.ON_SURFACE_VARIANT, width=80),
                pb,
                st,
                btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        return ft.Container(
            content=ft.Column([header_row, file_list], spacing=4),
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=6,
        )

    # ── Download logic ─────────────────────────────────────────

    async def download_company(code: str):
        ctrl = company_controls.get(code)
        if not ctrl or ctrl["running"]:
            return

        download_dir = download_dir_text.value
        if not download_dir or download_dir == "No directory selected":
            await flash_pick_dir_error()
            return

        year = (year_dd.value or "").strip()
        period = (period_dd.value or "").strip().lower()
        matched = company_attachments.get(code, [])
        if not matched:
            update_row(code, status="No files", running=False)
            return

        cancel_flags[code] = threading.Event()
        update_row(code, status="Queued...", progress=0, running=True)

        async with download_sem:
            if cancel_flags[code].is_set():
                update_row(code, status="Cancelled", running=False)
                return

            total = len(matched)
            ok = 0

            for i, att in enumerate(matched):
                if cancel_flags[code].is_set():
                    update_row(code, status=f"Cancelled ({ok}/{total})", running=False)
                    return

                fname = att.get("File_Name", "")
                update_row(code, status=f"Downloading {i + 1}/{total}...")

                success = await asyncio.to_thread(
                    scraper.download_file,
                    session,
                    code,
                    fname,
                    att.get("File_Path", ""),
                    download_dir,
                    year,
                    period,
                    cancelled=cancel_flags[code].is_set,
                )

                if success:
                    ok += 1
                    log(f"[{code}] {fname}")
                elif cancel_flags[code].is_set():
                    update_row(code, status=f"Cancelled ({ok}/{total})", running=False)
                    return
                else:
                    log(f"[{code}] FAILED: {fname}")

                update_row(code, progress=(i + 1) / total)

            label = "Done" if ok == total else "Partial"
            update_row(code, status=f"{label} ({ok}/{total})", progress=1.0, running=False)

    def on_start(code: str):
        page.run_task(download_company, code)

    def on_cancel(code: str):
        f = cancel_flags.get(code)
        if f:
            f.set()

    # ── Fetch ──────────────────────────────────────────────────

    fetch_btn = ft.Button("Fetch Reports", icon=ft.Icons.SEARCH)
    fetch_spinner = ft.ProgressRing(visible=False, width=20, height=20, stroke_width=3)

    async def on_fetch(e):
        year = (year_dd.value or "").strip()
        period = (period_dd.value or "").strip()
        if not year or not period:
            log("Tahun dan Periode harus diisi.")
            return

        for f in cancel_flags.values():
            f.set()

        fetch_btn.disabled = True
        fetch_spinner.visible = True
        page.update()

        try:
            data = await asyncio.to_thread(scraper.fetch_reports, session, year, period)
        except Exception as ex:
            log(f"Fetch error: {ex}")
            fetch_btn.disabled = False
            fetch_spinner.visible = False
            page.update()
            return

        fetch_btn.disabled = False
        fetch_spinner.visible = False

        if not data or "Results" not in data:
            log("No results from API.")
            page.update()
            return

        results = data.get("Results", [])
        log(f"API returned {data.get('ResultCount', len(results))} companies.")

        emitens = get_emitens_filter()

        company_controls.clear()
        cancel_flags.clear()
        company_attachments.clear()
        results_column.controls.clear()

        shown = 0
        for r in results:
            code = r.get("KodeEmiten", "").upper()
            if emitens and code not in emitens:
                continue
            matched = filter_attachments(r.get("Attachments", []))
            results_column.controls.append(build_row(code, matched))
            shown += 1

        emitens_note = "filtered" if emitens else "all emitens"
        log(f"Showing {shown} companies ({emitens_note}, {summarize_filters()}).")
        results_section.visible = shown > 0
        page.update()

    fetch_btn.on_click = on_fetch

    # ── Start All / Cancel All ─────────────────────────────────

    async def flash_pick_dir_error():
        pick_dir_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.ERROR)
        log("Please select a download directory first.")
        page.update()
        await asyncio.sleep(2)
        pick_dir_btn.style = None
        page.update()

    def on_start_all(e):
        download_dir = download_dir_text.value
        if not download_dir or download_dir == "No directory selected":
            page.run_task(flash_pick_dir_error)
            return
        for code in company_controls:
            if not company_controls[code]["running"] and company_attachments.get(code):
                page.run_task(download_company, code)

    def on_cancel_all(e):
        for f in cancel_flags.values():
            f.set()

    start_all_btn = ft.Button(
        "Start All",
        icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
        on_click=on_start_all,
    )
    cancel_all_btn = ft.OutlinedButton(
        "Cancel All",
        icon=ft.Icons.CANCEL,
        on_click=on_cancel_all,
    )
    pick_dir_btn = ft.Button(
        "Choose Directory",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=pick_download_dir,
    )

    # ── Layout ─────────────────────────────────────────────────

    controls_section = ft.Column(
        [
            ft.Row([year_dd, period_dd, fetch_btn, fetch_spinner], spacing=12),
            ft.Row(
                [
                    ft.Text("File types:", weight=ft.FontWeight.W_500),
                    cb_xlsx,
                    cb_pdf,
                    cb_zip,
                    cb_all,
                    regex_field,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            emitens_field,
        ],
        spacing=12,
    )

    results_section.controls = [
        ft.Row(
            [
                pick_dir_btn,
                download_dir_text,
                ft.Container(expand=True),
                start_all_btn,
                cancel_all_btn,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        results_container,
    ]

    page.services.append(dir_picker)
    page.add(
        ft.Column(
            [controls_section, ft.Divider(), results_section, log_container],
            expand=True,
            spacing=12,
        )
    )


ft.run(main)
