# JARPIZ: Local AI Assistant Workspace 🎙️🤖

An advanced, offline-first AI desktop assistant built with Python. Jarpiz combines modern interface design with powerful local language models to deliver real-time, privacy-focused voice interactions and system automation.

## 🚀 Key Features

* **Strict Tool Guardrails:** Smart context switching that understands when to chat naturally and when to trigger actionable tools.
* **Always-Listening Pipeline:** Seamless, zero-click asynchronous voice recognition with auto-send capabilities.
* **Local Intelligence:** Powered by LangChain and Ollama (Llama 3.2), ensuring your data never leaves your machine unless you explicitly route it to a cloud API.
* **High-Fidelity Synthesis:** Integrates Kokoro TTS for human-like voice synthesis with dynamically selectable personas and accents.
* **Web Scraping & Context Reading:** Built-in ability to dynamically extract, parse, and summarize web content locally via Python core libraries.
* **Modern Interface:** A sleek, glassmorphism-inspired dark mode desktop architecture built on Tkinter.

## 🛠️ Technology Stack

* **Core Language:** Python 3.x
* **AI Framework & Orchestration:** LangChain, Ollama (Local), OpenAI (API fallback)
* **Audio & Speech:** SpeechRecognition, PyAudio, Kokoro TTS Pipeline
* **UI Framework:** Custom Tkinter Implementation

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Reaivaldy/Jarpiz-simple-AI-Asistant.git](https://github.com/Reaivaldy/Jarpiz-simple-AI-Asistant.git)
   cd Jarpiz-simple-AI-Asistant
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On Mac/Linux:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   ```bash
   pip install numpy SpeechRecognition pyaudio langchain-core langchain-ollama langchain-openai kokoro
   ```

4. **Boot your local LLM engine:**
   Ensure you have [Ollama](https://ollama.com/) installed and running on your system.
   ```bash
   ollama run llama3.2
   ```

5. **Launch the Workspace:**
   ```bash
   python app.py
   ```

## 🧠 System Architecture Notes
This assistant uses a dynamic routing system to handle hardware inputs and audio outputs, mapping them in real-time without requiring system reboots. It specifically utilizes `HTMLParser` for safe, script-free text extraction from target URLs, keeping the Llama context window clean and highly focused.

## 👨‍💻 Author
**Reaivaldy Mahaputra Riyanto** *Information Systems & Full-Stack Developer* Focusing on Artificial Intelligence, Agentic Workflows, and System Integration.
