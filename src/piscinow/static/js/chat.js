document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const body = document.getElementById("chat-body");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage("user", message);
    input.value = "";

    const typing = showTyping();

    let text;
    try {
      const response = await fetch("/api/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ message }),
      });
      text = await response.text();
      if (!response.ok) {
        text = "Desculpe, tivemos um problema para responder agora. Tente novamente em instantes.";
      }
    } catch (err) {
      text = "Nao foi possivel falar com o concierge agora. Verifique sua conexao e tente de novo.";
    }

    typing.remove();
    appendMessage("agent", text);
  });

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    el.textContent = text;
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
    return el;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "typing";
    el.innerHTML = "<span></span><span></span><span></span>";
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
    return el;
  }
});
