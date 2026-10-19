"""PySide6 measurement UI. Start with python -m gearshift.gui."""
import math
import queue
import sys
import threading
from collections import Counter, deque

import pyqtgraph as pg
from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from .measurement import Session, Settings, export_csv


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Edge AI – mérőfelület')
        self.resize(1100, 850)
        self.session = None
        self.export_thread = None
        self.export_result = queue.SimpleQueue()
        self.closing = False
        self.finished = False
        self.points = deque(maxlen=2000)
        self.memory = deque(maxlen=2000)
        self.counts = Counter()
        self.result_index = 0
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.origin = QLabel('SZIMULÁCIÓ • hold döntési stub • virtuális idő • memóriabecslés')
        layout.addWidget(self.origin)
        form = QFormLayout()
        layout.addLayout(form)
        self.device = QComboBox()
        self.device.addItems(['Beépített eszközszimulátor', 'TCP eszközszimulátor'])
        form.addRow('Eszköz', self.device)
        self.host = QLineEdit('127.0.0.1')
        form.addRow('TCP host', self.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(8765)
        form.addRow('TCP port', self.port)
        self.mode = QComboBox()
        self.mode.addItems(['Élő megfigyelés', 'Előtöltött terhelésmérés'])
        form.addRow('Üzemmód', self.mode)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(.05, 600)
        self.timeout.setValue(5)
        self.timeout.setSuffix(' s')
        form.addRow('Kérés időtúllépése', self.timeout)
        self.duration = QSpinBox()
        self.duration.setRange(0, 10000)
        self.duration.setValue(3)
        self.duration.setSuffix(' ms')
        form.addRow('Beépített szimulátor virtuális feldolgozási ideje', self.duration)
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('Üresen: 200 élő demoablak / 8 előtöltött demoablak')
        self.browse = QPushButton('Bemenet…')
        self.browse.clicked.connect(self.choose_input)
        input_row.addWidget(self.input)
        input_row.addWidget(self.browse)
        form.addRow('Ablakok JSONL', input_row)
        profile_row = QHBoxLayout()
        self.profiles = []
        for period in (10, 20, 50, 100):
            box = QCheckBox(f'{period} ms')
            box.setChecked(True)
            profile_row.addWidget(box)
            self.profiles.append((period, box))
        form.addRow('Terhelési profilok (T=D)', profile_row)
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)
        controls = QHBoxLayout()
        layout.addLayout(controls)
        self.start_button = QPushButton('Indítás')
        self.stop_button = QPushButton('Leállítás')
        self.export_button = QPushButton('CSV-export…')
        for button in (self.start_button, self.stop_button, self.export_button):
            controls.addWidget(button)
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.export_button.clicked.connect(self.choose_export)
        self.status = QLabel('Készen áll – szimuláció')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.export_status = QLabel('')
        self.export_status.setWordWrap(True)
        layout.addWidget(self.export_status)
        self.totals = QLabel('Még nincs eredmény.')
        layout.addWidget(self.totals)
        self.time_plot = pg.PlotWidget(title='Virtuális MCU-feldolgozás – utolsó 2000 feladat')
        self.time_plot.setLabel('left', 'Feldolgozási idő', units='ms')
        self.time_plot.setLabel('bottom', 'Beérkezett feladat sorszáma (bemelegítéssel)')
        self.time_curve = self.time_plot.plot(pen='#58a6ff', symbol='o', symbolSize=3, connect='finite')
        layout.addWidget(self.time_plot)
        self.memory_plot = pg.PlotWidget(title='Szimulált munkakészlet – nem mért RAM')
        self.memory_plot.setLabel('left', 'Memóriabecslés', units='B')
        self.memory_plot.setLabel('bottom', 'Host eltelt idő', units='s')
        self.memory_curve = self.memory_plot.plot(pen='#3fb950', symbol='o')
        layout.addWidget(self.memory_plot)
        self.config_widgets = [self.device, self.host, self.port, self.mode, self.timeout,
                               self.duration, self.input, self.browse] + [b for _, b in self.profiles]
        self.mode.currentIndexChanged.connect(self.configure)
        self.device.currentIndexChanged.connect(self.configure)
        self.configure()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    @Slot()
    def configure(self):
        busy = self.session is not None and not self.finished
        for widget in self.config_widgets:
            widget.setEnabled(not busy)
        self.host.setEnabled(not busy and self.device.currentIndex() == 1)
        self.port.setEnabled(self.host.isEnabled())
        self.duration.setEnabled(not busy and self.device.currentIndex() == 0)
        for _, box in self.profiles:
            box.setEnabled(not busy and self.mode.currentIndex() == 1)
        self.explanation.setText(
            'Élő: ablakonkénti eredményátvitel, 50 ms hostoldali visszajátszási szünet; nem terhelési benchmark.'
            if self.mode.currentIndex() == 0 else
            'Terhelés: profilonként 100 bemelegítő + 3×1000 ütemezett feladat. '
            'Előtöltött készlet (≤8 ablak), execute alatt nincs kommunikáció; '
            'a grafikon csak a sorozat utáni eredményátvitelnél frissül.')

    @Slot()
    def choose_input(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Ablakok', '', 'JSON Lines (*.jsonl);;Minden fájl (*)')
        if path:
            self.input.setText(path)

    @Slot()
    def start(self):
        profiles = tuple(p for p, box in self.profiles if box.isChecked())
        if self.mode.currentIndex() == 1 and not profiles:
            self.status.setText('Hiba: válassz legalább egy terhelési profilt.')
            return
        self.points.clear()
        self.memory.clear()
        self.counts.clear()
        self.result_index = 0
        self.time_curve.setData([], [])
        self.memory_curve.setData([], [])
        self.totals.setText('Még nincs eredmény.')
        self.export_status.clear()
        self.session = Session(Settings(
            mode=('live', 'benchmark')[self.mode.currentIndex()],
            demo=self.device.currentIndex() == 0, host=self.host.text(), port=self.port.value(),
            timeout=self.timeout.value(), profiles=profiles or (10, 20, 50, 100),
            input_path=self.input.text(), duration_ms=self.duration.value()))
        self.finished = False
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.status.setText('Indítás… SZIMULÁCIÓ')
        self.configure()
        self.session.start()

    @Slot()
    def stop(self):
        if self.session and not self.finished:
            self.session.stop()
            self.stop_button.setEnabled(False)
            self.status.setText('Leállítás folyamatban… a futás részleges marad.')

    def consume(self, row):
        event = row['event']
        if event == 'batch_start':
            self.status.setText(f"SZIMULÁCIÓ • {row['mode']} • {row['batch_id']} • "
                                f"{row['phase']} • T=D={row['period_ms']} ms")
        elif event == 'send' and row['message']['type'] == 'execute':
            self.status.setText(f"SZIMULÁCIÓ • {row['mode']} • feldolgozás; eredményre vár…")
        elif event == 'receive' and 'simulated_memory_bytes' in row['message']:
            self.memory.append((row['host_elapsed_ms'] / 1000,
                                row['message']['simulated_memory_bytes']))
        elif event == 'result':
            self.result_index += 1
            self.points.append((self.result_index, row.get('processing_ms', math.nan)))
            self.counts[(row['phase'], row['status'])] += 1

    def show_totals(self):
        if self.result_index:
            self.totals.setText(' | '.join(
                f'{phase}: ' + ', '.join(f'{status}={self.counts[(phase, status)]}'
                                         for status in ('ok', 'late', 'missed', 'invalid_window'))
                for phase in ('live', 'warmup', 'measured')
                if any(p == phase for p, _ in self.counts)))

    @Slot()
    def poll(self):
        if self.session and not self.finished:
            for _ in range(1000):
                try:
                    self.consume(self.session.events.get_nowait())
                except queue.Empty:
                    break
            if self.points:
                x, y = zip(*self.points)
                self.time_curve.setData(x, y)
            if self.memory:
                x, y = zip(*self.memory)
                self.memory_curve.setData(x, y)
            self.show_totals()
            if self.session.done.is_set() and self.session.events.empty():
                self.finished = True
                # Cancellation can bypass a full notification queue. The archive
                # remains authoritative, including valid results already fetched.
                self.counts = Counter((r['phase'], r['status']) for r in self.session.rows
                                      if r['event'] == 'result')
                self.result_index = sum(self.counts.values())
                self.show_totals()
                terminal = self.session.rows[-1]
                self.status.setText({
                    'run_complete': 'Befejezett szimulált futás.',
                    'run_stopped': 'Leállított, részleges futás.',
                    'run_failed': 'Hibás, részleges futás.'
                }.get(terminal['event'], 'Hiányos futás.') + ' ' + terminal.get('error', ''))
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.export_button.setEnabled(True)
                self.configure()
        try:
            error = self.export_result.get_nowait()
        except queue.Empty:
            pass
        else:
            self.export_status.setText(f'Exporthiba: {error}' if error else 'CSV-export elkészült (szimulált futás).')
            self.start_button.setEnabled(True)
            self.export_button.setEnabled(True)
        if self.closing and (not self.session or self.finished) and (
                self.export_thread is None or not self.export_thread.is_alive()):
            self.close()

    @Slot()
    def choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'CSV-export', 'measurement.csv', 'CSV (*.csv)')
        if path:
            self.export_to(path)

    def export_to(self, path):
        rows = self.session.rows  # Immutable after done; no GUI-thread copy/file IO.
        self.start_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.export_status.setText('CSV-export folyamatban…')
        def write():
            try:
                export_csv(path, rows)
                error = ''
            except Exception as exc:
                error = str(exc)
            self.export_result.put(error)
        self.export_thread = threading.Thread(target=write, daemon=True)
        self.export_thread.start()

    def closeEvent(self, event):
        if (self.session and not self.finished) or (
                self.export_thread and self.export_thread.is_alive()):
            self.closing = True
            self.stop()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
