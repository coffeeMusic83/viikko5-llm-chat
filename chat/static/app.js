// Sends chat messages to the API (api/chat under /viikko5/) and shows the replies.
(function () {
  "use strict";
  const form = document.getElementById("send-form");
  const input = document.getElementById("message");
  const button = document.getElementById("send-button");
  const chat = document.getElementById("chat");
  const apiUrl = form.dataset.api;

  function addMessage(role, text, extraClass) {
    const empty = document.getElementById("empty");
    if (empty) empty.remove();
    const div = document.createElement("div");
    div.className = "msg " + role + (extraClass ? " " + extraClass : "");
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "you@browser:~$" : role === "assistant" ? "model@localhost:~$" : "error";
    const body = document.createElement("span");
    body.textContent = text;
    div.append(who, body);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  async function send(text) {
    addMessage("user", text);
    const thinking = addMessage("assistant", "thinking...", "thinking");
    button.disabled = true;
    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ message: text }),
      });
      const data = await response.json().catch(() => ({}));
      thinking.remove();
      if (response.ok) {
        addMessage("assistant", data.reply);
      } else {
        addMessage("error", data.error || "Error " + response.status);
      }
    } catch (err) {
      thinking.remove();
      addMessage("error", "Network error: " + err.message);
    } finally {
      button.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || button.disabled) return;
    input.value = "";
    send(text);
  });

  // Enter sends, Shift+Enter makes a new line.
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  chat.scrollTop = chat.scrollHeight;
})();
