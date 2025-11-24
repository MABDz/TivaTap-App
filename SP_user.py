import threading
import queue
import random
import serial
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox
import json
import os


# ====== SERIAL CONFIG ======
SERIAL_PORT = "COM7"
BAUD_RATE = 9600
# ===========================

# ====== LEADERBOARD FILE ======
LEADERBOARD_FILE = "leaderboard.json"
# ==============================


class ReactionGameApp:
    def __init__(self, master):
        self.master = master
        master.title("TivaTap - Reaction Time Challenge")
        master.configure(bg='#F5EDE0')
        master.state('zoomed')  # Start fullscreen on Windows

        # ---- Game state ----
        self.player_name = ""
        self.selected_rounds = 5  # default
        self.current_round = 0
        self.round_times = []
        self.waiting_for_result = False

        # Leaderboard: rounds -> list of (name, avg_ms)
        self.leaderboard = {1: [], 5: [], 10: []}

        # Queue for messages from serial thread
        self.rx_queue = queue.Queue()

        # ---- UI: main frames ----
        self.start_frame = tk.Frame(master)
        self.game_frame = tk.Frame(master)

        self.create_start_screen()
        self.create_game_screen()
        self.create_leaderboard_frame()
        
        # Load leaderboard after UI is created
        self.load_leaderboard()

        self.show_start_screen()

        # ---- Serial setup ----
        self.ser = None
        self.connect_serial()

        # Background thread for reading serial data
        self.stop_event = threading.Event()
        if self.ser is not None:
            self.thread = threading.Thread(target=self.serial_reader, daemon=True)
            self.thread.start()

        # Periodic check of RX queue
        self.master.after(50, self.process_rx_queue)

        # Clean up on close
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==============================
    # Leaderboard Persistence
    # ==============================

    def load_leaderboard(self):
        """Load leaderboard data from file."""
        try:
            if os.path.exists(LEADERBOARD_FILE):
                with open(LEADERBOARD_FILE, 'r') as f:
                    data = json.load(f)
                    # Convert string keys back to integers and tuples
                    for rounds in [1, 5, 10]:
                        if str(rounds) in data:
                            self.leaderboard[rounds] = [tuple(entry) for entry in data[str(rounds)]]
                self.update_leaderboard_ui()
        except (json.JSONDecodeError, IOError) as e:
            # If file is corrupted or can't be read, start fresh
            print(f"Could not load leaderboard: {e}")
            self.leaderboard = {1: [], 5: [], 10: []}

    def save_leaderboard(self):
        """Save leaderboard data to file."""
        try:
            # Convert integer keys to strings for JSON
            data = {str(rounds): entries for rounds, entries in self.leaderboard.items()}
            with open(LEADERBOARD_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Could not save leaderboard: {e}")

    # ==============================
    # Serial Connection
    # ==============================

    def connect_serial(self):
        """Attempt to connect to serial port, prompt user if failed."""
        try:
            self.ser = serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                timeout=0.1,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            # Successfully connected
            self.start_info_label.config(
                text=f"✓ Connected to {SERIAL_PORT}",
                fg="#2CA7A7"
            )
            return True
        except serial.SerialException as e:
            self.ser = None
            # Show connection error
            self.start_info_label.config(
                text=f"⚠ Controller not connected to {SERIAL_PORT}",
                fg="#F87060"
            )
            
            response = messagebox.askretrycancel(
                "Connection Error",
                f"Failed to connect to {SERIAL_PORT}\n\n"
                f"Error: {e}\n\n"
                f"Please:\n"
                f"1. Connect your TivaTap controller\n"
                f"2. Verify it's connected to {SERIAL_PORT}\n"
                f"3. Check that no other program is using the port\n\n"
                f"Click 'Retry' to try again or 'Cancel' to exit."
            )
            
            if response:
                # User clicked Retry
                return self.connect_serial()
            else:
                # User clicked Cancel - exit application
                self.master.destroy()
                return False

    # ==============================
    # UI construction
    # ==============================

    def create_start_screen(self):
        """Start screen: name, rounds selection, start button."""
        self.start_frame.configure(bg='#F5EDE0')
        
        # Configure grid to center content
        self.start_frame.grid_rowconfigure(0, weight=2)
        self.start_frame.grid_rowconfigure(7, weight=2)
        self.start_frame.grid_columnconfigure(0, weight=1)
        self.start_frame.grid_columnconfigure(1, weight=1)

        # Title
        title_label = tk.Label(
            self.start_frame,
            text="TivaTap",
            font=("Arial", 32, "bold"),
            bg='#F5EDE0',
            fg='#4D413D'
        )
        title_label.grid(row=1, column=0, columnspan=2, pady=(10, 5))

        subtitle_label = tk.Label(
            self.start_frame,
            text="Reaction Time Challenge",
            font=("Arial", 14),
            bg='#F5EDE0',
            fg='#D93750'
        )
        subtitle_label.grid(row=2, column=0, columnspan=2, pady=(0, 20))

        # Player name
        name_label = tk.Label(
            self.start_frame,
            text="Player Name:",
            font=("Arial", 12),
            bg='#F5EDE0',
            fg='#4D413D'
        )
        name_label.grid(row=3, column=0, padx=5, pady=8)

        self.name_entry = tk.Entry(
            self.start_frame,
            width=20,
            font=("Arial", 12),
            bg='#FFFFFF',
            fg='#4D413D',
            insertbackground='#D93750',
            relief=tk.FLAT,
            bd=2
        )
        self.name_entry.grid(row=3, column=1, padx=5, pady=8)

        # Round selection
        rounds_label = tk.Label(
            self.start_frame,
            text="Number of Rounds:",
            font=("Arial", 12),
            bg='#F5EDE0',
            fg='#4D413D'
        )
        rounds_label.grid(row=4, column=0, padx=5, pady=8)

        self.rounds_var = tk.IntVar(value=5)

        rounds_frame = tk.Frame(self.start_frame, bg='#F5EDE0')
        rounds_frame.grid(row=4, column=1, padx=5, pady=8)

        rb1 = tk.Radiobutton(
            rounds_frame, text="1", variable=self.rounds_var, value=1,
            font=("Arial", 11), bg='#F5EDE0', fg='#4D413D',
            selectcolor='#E4A853', activebackground='#F5EDE0', activeforeground='#D93750'
        )
        rb5 = tk.Radiobutton(
            rounds_frame, text="5", variable=self.rounds_var, value=5,
            font=("Arial", 11), bg='#F5EDE0', fg='#4D413D',
            selectcolor='#E4A853', activebackground='#F5EDE0', activeforeground='#D93750'
        )
        rb10 = tk.Radiobutton(
            rounds_frame, text="10", variable=self.rounds_var, value=10,
            font=("Arial", 11), bg='#F5EDE0', fg='#4D413D',
            selectcolor='#E4A853', activebackground='#F5EDE0', activeforeground='#D93750'
        )

        rb1.pack(side=tk.LEFT, padx=5)
        rb5.pack(side=tk.LEFT, padx=5)
        rb10.pack(side=tk.LEFT, padx=5)

        # Start game button
        start_button = tk.Button(
            self.start_frame,
            text="START GAME",
            width=20,
            font=("Arial", 14, "bold"),
            command=self.on_start_game_clicked,
            bg='#D93750',
            fg='#FFFFFF',
            activebackground='#F87060',
            activeforeground='#FFFFFF',
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        start_button.grid(row=5, column=0, columnspan=2, padx=5, pady=20)

        # Info label
        self.start_info_label = tk.Label(
            self.start_frame,
            text="",
            font=("Arial", 10),
            fg="#F87060",
            bg='#F5EDE0'
        )
        self.start_info_label.grid(row=6, column=0, columnspan=2)

    def create_game_screen(self):
        """Game screen: start round button, status, etc."""
        self.game_frame.configure(bg='#F5EDE0')

        # Title area
        title_frame = tk.Frame(self.game_frame, bg='#F5EDE0')
        title_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=(20, 10))

        game_title = tk.Label(
            title_frame,
            text="TivaTap",
            font=("Arial", 24, "bold"),
            bg='#F5EDE0',
            fg='#4D413D'
        )
        game_title.pack()

        # Info frame
        info_frame = tk.Frame(self.game_frame, bg='#F4E4C1', relief=tk.FLAT)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=10)

        # Player / rounds info
        self.player_label = tk.Label(
            info_frame,
            text="Player: -",
            font=("Arial", 12, "bold"),
            bg='#F4E4C1',
            fg='#4D413D'
        )
        self.player_label.pack(pady=5)

        self.progress_label = tk.Label(
            info_frame,
            text="Round 0 / 0",
            font=("Arial", 16, "bold"),
            bg='#F4E4C1',
            fg='#4D413D'
        )
        self.progress_label.pack(pady=5)

        # Result display
        result_frame = tk.Frame(self.game_frame, bg='#F5EDE0')
        result_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.last_result_label = tk.Label(
            result_frame,
            text="Ready to Start",
            font=("Arial", 20, "bold"),
            bg='#F5EDE0',
            fg='#2CA7A7'
        )
        self.last_result_label.pack(expand=True)

        # Status
        self.status_label = tk.Label(
            result_frame,
            text="Press START ROUND to begin",
            font=("Arial", 12),
            bg='#F5EDE0',
            fg='#4D413D'
        )
        self.status_label.pack()

        # Button frame
        button_frame = tk.Frame(self.game_frame, bg='#F5EDE0')
        button_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=10)

        # Start round button
        self.start_round_button = tk.Button(
            button_frame,
            text="START ROUND",
            width=20,
            font=("Arial", 14, "bold"),
            command=self.on_start_round_clicked,
            bg='#2CA7A7',
            fg='#FFFFFF',
            activebackground='#3CBEBE',
            activeforeground='#FFFFFF',
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        self.start_round_button.pack(pady=5)

    def show_final_results(self):
        """Display final average results after last round."""
        avg = sum(self.round_times) / len(self.round_times)
        self.status_label.config(
            text=f"🎉 Congratulations {self.player_name}! 🎉\nYou completed {self.selected_rounds} rounds!",
            fg='#D93750'
        )
        self.last_result_label.config(text=f"Average: {avg:.1f} ms", fg='#E4A853')
        self.start_round_button.config(
            text="RETURN TO MAIN MENU",
            state=tk.NORMAL,
            command=self.on_back_to_start_clicked
        )

        # Update leaderboard
        self.leaderboard[self.selected_rounds].append((self.player_name, avg))
        self.update_leaderboard_ui()
        self.save_leaderboard()

    def send_round_command(self):
        """Send the round command to microcontroller after delay."""
        # Pick random color and number
        color = random.choice("RGBCMYW")
        number = random.randint(2, 6)

        cmd = f"S{color}{number}\n"

        try:
            self.ser.write(cmd.encode("ascii"))
        except serial.SerialException as e:
            self.status_label.config(text="Connection error - please restart")
            self.start_round_button.config(state=tk.NORMAL)
            return

        self.waiting_for_result = True

        self.status_label.config(text="Get ready... TAP when you see the light!", fg='#4D413D')
        self.last_result_label.config(text="...", fg='#E4A853')

    def create_leaderboard_frame(self):
        """Leaderboard at bottom: separate for 1 / 5 / 10 rounds."""
        self.leaderboard_frame = tk.Frame(
            self.master,
            bg='#FCDAD0',
            relief=tk.FLAT,
            bd=2
        )
        self.leaderboard_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Title label centered at top
        title_label = tk.Label(
            self.leaderboard_frame,
            text="🏆 LEADERBOARD 🏆",
            font=("Arial", 18, "bold"),
            bg='#FCDAD0',
            fg='#D93750'
        )
        title_label.pack(pady=(10, 5))

        # Create a container frame to center the content
        content_frame = tk.Frame(self.leaderboard_frame, bg='#FCDAD0')
        content_frame.pack(expand=True)

        # Column titles
        tk.Label(
            content_frame,
            text="1 Round",
            font=("Arial", 10, "bold"),
            bg='#FCDAD0',
            fg='#4D413D'
        ).grid(row=0, column=0, padx=5, pady=5)
        tk.Label(
            content_frame,
            text="5 Rounds",
            font=("Arial", 10, "bold"),
            bg='#FCDAD0',
            fg='#4D413D'
        ).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(
            content_frame,
            text="10 Rounds",
            font=("Arial", 10, "bold"),
            bg='#FCDAD0',
            fg='#4D413D'
        ).grid(row=0, column=2, padx=5, pady=5)

        # Listboxes for each board
        self.lb_1 = tk.Listbox(
            content_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#FFFFFF',
            fg='#4D413D',
            selectbackground='#E4A853',
            selectforeground='#4D413D',
            relief=tk.FLAT,
            bd=0
        )
        self.lb_5 = tk.Listbox(
            content_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#FFFFFF',
            fg='#4D413D',
            selectbackground='#E4A853',
            selectforeground='#4D413D',
            relief=tk.FLAT,
            bd=0
        )
        self.lb_10 = tk.Listbox(
            content_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#FFFFFF',
            fg='#4D413D',
            selectbackground='#E4A853',
            selectforeground='#4D413D',
            relief=tk.FLAT,
            bd=0
        )

        self.lb_1.grid(row=1, column=0, padx=5, pady=5)
        self.lb_5.grid(row=1, column=1, padx=5, pady=5)
        self.lb_10.grid(row=1, column=2, padx=5, pady=5)

    # ==============================
    # Screen switching
    # ==============================

    def show_start_screen(self):
        self.game_frame.pack_forget()
        self.start_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

    def show_game_screen(self):
        self.start_frame.pack_forget()
        self.game_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

    # ==============================
    # Start screen callbacks
    # ==============================

    def on_start_game_clicked(self):
        name = self.name_entry.get().strip()
        rounds = self.rounds_var.get()

        if not name:
            self.start_info_label.config(text="Please enter a name.", fg="#F87060")
            return

        if rounds not in (1, 5, 10):
            self.start_info_label.config(text="Please select number of rounds.", fg="#F87060")
            return

        if self.ser is None or not self.ser.is_open:
            self.start_info_label.config(text=f"⚠ Controller not connected to {SERIAL_PORT}", fg="#F87060")
            
            response = messagebox.askretrycancel(
                "Connection Error",
                f"Controller is not connected to {SERIAL_PORT}\n\n"
                f"Please connect your TivaTap controller and try again.\n\n"
                f"Click 'Retry' to reconnect or 'Cancel' to go back."
            )
            
            if response:
                # Try to reconnect
                if self.connect_serial():
                    # Successfully connected, try starting game again
                    self.on_start_game_clicked()
            return

        self.start_info_label.config(text="")

        # Set up new game state
        self.player_name = name
        self.selected_rounds = rounds
        self.current_round = 0
        self.round_times = []
        self.waiting_for_result = False

        # Update game screen labels
        self.player_label.config(text=f"Player: {self.player_name}")
        self.progress_label.config(text=f"Round {self.current_round} / {self.selected_rounds}")
        self.status_label.config(text="Press START ROUND to begin", fg='#4D413D')
        self.last_result_label.config(text="Ready to Start", fg='#2CA7A7')
        self.start_round_button.config(
            text="START ROUND",
            state=tk.NORMAL,
            command=self.on_start_round_clicked
        )

        self.show_game_screen()

    def on_back_to_start_clicked(self):
        if self.waiting_for_result:
            if not messagebox.askyesno(
                "Confirm",
                "A round is currently in progress.\nReturn to main menu anyway?"
            ):
                return
        self.waiting_for_result = False
        self.show_start_screen()

    # ==============================
    # Game screen: start round
    # ==============================

    def on_start_round_clicked(self):
        if self.ser is None or not self.ser.is_open:
            self.status_label.config(text="Connection error - please restart game")
            return

        if self.waiting_for_result:
            self.status_label.config(text="Please wait for current round to finish...")
            return

        if self.current_round >= self.selected_rounds:
            self.status_label.config(text="All rounds complete!")
            self.start_round_button.config(state=tk.DISABLED)
            return

        # Disable button and show preparation message
        self.start_round_button.config(state=tk.DISABLED)
        self.status_label.config(text="Preparing round...")
        
        # Wait 2 seconds before starting round (microcontroller limitation)
        self.master.after(2000, self.send_round_command)

    # ==============================
    # Serial handling
    # ==============================

    def serial_reader(self):
        """
        Background thread:
        - Accumulates bytes
        - Uses \\n/\\r as line break if present
        - If no line ending but 3+ bytes, takes 3 bytes as one message
        """
        buffer = b""
        while not self.stop_event.is_set():
            try:
                if self.ser is None or not self.ser.is_open:
                    break

                data = self.ser.read(64)
                if data:
                    buffer += data

                    while True:
                        nl_pos = buffer.find(b"\n")
                        cr_pos = buffer.find(b"\r")
                        sep_positions = [p for p in (nl_pos, cr_pos) if p != -1]

                        if sep_positions:
                            sep = min(sep_positions)
                            line_bytes = buffer[:sep]
                            buffer = buffer[sep + 1:]
                            line = line_bytes.decode("ascii", errors="replace")
                            self.rx_queue.put(line)
                        elif len(buffer) >= 3:
                            line_bytes = buffer[:3]
                            buffer = buffer[3:]
                            line = line_bytes.decode("ascii", errors="replace")
                            self.rx_queue.put(line)
                        else:
                            break
            except serial.SerialException as e:
                self.rx_queue.put(f"[Serial error: {e}]")
                break

    def process_rx_queue(self):
        """Runs in GUI thread, handles messages from serial_reader."""
        try:
            while True:
                line = self.rx_queue.get_nowait()
                self.handle_serial_line(line)
        except queue.Empty:
            pass

        self.master.after(50, self.process_rx_queue)

    def handle_serial_line(self, line: str):
        """Interpret line from MCU, mainly 3-digit delays or error codes E0/E1."""
        line_stripped = line.strip()

        # Check for error codes first
        if line_stripped == "E0":
            # Error: Button pressed too early
            self.status_label.config(text="❌ Button pressed too early!", fg='#F87060')
            self.last_result_label.config(text="GAME OVER", fg='#D93750')
            
            self.waiting_for_result = False
            self.start_round_button.config(
                text="RETURN TO MAIN MENU",
                state=tk.NORMAL,
                command=self.on_back_to_start_clicked
            )
            return
        
        elif line_stripped == "E1":
            # Error: Wrong color combination
            self.status_label.config(text="❌ Wrong color combination!", fg='#F87060')
            self.last_result_label.config(text="GAME OVER", fg='#D93750')
            
            self.waiting_for_result = False
            self.start_round_button.config(
                text="RETURN TO MAIN MENU",
                state=tk.NORMAL,
                command=self.on_back_to_start_clicked
            )
            return

        # Try parse as integer (delay time)
        try:
            delay_ms = int(line_stripped)
        except ValueError:
            # Non-numeric data and not an error code: ignore silently
            return

        # Only process if we are actually expecting a result
        if not self.waiting_for_result:
            return

        self.waiting_for_result = False
        self.start_round_button.config(state=tk.NORMAL)

        # Record this round
        self.round_times.append(delay_ms)
        self.current_round += 1

        self.last_result_label.config(text=f"{delay_ms} ms", fg='#2CA7A7')
        self.progress_label.config(
            text=f"Round {self.current_round} / {self.selected_rounds}"
        )

        if self.current_round >= self.selected_rounds:
            # Game finished - show last round time first, then show average after 3.5 seconds
            self.status_label.config(text="Round complete!", fg='#2CA7A7')
            self.start_round_button.config(state=tk.DISABLED)
            
            # Wait 3.5 seconds before showing final average
            self.master.after(3500, self.show_final_results)
        else:
            self.status_label.config(text="Great! Press START ROUND to continue", fg='#4D413D')

    def update_leaderboard_ui(self):
        """Refresh the three leaderboard listboxes."""
        boards = [
            (1, self.lb_1),
            (5, self.lb_5),
            (10, self.lb_10),
        ]

        for rounds, lb in boards:
            lb.delete(0, tk.END)
            entries = sorted(self.leaderboard[rounds], key=lambda x: x[1])
            for name, avg in entries:
                lb.insert(tk.END, f"{name}: {avg:.1f} ms")

    # ==============================
    # Cleanup
    # ==============================

    def on_close(self):
        self.stop_event.set()
        if self.ser is not None and self.ser.is_open:
            try:
                self.ser.close()
            except serial.SerialException:
                pass
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ReactionGameApp(root)
    root.mainloop()
