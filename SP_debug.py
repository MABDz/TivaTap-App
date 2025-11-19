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
        master.title("Reaction Time Game")

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

        # Player name
        name_label = tk.Label(self.start_frame, text="Player name:")
        name_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.name_entry = tk.Entry(self.start_frame, width=20)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Round selection
        rounds_label = tk.Label(self.start_frame, text="Number of rounds:")
        rounds_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")

        self.rounds_var = tk.IntVar(value=5)

        rounds_frame = tk.Frame(self.start_frame)
        rounds_frame.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        rb1 = tk.Radiobutton(rounds_frame, text="1", variable=self.rounds_var, value=1)
        rb5 = tk.Radiobutton(rounds_frame, text="5", variable=self.rounds_var, value=5)
        rb10 = tk.Radiobutton(rounds_frame, text="10", variable=self.rounds_var, value=10)

        rb1.pack(side=tk.LEFT, padx=5)
        rb5.pack(side=tk.LEFT, padx=5)
        rb10.pack(side=tk.LEFT, padx=5)

        # Start game button
        start_button = tk.Button(
            self.start_frame,
            text="Start Game",
            width=12,
            command=self.on_start_game_clicked,
        )
        start_button.grid(row=2, column=0, columnspan=2, padx=5, pady=15)

        # Info label
        self.start_info_label = tk.Label(self.start_frame, text="", fg="red")
        self.start_info_label.grid(row=3, column=0, columnspan=2)

    def create_game_screen(self):
        """Game screen: start round button, status, log, etc."""

        top_frame = tk.Frame(self.game_frame)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # Player / rounds info
        self.player_label = tk.Label(top_frame, text="Player: -")
        self.player_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")

        self.rounds_info_label = tk.Label(top_frame, text="Rounds: -")
        self.rounds_info_label.grid(row=1, column=0, padx=5, pady=2, sticky="w")

        self.progress_label = tk.Label(top_frame, text="Progress: 0 / 0")
        self.progress_label.grid(row=2, column=0, padx=5, pady=2, sticky="w")

        # Status
        self.status_label = tk.Label(top_frame, text="Status: Ready")
        self.status_label.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        # Start round button
        self.start_round_button = tk.Button(
            top_frame,
            text="Start round",
            width=12,
            command=self.on_start_round_clicked,
        )
        self.start_round_button.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Back to main menu
        back_button = tk.Button(
            top_frame,
            text="Back to main menu",
            command=self.on_back_to_start_clicked,
        )
        back_button.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # Last command / result
        self.last_cmd_label = tk.Label(top_frame, text="Last command: (none)")
        self.last_cmd_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        self.last_result_label = tk.Label(top_frame, text="Last delay: (none)")
        self.last_result_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        # Log area
        self.log = ScrolledText(self.game_frame, wrap=tk.WORD, width=80, height=12)
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log.insert(tk.END, "Log:\n")

        if hasattr(self, "ser") and self.ser is not None:
            self.log.insert(tk.END, f"Opened {SERIAL_PORT} at {BAUD_RATE} bps\n")
        else:
            self.log.insert(tk.END, f"Serial port {SERIAL_PORT} not available\n")

    def create_leaderboard_frame(self):
        """Leaderboard at bottom: separate for 1 / 5 / 10 rounds."""
        self.leaderboard_frame = tk.LabelFrame(self.master, text="Leaderboard (average reaction time)")
        self.leaderboard_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Column titles
        tk.Label(self.leaderboard_frame, text="1 round").grid(row=0, column=0, padx=5, pady=2)
        tk.Label(self.leaderboard_frame, text="5 rounds").grid(row=0, column=1, padx=5, pady=2)
        tk.Label(self.leaderboard_frame, text="10 rounds").grid(row=0, column=2, padx=5, pady=2)

        # Listboxes for each board
        self.lb_1 = tk.Listbox(self.leaderboard_frame, height=6, width=25)
        self.lb_5 = tk.Listbox(self.leaderboard_frame, height=6, width=25)
        self.lb_10 = tk.Listbox(self.leaderboard_frame, height=6, width=25)

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
        self.rounds_info_label.config(text=f"Rounds: {self.selected_rounds}")
        self.progress_label.config(text=f"Progress: {self.current_round} / {self.selected_rounds}")
        self.status_label.config(text="Status: Ready")
        self.last_cmd_label.config(text="Last command: (none)")
        self.last_result_label.config(text="Last delay: (none)")
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
            self.status_label.config(text="Status: Serial not open")
            return

        if self.waiting_for_result:
            self.status_label.config(text="Status: Waiting for result...")
            return

        if self.current_round >= self.selected_rounds:
            self.status_label.config(text="Status: All rounds finished")
            self.start_round_button.config(state=tk.DISABLED)
            return

        # Pick random color and number
        color = random.choice("RGBCMYW")
        number = random.randint(2, 6)

        cmd = f"S{color}{number}\n"

        try:
            self.ser.write(cmd.encode("ascii"))
        except serial.SerialException as e:
            self.log.insert(tk.END, f"Serial write error: {e}\n")
            self.status_label.config(text="Status: Serial write error")
            return

        self.waiting_for_result = True
        self.start_round_button.config(state=tk.DISABLED)

        self.last_cmd_label.config(text=f"Last command: {cmd.strip()}")
        self.status_label.config(text="Status: Command sent, waiting for result...")
        self.log.insert(tk.END, f"TX: {cmd}")
        self.log.see(tk.END)

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
        if hasattr(self, "log"):
            self.log.insert(tk.END, f"RX: {repr(line)}\n")
            self.log.see(tk.END)

        line_stripped = line.strip()

        # Check for error codes first
        if line_stripped == "E0":
            # Error: Button pressed too early
            if hasattr(self, "status_label"):
                self.status_label.config(text="ERROR: Button pressed too early!")
            if hasattr(self, "last_result_label"):
                self.last_result_label.config(text="GAME OVER - Too Early!")
            
            self.waiting_for_result = False
            self.start_round_button.config(state=tk.DISABLED)
            
            messagebox.showerror(
                "Game Over - E0",
                f"{self.player_name}, you pressed the button too early!\n\n"
                f"Round: {self.current_round + 1} / {self.selected_rounds}\n"
                f"Game ended."
            )
            return
        
        elif line_stripped == "E1":
            # Error: Wrong color combination
            if hasattr(self, "status_label"):
                self.status_label.config(text="ERROR: Wrong color combination!")
            if hasattr(self, "last_result_label"):
                self.last_result_label.config(text="GAME OVER - Wrong Colors!")
            
            self.waiting_for_result = False
            self.start_round_button.config(state=tk.DISABLED)
            
            messagebox.showerror(
                "Game Over - E1",
                f"{self.player_name}, you pressed the wrong color combination!\n\n"
                f"Round: {self.current_round + 1} / {self.selected_rounds}\n"
                f"Game ended."
            )
            return

        # Try parse as integer (delay time)
        try:
            delay_ms = int(line_stripped)
        except ValueError:
            # Non-numeric data and not an error code: treat as info only
            if hasattr(self, "status_label"):
                self.status_label.config(text="Status: Received non-numeric data")
            return

        # Only process if we are actually expecting a result
        if not self.waiting_for_result:
            if hasattr(self, "status_label"):
                self.status_label.config(text="Status: Unexpected delay received")
            return

        self.waiting_for_result = False
        self.start_round_button.config(state=tk.NORMAL)

        # Record this round
        self.round_times.append(delay_ms)
        self.current_round += 1

        self.last_result_label.config(text=f"Last delay: {delay_ms} ms")
        self.progress_label.config(
            text=f"Progress: {self.current_round} / {self.selected_rounds}"
        )

        if self.current_round >= self.selected_rounds:
            # Game finished
            avg = sum(self.round_times) / len(self.round_times)
            self.status_label.config(text=f"Status: Finished! Average: {avg:.1f} ms")
            self.start_round_button.config(state=tk.DISABLED)

            # Update leaderboard
            self.leaderboard[self.selected_rounds].append((self.player_name, avg))
            self.update_leaderboard_ui()

            # Optional: pop-up result
            messagebox.showinfo(
                "Game finished",
                f"{self.player_name}, your average over {self.selected_rounds} "
                f"round(s) is {avg:.1f} ms",
            )
        else:
            self.status_label.config(text="Status: Round complete, start next round")

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
