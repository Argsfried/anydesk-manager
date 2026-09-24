# AnyDesk Manager

A lightweight, high-DPI-aware Windows utility built with **CustomTkinter** and **Python** designed to manage AnyDesk remote desktop connections, bypass UAC elevation prompts using scheduled tasks, and automate connection tracking.

<img width="742" height="792" alt="image" src="https://github.com/user-attachments/assets/e71964b4-2841-4ec2-8cee-e8d7519327c3" />

---

## Features

* **Elevated Service Control:** Effortlessly start, stop, or restart the underlying AnyDesk service (`net start anydesk`) directly from the manager.
* **UAC Bypass Autostart:** Integrated Windows Task Scheduler (`schtasks`) support allows the application to auto-start silently on user logon with highest privileges (`/RL HIGHEST`) without prompting UAC popups.
* **Clean & Modern UI:** Native high-DPI scaling powered by CustomTkinter with multi-resolution `.ico` assets.
* **Thread-Safe Architecture:** Handles background process monitoring asynchronously using `self.after()` and Python threading to eliminate UI freezes and crashes.
* **JSON State Persistence:** Automatically syncs saved connection lists and application preferences to a local JSON configuration store.

---

## Prerequisites

* **Operating System:** Windows 10 or Windows 11 (64-bit)
* **Privileges:** Administrator rights (required for service management & task scheduling)
* **Python Environment:** Python 3.10 or higher

---

## Installation & Setup

1. **Clone the Repository:**
   ```cmd
   git clone [https://github.com/argsfried/anydesk-manager.git](https://github.com/argsfried/anydesk-manager.git)
   cd anydesk-manager

---

## Package the Application

To ensure the application has proper permissions to run system commands without breaking background process hooks, build the single executable with the `--uac-admin` flag.

1. Open **Command Prompt** as Administrator.
2. Navigate to your project directory:
    ```cmd
    cd C:\Users\YourUser\Documents\Python

3. If you have an image you want to convert, you can use this website: [https://www.freeconvert.com/jpg-to-ico/download](https://www.freeconvert.com/jpg-to-ico/download).
4. Run PyInstaller to generate the standalone binary:
    ```cmd
    py -m PyInstaller --noconsole --onefile --uac-admin anydesk_manager.py

    //use the command below if you have an .ico file for custom icon

    py -m PyInstaller --noconsole --onefile --uac-admin --icon="app_icon.ico" --add-data "app_icon.ico;." anydesk_manager.py

5. Confirm the generated `.exe` is located at `dist\anydesk_manager.exe`.
6. To check if the auto-start is working, run this command in cmd:
    ```cmd
    schtasks /Query /TN "AnyDeskManagerApp_Autostart"

## Dependencies

This project relies on the following Python packages and standard library modules:

### Third-Party Dependencies
* **CustomTkinter** (`customtkinter`): Provides the modern, high-DPI aware graphical user interface components.
* **PyInstaller** (`pyinstaller`): Used to compile and package the Python script into a standalone Windows binary (`.exe`).

### Built-in Standard Libraries
* **subprocess**: Handles execution of elevated Windows CLI commands (`net start`, `schtasks`).
* **threading**: Executes asynchronous background tasks and keeps the UI responsive.
* **json**: Manages local data persistence for saved settings and connections.
* **winreg**: Interacts with the Windows Registry for startup configurations.

## License

[MIT License](LICENSE)
