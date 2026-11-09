
from pathlib import Path
import json
from datetime import datetime


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT_ROOT / "shared" / "settings.json"
MEMORY_FILE = PROJECT_ROOT / "storage" / "memory.json"


def load_settings():
    """Load application settings."""
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def memory_enabled():
    """Check whether local memory is enabled."""
    return load_settings().get("memory", False) is True


def load_memory():
    """Load saved memories."""
    if not memory_enabled():
        return []

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_memory(data):
    """Save memories locally."""
    if not memory_enabled():
        raise PermissionError("Local memory is disabled.")

    if not isinstance(data, list):
        raise ValueError("Memory data must be a list.")

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = MEMORY_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )
    temporary_file.replace(MEMORY_FILE)


def add_memory(note):
    """Save one note when explicitly requested."""
    if not memory_enabled():
        raise PermissionError("Local memory is disabled.")

    if not isinstance(note, str) or not note.strip():
        raise ValueError("Memory note cannot be empty.")

    memories = load_memory()

    entry = {
        "note": note.strip(),
        "saved_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
    }

    memories.append(entry)
    save_memory(memories)

    return entry


def get_memories():
    """Retrieve all saved notes."""
    return load_memory()

def delete_memory(note):
    """Delete one exact saved note."""
    if not memory_enabled():
        raise PermissionError("Local memory is disabled.")

    if not isinstance(note, str) or not note.strip():
        raise ValueError("Memory note cannot be empty.")

    memories = load_memory()
    target = note.strip()

    updated_memories = [
        item for item in memories
        if not (
            isinstance(item, dict)
            and item.get("note") == target
        )
    ]

    if len(updated_memories) == len(memories):
        return False

    save_memory(updated_memories)
    return True

def clear_memory():
    """Delete all saved notes."""
    if not memory_enabled():
        raise PermissionError("Local memory is disabled.")

    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

    return True
