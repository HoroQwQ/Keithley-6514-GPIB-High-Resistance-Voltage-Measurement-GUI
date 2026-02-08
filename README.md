# Keithley-6514-GPIB-High-Resistance-Voltage-Measurement-GUI

A Python-based GUI application for controlling a **Keithley 6514 Electrometer** via **GPIB** to perform long-duration, high-resistance voltage measurements.  
The program provides real-time plotting, configurable acquisition parameters, and data export to CSV and MAT formats.

The GUI is built with **Tkinter**, communication is handled via **PyVISA**, and data visualization uses **Matplotlib**.

---

## Features

- GPIB communication with Keithley 6514 via VISA
- Real-time voltage plotting
- Configurable measurement parameters:
  - Duration
  - Trigger count (chunk size)
  - NPLC
  - Auto range / fixed range
  - Zero correction (ZCOR acquire)
- Optional performance optimizations:
  - Disable display
  - Disable auto-zero
  - Disable averaging
- Threaded acquisition (non-blocking GUI)
- Data export:
  - CSV
  - MATLAB `.mat`
- Robust handling of unexpected instrument responses

---

## Hardware Requirements

- **Keithley 6514 Electrometer**
- **GPIB Interface**, tested with:
  - **Texas Instruments KUSB-488B**

---

## ⚠️ Very Important: GPIB Driver Compatibility (TI KUSB-488B)

If you are using **TI KUSB-488B**, you **must pay close attention to driver installation**, otherwise PyVISA will fail or behave unpredictably.

### Required Setup for TI KUSB-488B

You **must install**:

- **Texas Instruments GPIB Driver** (for KUSB-488B)
- **NI MAX**
- **NI-VISA**

### ❌ What You MUST Remove

- **NI-488.2**

> ⚠️ **NI-488.2 is NOT compatible with the TI KUSB-488B driver.**  
> If NI-488.2 is installed together with the TI driver, VISA resource discovery and GPIB communication may fail.

### Recommended Installation Order

1. Uninstall **NI-488.2** (if present)
2. Install **TI KUSB-488B GPIB Driver**
3. Install **NI-VISA**
4. Install **NI MAX**
5. Reboot the system

After this, the GPIB resource should be visible in **NI MAX** and discoverable via PyVISA.

---

## Software Requirements

- Python ≥ 3.10 (recommended)
- Required Python packages:

```bash
pip install numpy matplotlib pyvisa scipy
````

Additional notes:

* `scipy` is only required if you want to save data as `.mat`
* The program uses **system VISA** (`pyvisa.ResourceManager()`)

---

## Usage

1. Connect the Keithley 6514 to your computer via GPIB
2. Power on the instrument
3. Run the program:

```bash
python k6514_gui.py
```

4. In the GUI:

   * Click **Refresh** to list VISA resources
   * Select the GPIB resource (e.g. `GPIB0::22::INSTR`)
   * Click **Connect**
   * Configure acquisition parameters
   * Click **Start** to begin measurement

---

## Data Format

### CSV Output

Columns:

* `pc_time_s` — elapsed PC time (seconds)
* `reading_V` — measured voltage
* `inst_time` — instrument timestamp (if enabled)
* `status` — Keithley status word

### MAT Output

The `.mat` file contains:

* `qwq`: `N × 4` numeric array
* `columns`: column name labels

---

## Notes on Instrument Configuration

* Communication uses ASCII data format:

  * `FORM:DATA ASC`
  * `FORM:ELEM READ,TIME,STAT`
* Trigger mode:

  * Immediate trigger
  * Software-controlled `TRIG:COUN`
* The program attempts to restore display and auto-zero settings after acquisition

---

## Disclaimer

This software is provided **as-is**, without warranty.
Always verify measurement settings and results when working with high-impedance or sensitive measurements.

---

## License

MIT License
