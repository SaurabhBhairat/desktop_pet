
import json
import urllib.request
import urllib.error

from storage.memory import (
    add_memory,
    delete_memory,
    get_memories,
    memory_enabled
)


class OllamaClient:

    def __init__(self, model="qwen2.5:1.5b"):
        self.model = model
        self.url = "http://127.0.0.1:11434/api/chat"

    def generate_reply(self, message):

        if not isinstance(message, str) or not message.strip():
            return "Please enter a message."

        user_message = message.strip()
        lower_message = user_message.lower()

        # SAVE MEMORY: only after an explicit command.
        save_prefixes = (
            "remember that ",
            "remember this: ",
            "save this memory: "
        )

        for prefix in save_prefixes:
            if lower_message.startswith(prefix):

                if not memory_enabled():
                    return "Local memory is disabled. Please enable it in Settings."

                note = user_message[len(prefix):].strip()

                if not note:
                    return "Please tell me what you want me to remember."

                try:
                    saved = add_memory(note)
                    return f"I've saved this note: {saved['note']}"

                except (PermissionError, ValueError, OSError):
                    return "Sorry, I couldn't save that memory."

        # DELETE MEMORY: requires an exact note match.
        forget_prefixes = (
            "forget that ",
            "forget this: ",
            "delete memory: "
        )

        for prefix in forget_prefixes:
            if lower_message.startswith(prefix):

                if not memory_enabled():
                    return "Local memory is disabled."

                note = user_message[len(prefix):].strip()

                if not note:
                    return "Please specify which memory to forget."

                try:
                    deleted = delete_memory(note)

                    if deleted:
                        return f"I've forgotten this note: {note}"

                    return "I couldn't find that exact saved note."

                except (PermissionError, ValueError, OSError):
                    return "Sorry, I couldn't delete that memory."

        # NORMAL AI CONVERSATION.
        system_prompt = (
            "You are Baby Dragon, a helpful desktop assistant. "
            "Be friendly, clear, and concise. "
            "Never invent personal memories. "
            "Use only the supplied saved notes as evidence. "
            "If the notes do not contain the requested information, "
            "say honestly that you do not have it saved."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        # Load local notes only when memory is enabled.
        if memory_enabled():

            memories = get_memories()

            valid_notes = [
                item["note"].strip()
                for item in memories
                if isinstance(item, dict)
                and isinstance(item.get("note"), str)
                and item["note"].strip()
            ]

            if valid_notes:
                messages.append({
                    "role": "system",
                    "content": (
                        "SAVED NOTES (the only source of personal memories):\n"
                        + "\n".join(
                            f"- {note}" for note in valid_notes
                        )
                        + "\nDo not invent additional personal details."
                    )
                })

        messages.append({
            "role": "user",
            "content": user_message
        })

        data = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": 0
        }

        request_data = json.dumps(data).encode("utf-8")

        request = urllib.request.Request(
            self.url,
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))

            return result["message"]["content"].strip()

        except urllib.error.URLError:
            return "Local AI is unavailable. Please start Ollama."

        except (KeyError, ValueError, TimeoutError):
            return "Sorry, I could not generate a reply."


if __name__ == "__main__":

    dragon = OllamaClient()

    print("Baby Dragon local AI + memory test")
    message = input("You: ")

    reply = dragon.generate_reply(message)

    print("Dragon:", reply)
