import os
import sys
import json
import csv
import subprocess
import time
import winreg
import threading
import ctypes
import urllib.request
import customtkinter as ctk
from tkinter import messagebox, filedialog

# Configuration Paths
DATA_FILE = os.path.join(os.path.expanduser("~"), ".anydesk_manager_data.json")
ANYDESK_CONFIG_DIR = r"C:\ProgramData\AnyDesk"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "AnyDeskManagerApp"
ANYDESK_DOWNLOAD_URL = "https://download.anydesk.com/AnyDesk.exe"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AnyDeskManager(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AnyDesk Manager & Timer Reset")
        self.geometry("740x760")
        self.resizable(False, False)

        self.monitoring = False
        self.entries = self.load_data()
        self.editing_id = None
        self.active_proc = None

        self.create_widgets()
        self.refresh_list()
        self.update_install_button_state()
        self.monitor_process()

        # Global click binding to handle unfocusing safely
        self.bind("<Button-1>", self.handle_global_click)

        # Handle PyInstaller temporary directory path for bundled assets
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        icon_path = os.path.join(base_path, "app_icon.ico")

        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

    # --- Focus Management ---
    def handle_global_click(self, event):
        widget = event.widget
        entry_widgets = [self.search_entry, self.id_entry, self.pwd_entry, self.note_entry]
        
        try:
            is_input_click = any(
                widget == entry or widget in entry.winfo_children()
                for entry in entry_widgets
            )
            if not is_input_click:
                self.focus_set()
        except Exception:
            pass

    # --- AnyDesk Binary Path & UI State Management ---
    def get_anydesk_path(self):
        possible_paths = [
            r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
            r"C:\Program Files\AnyDesk\AnyDesk.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\AnyDesk\AnyDesk.exe")
        ]
        return next((p for p in possible_paths if os.path.exists(p)), None)

    def is_anydesk_installed(self):
        return self.get_anydesk_path() is not None

    def set_ui_state(self, state="normal"):
        """Recursively enable or disable all main interactive widgets except Install Button."""
        frames_to_toggle = [
            self.session_frame,
            self.form_container,
            self.list_header,
            self.scroll_frame,
            self.bottom_bar
        ]

        # Reset button inside top frame
        self.reset_btn.configure(state=state)
        self.autostart_cb.configure(state=state)

        for container in frames_to_toggle:
            self._toggle_container_widgets(container, state)

    def _toggle_container_widgets(self, parent, state):
        for child in parent.winfo_children():
            if isinstance(child, (ctk.CTkFrame, ctk.CTkScrollableFrame)):
                self._toggle_container_widgets(child, state)
            else:
                try:
                    if child == self.stop_btn and not self.active_proc and state == "normal":
                        child.configure(state="disabled")
                    else:
                        child.configure(state=state)
                except Exception:
                    pass

    def update_install_button_state(self):
        if self.is_anydesk_installed():
            self.install_btn.configure(
                text="Uninstall AnyDesk",
                fg_color="#D32F2F",
                hover_color="#9A0007",
                command=self.confirm_uninstall
            )
            self.set_ui_state("normal")
        else:
            self.install_btn.configure(
                text="Install AnyDesk",
                fg_color="#2E7D32",
                hover_color="#1B5E20",
                command=self.start_install_thread
            )
            self.set_ui_state("disabled")

    # --- Data & Startup Management ---
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data.get("entries", [])
                    elif isinstance(data, list):
                        return data
            except Exception:
                return []
        return []

    def save_data(self):
        """Saves entries without wiping out autostart settings in JSON."""
        current_data = {}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        current_data = loaded
            except Exception:
                pass

        current_data["entries"] = self.entries
        current_data["autostart_enabled"] = self.is_autostart_enabled()

        with open(DATA_FILE, "w") as f:
            json.dump(current_data, f, indent=4)

    def is_autostart_enabled(self):
        """Checks if the scheduled autostart task exists in Windows."""
        task_name = "AnyDeskManagerApp_Autostart"
        try:
            res = subprocess.run(f'schtasks /Query /TN "{task_name}"', shell=True, capture_output=True, text=True)
            return res.returncode == 0 and task_name in res.stdout
        except Exception:
            return False

    def toggle_autostart(self):
        task_name = "AnyDeskManagerApp_Autostart"
        is_ticked = self.autostart_var.get()

        if is_ticked:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
                tr_cmd = f'\\"{exe_path}\\"'
            else:
                py_exe = sys.executable
                script = os.path.abspath(__file__)
                tr_cmd = f'\\"{py_exe}\\" \\"{script}\\"'

            username = os.getlogin()

            # /SC ONLOGON triggers right after password entry
            # /RU specifies your user account
            # /IT ensures the window renders on your visible interactive desktop
            # /RL HIGHEST runs with Admin rights without showing a UAC prompt
            cmd = (
                f'schtasks /Create /TN "{task_name}" /TR "{tr_cmd}" '
                f'/SC ONLOGON /RU "{username}" /RL HIGHEST /IT /F'
            )

            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                messagebox.showerror("Autostart Error", f"Could not create scheduled task:\n{res.stderr.strip()}")
                self.autostart_var.set(False)
        else:
            cmd = f'schtasks /Delete /TN "{task_name}" /F'
            subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # --- CSV Import & Export ---
    def export_to_csv(self):
        if not self.entries:
            messagebox.showwarning("Export Warning", "No connections available to export.")
            return

        file_path = filedialog.asksaveasfilename(
            initialfile="anydesk_connections.csv",  # Sets the default file name
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Export Connections to CSV"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["ID", "Password", "Note"])
                for entry in self.entries:
                    writer.writerow([entry.get("id", ""), entry.get("pwd", ""), entry.get("note", "")])
            messagebox.showinfo("Export Successful", f"Successfully exported {len(self.entries)} entries to CSV.")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")

    def import_from_csv(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv")],
            title="Import Connections from CSV"
        )
        if not file_path:
            return

        imported_count = 0
        skipped_count = 0
        existing_ids = {str(item["id"]).strip() for item in self.entries}

        try:
            with open(file_path, mode="r", encoding="utf-8-sig") as file:
                reader = csv.reader(file)
                header = next(reader, None)

                for row in reader:
                    if not row or len(row) == 0:
                        continue

                    anydesk_id = row[0].strip()
                    if not anydesk_id:
                        continue

                    if anydesk_id in existing_ids:
                        skipped_count += 1
                        continue

                    pwd = row[1].strip() if len(row) > 1 else ""
                    note = row[2].strip() if len(row) > 2 else ""

                    self.entries.append({
                        "id": anydesk_id,
                        "pwd": pwd,
                        "note": note,
                        "last_used": time.time()
                    })
                    existing_ids.add(anydesk_id)
                    imported_count += 1

            self.save_data()
            self.refresh_list()
            messagebox.showinfo(
                "Import Summary",
                f"Import complete!\n\nImported: {imported_count}\nSkipped (Duplicates): {skipped_count}"
            )
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import CSV:\n{e}")

    # --- UI Setup ---
    def create_widgets(self):
        # Top Header Bar
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=15, pady=10)

        self.autostart_var = ctk.BooleanVar(value=self.is_autostart_enabled())
        self.autostart_cb = ctk.CTkCheckBox(
            top_frame, text="Auto-start with Windows", 
            variable=self.autostart_var, command=self.toggle_autostart
        )
        self.autostart_cb.pack(side="left", padx=10, pady=10)

        # Action Buttons Container (Right Header)
        btn_container = ctk.CTkFrame(top_frame, fg_color="transparent")
        btn_container.pack(side="right", padx=5)

        self.install_btn = ctk.CTkButton(btn_container, text="", width=120)
        self.install_btn.pack(side="right", padx=5, pady=10)

        self.reset_btn = ctk.CTkButton(
            btn_container, text="Reset AnyDesk Timer/ID", 
            fg_color="#D32F2F", hover_color="#9A0007", command=self.start_reset_thread
        )
        self.reset_btn.pack(side="right", padx=5, pady=10)

        # Active Session Control Panel
        self.session_frame = ctk.CTkFrame(self)
        self.session_frame.pack(fill="x", padx=15, pady=5)

        self.status_lbl = ctk.CTkLabel(self.session_frame, text="Status: Ready / Idle", font=("Arial", 12, "bold"))
        self.status_lbl.pack(side="left", padx=15, pady=10)

        self.stop_btn = ctk.CTkButton(
            self.session_frame, text="Stop Active Connection", fg_color="#D32F2F", 
            hover_color="#9A0007", state="disabled", command=self.stop_anydesk_session
        )
        self.stop_btn.pack(side="right", padx=10, pady=10)

        # Form Container
        self.form_container = ctk.CTkFrame(self, fg_color="transparent")
        self.form_container.pack(fill="x", padx=15, pady=5)

        self.add_entry_btn = ctk.CTkButton(
            self.form_container, text="+ Add New Entry", font=("Arial", 13, "bold"),
            height=35, command=self.show_add_mode
        )
        self.add_entry_btn.pack(fill="x", pady=5)

        # Collapsible Form Section
        self.form_frame = ctk.CTkFrame(self.form_container)

        self.mode_label = ctk.CTkLabel(
            self.form_frame, text="New Entry", 
            font=("Arial", 14, "bold"), text_color="#1F6AA5"
        )
        self.mode_label.pack(anchor="center", pady=(10, 5))

        # Inputs
        r1 = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r1, text="AnyDesk ID:", width=100, anchor="w", font=("Arial", 12, "bold")).pack(side="left")
        self.id_entry = ctk.CTkEntry(r1, placeholder_text="e.g. 1495263448")
        self.id_entry.pack(side="left", fill="x", expand=True)

        r2 = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r2, text="Password:", width=100, anchor="w", font=("Arial", 12, "bold")).pack(side="left")
        self.pwd_entry = ctk.CTkEntry(r2, placeholder_text="Enter password", show="*")
        self.pwd_entry.pack(side="left", fill="x", expand=True)

        r3 = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        r3.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(r3, text="Note / Name:", width=100, anchor="w", font=("Arial", 12, "bold")).pack(side="left")
        self.note_entry = ctk.CTkEntry(r3, placeholder_text="e.g. Office PC, Client A")
        self.note_entry.pack(side="left", fill="x", expand=True)

        r4 = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        r4.pack(fill="x", padx=10, pady=(6, 10))

        self.save_btn = ctk.CTkButton(r4, text="Save / Update Entry", command=self.save_entry)
        self.save_btn.pack(side="right", padx=5)

        cancel_btn = ctk.CTkButton(r4, text="Cancel", fg_color="gray", width=80, command=self.hide_form)
        cancel_btn.pack(side="right", padx=5)

        # Header Search Area
        self.list_header = ctk.CTkFrame(self)
        self.list_header.pack(fill="x", padx=15, pady=(10, 0))
        
        ctk.CTkLabel(self.list_header, text="Saved Connections", font=("Arial", 12, "bold")).pack(side="left", padx=10, pady=5)

        self.search_entry = ctk.CTkEntry(self.list_header, placeholder_text="Search ID or Note...", width=220)
        self.search_entry.pack(side="right", padx=10, pady=5)
        
        self.search_entry.bind("<KeyRelease>", lambda event: self.refresh_list())
        self.search_entry.bind("<Escape>", lambda event: self.focus_set())
        self.search_entry.bind("<Return>", lambda event: self.focus_set())

        # Middle Scroll Frame
        self.scroll_frame = ctk.CTkScrollableFrame(self, height=240)
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(10, 5))

        # Bottom Bar
        self.bottom_bar = ctk.CTkFrame(self)
        self.bottom_bar.pack(fill="x", padx=15, pady=(0, 10))

        export_btn = ctk.CTkButton(
            self.bottom_bar, text="Export (CSV)", fg_color="#2E7D32", 
            hover_color="#1B5E20", width=120, command=self.export_to_csv
        )
        export_btn.pack(side="right", padx=10, pady=8)

        import_btn = ctk.CTkButton(
            self.bottom_bar, text="Import (CSV)", fg_color="#1F6AA5", 
            hover_color="#144870", width=120, command=self.import_from_csv
        )
        import_btn.pack(side="right", padx=0, pady=8)

    # --- Install & Uninstall Logic ---
    def confirm_uninstall(self):
        confirm = messagebox.askyesno(
            "Confirm Uninstall",
            "Are you sure you want to uninstall AnyDesk from this computer?"
        )
        if confirm:
            self.status_lbl.configure(text="Status: Uninstalling AnyDesk...")
            threading.Thread(target=self.perform_uninstall, daemon=True).start()

    def perform_uninstall(self):
        anydesk_bin = self.get_anydesk_path()
        if anydesk_bin:
            subprocess.run("taskkill /F /IM AnyDesk.exe", shell=True, capture_output=True)
            subprocess.run(f'"{anydesk_bin}" --uninstall --silent', shell=True, capture_output=True)
            time.sleep(2)

        self.after(0, self.update_install_button_state)
        self.after(0, lambda: self.status_lbl.configure(text="Status: AnyDesk Uninstalled"))
        self.after(0, lambda: messagebox.showinfo("Uninstall Complete", "AnyDesk has been successfully uninstalled."))

    def start_install_thread(self):
        self.status_lbl.configure(text="Status: Downloading latest AnyDesk...")
        threading.Thread(target=self.perform_install, daemon=True).start()

    def perform_install(self):
        temp_installer = os.path.join(os.path.expanduser("~"), "AnyDesk_Setup.exe")
        try:
            # Bypass Cloudflare / HTTP 403 blocks by setting a browser User-Agent
            req = urllib.request.Request(
                ANYDESK_DOWNLOAD_URL, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            )

            with urllib.request.urlopen(req) as response, open(temp_installer, 'wb') as out_file:
                out_file.write(response.read())
            
            self.after(0, lambda: self.status_lbl.configure(text="Status: Installing AnyDesk..."))
            
            # Silent Installation
            cmd = f'"{temp_installer}" --install "C:\\Program Files (x86)\\AnyDesk" --start-with-win --silent'
            subprocess.run(cmd, shell=True, capture_output=True)
            time.sleep(3)

            if os.path.exists(temp_installer):
                try:
                    os.remove(temp_installer)
                except Exception:
                    pass

            self.after(0, self.update_install_button_state)
            self.after(0, lambda: self.status_lbl.configure(text="Status: AnyDesk Installed Successfully"))
            self.after(0, lambda: messagebox.showinfo("Install Complete", "The latest version of AnyDesk has been installed!"))

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Install Error", f"Failed to download or install AnyDesk:\n{e}"))
            self.after(0, lambda: self.status_lbl.configure(text="Status: Installation Failed"))

    # --- Form & View Controls ---
    def show_add_mode(self):
        self.clear_inputs()
        self.editing_id = None
        self.mode_label.configure(text="Creating New Entry")
        self.add_entry_btn.pack_forget()
        self.form_frame.pack(fill="x", pady=5)

    def show_edit_mode(self, item):
        self.clear_inputs()
        self.editing_id = item['id']
        self.id_entry.insert(0, item['id'])
        
        # Ensure password field is masked when populated
        self.pwd_entry.configure(show="*")
        self.pwd_entry.insert(0, item.get('pwd', ''))
        
        self.note_entry.insert(0, item.get('note', ''))
        self.mode_label.configure(text=f"Editing Entry: {item['id']}")
        self.add_entry_btn.pack_forget()
        self.form_frame.pack(fill="x", pady=5)

    def hide_form(self):
        self.clear_inputs()
        self.form_frame.pack_forget()
        self.add_entry_btn.pack(fill="x", pady=5)

    def refresh_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        query = self.search_entry.get().strip().lower()
        sorted_entries = sorted(self.entries, key=lambda x: x.get("last_used", 0), reverse=True)
        current_ui_state = "normal" if self.is_anydesk_installed() else "disabled"

        for item in sorted_entries:
            item_id = str(item.get('id', '')).lower()
            item_note = str(item.get('note', '')).lower()

            if query and (query not in item_id and query not in item_note):
                continue

            row = ctk.CTkFrame(self.scroll_frame)
            row.pack(fill="x", pady=4, padx=5)

            note_str = f" [{item.get('note')}]" if item.get('note') else ""
            display_text = f"ID: {item['id']}{note_str}"
            ctk.CTkLabel(row, text=display_text, anchor="w", font=("Arial", 12)).pack(side="left", padx=10, fill="x", expand=True)

            ctk.CTkButton(
                row, text="Connect", width=75, state=current_ui_state,
                command=lambda i=item['id'], p=item.get('pwd', ''): self.start_connection_thread(i, p)
            ).pack(side="right", padx=3, pady=5)

            ctk.CTkButton(
                row, text="Edit", width=60, fg_color="gray", state=current_ui_state,
                command=lambda data=item: self.show_edit_mode(data)
            ).pack(side="right", padx=3, pady=5)

            ctk.CTkButton(
                row, text="Delete", width=60, fg_color="#D32F2F", hover_color="#9A0007", state=current_ui_state,
                command=lambda i=item['id'], n=item.get('note', ''): self.delete_entry(i, n)
            ).pack(side="right", padx=3, pady=5)

    def save_entry(self):
        anydesk_id = self.id_entry.get().strip()
        pwd = self.pwd_entry.get().strip()
        note = self.note_entry.get().strip()

        if not anydesk_id:
            messagebox.showwarning("Input Error", "AnyDesk ID cannot be empty.")
            return

        if self.editing_id and self.editing_id != anydesk_id:
            self.entries = [i for i in self.entries if i['id'] != self.editing_id]

        existing = next((item for item in self.entries if item['id'] == anydesk_id), None)
        if existing:
            existing['pwd'] = pwd
            existing['note'] = note
            existing['last_used'] = time.time()
        else:
            self.entries.append({
                "id": anydesk_id,
                "pwd": pwd,
                "note": note,
                "last_used": time.time()
            })

        self.save_data()
        self.hide_form()
        self.refresh_list()

    def clear_inputs(self):
        self.editing_id = None
        self.id_entry.delete(0, 'end')
        self.pwd_entry.delete(0, 'end')
        self.note_entry.delete(0, 'end')

    def delete_entry(self, anydesk_id, note):
        label_text = f"ID: {anydesk_id}" + (f" ({note})" if note else "")
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete this connection?\n\n{label_text}"
        )
        if not confirm:
            return

        self.entries = [i for i in self.entries if i['id'] != anydesk_id]
        self.save_data()
        if self.editing_id == anydesk_id:
            self.hide_form()
        self.refresh_list()

    # --- Connection & Threading Logic ---
    def start_connection_thread(self, anydesk_id, password):
        if not self.is_anydesk_installed():
            messagebox.showerror("Error", "AnyDesk is not installed on this system.")
            return

        if self.active_proc and self.active_proc.poll() is None:
            messagebox.showwarning("Active Session", "An AnyDesk session is already active. Stop it first.")
            return

        threading.Thread(target=self.connect_anydesk, args=(anydesk_id, password), daemon=True).start()

    def is_anydesk_running(self):
        """Checks if AnyDesk.exe is already running in system processes."""
        try:
            output = subprocess.check_output('tasklist /FI "IMAGENAME eq AnyDesk.exe"', shell=True, text=True)
            return "AnyDesk.exe" in output
        except Exception:
            return False

    def connect_anydesk(self, anydesk_id, password):
        # Update last used timestamp
        for item in self.entries:
            if item['id'] == anydesk_id:
                item['last_used'] = time.time()
                break
        self.save_data()
        self.after(0, self.refresh_list)
        self.after(0, lambda: self.status_lbl.configure(text=f"Status: Connecting to {anydesk_id}..."))
        self.after(0, lambda: self.stop_btn.configure(state="normal"))

        anydesk_bin = self.get_anydesk_path() or "anydesk.exe"

        try:
            # Ensure background service is running
            subprocess.run("net start anydesk", shell=True, capture_output=True)

            already_open = self.is_anydesk_running()

            if not already_open:
                subprocess.Popen([anydesk_bin])
                time.sleep(1.5)

            if password:
                self.active_proc = subprocess.Popen(
                    [anydesk_bin, anydesk_id, "--with-password"], 
                    stdin=subprocess.PIPE, 
                    text=True
                )
                self.active_proc.communicate(input=f"{password}\n")
            else:
                self.active_proc = subprocess.Popen([anydesk_bin, anydesk_id])

            # Safely hand off monitoring initialization back to the main thread
            self.after(0, self.start_monitoring)

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Execution Error", f"Failed to launch AnyDesk:\n{e}"))

    def start_monitoring(self):
        """Safely called on the main UI thread."""
        if not getattr(self, 'monitoring', False):
            self.monitoring = True
            # Call your loop method (e.g. self.monitor_process())
            if hasattr(self, 'monitor_process'):
                self.monitor_process()

    def stop_anydesk_session(self):
        subprocess.run("taskkill /F /IM AnyDesk.exe", shell=True, capture_output=True)
        self.active_proc = None
        self.status_lbl.configure(text="Status: Stopped manually")
        self.stop_btn.configure(state="disabled")

    def monitor_process(self):
        if self.active_proc:
            if self.active_proc.poll() is not None:
                self.active_proc = None
                self.status_lbl.configure(text="Status: Session closed")
                self.stop_btn.configure(state="disabled")
            else:
                self.status_lbl.configure(text="Status: Connection Active")
        
        self.after(1000, self.monitor_process)

    # --- Safe Timer Reset Logic ---
    def start_reset_thread(self):
        if not self.is_anydesk_installed():
            messagebox.showwarning("Reset Warning", "AnyDesk is not installed.")
            return

        confirm = messagebox.askyesno(
            "Confirm Reset",
            "This will close active AnyDesk instances and reset the background service files. Proceed?"
        )
        if not confirm:
            return

        self.status_lbl.configure(text="Status: Resetting AnyDesk service...")
        threading.Thread(target=self.perform_reset, daemon=True).start()

    def perform_reset(self):
        subprocess.run("taskkill /F /IM AnyDesk.exe", shell=True, capture_output=True)
        subprocess.run("net stop anydesk", shell=True, capture_output=True)

        time.sleep(2)

        files_to_delete = ["service.conf", "service.conf.lock", "system.conf", "system.conf.lock"]
        deleted = 0
        failed = 0

        for file_name in files_to_delete:
            file_path = os.path.join(ANYDESK_CONFIG_DIR, file_name)
            if os.path.exists(file_path):
                subprocess.run(f'attrib -r -s -h "{file_path}"', shell=True, capture_output=True)
                is_deleted = False
                for _ in range(3):
                    try:
                        os.remove(file_path)
                        is_deleted = True
                        break
                    except Exception:
                        time.sleep(0.5)

                if is_deleted:
                    deleted += 1
                else:
                    failed += 1

        subprocess.run("net start anydesk", shell=True, capture_output=True)

        self.after(0, lambda: self.status_lbl.configure(text="Status: AnyDesk Reset Completed"))
        self.after(0, lambda: self.stop_btn.configure(state="disabled"))
        
        status_msg = f"AnyDesk Reset Complete!\n\nDeleted config files: {deleted}\nFailed/Locked: {failed}"
        self.after(0, lambda: messagebox.showinfo("Reset Complete", status_msg))

# --- UAC Administrator Execution Handler ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

if __name__ == "__main__":
    if not is_admin():
        if getattr(sys, 'frozen', False):
            executable = sys.executable
            arguments = " ".join(sys.argv[1:])
        else:
            executable = sys.executable
            arguments = f'"{os.path.abspath(__file__)}"'
            if len(sys.argv) > 1:
                arguments += " " + " ".join(sys.argv[1:])

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, arguments, None, 1
        )
        sys.exit(0)

    app = AnyDeskManager()
    app.mainloop()