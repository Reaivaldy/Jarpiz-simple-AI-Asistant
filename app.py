import numpy as np
import os
import json
import speech_recognition as sr
import threading
import pyaudio
import tkinter as tk
from tkinter import ttk
import time
from datetime import datetime
import webbrowser
import subprocess
import urllib.request
from html.parser import HTMLParser
from kokoro import KPipeline
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# ==========================================
# 1. CONFIGURATION & CONFIG PROFILE
# ==========================================
CONFIG_FILE = "ai_config.json"

def load_or_create_ai_name():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            return config.get("ai_name", "Jarvis")
    else:
        root = tk.Tk()
        root.withdraw()
        print("\n===========================================")
        print("  INITIALIZATION STATION: CONFIGURING AI   ")
        print("===========================================")
        chosen_name = input("What would you like to name your AI assistant? (e.g. Jarvis) -> ").strip()
        if not chosen_name: chosen_name = "Jarvis"
        with open(CONFIG_FILE, "w") as f:
            json.dump({"ai_name": chosen_name}, f)
        return chosen_name

AI_NAME = load_or_create_ai_name()
WAKE_WORD = AI_NAME.lower()

# Shared Global Application States
is_ai_speaking = False
current_audio_amplitude = 0  
status_text = "Initializing System Hardware..."
active_alarms = []  

# Dynamic Configuration Settings via UI
current_llm_type = "Local (Ollama)"
current_llm_model = "llama3.2"
current_api_key = ""
current_voice = "bm_lewis"
current_language_label = "English"
speech_lang_code = "en-US"

# Active Hardware Audio Device Mapping Indices
current_input_idx = None
current_output_idx = None
restart_mic_flag = threading.Event()

# Memory and Context Management
chat_memory = []

def rebuild_system_instructions():
    """Generates localized instructions based on selected UI settings with STRICT tool guardrails."""
    global chat_memory
    
    lang_directives = {
        "English": "Always speak and respond to the user in fluent English.",
        "Indonesian": "Always speak and respond to the user in fluent Indonesian (Bahasa Indonesia)."
    }
    directive = lang_directives.get(current_language_label, lang_directives["English"])
    
    # THE UPGRADE: Strict boundaries to stop "Tool-Happy" hallucinations!
    sys_content = f"""You are a brilliant, highly capable conversational AI assistant named {AI_NAME}.
1. {directive}
2. STRICT TOOL RULE: NEVER use a tool unless the user explicitly commands it.
3. If the user asks a general question, says hello, or wants to chat (e.g., "how are you", "what is quantum physics", "write me a poem"), answer DIRECTLY from your own knowledge base. DO NOT use tools for this.
4. ONLY use tools if the user explicitly says something like "what time is it", "set an alarm", "open notepad", "open youtube", or "read this link".
5. Keep your responses natural, friendly, and concise. Never output raw JSON code block structures to the user.
"""
    if not chat_memory:
        chat_memory.append(SystemMessage(content=sys_content))
    else:
        chat_memory[0] = SystemMessage(content=sys_content)

# Initialize instructions
rebuild_system_instructions()

# Draggable Configuration Values for Visualizer
viz_x = 220  
viz_y = 150  
viz_width = 180
viz_height = 100
is_dragging = False

# ==========================================
# EXTRACTION UTILITY FOR WEB SCRAPING
# ==========================================
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.ignore = False
        
    def handle_starttag(self, tag, attrs):
        if tag in ['script', 'style', 'header', 'footer', 'nav', 'meta']:
            self.ignore = True
            
    def handle_endtag(self, tag):
        if tag in ['script', 'style', 'header', 'footer', 'nav', 'meta']:
            self.ignore = False
            
    def handle_data(self, data):
        if not self.ignore:
            stripped = data.strip()
            if stripped:
                self.result.append(stripped)
                
    def get_clean_text(self):
        return " ".join(self.result)

# ==========================================
# 2. RUNTIME MODEL DEPENDENCY ENGINES & TOOLS
# ==========================================
print("Booting Kokoro TTS Voice Synthesizer...")
voice_pipeline = KPipeline(lang_code='b') 

