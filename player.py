"""
player.py — XONNIE CAREY BAKER v0.1.3
Semua urusan audio, dipisahkan dari GUI.

State machine: "stopped" | "playing" | "paused"

Quirk pygame yang ditangani di sini. Semua diverifikasi terhadap
dokumentasi resmi pygame (pygame.org/docs/ref/music.html):

A. set_volume(): "When new music is loaded the volume is reset to
   full volume." -> volume user disimpan di _volume dan di-reapply
   setiap kali load().

B. get_busy(): "In pygame 2.0.1 and above this function returns
   False when the music is paused." -> tick() memeriksa _state
   internal lebih dulu, sehingga pause tidak pernah dianggap
   "lagu selesai".

C. get_pos(): dokumentasi TIDAK menyebutkan perilakunya saat musik
   paused; implementasi pygame menghitung wall-clock di thread
   internal sehingga posisi terus maju saat pause. Karena ini
   bukan jaminan API, rumus _pause_offset di bawah sengaja dibuat
   benar untuk KEDUA skenario:
     offset = get_pos_raw_saat_resume - posisi_yang_dibekukan
   Jika get_pos() maju saat pause -> offset menyerap selisihnya.
   Jika get_pos() beku saat pause -> offset tidak berubah.
   Hasilnya sama: resume lanjut persis dari titik pause
   (00:17 -> PAUSE -> tunggu 5 detik -> 00:17, 00:18, 00:19...).

D. load(): "If a music stream is already playing it will be
   stopped." -> OPEN saat playing/paused aman by design; load()
   kita juga memanggil stop() sendiri untuk me-reset state.
"""

import os

import pygame
from mutagen import MutagenError
from mutagen.mp3 import MP3

class PlayerError(Exception):
    """Error yang 'normal' — user melakukan hal yang manusiawi."""
    pass

class Mp3Player:

    def __init__(self):
        try:
            pygame.mixer.init()
        except pygame.error as exc:
            raise PlayerError(f"audio initialization failed: {exc}")

        # Seluruh state diinisialisasi di constructor.
        # Setelah Mp3Player() dibuat, SEMUA attribute di bawah
        # PASTI ada — tidak ada lazy init di tempat lain.
        self.file_path = None        # path MP3 yang di-load, atau None
        self.duration = 0.0          # detik; 0.0 jika tidak terbaca
        self.loop = False
        self._state = "stopped"      # stopped | playing | paused
        self._volume = 1.0           # quirk A: di-reapply setelah load
        self._pause_offset = 0.0     # quirk C: koreksi get_pos()
        self._paused_position = 0.0  # posisi yang dibekukan saat pause

    # ------------------------------------------------ loading

    def load(self, path):
        """Validasi lalu siapkan file untuk diputar."""
        if not os.path.isfile(path):
            raise PlayerError("file not found")
        if not path.lower().endswith(".mp3"):
            raise PlayerError("not an mp3")

        try:
            self.duration = MP3(path).info.length
        except MutagenError:
            # Keputusan sadar: hanya menangkap MutagenError (base
            # class mutagen untuk header/metadata rusak), bukan
            # Exception. Metadata gagal dibaca bukan alasan menolak
            # lagu — file tetap boleh dicoba dimainkan, durasi
            # fallback 0.0. Exception non-mutagen (bug internal,
            # MemoryError) SENGAJA dibiarkan naik agar tidak
            # tersembunyi.
            self.duration = 0.0

        # Hentikan file lama (jika ada) sebelum ganti. Mencegah
        # state "GUI shows song B, audio plays song A".
        self.stop()
        self.file_path = path

    # ------------------------------------------------ playback

    def play(self):
        if self.file_path is None:
            raise PlayerError("no file loaded")

        if self._state == "paused":
            # Resume. Bekukan selisih raw get_pos() vs posisi pause
            # sebagai offset baru (lihat quirk C di docstring modul).
            raw = pygame.mixer.music.get_pos() / 1000.0
            self._pause_offset = raw - self._paused_position
            pygame.mixer.music.unpause()
            self._state = "playing"
            return

        try:
            pygame.mixer.music.load(self.file_path)
            # Quirk A: load() me-reset volume ke penuh.
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play()   # selalu loops=0; loop diatur manual
        except pygame.error as exc:
            # Jalur gagal (mis. MP3 corrupt): pastikan state bersih,
            # tidak ada offset residual.
            self._state = "stopped"
            self._pause_offset = 0.0
            self._paused_position = 0.0
            raise PlayerError(f"cannot play this file: {exc}")

        self._state = "playing"
        self._pause_offset = 0.0
        self._paused_position = 0.0

    def pause(self):
        if self._state == "playing":
            self._paused_position = self.get_position()
            pygame.mixer.music.pause()
            self._state = "paused"
        # Pause saat stopped/paused: no-op. Tidak ada state korup.

    def stop(self):
        pygame.mixer.music.stop()
        self._state = "stopped"
        self._pause_offset = 0.0
        self._paused_position = 0.0
        # Aman dipanggil kapan saja, termasuk saat sudah stopped.

    # ------------------------------------------------ controls

    def set_volume(self, value):
        """value: 0.0 sampai 1.0. Disimpan + langsung diterapkan.

        _volume adalah satu-satunya sumber kebenaran; slider GUI
        dan audio internal tidak pernah berbeda.
        """
        self._volume = max(0.0, min(1.0, value))
        pygame.mixer.music.set_volume(self._volume)

    def set_loop(self, enabled):
        self.loop = bool(enabled)

    # ------------------------------------------------ reporting

    def get_position(self):
        """Posisi playback dalam detik. Selalu float >= 0."""
        if self._state == "stopped":
            return 0.0
        if self._state == "paused":
            pos = self._paused_position
        else:
            pos = pygame.mixer.music.get_pos() / 1000.0 - self._pause_offset
        pos = max(0.0, pos)
        if self.duration > 0.0:
            # Clamp kosmetik: jangan tampilkan 03:43 / 03:42 di gap
            # antara lagu benar-benar habis dan tick() berikutnya.
            pos = min(pos, self.duration)
        return pos

    def tick(self):
        """
        Dipanggil berkala oleh GUI. Mengembalikan:
          "finished" -> lagu selesai (loop off)
          "looped"   -> lagu selesai lalu diulang (loop on)
          None       -> tidak ada kejadian menarik

        PENTING (quirk B): jangan hapus guard _state di bawah.
        get_busy() bernilai False saat PAUSED (pygame >= 2.0.1),
        jadi tanpa guard ini pause akan dianggap lagu selesai.
        """
        if self._state != "playing":
            return None

        if pygame.mixer.music.get_busy():
            return None

        # Musik berhenti sendiri: lagu selesai.
        if self.loop:
            try:
                pygame.mixer.music.play()
            except pygame.error:
                self._state = "stopped"
                return "finished"
            self._pause_offset = 0.0
            self._paused_position = 0.0
            return "looped"

        self._state = "stopped"
        self._pause_offset = 0.0
        self._paused_position = 0.0
        return "finished"

    # ------------------------------------------------ cleanup

    def close(self):
        """Bebaskan resource audio. Dipanggil saat window ditutup."""
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except pygame.error:
            pass  # sudah mati duluan — tidak masalah, kita sedang cleanup
        pygame.mixer.quit()
        self._state = "stopped"

    @property
    def state(self):
        return self._state