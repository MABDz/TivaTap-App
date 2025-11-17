import threading
import queue
import random
import serial
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox


# ====== SERIAL CONFIG ======
SERIAL_PORT = "COM7"
BAUD_RATE = 9600
# ===========================


class ReactionGameApp:
    def __init__(self, master):
        self.master = master
        master.title("TivaTap - Reaction Time Challenge")
        master.configure(bg='#1a1a2e')
        master.geometry('600x500')

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

        self.show_start_screen()

        # ---- Serial setup ----
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
            # Log later when game screen is visible
        except serial.SerialException as e:
            self.ser = None
            messagebox.showerror("Serial Error", f"Error opening {SERIAL_PORT}: {e}")

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
    # UI construction
    # ==============================

    def create_start_screen(self):
        """Start screen: name, rounds selection, start button."""
        self.start_frame.configure(bg='#1a1a2e')

        # Title
        title_label = tk.Label(
            self.start_frame,
            text="TivaTap",
            font=("Arial", 32, "bold"),
            bg='#1a1a2e',
            fg='#00d4ff'
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(30, 10))

        subtitle_label = tk.Label(
            self.start_frame,
            text="Reaction Time Challenge",
            font=("Arial", 14),
            bg='#1a1a2e',
            fg='#bbbbbb'
        )
        subtitle_label.grid(row=1, column=0, columnspan=2, pady=(0, 30))

        # Player name
        name_label = tk.Label(
            self.start_frame,
            text="Player Name:",
            font=("Arial", 12),
            bg='#1a1a2e',
            fg='#ffffff'
        )
        name_label.grid(row=2, column=0, padx=5, pady=10, sticky="e")

        self.name_entry = tk.Entry(
            self.start_frame,
            width=20,
            font=("Arial", 12),
            bg='#16213e',
            fg='#ffffff',
            insertbackground='#ffffff',
            relief=tk.FLAT,
            bd=2
        )
        self.name_entry.grid(row=2, column=1, padx=5, pady=10, sticky="w")

        # Round selection
        rounds_label = tk.Label(
            self.start_frame,
            text="Number of Rounds:",
            font=("Arial", 12),
            bg='#1a1a2e',
            fg='#ffffff'
        )
        rounds_label.grid(row=3, column=0, padx=5, pady=10, sticky="e")

        self.rounds_var = tk.IntVar(value=5)

        rounds_frame = tk.Frame(self.start_frame, bg='#1a1a2e')
        rounds_frame.grid(row=3, column=1, padx=5, pady=10, sticky="w")

        rb1 = tk.Radiobutton(
            rounds_frame, text="1", variable=self.rounds_var, value=1,
            font=("Arial", 11), bg='#1a1a2e', fg='#ffffff',
            selectcolor='#16213e', activebackground='#1a1a2e', activeforeground='#00d4ff'
        )
        rb5 = tk.Radiobutton(
            rounds_frame, text="5", variable=self.rounds_var, value=5,
            font=("Arial", 11), bg='#1a1a2e', fg='#ffffff',
            selectcolor='#16213e', activebackground='#1a1a2e', activeforeground='#00d4ff'
        )
        rb10 = tk.Radiobutton(
            rounds_frame, text="10", variable=self.rounds_var, value=10,
            font=("Arial", 11), bg='#1a1a2e', fg='#ffffff',
            selectcolor='#16213e', activebackground='#1a1a2e', activeforeground='#00d4ff'
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
            bg='#00d4ff',
            fg='#1a1a2e',
            activebackground='#00a8cc',
            activeforeground='#1a1a2e',
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        start_button.grid(row=4, column=0, columnspan=2, padx=5, pady=30)

        # Info label
        self.start_info_label = tk.Label(
            self.start_frame,
            text="",
            font=("Arial", 10),
            fg="#ff6b6b",
            bg='#1a1a2e'
        )
        self.start_info_label.grid(row=5, column=0, columnspan=2)

    def create_game_screen(self):
        """Game screen: start round button, status, etc."""
        self.game_frame.configure(bg='#1a1a2e')

        # Title area
        title_frame = tk.Frame(self.game_frame, bg='#1a1a2e')
        title_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=(20, 10))

        game_title = tk.Label(
            title_frame,
            text="TivaTap",
            font=("Arial", 24, "bold"),
            bg='#1a1a2e',
            fg='#00d4ff'
        )
        game_title.pack()

        # Info frame
        info_frame = tk.Frame(self.game_frame, bg='#16213e', relief=tk.FLAT)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=10)

        # Player / rounds info
        self.player_label = tk.Label(
            info_frame,
            text="Player: -",
            font=("Arial", 12, "bold"),
            bg='#16213e',
            fg='#00d4ff'
        )
        self.player_label.pack(pady=5)

        self.progress_label = tk.Label(
            info_frame,
            text="Round 0 / 0",
            font=("Arial", 16, "bold"),
            bg='#16213e',
            fg='#ffffff'
        )
        self.progress_label.pack(pady=5)

        # Result display
        result_frame = tk.Frame(self.game_frame, bg='#1a1a2e')
        result_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.last_result_label = tk.Label(
            result_frame,
            text="Ready to Start",
            font=("Arial", 20, "bold"),
            bg='#1a1a2e',
            fg='#4ecca3'
        )
        self.last_result_label.pack(expand=True)

        # Status
        self.status_label = tk.Label(
            result_frame,
            text="Press START ROUND to begin",
            font=("Arial", 12),
            bg='#1a1a2e',
            fg='#bbbbbb'
        )
        self.status_label.pack()

        # Button frame
        button_frame = tk.Frame(self.game_frame, bg='#1a1a2e')
        button_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=10)

        # Start round button
        self.start_round_button = tk.Button(
            button_frame,
            text="START ROUND",
            width=20,
            font=("Arial", 14, "bold"),
            command=self.on_start_round_clicked,
            bg='#4ecca3',
            fg='#1a1a2e',
            activebackground='#3daa82',
            activeforeground='#1a1a2e',
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        self.start_round_button.pack(pady=5)

        # Back to main menu
        back_button = tk.Button(
            button_frame,
            text="Back to Menu",
            font=("Arial", 10),
            command=self.on_back_to_start_clicked,
            bg='#1a1a2e',
            fg='#bbbbbb',
            activebackground='#16213e',
            activeforeground='#ffffff',
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        back_button.pack(pady=5)

    def create_leaderboard_frame(self):
        """Leaderboard at bottom: separate for 1 / 5 / 10 rounds."""
        self.leaderboard_frame = tk.LabelFrame(
            self.master,
            text="🏆 LEADERBOARD 🏆",
            font=("Arial", 12, "bold"),
            bg='#16213e',
            fg='#ffd700',
            relief=tk.FLAT,
            bd=2
        )
        self.leaderboard_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Column titles
        tk.Label(
            self.leaderboard_frame,
            text="1 Round",
            font=("Arial", 10, "bold"),
            bg='#16213e',
            fg='#00d4ff'
        ).grid(row=0, column=0, padx=5, pady=5)
        tk.Label(
            self.leaderboard_frame,
            text="5 Rounds",
            font=("Arial", 10, "bold"),
            bg='#16213e',
            fg='#00d4ff'
        ).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(
            self.leaderboard_frame,
            text="10 Rounds",
            font=("Arial", 10, "bold"),
            bg='#16213e',
            fg='#00d4ff'
        ).grid(row=0, column=2, padx=5, pady=5)

        # Listboxes for each board
        self.lb_1 = tk.Listbox(
            self.leaderboard_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#0f1626',
            fg='#ffffff',
            selectbackground='#00d4ff',
            selectforeground='#1a1a2e',
            relief=tk.FLAT,
            bd=0
        )
        self.lb_5 = tk.Listbox(
            self.leaderboard_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#0f1626',
            fg='#ffffff',
            selectbackground='#00d4ff',
            selectforeground='#1a1a2e',
            relief=tk.FLAT,
            bd=0
        )
        self.lb_10 = tk.Listbox(
            self.leaderboard_frame,
            height=6,
            width=25,
            font=("Arial", 9),
            bg='#0f1626',
            fg='#ffffff',
            selectbackground='#00d4ff',
            selectforeground='#1a1a2e',
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
            self.start_info_label.config(text="Please enter a name.")
            return

        if rounds not in (1, 5, 10):
            self.start_info_label.config(text="Please select number of rounds.")
            return

        if self.ser is None or not self.ser.is_open:
            self.start_info_label.config(text="Serial port not open.")
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
        self.status_label.config(text="Press START ROUND to begin")
        self.last_result_label.config(text="Ready to Start", fg='#4ecca3')
        self.start_round_button.config(state=tk.NORMAL)

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

        # Pick random color and number
        color = random.choice("RGBCMYW")
        number = random.randint(2, 6)

        cmd = f"S{color}{number}\n"

        try:
            self.ser.write(cmd.encode("ascii"))
        except serial.SerialException as e:
            self.status_label.config(text="Connection error - please restart")
            return

        self.waiting_for_result = True
        self.start_round_button.config(state=tk.DISABLED)

        self.status_label.config(text="Get ready... TAP when you see the light!")
        self.last_result_label.config(text="...", fg='#ffcc00')

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
        """Interpret line from MCU, mainly 3-digit delays."""
        # Try parse as integer
        try:
            delay_ms = int(line.strip())
        except ValueError:
            # Non-numeric data: ignore silently
            return

        # Only process if we are actually expecting a result
        if not self.waiting_for_result:
            return

        self.waiting_for_result = False
        self.start_round_button.config(state=tk.NORMAL)

        # Record this round
        self.round_times.append(delay_ms)
        self.current_round += 1

        self.last_result_label.config(text=f"{delay_ms} ms", fg='#4ecca3')
        self.progress_label.config(
            text=f"Round {self.current_round} / {self.selected_rounds}"
        )

        if self.current_round >= self.selected_rounds:
            # Game finished
            avg = sum(self.round_times) / len(self.round_times)
            self.status_label.config(text=f"Game Complete!")
            self.last_result_label.config(text=f"Average: {avg:.1f} ms", fg='#ffd700')
            self.start_round_button.config(state=tk.DISABLED)

            # Update leaderboard
            self.leaderboard[self.selected_rounds].append((self.player_name, avg))
            self.update_leaderboard_ui()

            # Show result popup
            messagebox.showinfo(
                "🎉 Game Complete!",
                f"Congratulations {self.player_name}!\n\n"
                f"Average Reaction Time: {avg:.1f} ms\n"
                f"Rounds Completed: {self.selected_rounds}",
            )
        else:
            self.status_label.config(text="Great! Press START ROUND to continue")

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