@tool
def read_website_content(url: str) -> str:
    """Use this ONLY when the user explicitly asks you to read, summarize, or extract text from a specific URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            html_raw = response.read().decode('utf-8', errors='ignore')
            
        parser = HTMLTextExtractor()
        parser.feed(html_raw)
        clean_text = parser.get_clean_text()
        
        if not clean_text:
            return "The page loaded successfully but contains no parseable text elements."
        return clean_text[:5000]
    except Exception as err:
        return f"Failed connecting to target domain. Core error trace: {str(err)}"

@tool
def open_website(url: str) -> str:
    """Use this ONLY if the user explicitly asks to launch a browser window or open a webpage externally."""
    webbrowser.open(url)
    return f"Successfully opened the website: {url}"

@tool
def open_notepad() -> str:
    """Use this ONLY to open the Windows Notepad text editor when explicitly asked."""
    subprocess.Popen(["notepad.exe"])
    return "Notepad has been launched on the user's screen."

@tool
def get_current_time() -> str:
    """Use this ONLY whenever the user explicitly asks for the current time, clock, or date."""
    now = datetime.now()
    return f"The current time is {now.strftime('%I:%M %p')} and the date is {now.strftime('%A, %B %d, %Y')}."

@tool
def set_assistant_alarm(alarm_time: str) -> str:
    """Use this ONLY to set a new alarm when the user explicitly asks for one. Format: 24-hour HH:MM."""
    global active_alarms
    try:
        time.strptime(alarm_time, "%H:%M")
        active_alarms.append(alarm_time)
        return f"Success! Alarm has been set for {alarm_time}."
    except ValueError:
        return "Failed to parse time format. Please use HH:MM 24-hour format."

tools_list = [read_website_content, open_website, open_notepad, get_current_time, set_assistant_alarm]

def get_active_llm_instance():
    """Dynamically bundles runtime LLM engines based on configurations chosen in the user interface."""
    if current_llm_type == "Local (Ollama)":
        return ChatOllama(model=current_llm_model, temperature=0).bind_tools(tools_list)
    else:
        api_key = current_api_key if current_api_key else "mock_key"
        return ChatOpenAI(model=current_llm_model, openai_api_key=api_key, temperature=0).bind_tools(tools_list)

# ==========================================
# 3. INTERACTIVE GUI WITH SETTINGS CONTROL
# ==========================================
class AISmartAssistantUI:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)
        self.window.geometry("1000x650")
        self.window.configure(bg="#1e1e2e")
        
        self.window.columnconfigure(0, weight=4)
        self.window.columnconfigure(1, weight=5)
        self.window.rowconfigure(0, weight=1)
        
        # --- LEFT PANEL: Hardware & Engine Customizations ---
        self.left_frame = tk.Frame(self.window, bg="#1e1e2e")
        self.left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.left_frame.rowconfigure(0, weight=1)
        self.left_frame.columnconfigure(0, weight=1)
        
        # Visualizer Wave Block
        self.canvas_frame = tk.Frame(self.left_frame, bg="#11111b", bd=2, relief=tk.SUNKEN)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.canvas = tk.Canvas(self.canvas_frame, bg="#11111b", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        # AI Configuration Sub-panel
        self.engine_frame = tk.LabelFrame(self.left_frame, text=" AI Engine Parameters ", 
                                           font=("Arial", 10, "bold"), fg="#cdd6f4", bg="#1e1e2e", bd=1)
        self.engine_frame.grid(row=1, column=0, sticky="ew", ipady=5, pady=(0, 10))
        self.engine_frame.columnconfigure(1, weight=1)
        
        # Core Model Router Toggle
        tk.Label(self.engine_frame, text="LLM Type:", fg="#a6adc8", bg="#1e1e2e").grid(row=0, column=0, padx=10, sticky="w")
        self.cbo_llm_type = ttk.Combobox(self.engine_frame, state="readonly", values=["Local (Ollama)", "API Cloud Provider"])
        self.cbo_llm_type.grid(row=0, column=1, padx=10, pady=3, sticky="ew")
        self.cbo_llm_type.set(current_llm_type)
        self.cbo_llm_type.bind("<<ComboboxSelected>>", self.on_llm_type_changed)
        
        # Text Entry Target Model Descriptor String
        tk.Label(self.engine_frame, text="Model Identifier:", fg="#a6adc8", bg="#1e1e2e").grid(row=1, column=0, padx=10, sticky="w")
        self.txt_model_id = tk.Entry(self.engine_frame, bg="#313244", fg="#cdd6f4", font=("Arial", 10), insertbackground="#cdd6f4", bd=1)
        self.txt_model_id.grid(row=1, column=1, padx=10, pady=3, sticky="ew")
        self.txt_model_id.insert(0, current_llm_model)
        self.txt_model_id.bind("<FocusOut>", self.on_model_id_changed)
        
        # Optional Cloud API token registration pipeline
        tk.Label(self.engine_frame, text="API Secret Key:", fg="#a6adc8", bg="#1e1e2e").grid(row=2, column=0, padx=10, sticky="w")
        self.txt_api_key = tk.Entry(self.engine_frame, bg="#313244", fg="#cdd6f4", font=("Arial", 10), show="*", insertbackground="#cdd6f4", bd=1)
        self.txt_api_key.grid(row=2, column=1, padx=10, pady=3, sticky="ew")
        self.txt_api_key.bind("<FocusOut>", self.on_api_key_changed)
        
        # Voice Actor Profiles Selection Row
        tk.Label(self.engine_frame, text="Voice Persona:", fg="#a6adc8", bg="#1e1e2e").grid(row=3, column=0, padx=10, sticky="w")
        self.cbo_voice = ttk.Combobox(self.engine_frame, state="readonly", values=["bm_lewis", "bm_george", "bf_emma", "af_bella", "af_sarah"])
        self.cbo_voice.grid(row=3, column=1, padx=10, pady=3, sticky="ew")
        self.cbo_voice.set(current_voice)
        self.cbo_voice.bind("<<ComboboxSelected>>", self.on_voice_changed)
        
        # International UI Language Framework Option
        tk.Label(self.engine_frame, text="System Language:", fg="#a6adc8", bg="#1e1e2e").grid(row=4, column=0, padx=10, sticky="w")
        self.cbo_lang = ttk.Combobox(self.engine_frame, state="readonly", values=["English", "Indonesian"])
        self.cbo_lang.grid(row=4, column=1, padx=10, pady=3, sticky="ew")
        self.cbo_lang.set(current_language_label)
        self.cbo_lang.bind("<<ComboboxSelected>>", self.on_lang_changed)
        
        # Audio System Interface Parameters Matrix 
        self.routing_frame = tk.LabelFrame(self.left_frame, text=" Audio Routing Core System ", 
                                           font=("Arial", 10, "bold"), fg="#cdd6f4", bg="#1e1e2e", bd=1)
        self.routing_frame.grid(row=2, column=0, sticky="ew", ipady=5)
        self.routing_frame.columnconfigure(1, weight=1)
        
        tk.Label(self.routing_frame, text="Input (Mic):", fg="#a6adc8", bg="#1e1e2e").grid(row=0, column=0, padx=10, sticky="w")
        self.cbo_input = ttk.Combobox(self.routing_frame, state="readonly")
        self.cbo_input.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        self.cbo_input.bind("<<ComboboxSelected>>", self.on_input_changed)
        
        tk.Label(self.routing_frame, text="Output (Spk):", fg="#a6adc8", bg="#1e1e2e").grid(row=1, column=0, padx=10, sticky="w")
        self.cbo_output = ttk.Combobox(self.routing_frame, state="readonly")
        self.cbo_output.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.cbo_output.bind("<<ComboboxSelected>>", self.on_output_changed)
        
        # --- RIGHT PANEL ---
        self.console_frame = tk.Frame(self.window, bg="#1e1e2e")
        self.console_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        self.console_frame.rowconfigure(1, weight=1) 
        self.console_frame.columnconfigure(0, weight=1)
        
        self.lbl_title = tk.Label(self.console_frame, text=f"{AI_NAME.upper()} INTEGRATED WORKSPACE", 
                                  font=("Courier", 14, "bold"), fg="#cdd6f4", bg="#1e1e2e")
        self.lbl_title.grid(row=0, column=0, pady=(0,10), sticky="w")
        
        self.txt_log = tk.Text(self.console_frame, bg="#11111b", fg="#a6e3a1", 
                              font=("Consolas", 10), wrap=tk.WORD, state=tk.DISABLED, bd=0)
        self.txt_log.grid(row=1, column=0, sticky="nsew", pady=(0,10))
        
        scrollbar = ttk.Scrollbar(self.console_frame, command=self.txt_log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0,10))
        self.txt_log['yscrollcommand'] = scrollbar.set
        
        self.input_frame = tk.Frame(self.console_frame, bg="#1e1e2e")
        self.input_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.input_frame.columnconfigure(0, weight=1)
        
        self.txt_entry = tk.Entry(self.input_frame, bg="#313244", fg="#cdd6f4", font=("Arial", 11), insertbackground="#cdd6f4", bd=1, relief=tk.FLAT)
        self.txt_entry.grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 10))
        self.txt_entry.bind("<Return>", self.send_text_query) 
        
        self.btn_send = tk.Button(self.input_frame, text="Send", bg="#89b4fa", fg="#11111b", font=("Arial", 10, "bold"), relief=tk.FLAT, command=self.send_text_query)
        self.btn_send.grid(row=0, column=1, ipadx=10, ipady=3)
        
        self.lbl_status = tk.Label(self.console_frame, text="System: Online", 
                                    font=("Arial", 10, "italic"), fg="#f5e0dc", bg="#1e1e2e")
        self.lbl_status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0,5))

        self.lbl_transcription = tk.Label(self.console_frame, text="Mic heard: (Waiting for speech...)", 
                                    font=("Consolas", 10, "italic"), fg="#f9e2af", bg="#1e1e2e")
        self.lbl_transcription.grid(row=4, column=0, columnspan=2, sticky="w")
        
        self.populate_audio_devices()
        self.update_gui_loop()

    # Dynamic Settings Event Handling Pipeline
    def on_llm_type_changed(self, event):
        global current_llm_type, current_llm_model
        current_llm_type = self.cbo_llm_type.get()
        if current_llm_type == "Local (Ollama)":
            current_llm_model = "llama3.2"
        else:
            current_llm_model = "gpt-4o-mini"
        self.txt_model_id.delete(0, tk.END)
        self.txt_model_id.insert(0, current_llm_model)
        self.log_message("Engine Swap", f"Switched backend environment to: {current_llm_type} ({current_llm_model})")

    def on_model_id_changed(self, event):
        global current_llm_model
        current_llm_model = self.txt_model_id.get().strip()
        self.log_message("Engine Swap", f"Model identifier target explicitly mapped to: {current_llm_model}")

    def on_api_key_changed(self, event):
        global current_api_key
        current_api_key = self.txt_api_key.get().strip()
        if current_api_key:
            self.log_message("Security Core", "Cloud authorization payload integrated successfully.")

    def on_voice_changed(self, event):
        global current_voice
        current_voice = self.cbo_voice.get()
        self.log_message("Audio Edge", f"Acoustic delivery profile switched to: {current_voice}")

    def on_lang_changed(self, event):
        global current_language_label, speech_lang_code
        current_language_label = self.cbo_lang.get()
        if current_language_label == "Indonesian":
            speech_lang_code = "id-ID"
        else:
            speech_lang_code = "en-US"
        rebuild_system_instructions()
        self.log_message("System Localization", f"UI logic translation set to {current_language_label}. Mic target stream: {speech_lang_code}")
        restart_mic_flag.set()

    def show_transcription(self, heard_text):
        self.lbl_transcription.config(text=f"Mic heard: '{heard_text}'")

    def clear_chatbox(self):
        self.txt_entry.delete(0, tk.END)
        
    def send_text_query(self, event=None):
        user_text = self.txt_entry.get().strip()
        if not user_text: return
        
        self.txt_entry.delete(0, tk.END)
        self.log_message("User (Typed)", user_text)
        threading.Thread(target=self.process_agent_query, args=(user_text,), daemon=True).start()

    def process_agent_query(self, command):
        global status_text, chat_memory
        status_text = "Processing Query..."
        self.log_message("System Edge", f"Invoking active core handler model [{current_llm_model}]...")
        
        try:
            active_llm = get_active_llm_instance()
            chat_memory.append(HumanMessage(content=command))
            agent_response = active_llm.invoke(chat_memory)
            
            # 1. Tool Processing Logic
            if getattr(agent_response, 'tool_calls', None):
                tool_name = agent_response.tool_calls[0]['name']
                tool_args = agent_response.tool_calls[0]['args']
                
                self.log_message("System Edge", f"Executing System Tool: {tool_name}")
                
                if tool_name == "read_website_content":
                    tool_output = read_website_content.invoke(tool_args)
                elif tool_name == "open_website":
                    tool_output = open_website.invoke(tool_args)
                elif tool_name == "open_notepad":
                    tool_output = open_notepad.invoke(tool_args)
                elif tool_name == "get_current_time":
                    tool_output = get_current_time.invoke(tool_args)
                else:
                    tool_output = set_assistant_alarm.invoke(tool_args)
                    
                # CONTEXTUAL SUMMARY LOOP FOR DATA GATHERING
                if tool_name in ["set_assistant_alarm", "open_website", "open_notepad"]:
                    final_text = tool_output
                else:
                    if current_llm_type == "Local (Ollama)":
                        clean_llm = ChatOllama(model=current_llm_model, temperature=0)
                    else:
                        api_key = current_api_key if current_api_key else "mock_key"
                        clean_llm = ChatOpenAI(model=current_llm_model, openai_api_key=api_key, temperature=0)
                        
                    summary_prompt = (
                        f"The user asked: '{command}'. Here is the data extracted from the tool framework:\n"
                        f"{tool_output}\n\nPlease answer the user's specific prompt naturally and concisely based on this data."
                    )
                    summary = clean_llm.invoke(summary_prompt)
                    final_text = summary.content
                
                speak_response(final_text, self)
                chat_memory.append(AIMessage(content=final_text))
                
            # 2. JSON Hallucination Catcher
            elif "{" in agent_response.content and "}" in agent_response.content:
                self.log_message("System Edge", "Caught JSON leak! Forcing natural conversation reset...")
                if current_llm_type == "Local (Ollama)":
                    clean_llm = ChatOllama(model=current_llm_model, temperature=0)
                else:
                    api_key = current_api_key if current_api_key else "mock_key"
                    clean_llm = ChatOpenAI(model=current_llm_model, openai_api_key=api_key, temperature=0)
                clean_response = clean_llm.invoke(f"Answer this naturally and conversationally. Do not use JSON or code. User says: {command}")
                
                speak_response(clean_response.content, self)
                chat_memory.append(AIMessage(content=clean_response.content))
                
            # 3. Standard Text Response
            else:
                final_text = agent_response.content.strip()
                if not final_text:
                    self.log_message("System Edge", "Model content empty. Attempting structural context query extraction...")
                    speak_response("System received empty string from context workspace. Let's try again.", self)
                else:
                    speak_response(final_text, self)
                    chat_memory.append(AIMessage(content=final_text))
            
            if len(chat_memory) > 11:
                chat_memory = [chat_memory[0]] + chat_memory[-10:]
                
        except Exception as ollama_err:
            self.log_message("ENGINE CRASH", f"Check connection endpoints or initialization parameters. Error: {str(ollama_err)}")
            status_text = "Target Engine Offline."
            if len(chat_memory) > 1: chat_memory.pop() 
        
    def populate_audio_devices(self):
        global current_input_idx, current_output_idx
        p = pyaudio.PyAudio()
        
        input_devices = []
        output_devices = []
        self.input_map = {}
        self.output_map = {}
        
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            name = info.get('name')
            
            if info.get('maxInputChannels') > 0 and "mapper" not in name.lower():
                display_name = f"[{i}] {name}"
                input_devices.append(display_name)
                self.input_map[display_name] = i
                    
            if info.get('maxOutputChannels') > 0 and "mapper" not in name.lower():
                display_name = f"[{i}] {name}"
                output_devices.append(display_name)
                self.output_map[display_name] = i
                    
        p.terminate()
        
        self.cbo_input['values'] = input_devices
        self.cbo_output['values'] = output_devices
        
        if input_devices:
            current_input_idx = self.input_map[input_devices[0]]
            self.cbo_input.set(input_devices[0])
            
        if output_devices:
            current_output_idx = self.output_map[output_devices[0]]
            self.cbo_output.set(output_devices[0])

    def on_input_changed(self, event):
        global current_input_idx
        selected = self.cbo_input.get()
        current_input_idx = self.input_map[selected]
        self.log_message("System Edge", f"Microphone track routed to device index: {current_input_idx}")
        restart_mic_flag.set()

    def on_output_changed(self, event):
        global current_output_idx
        selected = self.cbo_output.get()
        current_output_idx = self.output_map[selected]
        self.log_message("System Edge", f"Speaker playback channel routed to device index: {current_output_idx}")

    def log_message(self, tag, message):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f"[{tag}]: {message}\n\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def on_mouse_down(self, event):
        global is_dragging
        if (viz_x - viz_width // 2 <= event.x <= viz_x + viz_width // 2) and \
           (viz_y - viz_height // 2 <= event.y <= viz_y + viz_height // 2):
            is_dragging = True

    def on_mouse_drag(self, event):
        global viz_x, viz_y
        if is_dragging:
            viz_x = max(viz_width // 2, min(event.x, 440 - viz_width // 2))
            viz_y = max(viz_height // 2, min(event.y, 300 - viz_height // 2))

    def on_mouse_up(self, event):
        global is_dragging
        is_dragging = False

    def update_gui_loop(self):
        global is_ai_speaking, current_audio_amplitude, status_text
        self.canvas.delete("all")
        self.lbl_status.config(text=f"Status: {status_text}")
        
        self.canvas.create_rectangle(viz_x - viz_width // 2, viz_y - viz_height // 2,
                                     viz_x + viz_width // 2, viz_y + viz_height // 2,
                                     outline="#313244", width=1)
        
        if is_ai_speaking:
            num_bars = 9
            bar_width = 10
            spacing = 6
            for i in range(num_bars):
                dist = abs(i - (num_bars // 2))
                factor = (num_bars // 2 + 1) - dist
                bar_height = int(current_audio_amplitude * (factor / (num_bars // 2 + 1)))
                bar_height = max(6, bar_height + np.random.randint(-4, 5))
                x_pos = viz_x + (i - num_bars // 2) * (bar_width + spacing)
                self.canvas.create_rectangle(x_pos - bar_width // 2, viz_y - bar_height // 2,
                                             x_pos + bar_width // 2, viz_y + bar_height // 2,
                                             fill="#f9e2af", outline="")
        else:
            self.canvas.create_text(viz_x, viz_y, text="Voice Active", fill="#45475a", font=("Arial", 9))
            
        self.window.after(20, self.update_gui_loop)

# ==========================================
# 4. AUDIO PLAYBACK VIA LIVE STREAMING
# ==========================================
def play_numpy_audio_with_visualization(audio_data, sample_rate=24000):
    global current_audio_amplitude, current_output_idx
    p = pyaudio.PyAudio()
    
    stream_kwargs = {
        'format': pyaudio.paFloat32,
        'channels': 1,
        'rate': sample_rate,
        'output': True
    }
    
    if current_output_idx is not None:
        stream_kwargs['output_device_index'] = current_output_idx
        
    stream = p.open(**stream_kwargs)
    
    if hasattr(audio_data, 'numpy'):
        audio_data = audio_data.numpy()
        
    chunk_size = 1024
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i+chunk_size]
        stream.write(chunk.tobytes())
        
        if len(chunk) > 0:
            peak = np.abs(chunk).max()
            current_audio_amplitude = min(80, int(peak * 130))
            
    stream.stop_stream()
    stream.close()
    p.terminate()
    current_audio_amplitude = 0

def speak_response(text: str, ui_handle):
    global is_ai_speaking, status_text
    is_ai_speaking = True 
    status_text = "Speaking..."
    
    ui_handle.log_message(AI_NAME, text)
    
    stream_text = text.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n')
    generator = voice_pipeline(stream_text, voice=current_voice, speed=1.0, split_pattern=r'\n')
    
    for gs, ps, audio in generator:
        if audio is not None and len(audio) > 0:
            play_numpy_audio_with_visualization(audio, sample_rate=24000)
            
    status_text = "Listening..."
    is_ai_speaking = False

# ==========================================
# 5. DYNAMIC ASYNCHRONOUS BACKEND AUDIO LISTENER & ALARM ENGINE
# ==========================================
def alarm_checker_loop(ui_handle):
    global active_alarms
    while True:
        current_clock = datetime.now().strftime("%H:%M")
        if current_clock in active_alarms:
            active_alarms.remove(current_clock)
            ui_handle.log_message("ALARM SYSTEM", f"Alarm alert triggered: {current_clock}!")
            threading.Thread(target=speak_response, args=(f"Attention please. This is your scheduled alarm alert for {current_clock}!", ui_handle), daemon=True).start()
        time.sleep(1.0)

def background_voice_listener(ui_handle):
    global is_ai_speaking, status_text, current_input_idx, speech_lang_code
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.energy_threshold = 300
    recognizer.pause_threshold = 0.6  

    while True:
        status_text = "Connecting Audio Stream..."
        try:
            if current_input_idx is not None:
                mic = sr.Microphone(device_index=current_input_idx)
            else:
                mic = sr.Microphone()
        except Exception as e:
            ui_handle.log_message("System Error", f"Failed binding device target path: {e}")
            status_text = "Hardware Selection Error"
            time.sleep(2.0)
            continue

        with mic as source:
            status_text = "Calibrating Device Channel..."
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            status_text = "Listening..." 
            
            restart_mic_flag.clear()
            
            while not restart_mic_flag.is_set():
                if is_ai_speaking:
                    time.sleep(0.4)
                    continue
                    
                try:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
                    text = recognizer.recognize_google(audio, language=speech_lang_code).lower()
                    
                    ui_handle.show_transcription(text)
                    command = text.replace(WAKE_WORD, "").strip()
                    
                    if not command:
                        continue
                        
                    ui_handle.log_message("User (Spoken)", text)
                    ui_handle.clear_chatbox()
                    ui_handle.process_agent_query(command)
                            
                except (sr.UnknownValueError, sr.WaitTimeoutError):
                    pass 
                except sr.RequestError as e:
                    ui_handle.log_message("Error", f"Recognition service connection drop: {e}")
        
        print("[System Reset]: Input state modifier caught. Re-aligning thread mapping context layers...")

# ==========================================
# 6. APP EXECUTION INITIALIZER
# ==========================================
if __name__ == "__main__":
    main_window = tk.Tk()
    app_ui = AISmartAssistantUI(main_window, f"{AI_NAME} OS Custom Workspace")
    
    voice_thread = threading.Thread(target=background_voice_listener, args=(app_ui,), daemon=True)
    voice_thread.start()
    
    alarm_thread = threading.Thread(target=alarm_checker_loop, args=(app_ui,), daemon=True)
    alarm_thread.start()
    
    main_window.mainloop()