"""Plain-language facts used by the public user guide and app-help answers."""

import re

GUIDE_PASSAGES = [
    "DocuMind helps you find information in your files and ask questions about it. It can also search trusted public documents. Answers show a file name, page, or source when available. AI can make mistakes, so check important details against the original file or official source.",
    "A file is a PDF, Word document, text file, or photo that you add. A folder is a place to keep related files; personal folders are private to you. A team is a shared space for coworkers or classmates. A team owner or manager can invite people and choose what they can do. Public documents are trusted reference material in DocuMind, separate from files you upload. A chat is a saved question and answer tied to a file or folder.",
    "To start, sign in, open or create a folder, add a PDF, Word file, text file, or photo, and wait for it to say Ready. Clear scans and photos are easier to read. Ask a question in everyday words, request a summary, or ask about a detail. Check the file name, page, and quoted source with the answer. Open the original when a detail matters.",
    "This file searches one selected file. This folder searches all ready files in the selected folder. Folder + public docs searches the folder and public reference documents together. The user does not need the exact words from a file; they can describe its topic, what it might contain, a person or business name, or a remembered detail.",
    "Find files or chats searches by meaning and matching words across folders, public documents, and saved chats. A user can describe what they remember without knowing the exact file name or wording. Results show the full path, such as Team name / Folder name / File name, or Public documents / Group / Title. Select a file result to open that file. Select a chat to reopen that saved conversation. Public document results link to the original source or let the user ask about that document group. Search results only include items the user is allowed to see.",
    "Recent chats appear under the folder or file they belong to. Find files or chats can search older conversations by describing what was discussed. A user can rename, pin, archive, or download a chat. Selecting a chat reopens it; it does not automatically download a copy.",
    "Important dates shows dates found in files and reminders to review. Business tools can explain a tax letter, check a tender, read a receipt, and compare a payroll file with rates entered by an administrator. Plan and billing shows plans and payment status. Account settings has language, WhatsApp, privacy, account download, and sign-out options. Review results before acting, especially for tax, legal, pay, or payment matters.",
    "Only upload files you are allowed to use. When a user asks a question, relevant file text may be sent to the AI service to prepare an answer. Do not add sensitive information unless the team allows this. Sign out on a shared device.",
    "If a file is still being prepared, wait and refresh the file list. If a scan cannot be read, try a clearer photo or text copy. If a file or chat does not appear, check access to its folder and whether the file says Ready. If an answer is unclear, ask a shorter question or choose This file or This folder. If an error continues, contact the team owner or support.",
]
GUIDE_CONTEXT = "\n\n".join(f"[{index}] {passage}" for index, passage in enumerate(GUIDE_PASSAGES, 1))


def is_guide_question(question: str) -> bool:
    """Recognize questions about using the app, not questions about user files."""
    value = (question or "").strip().lower()
    patterns = (
        r"\bhow (?:do|can) i use (?:documind|this app|the app)\b",
        r"\bwhat (?:can|does) (?:documind|this app|the app)\b",
        r"\b(?:explain|summari[sz]e) (?:the )?(?:documind )?(?:user guide|manual|app|system)\b",
        r"\b(?:i am|i'm) new (?:here|to documind|to this app)\b",
        r"\bwhat (?:is|does) (?:an? )?(?:organization|team|library|public documents?|folder|chat history)\b",
        r"\bdifference between\b.{0,60}\b(?:organization|team|library|folder|public documents?)\b",
        r"\bhow (?:do|can) i (?:create|make|find|search|upload|invite|share|open|use)\b.{0,80}\b(?:team|organization|library|folder|file|chat|document|app|system)\b",
        r"\bhow does (?:a )?(?:team|organization|library|folder|chat history|this app) work\b",
        r"\bwhere (?:do|can) i (?:find|open|manage)\b.{0,60}\b(?:team|organization|library|folder|chat|account|settings)\b",
    )
    return any(re.search(pattern, value) for pattern in patterns)
