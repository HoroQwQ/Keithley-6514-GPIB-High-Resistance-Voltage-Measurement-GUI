import threading
import queue
import time
import csv
from dataclasses import dataclass
from datetime import datetime

import numpy as np

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import pyvisa


@dataclass
class Sample:
    pc_time: float
    reading: float
    inst_time: float | float("nan")
    status: float | float("nan")


class K6514Controller:
    def __init__(self):
        self.rm = None
        self.dev = None
        self.resource_name = None

    def open(self, resource_name: str, timeout_ms: int = 10000):
        self.close()

        self.rm = pyvisa.ResourceManager()  # use system VISA
        self.resource_name = resource_name
        self.dev = self.rm.open_resource(resource_name)

        # GPIB 常用：行结束 LF；大多数 6514 对 SCPI 换行没问题
        # 若你的环境需要 CRLF，可改成 "\r\n"
        self.dev.write_termination = "\n"
        self.dev.read_termination = "\n"
        self.dev.timeout = timeout_ms

        self.flush()

        idn = self.query("*IDN?")
        return idn.strip()

    def close(self):
        try:
            if self.dev is not None:
                try:
                    self.flush()
                except Exception:
                    pass
                try:
                    self.dev.close()
                except Exception:
                    pass
        finally:
            self.dev = None

        try:
            if self.rm is not None:
                self.rm.close()
        except Exception:
            pass
        finally:
            self.rm = None

    def flush(self):
        if self.dev is None:
            return
        # 尝试清输入缓冲，避免“上一条残留”
        try:
            self.dev.clear()
        except Exception:
            pass

    def write(self, cmd: str):
        if self.dev is None:
            raise RuntimeError("Device not connected")
        self.dev.write(cmd)

    def read(self) -> str:
        if self.dev is None:
            raise RuntimeError("Device not connected")
        return self.dev.read()

    def query(self, cmd: str) -> str:
        if self.dev is None:
            raise RuntimeError("Device not connected")
        return self.dev.query(cmd)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Keithley 6514 GPIB Acquisition (GUI)")
        self.geometry("1100x700")

        self.ctrl = K6514Controller()

        self.data = []  # list[Sample]
        self.q = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.is_running = False

        self._build_ui()
        self._build_plot()

        self.after(100, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._refresh_resources()

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        # Resource
        ttk.Label(top, text="VISA Resource:").grid(row=0, column=0, sticky="w")
        self.resource_var = tk.StringVar()
        self.resource_box = ttk.Combobox(top, textvariable=self.resource_var, width=36)
        self.resource_box.grid(row=0, column=1, padx=6, sticky="w")

        ttk.Button(top, text="Refresh", command=self._refresh_resources).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Connect", command=self._connect).grid(row=0, column=3, padx=4)
        ttk.Button(top, text="Disconnect", command=self._disconnect).grid(row=0, column=4, padx=4)

        # IDN
        ttk.Label(top, text="IDN:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.idn_var = tk.StringVar(value="(not connected)")
        ttk.Label(top, textvariable=self.idn_var).grid(row=1, column=1, columnspan=4, sticky="w", pady=(6, 0))

        # Settings panel
        settings = ttk.LabelFrame(self, text="Acquisition Settings")
        settings.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        self.duration_var = tk.DoubleVar(value=150.0)
        self.chunk_var = tk.IntVar(value=10)
        self.nplc_var = tk.DoubleVar(value=1.0)

        self.autorange_var = tk.BooleanVar(value=True)
        self.fixed_range_var = tk.DoubleVar(value=20.0)

        self.zero_correct_var = tk.BooleanVar(value=False)

        self.disable_display_var = tk.BooleanVar(value=True)
        self.disable_autozero_var = tk.BooleanVar(value=True)
        self.disable_avg_var = tk.BooleanVar(value=True)

        r = 0
        ttk.Label(settings, text="Duration (s):").grid(row=r, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(settings, textvariable=self.duration_var, width=10).grid(row=r, column=1, sticky="w", pady=4)

        ttk.Label(settings, text="Chunk (TRIG:COUN):").grid(row=r, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(settings, textvariable=self.chunk_var, width=10).grid(row=r, column=3, sticky="w", pady=4)

        ttk.Label(settings, text="NPLC:").grid(row=r, column=4, sticky="w", padx=6, pady=4)
        ttk.Entry(settings, textvariable=self.nplc_var, width=10).grid(row=r, column=5, sticky="w", pady=4)

        r += 1
        ttk.Checkbutton(settings, text="Auto Range", variable=self.autorange_var,
                        command=self._toggle_range_entry).grid(row=r, column=0, sticky="w", padx=6, pady=4)

        ttk.Label(settings, text="Fixed Range (V):").grid(row=r, column=2, sticky="w", padx=6, pady=4)
        self.fixed_range_entry = ttk.Entry(settings, textvariable=self.fixed_range_var, width=10)
        self.fixed_range_entry.grid(row=r, column=3, sticky="w", pady=4)

        ttk.Checkbutton(settings, text="Zero Correct (ZCOR acquire)", variable=self.zero_correct_var)\
            .grid(row=r, column=4, columnspan=2, sticky="w", padx=6, pady=4)

        r += 1
        ttk.Checkbutton(settings, text="Disable Display (DISP:ENAB OFF)", variable=self.disable_display_var)\
            .grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(settings, text="Disable AutoZero (SYST:AZER OFF)", variable=self.disable_autozero_var)\
            .grid(row=r, column=2, columnspan=2, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(settings, text="Disable Averaging (AVER OFF)", variable=self.disable_avg_var)\
            .grid(row=r, column=4, columnspan=2, sticky="w", padx=6, pady=4)

        # Buttons
        buttons = ttk.Frame(self)
        buttons.pack(side=tk.TOP, fill=tk.X, padx=10, pady=6)

        ttk.Button(buttons, text="Start", command=self._start).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Stop", command=self._stop).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Save CSV", command=self._save_csv).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Save MAT (scipy)", command=self._save_mat).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Clear Data", command=self._clear_data).pack(side=tk.LEFT, padx=6)

        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(buttons, textvariable=self.status_var).pack(side=tk.RIGHT)

        self._toggle_range_entry()

    def _build_plot(self):
        frame = ttk.Frame(self)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=8)

        fig = Figure(figsize=(8, 4), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.grid(True)
        self.line, = self.ax.plot([], [])

        self.canvas = FigureCanvasTkAgg(fig, master=frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _toggle_range_entry(self):
        state = "disabled" if self.autorange_var.get() else "normal"
        self.fixed_range_entry.configure(state=state)

    # ---------------- VISA / connect ----------------
    def _refresh_resources(self):
        try:
            rm = pyvisa.ResourceManager()
            resources = list(rm.list_resources())
            rm.close()
        except Exception as e:
            messagebox.showerror("VISA Error", f"Failed to list resources:\n{e}")
            return

        # 优先把 GPIB 放前面
        resources.sort(key=lambda x: (0 if x.startswith("GPIB") else 1, x))
        self.resource_box["values"] = resources
        if resources and not self.resource_var.get():
            self.resource_var.set(resources[0])

    def _connect(self):
        if self.ctrl.dev is not None:
            messagebox.showinfo("Info", "Already connected.")
            return

        rsrc = self.resource_var.get().strip()
        if not rsrc:
            messagebox.showwarning("Warning", "Please select a VISA resource.")
            return

        try:
            idn = self.ctrl.open(rsrc)
            self.idn_var.set(idn)
            self.status_var.set("Connected.")
        except Exception as e:
            messagebox.showerror("Connect failed", str(e))

    def _disconnect(self):
        if self.is_running:
            self._stop()
        self.ctrl.close()
        self.idn_var.set("(not connected)")
        self.status_var.set("Disconnected.")

    # ---------------- acquisition ----------------
    def _start(self):
        if self.ctrl.dev is None:
            messagebox.showwarning("Warning", "Not connected.")
            return
        if self.is_running:
            messagebox.showinfo("Info", "Already running.")
            return

        self.stop_event.clear()
        self.is_running = True
        self.status_var.set("Running...")

        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def _stop(self):
        if not self.is_running:
            return
        self.stop_event.set()
        self.status_var.set("Stopping...")

    def _worker_loop(self):
        t0 = time.monotonic()
        duration = float(self.duration_var.get())
        chunk = int(self.chunk_var.get())
        nplc = float(self.nplc_var.get())

        try:
            # ---------- configure instrument ----------
            self.ctrl.write("*CLS")
            # self.ctrl.write("*RST")  # 如需每次复位可打开

            self.ctrl.write("SENS:FUNC 'VOLT'")

            if self.autorange_var.get():
                self.ctrl.write("SENS:VOLT:RANG:AUTO ON")
            else:
                rng = float(self.fixed_range_var.get())
                self.ctrl.write(f"SENS:VOLT:RANG {rng:g}")

            self.ctrl.write(f"SENS:VOLT:NPLC {nplc:g}")

            # Trigger / format
            self.ctrl.write("TRIG:SOUR IMM")
            self.ctrl.write("TRIG:DEL 0")
            self.ctrl.write(f"TRIG:COUN {chunk}")

            self.ctrl.write("FORM:DATA ASC")
            self.ctrl.write("FORM:ELEM READ,TIME,STAT")  # 3 numbers per reading

            if self.disable_avg_var.get():
                self.ctrl.write("AVER OFF")
            if self.disable_autozero_var.get():
                self.ctrl.write("SYST:AZER OFF")
            if self.disable_display_var.get():
                self.ctrl.write("DISP:ENAB OFF")

            # Optional Zero Correct (Acquire method)
            if self.zero_correct_var.get():
                # 标准流程：ZCH ON -> INIT -> ZCOR:ACQ -> ZCH OFF -> ZCOR ON
                self.ctrl.write("SYST:ZCOR OFF")
                self.ctrl.write("SYST:ZCH ON")
                self.ctrl.write("INIT")
                self.ctrl.write("SYST:ZCOR:ACQ")
                self.ctrl.write("SYST:ZCH OFF")
                self.ctrl.write("SYST:ZCOR ON")

            # ---------- acquisition loop ----------
            while (time.monotonic() - t0) < duration and (not self.stop_event.is_set()):
                # 允许运行中改 chunk
                chunk = int(self.chunk_var.get())
                self.ctrl.write(f"TRIG:COUN {chunk}")

                resp = self.ctrl.query(":READ?").strip()
                nums = np.fromstring(resp.replace(",", " "), sep=" ")

                # 期望 3*chunk；容错
                if nums.size == 3 * chunk:
                    M = nums.reshape(-1, 3)
                    read_vals = M[:, 0]
                    inst_time = M[:, 1]
                    stat_vals = M[:, 2]
                elif nums.size == chunk:
                    read_vals = nums
                    inst_time = np.full_like(read_vals, np.nan, dtype=float)
                    stat_vals = np.full_like(read_vals, np.nan, dtype=float)
                else:
                    # 异常返回：丢弃但不中断
                    self.q.put(("log", f"Unexpected response length={nums.size}: {resp[:120]}"))
                    continue

                pc_now = time.monotonic() - t0
                for i in range(read_vals.size):
                    s = Sample(pc_time=pc_now,
                               reading=float(read_vals[i]),
                               inst_time=float(inst_time[i]) if np.isfinite(inst_time[i]) else float("nan"),
                               status=float(stat_vals[i]) if np.isfinite(stat_vals[i]) else float("nan"))
                    self.q.put(("data", s))

            self.q.put(("done", None))

        except Exception as e:
            self.q.put(("error", str(e)))
        finally:
            # 尽量恢复仪器（减少“下次面板/状态怪”）
            try:
                if self.disable_display_var.get():
                    self.ctrl.write("DISP:ENAB ON")
            except Exception:
                pass
            try:
                if self.disable_autozero_var.get():
                    self.ctrl.write("SYST:AZER ON")
            except Exception:
                pass

    # ---------------- queue + plot ----------------
    def _poll_queue(self):
        try:
            updated = False
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "data":
                    self.data.append(payload)
                    updated = True
                elif kind == "log":
                    self.status_var.set(str(payload))
                elif kind == "error":
                    self.is_running = False
                    self.status_var.set("Error.")
                    messagebox.showerror("Acquisition Error", str(payload))
                elif kind == "done":
                    self.is_running = False
                    self.status_var.set(f"Done. Points={len(self.data)}")
        except queue.Empty:
            pass

        if updated:
            self._update_plot()

        self.after(100, self._poll_queue)

    def _update_plot(self):
        if not self.data:
            return
        t = np.array([s.pc_time for s in self.data], dtype=float)
        v = np.array([s.reading for s in self.data], dtype=float)

        self.line.set_data(t, v)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    # ---------------- save ----------------
    def _clear_data(self):
        if self.is_running:
            messagebox.showwarning("Warning", "Stop first.")
            return
        self.data.clear()
        self.line.set_data([], [])
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()
        self.status_var.set("Cleared.")

    def _save_csv(self):
        if not self.data:
            messagebox.showwarning("Warning", "No data.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"k6514_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["pc_time_s", "reading_V", "inst_time", "status"])
            for s in self.data:
                w.writerow([s.pc_time, s.reading, s.inst_time, s.status])
        self.status_var.set(f"Saved CSV: {path}")

    def _save_mat(self):
        if not self.data:
            messagebox.showwarning("Warning", "No data.")
            return
        try:
            from scipy.io import savemat
        except Exception:
            messagebox.showerror("Missing scipy", "Please install scipy: pip install scipy")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".mat",
            filetypes=[("MAT", "*.mat")],
            initialfile=f"k6514_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mat"
        )
        if not path:
            return

        arr = np.array([[s.pc_time, s.reading, s.inst_time, s.status] for s in self.data], dtype=float)
        savemat(path, {"qwq": arr, "columns": np.array(["pc_time_s", "reading_V", "inst_time", "status"], dtype=object)})
        self.status_var.set(f"Saved MAT: {path}")

    # ---------------- close ----------------
    def _on_close(self):
        try:
            if self.is_running:
                self.stop_event.set()
                time.sleep(0.2)
        except Exception:
            pass
        try:
            self.ctrl.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
