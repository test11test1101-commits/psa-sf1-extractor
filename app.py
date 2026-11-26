"""Windows Desktop Application: PSA Birth Certificate (2007/Current) to SF1 Excel Extractor."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from psa_sf1.models import PSADocumentRecord
from psa_sf1.ocr_engine import OCREngine
from psa_sf1.pipeline import process_psa_file
from psa_sf1.sf1_exporter import export_to_sf1_xlsx


EXPORT_SUCCESS_MESSAGE = (
    "Export Successful! Please check for errors in the Excel file before submitting as SF1."
)


class PSASF1App(tk.Tk):
    """Main Tkinter window for uploading PSA files, reviewing extracted fields, and exporting SF1."""

    COLUMNS = (
        ("source_file", "Source File", 150),
        ("name", "Name", 210),
        ("birthdate", "Birthdate", 100),
        ("sex", "Sex", 55),
        ("father_name", "Father's Name", 200),
        ("mother_maiden_name", "Mother's Maiden Name", 200),
        ("format_detected", "Format", 115),
        ("status", "Status", 90),
    )
    EDITABLE_COLS = {"name", "birthdate", "sex", "father_name", "mother_maiden_name"}

    def __init__(self) -> None:
        super().__init__()
        self.title("PSA to SF1 Excel Extractor (2007 / Current Format)")
        self.geometry("1180x640")
        self.minsize(960, 520)

        self.records: List[PSADocumentRecord] = []
        self._ocr_engine: Optional[OCREngine] = None
        self._queue: queue.Queue = queue.Queue()
        self._is_processing = False
        self._edit_entry: Optional[tk.Entry] = None

        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        # Top header
        header_frame = ttk.Frame(self, padding=(14, 12, 14, 6))
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text="PSA Birth Certificate to SF1 Extractor",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            header_frame,
            text=(
                "Upload multiple .jpg or .pdf PSA documents (2007 or current format only). "
                "Double-click any extracted cell to edit before exporting."
            ),
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(2, 0))

        # Action toolbar
        toolbar = ttk.Frame(self, padding=(14, 6))
        toolbar.pack(fill=tk.X)

        self.upload_btn = ttk.Button(toolbar, text="Upload", command=self._on_upload, width=14)
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.export_btn = ttk.Button(toolbar, text="Export", command=self._on_export, width=14)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 16))

        self.remove_btn = ttk.Button(toolbar, text="Remove Selected", command=self._on_remove_selected)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.clear_btn = ttk.Button(toolbar, text="Clear All", command=self._on_clear_all)
        self.clear_btn.pack(side=tk.LEFT)

        self.count_var = tk.StringVar(value="0 documents loaded")
        ttk.Label(toolbar, textvariable=self.count_var, font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        # Progress bar & status
        status_frame = ttk.Frame(self, padding=(14, 2, 14, 6))
        status_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(status_frame, mode="determinate")
        self.progress.pack(fill=tk.X, side=tk.TOP)

        self.status_var = tk.StringVar(value="Ready. Click [Upload] to select PSA .jpg or .pdf files.")
        ttk.Label(status_frame, textvariable=self.status_var, font=("Segoe UI", 9)).pack(
            anchor=tk.W, pady=(4, 0)
        )

        # Table (Treeview)
        table_frame = ttk.Frame(self, padding=(14, 4, 14, 14))
        table_frame.pack(fill=tk.BOTH, expand=True)

        col_ids = [c[0] for c in self.COLUMNS]
        self.tree = ttk.Treeview(table_frame, columns=col_ids, show="headings", selectmode="extended")

        for col_id, heading, width in self.COLUMNS:
            self.tree.heading(col_id, text=heading)
            anchor = tk.CENTER if col_id in ("birthdate", "sex", "status") else tk.W
            self.tree.column(col_id, width=width, minwidth=50, anchor=anchor)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._on_double_click)

    def _set_busy(self, busy: bool) -> None:
        self._is_processing = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.upload_btn.config(state=state)
        self.export_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.clear_btn.config(state=state)

    def _on_upload(self) -> None:
        if self._is_processing:
            return

        file_paths = filedialog.askopenfilenames(
            title="Select PSA Birth Certificate Files (.jpg or .pdf)",
            filetypes=[
                ("PSA Documents (*.jpg, *.jpeg, *.pdf)", "*.jpg *.jpeg *.pdf"),
                ("JPEG Images (*.jpg, *.jpeg)", "*.jpg *.jpeg"),
                ("PDF Documents (*.pdf)", "*.pdf"),
            ],
        )
        if not file_paths:
            return

        self._set_busy(True)
        self.progress["maximum"] = len(file_paths)
        self.progress["value"] = 0
        self.status_var.set(f"Initializing OCR and processing {len(file_paths)} file(s)...")

        worker = threading.Thread(
            target=self._process_files_worker,
            args=(list(file_paths),),
            daemon=True,
        )
        worker.start()

    def _process_files_worker(self, file_paths: List[str]) -> None:
        try:
            if self._ocr_engine is None:
                self._queue.put(("status", "Loading offline OCR engine..."))
                self._ocr_engine = OCREngine()

            total = len(file_paths)
            for idx, fp in enumerate(file_paths, start=1):
                name = Path(fp).name
                self._queue.put(("status", f"Cleaning & reading ({idx}/{total}): {name}"))
                try:
                    record = process_psa_file(fp, ocr_engine=self._ocr_engine)
                except Exception as exc:
                    record = PSADocumentRecord(
                        source_file=name,
                        format_detected="Error",
                        status="Error",
                        warnings=[str(exc)],
                    )
                self._queue.put(("record", record, idx, total))
        except Exception as exc:
            self._queue.put(("error", f"OCR initialization failed: {exc}"))
        finally:
            self._queue.put(("done",))

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status_var.set(msg[1])
                elif kind == "record":
                    _, record, idx, total = msg
                    self._add_record(record)
                    self.progress["value"] = idx
                    self.count_var.set(f"{len(self.records)} document(s) loaded")
                elif kind == "error":
                    messagebox.showerror("Processing Error", msg[1])
                elif kind == "done":
                    self._set_busy(False)
                    self.status_var.set(
                        f"Finished processing. {len(self.records)} document(s) ready for export."
                    )
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_queue)

    def _add_record(self, rec: PSADocumentRecord) -> None:
        self.records.append(rec)
        status_text = rec.status if not rec.warnings else f"{rec.status}: {rec.warnings[0]}"
        self.tree.insert(
            "",
            tk.END,
            values=(
                rec.source_file,
                rec.name,
                rec.birthdate,
                rec.sex,
                rec.father_name,
                rec.mother_maiden_name,
                rec.format_detected,
                status_text,
            ),
        )

    def _on_double_click(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.tree.identify_row(event.y)
        col_ident = self.tree.identify_column(event.x)
        if not row_id or not col_ident:
            return

        col_idx = int(col_ident.replace("#", "")) - 1
        col_name = self.COLUMNS[col_idx][0]
        if col_name not in self.EDITABLE_COLS:
            return

        bbox = self.tree.bbox(row_id, col_ident)
        if not bbox:
            return

        if self._edit_entry is not None:
            self._edit_entry.destroy()

        x, y, w, h = bbox
        current_val = self.tree.set(row_id, col_name)
        entry = tk.Entry(self.tree, font=("Segoe UI", 9))
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, current_val)
        entry.select_range(0, tk.END)
        entry.focus()
        self._edit_entry = entry

        def commit(_event: Optional[tk.Event] = None) -> None:
            new_val = entry.get().strip()
            self.tree.set(row_id, col_name, new_val)
            row_index = self.tree.index(row_id)
            setattr(self.records[row_index], col_name, new_val)
            entry.destroy()
            self._edit_entry = None

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _e: (entry.destroy(), setattr(self, "_edit_entry", None)))

    def _on_remove_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        indices = sorted((self.tree.index(item) for item in selected), reverse=True)
        for item in selected:
            self.tree.delete(item)
        for idx in indices:
            del self.records[idx]
        self.count_var.set(f"{len(self.records)} document(s) loaded")

    def _on_clear_all(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.records.clear()
        self.progress["value"] = 0
        self.count_var.set("0 documents loaded")
        self.status_var.set("Cleared. Click [Upload] to select PSA .jpg or .pdf files.")

    def _on_export(self) -> None:
        if not self.records:
            messagebox.showwarning("No Data", "Please upload at least one PSA document before exporting.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Save SF1 Excel File",
            defaultextension=".xlsx",
            initialfile="SF1_Extracted.xlsx",
            filetypes=[("Excel Workbook (*.xlsx)", "*.xlsx")],
        )
        if not output_path:
            return

        try:
            export_to_sf1_xlsx(self.records, output_path)
        except Exception as exc:
            messagebox.showerror("Export Failed", f"Could not write Excel file:\n{exc}")
            return

        self.status_var.set(f"Exported to {output_path}")
        messagebox.showinfo("Export Successful", EXPORT_SUCCESS_MESSAGE)


def main() -> None:
    app = PSASF1App()
    app.mainloop()


if __name__ == "__main__":
    main()

