"""Gradio ChatInterface — same agent runner as POST /chat."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import gradio as gr

from recruiter_agent.config import MAX_JD_CHARS, MAX_QUESTION_CHARS, get_settings
from recruiter_agent.errors import (
    MSG_JD_TOO_LONG,
    MSG_QUESTION_REQUIRED,
    MSG_QUESTION_TOO_LONG,
    MSG_UNAVAILABLE,
    friendly_error,
)

AVATAR_PATH = Path(__file__).resolve().parent / "static" / "avatar.jpg"

# Short chips only — do not pass examples= to ChatInterface (it renders a tall table
# when additional_inputs are present).
_SUGGESTIONS = [
    ("Previous experience", "Previous experience"),
    ("Tech stack", "Tech stack"),
    ("How can I schedule a meeting?", "How can I schedule a meeting?"),
]

_SUBMIT_JS = """
() => {
  const click = () => {
    const btn = document.querySelector('button[data-testid="submit-button"]');
    if (btn && !btn.disabled) btn.click();
  };
  requestAnimationFrame(() => requestAnimationFrame(click));
}
"""

# Standalone /ui page. Blog widget is native JS and does not iframe this.
GRADIO_HEAD = """
<script>
(function () {
  var theme = "light";
  try {
    var q = new URLSearchParams(location.search).get("theme");
    if (q === "dark" || q === "light") theme = q;
    else if (window.matchMedia("(prefers-color-scheme: dark)").matches) theme = "dark";
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.background = theme === "dark" ? "#000123" : "#f6eee1";
})();
</script>
"""

GRADIO_JS = """
() => {
  const apply = (theme) => {
    if (theme !== "dark" && theme !== "light") return;
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.background =
      theme === "dark" ? "#000123" : "#f6eee1";
  };
  try {
    apply(new URLSearchParams(window.location.search).get("theme"));
  } catch (e) {}
  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || data.type !== "recruiter-theme") return;
    apply(data.theme);
  });
}
"""

GRADIO_CSS = """
:root,
html[data-theme="light"] {
  --background: #f6eee1;
  --foreground: #012c56;
  --accent: #e14a39;
  --muted: #efd8b0;
  --border: #dc9891;
  --on-accent: #f6eee1;
}
html[data-theme="dark"] {
  --background: #000123;
  --foreground: #eaedf3;
  --accent: #617bff;
  --muted: #0c0e4f;
  --border: #303f8a;
  --on-accent: #eaedf3;
}
html, body {
  min-height: 100%;
  margin: 0;
  background: var(--background) !important;
  color: var(--foreground) !important;
}
footer,
.footer,
.built-with,
.gradio-container footer {
  display: none !important;
}
.gradio-container,
.gradio-container.dark,
.dark .gradio-container {
  --body-background-fill: var(--background);
  --body-background-fill-dark: var(--background);
  --body-text-color: var(--foreground);
  --body-text-color-dark: var(--foreground);
  --body-text-color-subdued: var(--foreground);
  --body-text-color-subdued-dark: var(--foreground);
  --background-fill-primary: var(--background);
  --background-fill-primary-dark: var(--background);
  --background-fill-secondary: var(--muted);
  --background-fill-secondary-dark: var(--muted);
  --block-background-fill: var(--background);
  --block-background-fill-dark: var(--background);
  --block-border-color: var(--border);
  --block-border-color-dark: var(--border);
  --block-label-text-color: var(--foreground);
  --block-label-text-color-dark: var(--foreground);
  --block-title-text-color: var(--foreground);
  --block-title-text-color-dark: var(--foreground);
  --border-color-accent: var(--accent);
  --border-color-accent-dark: var(--accent);
  --border-color-primary: var(--border);
  --border-color-primary-dark: var(--border);
  --color-accent: var(--accent);
  --color-accent-soft: var(--muted);
  --color-accent-soft-dark: var(--muted);
  --button-primary-background-fill: var(--accent);
  --button-primary-background-fill-dark: var(--accent);
  --button-primary-background-fill-hover: var(--accent);
  --button-primary-background-fill-hover-dark: var(--accent);
  --button-primary-text-color: var(--on-accent);
  --button-primary-text-color-dark: var(--on-accent);
  --button-secondary-background-fill: var(--muted);
  --button-secondary-background-fill-dark: var(--muted);
  --button-secondary-background-fill-hover: var(--muted);
  --button-secondary-background-fill-hover-dark: var(--muted);
  --button-secondary-text-color: var(--foreground);
  --button-secondary-text-color-dark: var(--foreground);
  --input-background-fill: var(--muted);
  --input-background-fill-dark: var(--muted);
  --input-border-color: var(--border);
  --input-border-color-dark: var(--border);
  --input-placeholder-color: var(--foreground);
  --input-placeholder-color-dark: var(--foreground);
  --checkbox-background-color: var(--muted);
  --checkbox-border-color: var(--border);
  --link-text-color: var(--accent);
  --link-text-color-dark: var(--accent);
  --table-even-background-fill: var(--background);
  --table-odd-background-fill: var(--muted);
  min-height: 100vh !important;
  max-width: 42rem !important;
  margin: 0 auto !important;
  padding: 1.1rem 1rem 1.5rem !important;
  font-size: 0.9rem !important;
  background: var(--background) !important;
  color: var(--foreground) !important;
}
.gradio-container .contain,
.gradio-container .main,
.gradio-container .wrap,
.gradio-container .block,
.gradio-container .panel,
.gradio-container .form,
.gradio-container .bubble-wrap {
  background: var(--background) !important;
  color: var(--foreground) !important;
  border-color: var(--border) !important;
}
.gradio-container .contain,
.gradio-container .main,
.gradio-container .wrap {
  height: 100%;
  gap: 0.35rem !important;
}
#chat-title {
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1.2;
  color: var(--foreground) !important;
}
#chat-title p,
#chat-title h1,
#chat-title h2 {
  margin: 0 !important;
  font-size: 0.95rem !important;
  font-weight: 600 !important;
  line-height: 1.25 !important;
  color: var(--foreground) !important;
}
#jd-accordion,
#suggestions {
  margin: 0 !important;
  background: var(--background) !important;
  border-color: var(--border) !important;
  color: var(--foreground) !important;
}
#jd-accordion .label-wrap,
#suggestions .label-wrap {
  padding: 0.15rem 0.1rem !important;
  font-size: 0.75rem !important;
  min-height: 0 !important;
  color: var(--foreground) !important;
}
#jd-accordion textarea {
  max-height: 5.5rem !important;
  font-size: 0.8rem !important;
}
#suggestion-chips {
  gap: 0.3rem !important;
  flex-wrap: wrap !important;
}
#suggestion-chips button {
  font-size: 0.72rem !important;
  padding: 0.12rem 0.45rem !important;
  min-height: 0 !important;
  min-width: 0 !important;
  height: auto !important;
  line-height: 1.2 !important;
  background: var(--muted) !important;
  color: var(--foreground) !important;
  border: 1px solid var(--border) !important;
}
.gradio-container .chatbot,
.gradio-container [data-testid="chatbot"] {
  font-size: 0.82rem !important;
  background: var(--background) !important;
  border-color: var(--border) !important;
}
.gradio-container textarea,
.gradio-container input {
  font-size: 0.85rem !important;
  background: var(--muted) !important;
  color: var(--foreground) !important;
  border-color: var(--border) !important;
}
.gradio-container button {
  color: var(--foreground);
}
.gradio-container button.primary,
.gradio-container button[data-testid="submit-button"] {
  background: var(--accent) !important;
  color: var(--on-accent) !important;
  border-color: var(--accent) !important;
}
.avatar-container,
.avatar-container img {
  width: 1.75rem !important;
  height: 1.75rem !important;
  border-radius: 50% !important;
  object-fit: cover !important;
  border-color: var(--border) !important;
}
.bot-row .message,
.bot-row .bubble,
.bot .message,
.message.bot {
  background: var(--muted) !important;
  color: var(--foreground) !important;
  border-color: var(--border) !important;
}
.user-row .message,
.user-row .bubble,
.user .message,
.message.user {
  background: var(--accent) !important;
  color: var(--on-accent) !important;
  border-color: var(--accent) !important;
}
.user-row .message *,
.user .message *,
.message.user * {
  color: var(--on-accent) !important;
}
.bot-row .message *,
.bot .message *,
.message.bot * {
  color: var(--foreground) !important;
}
"""


async def _respond(message: str, _history: list, jd: str = "") -> AsyncIterator[str]:
    from recruiter_agent.agent import is_ready, stream_answer

    if not is_ready():
        yield MSG_UNAVAILABLE
        return
    q = (message or "").strip()
    if not q:
        yield MSG_QUESTION_REQUIRED
        return
    if len(q) > MAX_QUESTION_CHARS:
        yield MSG_QUESTION_TOO_LONG
        return
    jd_text = (jd or "").strip()
    if len(jd_text) > MAX_JD_CHARS:
        yield MSG_JD_TOO_LONG
        return
    try:
        async for chunk in stream_answer(jd_text, q):
            yield chunk
    except Exception as exc:
        yield friendly_error(exc)


def _fill(prompt: str):
    def _inner() -> str:
        return prompt

    return _inner


def build_demo() -> gr.Blocks:
    avatar = str(AVATAR_PATH) if AVATAR_PATH.is_file() else None
    with gr.Blocks(
        title="Ask about fit — Vasu Bansal",
        fill_height=True,
        fill_width=True,
    ) as demo:
        gr.Markdown("**Ask about fit**", elem_id="chat-title")
        with gr.Accordion(
            "Job description (optional)",
            open=False,
            elem_id="jd-accordion",
        ):
            jd = gr.Textbox(
                label="Job description",
                show_label=False,
                lines=3,
                max_lines=4,
                placeholder="Paste the job description (optional)",
            )
        with gr.Accordion("Try an example", open=False, elem_id="suggestions"):
            with gr.Row(elem_id="suggestion-chips"):
                suggestion_btns = [
                    gr.Button(label, size="sm", min_width=0) for label, _ in _SUGGESTIONS
                ]

        # _respond is an async generator. ChatInterface uses the messages
        # format and replaces the assistant bubble as growing text arrives.
        chat = gr.ChatInterface(
            fn=_respond,
            additional_inputs=[jd],
            chatbot=gr.Chatbot(
                show_label=False,
                scale=1,
                min_height=80,
                height="100%",
                layout="bubble",
                avatar_images=(None, avatar),
                buttons=[],
                feedback_options=[],
                render_markdown=True,
                placeholder="Ask why he’s a fit. Answers stay inside listed experience.",
            ),
            textbox=gr.Textbox(
                show_label=False,
                placeholder="Ask about fit…",
                lines=1,
                max_lines=3,
                submit_btn=True,
                autofocus=True,
            ),
            title=None,
            description=None,
            flagging_mode="never",
            fill_height=True,
            fill_width=True,
            autofocus=True,
        )
        for btn, (_label, prompt) in zip(suggestion_btns, _SUGGESTIONS, strict=True):
            btn.click(_fill(prompt), outputs=chat.textbox, queue=False).then(
                fn=None,
                js=_SUBMIT_JS,
            )
    return demo


demo = build_demo()


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=get_settings().port,
        css=GRADIO_CSS,
        js=GRADIO_JS,
        head=GRADIO_HEAD,
    )
