"""
main.py — XONNIE CAREY BAKER v0.1.3
A tiny MP3 player that takes itself way too seriously.

Tanggung jawab file ini hanya GUI:
- membangun widget Tkinter
- menerjemahkan klik user menjadi panggilan ke Mp3Player
- polling posisi tiap 200 ms untuk update timer + deteksi lagu selesai
- cleanup saat window ditutup

Semua urusan audio ada di player.py.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from player import Mp3Player, PlayerError

APP_TITLE = "XONNIE CAREY BAKER"
POLL_INTERVAL_MS = 200

# The Bloon Requirement: semua konstanta di bawah ini dipakai.
STATUS_STARTUP = "Status: pretending to be Winamp."
STATUS_PLAYING = "Status: playing music very seriously."
STATUS_PAUSED = "Status: frozen mid-emotion."
STATUS_IDLE = "Status: no music. excellent."
STATUS_FINISHED = "Status: music has escaped."
STATUS_LOOPED = "Status: again. and again. this is fine."
STATUS_NO_FILE = "Status: you pressed PLAY on nothing. bold."
STATUS_NOT_MP3 = "Status: that is not an MP3, human."
STATUS_NOT_FOUND = "Status: the file ran away."
STATUS_FILE_READY = "Status: file acquired. awaiting orders."
STATUS_AUDIO_DEAD = "Audio initialization failed. Check your sound device."

def format_time(seconds):
    """
    123.4 -> "02:03". Format M:SS sederhana, tanpa drama.

    Kontrak: pemanggil HARUS mengirim angka (int/float).
    Kedua pemanggil di file ini (player.duration dan
    player.get_position()) dijamin mengembalikan float, jadi
    None tidak akan pernah masuk ke sini. Nilai negatif
    di-clamp ke 0.
    """
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"

class App:

    def __init__(self, root):
        # ok=False berarti aplikasi gagal dibangun; main() tidak
        # boleh memanggil mainloop() pada root yang sudah di-destroy.
        self.ok = False
        self._closed = False
        self._after_id = None
        self.root = root
        self.root.title(APP_TITLE)
        self.root.resizable(False, False)

        try:
            self.player = Mp3Player()
        except PlayerError:
            messagebox.showerror(APP_TITLE, STATUS_AUDIO_DEAD)
            root.destroy()
            return

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._set_status(STATUS_STARTUP)
        self._poll()
        self.ok = True

    # ------------------------------------------------ UI

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        tk.Label(self.root, text=APP_TITLE,
                 font=("Helvetica", 18, "bold")).pack(pady=(16, 0))
        tk.Label(self.root, text="♪ MP3 PLAYER FOR HUMANS ♪",
                 font=("Helvetica", 10, "italic")).pack(pady=(0, 10))

        tk.Label(self.root, text="Current file:",
                 anchor="w").pack(fill="x", **pad)
        self.file_label = tk.Label(self.root, text="(none — the void)",
                                   anchor="w", font=("Courier", 10),
                                   fg="#3355cc")
        self.file_label.pack(fill="x", **pad)

        # Playback buttons
        btn_row = tk.Frame(self.root)
        btn_row.pack(pady=10)
        tk.Button(btn_row, text="PLAY", width=8,
                  command=self.on_play).pack(side="left", padx=4)
        tk.Button(btn_row, text="PAUSE", width=8,
                  command=self.on_pause).pack(side="left", padx=4)
        tk.Button(btn_row, text="STOP", width=8,
                  command=self.on_stop).pack(side="left", padx=4)

        # Volume. set(80) mungkin memicu command, mungkin tidak
        # (detail Tk) — karena itu volume awal juga di-set
        # eksplisit ke player agar slider dan internal tidak beda.
        tk.Label(self.root, text="Volume").pack()
        self.volume = tk.Scale(self.root, from_=0, to=100,
                               orient="horizontal", length=260,
                               showvalue=False,
                               command=self.on_volume)
        self.volume.set(80)
        self.volume.pack(pady=(0, 6))
        self.player.set_volume(0.8)

        # Progress
        self.time_label = tk.Label(self.root, text="00:00 / 00:00",
                                   font=("Courier", 12))
        self.time_label.pack(pady=4)

        # File & loop
        tk.Button(self.root, text="OPEN MP3", width=16,
                  command=self.on_open).pack(pady=6)
        self.loop_button = tk.Button(self.root, text="LOOP: OFF",
                                     width=16, command=self.on_loop)
        self.loop_button.pack(pady=(0, 6))

        # Status bar (the bloon lives here)
        self.status_label = tk.Label(self.root, text="", anchor="w",
                                     relief="sunken", bd=1,
                                     font=("Courier", 9))
        self.status_label.pack(fill="x", side="bottom")

    # ------------------------------------------------ events

    def on_open(self):
        path = filedialog.askopenfilename(
            title="Choose an MP3 (your own, please)",
            filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")],
        )
        if not path:
            # User cancel. askopenfilename mengembalikan "" —
            # bukan exception. Diam dan hormati keputusannya.
            return

        try:
            self.player.load(path)
        except PlayerError as exc:
            message = str(exc)
            if message == "not an mp3":
                self._set_status(STATUS_NOT_MP3)
            elif message == "file not found":
                self._set_status(STATUS_NOT_FOUND)
            else:
                self._set_status(f"Status: {message}")
            return

        self.file_label.config(text=os.path.basename(path))
        self._set_status(STATUS_FILE_READY)
        self._update_time()

    def on_play(self):
        try:
            self.player.play()
        except PlayerError as exc:
            if str(exc) == "no file loaded":
                self._set_status(STATUS_NO_FILE)
            else:
                self._set_status(f"Status: {exc}")
            return
        self._set_status(STATUS_PLAYING)

    def on_pause(self):
        self.player.pause()
        if self.player.state == "paused":
            self._set_status(STATUS_PAUSED)

    def on_stop(self):
        if self.player.state != "stopped":
            self.player.stop()
            self._set_status(STATUS_IDLE)

    def on_volume(self, value):
        # Tkinter Scale mengirim value sebagai string.
        self.player.set_volume(int(value) / 100.0)

    def on_loop(self):
        self.player.set_loop(not self.player.loop)
        self.loop_button.config(
            text="LOOP: ON" if self.player.loop else "LOOP: OFF")

    # ------------------------------------------------ polling & lifecycle

    def _poll(self):
        if self._closed:
            return
        event = self.player.tick()
        if event == "finished":
            self._set_status(STATUS_FINISHED)
        elif event == "looped":
            self._set_status(STATUS_LOOPED)
        self._update_time()
        # Simpan id supaya bisa di-cancel saat window ditutup;
        # hanya satu callback pending dalam satu waktu (rantai,
        # bukan tumpukan).
        self._after_id = self.root.after(POLL_INTERVAL_MS, self._poll)

    def on_close(self):
        """WM_DELETE_WINDOW: hentikan audio, batalkan polling, bersih-bersih.

        Urutan wajib: after_cancel -> player.close() -> root.destroy().
        """
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.player.close()
        self.root.destroy()

    def _update_time(self):
        pos = format_time(self.player.get_position())
        total = format_time(self.player.duration)
        self.time_label.config(text=f"{pos} / {total}")

    def _set_status(self, text):
        self.status_label.config(text=text)

def main():
    root = tk.Tk()
    app = App(root)
    if app.ok:
        root.mainloop()
    # Jika app.ok False, root sudah di-destroy di App.__init__
    # dan mainloop() TIDAK boleh dipanggil.

if __name__ == "__main__":
    main()