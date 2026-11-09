
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
from pathlib import Path
from storage.memory import get_memories, delete_memory, memory_enabled

PROJECT = Path(__file__).resolve().parent.parent
SETTINGS_DIR = PROJECT / "shared"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
SETTINGS_DIR.mkdir(exist_ok=True)

DEFAULTS = {
    "file_access": "Off",
    "code_analysis": "Ask each time",
    "memory": False,
    "voice_input": False,
    "voice_output": False,
    "proactive_suggestions": False,
    "privacy_lock": False,
    "approved_folder": ""
}


def load_settings():
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            result = DEFAULTS.copy()
            result.update(data)
            return result
    except (OSError, json.JSONDecodeError):
        pass

    return DEFAULTS.copy()


def save_settings(show_message=True):
    data = {
        "file_access": file_access.get(),
        "code_analysis": code_analysis.get(),
        "memory": memory.get(),
        "voice_input": voice_input.get(),
        "voice_output": voice_output.get(),
        "proactive_suggestions": proactive.get(),
        "privacy_lock": privacy_lock.get(),
        "approved_folder": approved_folder.get()
    }

    try:
        SETTINGS_FILE.write_text(
            json.dumps(data, indent=4),
            encoding="utf-8"
        )
        if show_message:
            messagebox.showinfo("Saved", "Settings saved successfully!")
    except OSError as error:
        messagebox.showerror("Save error", str(error))


def choose_folder():
    folder = filedialog.askdirectory(title="Choose approved folder")
    if folder:
        approved_folder.set(folder)
        file_access.set("Approved folder")
        update_folder_label()
        save_settings(False)


def revoke_access():
    approved_folder.set("")
    file_access.set("Off")
    update_folder_label()
    save_settings(False)
    messagebox.showinfo("Access revoked", "Folder approval removed.")


def update_folder_label():
    folder_label.config(
        text=approved_folder.get() or "No folder approved"
    )
def refresh_memory_list():
    memory_list.delete(0, tk.END)

    if not memory_enabled():
        memory_status.config(text="Memory is disabled in settings.")
        return

    memories = get_memories()

    if not memories:
        memory_status.config(text="No saved memories yet.")
        return

    for item in memories:
        if isinstance(item, dict):
            note = item.get("note", "")
            saved_at = item.get("saved_at", "")
            memory_list.insert(
                tk.END,
                f"{note}  |  {saved_at}"
            )

    memory_status.config(
        text=f"{memory_list.size()} saved memories"
    )


def delete_selected_memory():
    selection = memory_list.curselection()

    if not selection:
        messagebox.showwarning(
            "Select a memory",
            "Please select a memory to delete."
        )
        return

    if not memory_enabled():
        messagebox.showwarning(
            "Memory disabled",
            "Enable memory in settings first."
        )
        return

    memories = get_memories()
    index = selection[0]

    if index >= len(memories):
        return

    note = memories[index].get("note", "")

    confirm = messagebox.askyesno(
        "Confirm deletion",
        f"Delete this saved memory?\n\n{note}"
    )

    if confirm:
        try:
            if delete_memory(note):
                refresh_memory_list()
                messagebox.showinfo(
                    "Deleted",
                    "Memory deleted successfully."
                )
            else:
                messagebox.showwarning(
                    "Not found",
                    "That memory was not found."
                )
        except (PermissionError, ValueError, OSError) as error:
            messagebox.showerror("Delete error", str(error))

current = load_settings()

root = tk.Tk()
root.title("Baby Dragon - Control Center")
root.state("zoomed")
root.minsize(480, 500)

# Main content area
main = ttk.Frame(root, padding=15)
main.pack(fill="both", expand=True)

ttk.Label(
    main,
    text="BABY DRAGON CONTROL CENTER",
    font=("Segoe UI", 16, "bold")
).pack(pady=(5, 3))

ttk.Label(
    main,
    text="Manage your Dragon's settings and privacy"
).pack(pady=(0, 12))

# Permissions
permissions = ttk.LabelFrame(
    main, text="Privacy and Permissions", padding=10
)
permissions.pack(fill="x", pady=6)

file_access = tk.StringVar(value=current["file_access"])
code_analysis = tk.StringVar(value=current["code_analysis"])

ttk.Label(permissions, text="File access:").grid(
    row=0, column=0, sticky="w", pady=5
)

