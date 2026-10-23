import unittest
from test_measurement_ui import HAS_QT
if HAS_QT:
    from PySide6.QtWidgets import QApplication
    from gearshift.gui import Window

@unittest.skipUnless(HAS_QT, 'Install requirements-ui.txt for GUI acceptance tests')
class HardwareGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hardware_selection_and_results_are_labelled_as_measured(self):
        widget = Window()
        try:
            widget.device.setCurrentIndex(2)
            widget.configure()
            self.assertIn('ESP32', widget.origin.text())
            self.assertNotIn('SZIMULÁCIÓ', widget.origin.text())
            self.assertTrue(widget.serial_port.isEnabled())
            widget.consume(dict(event='batch_start', simulated=False, mode='live',
                                batch_id='real', phase='live', period_ms=50))
            self.assertIn('ESP32', widget.status.text())
            widget.consume(dict(event='batch_memory', simulated=False, host_elapsed_ms=100,
                                memory={'after': {'free_heap_bytes': 12345}}))
            self.assertEqual(widget.memory[-1][1], 12345)
            self.assertNotIn('Virtuális', widget.time_plot.plotItem.titleLabel.text)
        finally:
            widget.close()