ttk.Combobox(
    permissions,
    textvariable=file_access,
    values=["Off", "Selected files", "Approved folder"],
    state="readonly",
    width=22
).grid(row=0, column=1, sticky="e", pady=5)

ttk.Label(permissions, text="Code analysis:").grid(
    row=1, column=0, sticky="w", pady=5
)

ttk.Combobox(
    permissions,
    textvariable=code_analysis,
    values=["Never", "Ask each time", "Always allow"],
    state="readonly",
    width=22
).grid(row=1, column=1, sticky="e", pady=5)

permissions.columnconfigure(0, weight=1)

# Folder manager
folder_frame = ttk.LabelFrame(
    main, text="Approved Folder Manager", padding=10
)
folder_frame.pack(fill="x", pady=6)

approved_folder = tk.StringVar(value=current["approved_folder"])

ttk.Label(
    folder_frame,
    text="Currently approved folder:"
).pack(anchor="w")

folder_label = ttk.Label(
    folder_frame,
    text="",
    wraplength=480
)
folder_label.pack(anchor="w", pady=5)

folder_buttons = ttk.Frame(folder_frame)
folder_buttons.pack(anchor="w")

ttk.Button(
    folder_buttons,
    text="Choose Folder",
    command=choose_folder
).pack(side="left", padx=(0, 8))

ttk.Button(
    folder_buttons,
    text="Revoke Access",
    command=revoke_access
).pack(side="left")

# General settings
general = ttk.LabelFrame(
    main, text="General Settings", padding=10
)
general.pack(fill="x", pady=6)

memory = tk.BooleanVar(value=current["memory"])
voice_input = tk.BooleanVar(value=current["voice_input"])
voice_output = tk.BooleanVar(value=current["voice_output"])
proactive = tk.BooleanVar(value=current["proactive_suggestions"])

ttk.Checkbutton(
    general, text="Remember preferences locally", variable=memory
).pack(anchor="w", pady=3)

ttk.Checkbutton(
    general, text="Enable voice input", variable=voice_input
).pack(anchor="w", pady=3)

ttk.Checkbutton(
    general, text="Enable voice responses", variable=voice_output
).pack(anchor="w", pady=3)

ttk.Checkbutton(
    general, text="Allow proactive suggestions", variable=proactive
).pack(anchor="w", pady=3)


# Memory Manager
memory_frame = ttk.LabelFrame(
    main, text="Local Memory Manager", padding=10
)
memory_frame.pack(fill="both", expand=True, pady=6)

memory_status = ttk.Label(
    memory_frame,
    text="Loading saved memories..."
)
memory_status.pack(anchor="w", pady=4)

memory_list = tk.Listbox(
    memory_frame,
    height=5,
    selectmode=tk.SINGLE,
    font=("Segoe UI", 9)
)
memory_list.pack(fill="both", expand=True, pady=5)

memory_buttons = ttk.Frame(memory_frame)
memory_buttons.pack(anchor="w", pady=4)

ttk.Button(
    memory_buttons,
    text="Refresh",
    command=refresh_memory_list
).pack(side="left", padx=(0, 8))

ttk.Button(
    memory_buttons,
    text="Delete Selected",
    command=delete_selected_memory
).pack(side="left")

# Protection
protection = ttk.LabelFrame(
    main, text="Extra Protection", padding=10
)
protection.pack(fill="x", pady=6)

privacy_lock = tk.BooleanVar(value=current["privacy_lock"])

ttk.Checkbutton(
    protection, text="Privacy Lock", variable=privacy_lock
).pack(anchor="w")

ttk.Label(
    protection,
    text="Internet access: Disabled by design",
    foreground="green"
).pack(anchor="w", pady=3)

update_folder_label()
refresh_memory_list()

# Fixed bottom section: always visible
bottom = ttk.Frame(root, padding=(15, 8))
bottom.pack(side="bottom", fill="x")

ttk.Separator(bottom).pack(fill="x", pady=(0, 8))

ttk.Button(
    bottom,
    text="SAVE ALL SETTINGS",
    command=save_settings
).pack(fill="x", ipady=7)

ttk.Label(
    bottom,
    text="Baby Dragon | Local Control Center"
).pack(pady=(5, 0))

root.mainloop()
