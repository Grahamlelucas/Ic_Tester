# ic_tester_app/web_ui/app.py
# Last edited: 2026-04-14
# Purpose: Flask application factory with SocketIO — full feature parity with tkinter GUI
# Dependencies: flask, flask-socketio, flask-cors
# Related: gui/app.py (tkinter equivalent)

"""
Flask Web Application for IC Tester.

This module mirrors every capability of the tkinter ICTesterApp class:
- Arduino connection management with health monitoring
- Chip selection, pin mapping save/load/validate
- Test execution with progress streaming
- Advanced diagnostics (statistical, signal, fingerprint, benchmark, analog)
- Intelligence (knowledge base, session tracker, pattern analyzer, educator)
- ML fault classification
- Counter mode
- Diagnostic report generation
"""

import os
import sys
import json
import time
import threading
from threading import Lock
from typing import Dict, Optional, Any

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..arduino import ArduinoConnection
from ..chips import ChipDatabase, ICTester
from ..chips.migration import PinMigrationHelper
from ..config import Config
from ..logger import get_logger, setup_logging
from ..intelligence import ChipKnowledge, SessionTracker, PatternAnalyzer, ChipEducator
from ..intelligence.ml_classifier import MLFaultClassifier
from ..diagnostics import (
    StatisticalTester, SignalAnalyzer, DiagnosticReportGenerator, ICFingerprinter,
    AnalogAnalyzer,
)
from ..chips.test_generator import TestGenerator
from ..performance import PerformanceBenchmark

logger = get_logger("web_ui")

thread_lock = Lock()


class WebUIState:
    """Shared state between Flask routes and SocketIO events — mirrors ICTesterApp."""

    def __init__(self):
        # Core hardware/test services
        self.arduino = ArduinoConnection()
        self.chip_db = ChipDatabase(board=Config.DEFAULT_BOARD)
        self.tester = ICTester(self.arduino, self.chip_db)

        # Intelligence helpers
        self.knowledge = ChipKnowledge()
        self.session_tracker = SessionTracker()
        self.pattern_analyzer = PatternAnalyzer()
        self.educator = ChipEducator(self.knowledge, self.session_tracker)
        self.migration_helper = PinMigrationHelper(self.chip_db)

        # Diagnostic tools
        self.statistical_tester = StatisticalTester(self.tester)
        self.signal_analyzer = SignalAnalyzer(self.arduino)
        self.report_generator = DiagnosticReportGenerator()
        self.ml_classifier: Optional[MLFaultClassifier] = None
        self.fingerprinter = ICFingerprinter(self.arduino, self.chip_db)
        self.test_generator = TestGenerator()
        self.benchmark = PerformanceBenchmark(self.arduino)
        self.analog_analyzer = AnalogAnalyzer(self.arduino)

        # Runtime state
        self.is_testing = False
        self.counter_running = False
        self.last_result = None
        self.test_start_time = None
        self._current_test_mapping = {}
        self._previous_chip_id = None
        self._previous_chip_mapping = None
        self.connected_clients = set()
        self._last_connect_time = time.time()

    def get_ml_classifier(self) -> Optional[MLFaultClassifier]:
        """Lazy-init ML classifier."""
        if self.ml_classifier is None:
            try:
                self.ml_classifier = MLFaultClassifier()
            except Exception as e:
                logger.warning(f"ML classifier unavailable: {e}")
                return None
        return self.ml_classifier

    def get_status(self) -> Dict[str, Any]:
        """Get current system status for UI."""
        board_type = 'Unknown'
        pin_ranges = None
        if self.arduino.connected and self.arduino.commands:
            board_type = self.arduino.commands.get_board_type()
            try:
                pin_ranges = self.arduino.commands.get_pin_ranges()
            except Exception:
                pass

        return {
            'connected': self.arduino.connected,
            'port': getattr(self.arduino, '_port', None),
            'board_type': board_type,
            'pin_ranges': pin_ranges,
            'is_testing': self.is_testing,
            'counter_running': self.counter_running,
            'chip_count': self.chip_db.get_chip_count(),
        }


state: Optional[WebUIState] = None
socketio: Optional[SocketIO] = None


def create_app():
    """Create and configure Flask application."""
    global state, socketio

    setup_logging()
    logger.info("Creating Flask Web UI application")

    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')
    app.config['SECRET_KEY'] = 'ic-tester-secret-key'

    CORS(app)

    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

    state = WebUIState()
    Config.ensure_directories()

    register_routes(app)
    register_socketio_events(socketio)

    logger.info("Flask Web UI application created successfully")
    return app


# =========================================================================
# REST Routes
# =========================================================================

def register_routes(app: Flask):
    """Register Flask REST routes."""

    @app.route('/')
    def index():
        return render_template('index.html',
                               app_name=Config.APP_NAME,
                               app_version=Config.APP_VERSION,
                               app_subtitle=Config.APP_SUBTITLE)

    @app.route('/api/ports')
    def get_ports():
        ports = state.arduino.find_arduino_ports()
        return jsonify({'ports': ports, 'count': len(ports)})

    @app.route('/api/chips')
    def get_chips():
        chips = state.chip_db.get_all_chip_ids()
        chip_info = []
        for chip_id in sorted(chips):
            chip = state.chip_db.get_chip(chip_id)
            if chip:
                pinout = chip.get('pinout', {})
                input_names = [p['name'] for p in pinout.get('inputs', [])]
                is_counter = any(n in input_names for n in ['CKA', 'CKB', 'CLK', 'CLOCK'])
                chip_info.append({
                    'id': chip_id,
                    'name': chip.get('name', chip_id),
                    'description': chip.get('description', ''),
                    'package': chip.get('package', '14-pin DIP'),
                    'is_counter': is_counter,
                })
        return jsonify({'chips': chip_info, 'count': len(chip_info)})

    @app.route('/api/chip/<chip_id>')
    def get_chip_details(chip_id: str):
        chip = state.chip_db.get_chip(chip_id)
        if not chip:
            return jsonify({'error': 'Chip not found'}), 404
        return jsonify(chip)

    @app.route('/api/status')
    def get_status():
        return jsonify(state.get_status())

    @app.route('/api/board/info')
    def get_board_info():
        if not state.arduino.connected:
            return jsonify({'error': 'Not connected'}), 400
        try:
            commands = state.arduino.commands
            return jsonify({
                'board_type': commands.get_board_type(),
                'firmware_version': commands.get_firmware_version(),
                'pin_ranges': commands.get_pin_ranges(),
            })
        except Exception as e:
            logger.error(f"Error getting board info: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/pin_mapping/<chip_id>', methods=['GET'])
    def load_pin_mapping(chip_id: str):
        """Load saved pin mapping for a chip."""
        filename = Config.PIN_MAPPINGS_DIR / f"{chip_id}_mapping.json"
        if not filename.exists():
            return jsonify({'found': False})
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            return jsonify({'found': True, 'data': data})
        except Exception as e:
            return jsonify({'found': False, 'error': str(e)})

    @app.route('/api/pin_mapping/<chip_id>', methods=['POST'])
    def save_pin_mapping(chip_id: str):
        """Save pin mapping for a chip."""
        mapping_data = request.get_json()
        if not mapping_data:
            return jsonify({'error': 'No data provided'}), 400
        Config.PIN_MAPPINGS_DIR.mkdir(exist_ok=True)
        filename = Config.PIN_MAPPINGS_DIR / f"{chip_id}_mapping.json"
        try:
            with open(filename, 'w') as f:
                json.dump({'chipId': chip_id, 'mappings': mapping_data}, f, indent=2)
            return jsonify({'success': True, 'filename': filename.name})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/session_stats/<chip_id>')
    def get_session_stats(chip_id: str):
        """Get historical session stats for a chip."""
        stats = state.session_tracker.get_chip_stats(chip_id)
        rate = state.session_tracker.get_success_rate(chip_id)
        improving = state.session_tracker.is_improving(chip_id)
        return jsonify({
            'total_tests': stats.total_tests if stats else 0,
            'successful_tests': stats.successful_tests if stats else 0,
            'success_rate': rate,
            'improving': improving,
        })

    @app.route('/api/education/hints/<chip_id>')
    def get_education_hints(chip_id: str):
        """Get educational pre-test hints."""
        hints = state.educator.get_pre_test_hints(chip_id)
        return jsonify({'hints': [{'title': h.title, 'content': h.content} for h in hints[:3]]})

    @app.route('/api/migration', methods=['POST'])
    def get_migration_plan():
        """Get pin migration suggestions when switching chips."""
        data = request.get_json()
        from_chip = data.get('from_chip')
        to_chip = data.get('to_chip')
        old_mapping = data.get('old_mapping', {})
        if not from_chip or not to_chip:
            return jsonify({'error': 'Missing from_chip or to_chip'}), 400
        plan = state.migration_helper.analyze_migration(from_chip, to_chip, old_mapping)
        suggested = state.migration_helper.get_new_mapping_suggestion(from_chip, to_chip, old_mapping)
        return jsonify({
            'suggestions': plan.suggestions,
            'keep_pins': plan.keep_pins,
            'move_pins': plan.move_pins,
            'suggested_mapping': suggested or {},
        })


# =========================================================================
# Background Test Runner
# =========================================================================

def _run_test_background(sio, sid, chip_id, pin_mapping, board):
    """Run the test in a background thread so abort events can be processed."""
    def _send(event, data):
        sio.emit(event, data, to=sid)

    state.test_start_time = time.time()
    state._current_test_mapping = pin_mapping
    logger.info(f"Starting test for chip {chip_id} (background thread)")

    _send('test_started', {'chip_id': chip_id})
    _send('log', {'message': '', 'level': 'info'})
    _send('log', {'message': '═' * 50, 'level': 'header'})
    _send('log', {'message': f'  TESTING: {chip_id}', 'level': 'header'})
    _send('log', {'message': '═' * 50, 'level': 'header'})

    # Pre-test educational hints
    hints = state.educator.get_pre_test_hints(chip_id)
    for hint in hints[:2]:
        _send('log', {'message': f'💡 {hint.title}: {hint.content}', 'level': 'info'})

    def progress_callback(msg):
        _send('log', {'message': msg, 'level': 'info'})

    try:
        results = state.tester.run_test(
            chip_id,
            progress_callback=progress_callback,
            custom_mapping=pin_mapping if pin_mapping else None,
            board=board,
        )
        state.last_result = results

        # Calculate duration
        duration = time.time() - state.test_start_time if state.test_start_time else 0

        # Record session
        state.session_tracker.record_test(
            chip_id=chip_id,
            results=results,
            pin_mapping=pin_mapping,
            duration=duration,
        )

        # Confidence
        historical_rate = state.session_tracker.get_success_rate(chip_id)
        confidence = state.pattern_analyzer.calculate_confidence(
            chip_id, results, historical_rate
        )

        # Log test results summary
        passed = results.get('testsPassed', 0)
        failed = results.get('testsFailed', 0)
        total = results.get('testsRun', 0)

        _send('log', {'message': '', 'level': 'info'})
        _send('log', {'message': '─' * 50, 'level': 'header'})
        _send('log', {'message': 'TEST RESULTS', 'level': 'header'})
        _send('log', {'message': '─' * 50, 'level': 'header'})
        _send('log', {'message': f'Chip: {results.get("chipName", "Unknown")} ({chip_id})', 'level': 'info'})
        _send('log', {'message': f'Tests Run: {total}', 'level': 'info'})
        _send('log', {'message': f'Passed: {passed}', 'level': 'success'})
        _send('log', {'message': f'Failed: {failed}', 'level': 'error' if failed > 0 else 'info'})

        if results.get('success'):
            _send('log', {'message': '\n🎉 CHIP PASSED ALL TESTS! ✅', 'level': 'success'})
        else:
            _send('log', {'message': '\n❌ CHIP FAILED - See details above', 'level': 'error'})

        _send('log', {'message': '═' * 50, 'level': 'header'})

        # Post-test education
        explanation = state.educator.get_post_test_explanation(chip_id, results)
        _send('log', {'message': explanation.get("summary", ""), 'level': 'success' if results.get('success') else 'error'})
        if explanation.get("celebration"):
            _send('log', {'message': explanation["celebration"], 'level': 'success'})
        for point in explanation.get("learning_points", [])[:3]:
            _send('log', {'message': f'   📚 {point}', 'level': 'info'})

        _send('log', {'message': f'\n🎯 Confidence: {confidence.overall:.0%}', 'level': 'info'})
        for factor in confidence.factors[:2]:
            _send('log', {'message': f'   • {factor}', 'level': 'info'})

        # Pin diagnostics summary
        _emit_pin_diagnostics(results, _send)

        # Generate diagnostic report
        mistakes = []
        if not results.get('success'):
            mistakes = state.pattern_analyzer.analyze_failure(
                chip_id, results, pin_mapping
            )

        diag_report = state.report_generator.generate_report(
            test_result=results,
            pattern_mistakes=mistakes,
            confidence_score=confidence,
        )

        # ML fault classification
        ml_predictions = {}
        ml_cls = state.get_ml_classifier()
        if ml_cls is not None:
            ml_predictions = ml_cls.classify_test_result(results)
            ml_cls.auto_label_and_train(results)

        # Save report
        try:
            state.report_generator.save_report(diag_report)
        except Exception as e:
            logger.debug(f"Failed to save diagnostic report: {e}")

        # Intelligent analysis on failure
        analysis = {}
        if not results.get('success'):
            if mistakes:
                _send('log', {'message': '\n🧠 Intelligent Analysis:', 'level': 'info'})
                for m in mistakes[:3]:
                    _send('log', {'message': f'   Possible: {m.description} ({m.confidence:.0%} likely)', 'level': 'warning'})
                fixes = state.pattern_analyzer.get_fix_priority(mistakes)
                if fixes:
                    _send('log', {'message': '\n🔧 Suggested Fixes (try in order):', 'level': 'info'})
                    for i, fix in enumerate(fixes[:3], 1):
                        _send('log', {'message': f'   {i}. {fix}', 'level': 'info'})
                analysis = {
                    'mistakes': [{'description': m.description, 'confidence': m.confidence} for m in mistakes[:5]],
                    'fixes': fixes[:5] if fixes else [],
                }

            # Historical context
            stats = state.session_tracker.get_chip_stats(chip_id)
            if stats and stats.total_tests > 1:
                rate = stats.successful_tests / stats.total_tests
                _send('log', {'message': f'\n📊 Your history with {chip_id}: {rate:.0%} success ({stats.total_tests} tests)', 'level': 'info'})
                if state.session_tracker.is_improving(chip_id):
                    _send('log', {'message': '   📈 You\'re improving with this chip!', 'level': 'success'})

        # Build serializable report dict for dashboard
        report_data = _serialize_diagnostic_report(diag_report)

        _send('test_complete', {
            'chip_id': chip_id,
            'success': results.get('success', False),
            'results': results,
            'confidence': confidence.overall,
            'confidence_factors': confidence.factors[:4],
            'report': report_data,
            'ml_predictions': {k: {'fault': v.predicted_fault, 'confidence': v.confidence}
                               for k, v in ml_predictions.items()} if ml_predictions else {},
            'analysis': analysis,
            'duration': duration,
        })

    except Exception as e:
        logger.error(f"Test error: {e}")
        _send('test_error', {'error': str(e)})
        _send('log', {'message': f'\n❌ Test error: {e}', 'level': 'error'})
    finally:
        with thread_lock:
            state.is_testing = False
        _send('test_finished', {})


# =========================================================================
# SocketIO Events
# =========================================================================

def register_socketio_events(sio: SocketIO):
    """Register SocketIO event handlers."""

    @sio.on('connect')
    def handle_connect():
        client_id = request.sid
        with thread_lock:
            state.connected_clients.add(client_id)
        logger.info(f"Client connected: {client_id}")
        emit('status', state.get_status())

    @sio.on('disconnect')
    def handle_disconnect():
        client_id = request.sid
        with thread_lock:
            state.connected_clients.discard(client_id)
        logger.info(f"Client disconnected: {client_id}")

    @sio.on('scan_ports')
    def handle_scan_ports():
        logger.info("Scanning for ports")
        emit('log', {'message': '🔍 Scanning for Arduino devices...', 'level': 'info'})
        try:
            ports = state.arduino.find_arduino_ports()
            emit('ports_found', {'ports': ports, 'count': len(ports)})
            if ports:
                emit('log', {'message': f'✅ Found {len(ports)} device(s): {", ".join(ports)}', 'level': 'success'})
            else:
                emit('log', {'message': '⚠️ No Arduino devices found. Check USB connection.', 'level': 'warning'})
        except Exception as e:
            logger.error(f"Scan error: {e}")
            emit('error', {'message': str(e)})

    @sio.on('connect_arduino')
    def handle_connect_arduino(data):
        port = data.get('port')
        if not port:
            emit('error', {'message': 'No port specified'})
            return

        logger.info(f"Connecting to Arduino on {port}")
        emit('log', {'message': f'🔌 Connecting to {port}...', 'level': 'info'})

        try:
            state._last_connect_time = time.time()
            success = state.arduino.connect(port)
            if success:
                board_type = state.arduino.commands.get_board_type()
                pin_ranges = state.arduino.commands.get_pin_ranges()
                d_count = pin_ranges['digital'][1] - pin_ranges['digital'][0] + 1
                a_count = pin_ranges['analog'][1] - pin_ranges['analog'][0] + 1

                emit('connected', {
                    'success': True,
                    'port': port,
                    'board_type': board_type,
                    'pin_ranges': pin_ranges,
                    'd_count': d_count,
                    'a_count': a_count,
                })
                emit('log', {'message': f'✅ Arduino connected successfully! Board: {board_type}', 'level': 'success'})
            else:
                emit('connected', {'success': False, 'error': 'Connection failed'})
                emit('log', {'message': '❌ Failed to connect to Arduino', 'level': 'error'})
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            emit('connected', {'success': False, 'error': str(e)})
            emit('log', {'message': f'Error: {e}', 'level': 'error'})

    @sio.on('disconnect_arduino')
    def handle_disconnect_arduino():
        logger.info("Disconnecting from Arduino")
        try:
            state.arduino.disconnect()
            emit('disconnected', {'success': True})
            emit('log', {'message': '🔌 Disconnected from Arduino', 'level': 'info'})
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
            emit('error', {'message': str(e)})

    @sio.on('request_status')
    def handle_request_status():
        emit('status', state.get_status())

    # ------------------------------------------------------------------
    # Test Execution
    # ------------------------------------------------------------------

    @sio.on('run_test')
    def handle_run_test(data):
        chip_id = data.get('chip_id')
        pin_mapping = data.get('pin_mapping', {})
        board = data.get('board', state.chip_db.get_board())
        sid = request.sid

        if not chip_id:
            emit('error', {'message': 'No chip selected'})
            return
        if not state.arduino.connected:
            emit('error', {'message': 'Arduino not connected'})
            return

        with thread_lock:
            if state.is_testing:
                emit('error', {'message': 'Test already in progress'})
                return
            state.is_testing = True

        # Run the actual test in a background thread so the SocketIO event
        # loop stays free to process abort_test and other events.
        sio.start_background_task(_run_test_background, sio, sid, chip_id, pin_mapping, board)

    @sio.on('abort_test')
    def handle_abort_test():
        """Abort a running test."""
        if state.is_testing:
            state.tester.abort()
            emit('log', {'message': '⏹ Aborting test...', 'level': 'warning'})

    # ------------------------------------------------------------------
    # Advanced Diagnostics
    # ------------------------------------------------------------------

    @sio.on('run_statistical')
    def handle_statistical(data):
        chip_id = data.get('chip_id')
        pin_mapping = data.get('pin_mapping', {})
        if not _validate_diag_prereqs(chip_id):
            return
        with thread_lock:
            state.is_testing = True
        emit('test_started', {'chip_id': chip_id})
        emit('log', {'message': f'📊 Starting statistical test for {chip_id}...', 'level': 'header'})

        def progress(msg):
            emit('log', {'message': msg, 'level': 'info'})

        try:
            result = state.statistical_tester.run_statistical_test(
                chip_id, num_runs=5,
                progress_callback=progress,
                custom_mapping=pin_mapping if pin_mapping else None,
                board=state.chip_db.get_board(),
            )
            emit('diagnostic_complete', {
                'type': 'statistical',
                'pass_rate': result.overall_pass_rate,
            })
            emit('log', {'message': f'📊 Statistical test done. Pass rate: {result.overall_pass_rate:.0%}', 'level': 'success' if result.overall_pass_rate >= 0.9 else 'warning'})
        except Exception as e:
            emit('test_error', {'error': str(e)})
            emit('log', {'message': f'❌ Statistical test error: {e}', 'level': 'error'})
        finally:
            with thread_lock:
                state.is_testing = False
            emit('test_finished')

    @sio.on('run_signals')
    def handle_signals(data):
        chip_id = data.get('chip_id')
        if not _validate_diag_prereqs(chip_id):
            return
        chip_data = state.chip_db.get_chip(chip_id, board=state.chip_db.get_board())
        if not chip_data:
            emit('error', {'message': f'Chip {chip_id} not found'})
            return
        with thread_lock:
            state.is_testing = True
        emit('test_started', {'chip_id': chip_id})
        emit('log', {'message': f'📡 Starting signal analysis for {chip_id}...', 'level': 'header'})

        def progress(msg):
            emit('log', {'message': msg, 'level': 'info'})

        try:
            report = state.signal_analyzer.analyze_chip_signals(chip_data, progress_callback=progress)
            if report.overall_stability >= 0.95:
                emit('log', {'message': '✅ All signals stable', 'level': 'success'})
            elif report.flickering_pins:
                emit('log', {'message': f'⚠️ {len(report.flickering_pins)} flickering pin(s) detected', 'level': 'warning'})
            emit('diagnostic_complete', {'type': 'signals', 'stability': report.overall_stability})
        except Exception as e:
            emit('test_error', {'error': str(e)})
            emit('log', {'message': f'❌ Signal analysis error: {e}', 'level': 'error'})
        finally:
            with thread_lock:
                state.is_testing = False
            emit('test_finished')

    @sio.on('run_fingerprint')
    def handle_fingerprint(data):
        chip_id = data.get('chip_id')
        if not _validate_diag_prereqs(chip_id):
            return
        chip_data = state.chip_db.get_chip(chip_id, board=state.chip_db.get_board())
        if not chip_data:
            emit('error', {'message': f'Chip {chip_id} not found'})
            return
        with thread_lock:
            state.is_testing = True
        emit('test_started', {'chip_id': chip_id})
        emit('log', {'message': f'🔍 Starting IC fingerprinting for {chip_id}...', 'level': 'header'})

        def progress(msg):
            emit('log', {'message': msg, 'level': 'info'})

        try:
            fp = state.fingerprinter.fingerprint_chip(chip_data, progress_callback=progress)
            result = {}
            if fp.best_match_chip:
                conf = fp.best_match_confidence
                result = {'match': fp.best_match_chip, 'confidence': conf}
                if conf >= 0.8:
                    emit('log', {'message': f'✅ Identified: {fp.best_match_chip} ({conf:.0%})', 'level': 'success'})
                elif conf >= 0.5:
                    emit('log', {'message': f'⚠️ Maybe: {fp.best_match_chip}? ({conf:.0%})', 'level': 'warning'})
                else:
                    emit('log', {'message': f'❌ No confident match', 'level': 'error'})
            emit('diagnostic_complete', {'type': 'fingerprint', **result})
        except Exception as e:
            emit('test_error', {'error': str(e)})
            emit('log', {'message': f'❌ Fingerprint error: {e}', 'level': 'error'})
        finally:
            with thread_lock:
                state.is_testing = False
            emit('test_finished')

    @sio.on('run_benchmark')
    def handle_benchmark(data):
        if not state.arduino.connected:
            emit('error', {'message': 'Arduino not connected'})
            return
        with thread_lock:
            if state.is_testing:
                emit('error', {'message': 'Test already in progress'})
                return
            state.is_testing = True
        emit('test_started', {'chip_id': 'benchmark'})
        emit('log', {'message': '⚡ Starting performance benchmark...', 'level': 'header'})

        def progress(msg):
            emit('log', {'message': msg, 'level': 'info'})

        try:
            report = state.benchmark.run_full_benchmark(progress_callback=progress, iterations=30)
            emit('log', {'message': '📋 Benchmark complete', 'level': 'success'})
            emit('diagnostic_complete', {'type': 'benchmark'})
        except Exception as e:
            emit('test_error', {'error': str(e)})
            emit('log', {'message': f'❌ Benchmark error: {e}', 'level': 'error'})
        finally:
            with thread_lock:
                state.is_testing = False
            emit('test_finished')

    @sio.on('run_analog')
    def handle_analog(data):
        chip_id = data.get('chip_id')
        pin_mapping = data.get('pin_mapping', {})
        if not _validate_diag_prereqs(chip_id):
            return
        chip_data = state.chip_db.get_chip(chip_id, board=state.chip_db.get_board())
        if not chip_data:
            emit('error', {'message': f'Chip {chip_id} not found'})
            return

        pinout = chip_data.get("pinout", {})
        analog_pin_map = {}
        for section in ['outputs', 'inputs']:
            for p in pinout.get(section, []):
                pin_name = p["name"]
                chip_pin = str(p["pin"])
                ard_pin = pin_mapping.get(chip_pin)
                if ard_pin is not None:
                    try:
                        ard_int = int(ard_pin)
                        if 54 <= ard_int <= 69:
                            analog_pin_map[pin_name] = ard_int
                    except (ValueError, TypeError):
                        pass

        if not analog_pin_map:
            guide = AnalogAnalyzer.get_analog_pin_guide()
            emit('log', {'message': guide, 'level': 'info'})
            emit('log', {'message': 'ℹ️ No pins mapped to analog range (A0-A15 = pins 54-69).', 'level': 'warning'})
            return

        with thread_lock:
            state.is_testing = True
        emit('test_started', {'chip_id': chip_id})
        emit('log', {'message': f'🔬 Starting analog analysis with {len(analog_pin_map)} pin(s)...', 'level': 'header'})
        for name, apin in analog_pin_map.items():
            emit('log', {'message': f'   {name} → A{apin - 54} (pin {apin})', 'level': 'info'})

        def progress(msg):
            emit('log', {'message': msg, 'level': 'info'})

        try:
            report = state.analog_analyzer.analyze_chip_analog(
                chip_data, analog_pin_map=analog_pin_map, progress_callback=progress,
            )
            health = report.overall_voltage_health
            if health == "ok":
                emit('log', {'message': '✅ Voltages OK', 'level': 'success'})
            elif health == "warning":
                issues = len(report.marginal_pins) + len(report.noisy_pins)
                emit('log', {'message': f'⚠️ {issues} voltage warning(s)', 'level': 'warning'})
            else:
                issues = len(report.floating_pins)
                emit('log', {'message': f'❌ {issues} voltage error(s)', 'level': 'error'})
            emit('diagnostic_complete', {'type': 'analog', 'health': health})
        except Exception as e:
            emit('test_error', {'error': str(e)})
            emit('log', {'message': f'❌ Analog analysis error: {e}', 'level': 'error'})
        finally:
            with thread_lock:
                state.is_testing = False
            emit('test_finished')

    # ------------------------------------------------------------------
    # Counter Mode
    # ------------------------------------------------------------------

    @sio.on('start_counter')
    def handle_start_counter(data):
        if not state.arduino.connected:
            emit('error', {'message': 'Connect to Arduino first'})
            return
        if state.counter_running:
            return
        state.counter_running = True
        emit('log', {'message': '⏱ Starting continuous counter mode...', 'level': 'info'})

    @sio.on('stop_counter')
    def handle_stop_counter():
        if state.counter_running:
            state.counter_running = False
            emit('log', {'message': '⏱ Counter stopped.', 'level': 'info'})
        if state.is_testing:
            state.tester.abort()
            emit('log', {'message': '⏹ Aborting test...', 'level': 'warning'})

    # ------------------------------------------------------------------
    # Manual Pin Control
    # ------------------------------------------------------------------

    @sio.on('manual_write_pin')
    def handle_manual_write_pin(data):
        """Write HIGH or LOW to an Arduino pin."""
        arduino_pin = data.get('arduino_pin')
        pin_state = data.get('state', 'LOW').upper()
        if not state.arduino.connected:
            emit('error', {'message': 'Connect to Arduino first'})
            return
        if state.is_testing:
            emit('error', {'message': 'Cannot control pins during a test'})
            return
        try:
            arduino_pin = int(arduino_pin)
            commands = state.arduino.commands
            mode_ok = commands.set_pin_output(arduino_pin)
            write_ok = commands.write_pin(arduino_pin, pin_state)
            logger.info(f"Manual write: pin {arduino_pin} → {pin_state} (mode={mode_ok}, write={write_ok})")
            emit('pin_state_changed', {
                'arduino_pin': arduino_pin,
                'state': pin_state,
                'success': mode_ok and write_ok,
            })
            if not (mode_ok and write_ok):
                emit('log', {'message': f'⚠️ Pin {arduino_pin} write may have failed (mode={mode_ok}, write={write_ok})', 'level': 'warning'})
        except Exception as e:
            logger.error(f"Manual write error: {e}")
            emit('pin_state_changed', {
                'arduino_pin': arduino_pin,
                'state': pin_state,
                'success': False,
                'error': str(e),
            })

    @sio.on('manual_read_pin')
    def handle_manual_read_pin(data):
        """Read state from an Arduino pin."""
        arduino_pin = data.get('arduino_pin')
        if not state.arduino.connected:
            emit('error', {'message': 'Connect to Arduino first'})
            return
        try:
            arduino_pin = int(arduino_pin)
            commands = state.arduino.commands
            commands.set_pin_input(arduino_pin)
            result = commands.read_pin(arduino_pin)
            emit('pin_read_result', {
                'arduino_pin': arduino_pin,
                'state': result if result in ('HIGH', 'LOW') else 'ERROR',
                'success': True,
            })
        except Exception as e:
            logger.error(f"Manual read error: {e}")
            emit('pin_read_result', {
                'arduino_pin': arduino_pin,
                'state': 'ERROR',
                'success': False,
                'error': str(e),
            })

    @sio.on('manual_reset_all')
    def handle_manual_reset_all(data):
        """Reset all mapped input pins to LOW in one batch command."""
        pin_mapping = data.get('pin_mapping', {})
        chip_id = data.get('chip_id')
        if not state.arduino.connected:
            emit('error', {'message': 'Connect to Arduino first'})
            return
        chip = state.chip_db.get_chip(chip_id) if chip_id else None
        if not chip:
            emit('error', {'message': 'No chip selected'})
            return
        # Collect all mapped input Arduino pins
        pin_states = {}
        for p in chip.get('pinout', {}).get('inputs', []):
            ard = pin_mapping.get(str(p['pin']))
            if ard is not None:
                pin_states[int(ard)] = 'LOW'
        if not pin_states:
            emit('manual_reset_done', {'success': True})
            return
        commands = state.arduino.commands
        ok = commands.batch_set_pins(pin_states)
        if not ok:
            # Fallback: set individually
            for pin, st in pin_states.items():
                commands.write_pin(pin, st)
        logger.info(f"Manual reset: {len(pin_states)} pins → LOW (batch={ok})")
        emit('manual_reset_done', {'success': True})

    @sio.on('counter_clock_to')
    def handle_counter_clock_to(data):
        """Clock a 7490-style decade counter to a target value (0-9).
        
        Resets to 0 first via R0_1+R0_2, then fires CKA pulses (and CKB where
        needed, simulating the QA→CKB external connection) until the counter
        reaches the requested decimal value.
        """
        import time as _time
        pin_mapping = data.get('pin_mapping', {})
        chip_id     = data.get('chip_id')
        target      = data.get('target', 0)

        if not state.arduino.connected:
            emit('counter_clock_done', {'success': False, 'target': target, 'error': 'Not connected'})
            return

        chip = state.chip_db.get_chip(chip_id) if chip_id else None
        if not chip:
            emit('counter_clock_done', {'success': False, 'target': target, 'error': 'No chip selected'})
            return

        io = pin_mapping
        # Resolve named pins to Arduino pin numbers
        def ard(chip_pin_str):
            v = io.get(str(chip_pin_str))
            return int(v) if v and str(v).isdigit() else None

        # 7490 pin numbers from JSON
        R0_1 = ard(2);  R0_2 = ard(3)
        CKA  = ard(14); CKB  = ard(1)

        if None in (R0_1, R0_2, CKA, CKB):
            emit('counter_clock_done', {'success': False, 'target': target,
                 'error': 'Missing CKA/CKB/R0 in pin mapping'})
            return

        cmd = state.arduino.commands

        def pulse(pin):
            cmd.write_pin(pin, 'HIGH')
            _time.sleep(0.02)
            cmd.write_pin(pin, 'LOW')
            _time.sleep(0.02)

        # Step 1 — reset counter to 0
        cmd.write_pin(R0_1, 'HIGH')
        cmd.write_pin(R0_2, 'HIGH')
        _time.sleep(0.05)
        cmd.write_pin(R0_1, 'LOW')
        cmd.write_pin(R0_2, 'LOW')
        _time.sleep(0.05)

        if target == 0:
            emit('counter_clock_done', {'success': True, 'target': target})
            return

        # Step 2 — clock up to target using the same CKA+CKB pattern as tests
        # Each BCD count step:
        #   odd  counts (1,3,5,7,9): pulse CKA only
        #   even counts (2,4,6,8)  : pulse CKA then CKB (simulates QA→CKB wire)
        for count in range(1, target + 1):
            pulse(CKA)
            if count % 2 == 0:      # QA just fell — clock the divide-by-5 section
                pulse(CKB)
            _time.sleep(0.01)

        logger.info(f"Counter clocked to {target}")
        emit('counter_clock_done', {'success': True, 'target': target})

    @sio.on('manual_read_all_outputs')
    def handle_manual_read_all_outputs(data):
        """Read all output pins for the current chip and return their states."""
        pin_mapping = data.get('pin_mapping', {})
        chip_id = data.get('chip_id')
        if not state.arduino.connected:
            emit('error', {'message': 'Connect to Arduino first'})
            return
        chip = state.chip_db.get_chip(chip_id) if chip_id else None
        output_pins = []
        if chip:
            for p in chip.get('pinout', {}).get('outputs', []):
                ard = pin_mapping.get(str(p['pin']))
                if ard is not None:
                    output_pins.append({'chip_pin': p['pin'], 'name': p['name'], 'arduino_pin': int(ard)})
        results = {}
        commands = state.arduino.commands
        for op in output_pins:
            try:
                commands.set_pin_input(op['arduino_pin'])
                val = commands.read_pin(op['arduino_pin'])
                results[str(op['chip_pin'])] = {
                    'name': op['name'],
                    'arduino_pin': op['arduino_pin'],
                    'state': val if val in ('HIGH', 'LOW') else 'ERROR',
                }
            except Exception:
                results[str(op['chip_pin'])] = {
                    'name': op['name'],
                    'arduino_pin': op['arduino_pin'],
                    'state': 'ERROR',
                }
        emit('all_outputs_read', {'results': results})


# =========================================================================
# Helper Functions
# =========================================================================

def _validate_diag_prereqs(chip_id: str) -> bool:
    """Check common preconditions for diagnostic runs."""
    if not state.arduino.connected:
        emit('error', {'message': 'Connect to Arduino first'})
        return False
    if state.is_testing:
        emit('error', {'message': 'Test already in progress'})
        return False
    if not chip_id:
        emit('error', {'message': 'No chip selected'})
        return False
    return True


def _emit_pin_diagnostics(results, _send=None):
    """Stream per-pin diagnostic summary to log (matches tkinter output).

    Args:
        results: Test results dict with pinDiagnostics.
        _send: Callable(event, data) for emitting. Falls back to bare emit().
    """
    if _send is None:
        _send = lambda ev, d: emit(ev, d)

    pin_diag = results.get('pinDiagnostics', {})
    if not pin_diag:
        return

    has_issues = any(
        d.get('timesWrong', 0) > 0 or d.get('timesError', 0) > 0 or d.get('stuckState')
        for d in pin_diag.values()
    )
    if not has_issues and results.get('success'):
        return

    _send('log', {'message': '\n' + '═' * 50, 'level': 'info'})
    _send('log', {'message': '📊 PIN DIAGNOSTIC REPORT', 'level': 'info'})
    _send('log', {'message': '═' * 50, 'level': 'info'})

    for pin_name, diag in pin_diag.items():
        tested = diag.get('timesTested', 0)
        correct = diag.get('timesCorrect', 0)
        wrong = diag.get('timesWrong', 0)
        errors = diag.get('timesError', 0)
        stuck = diag.get('stuckState')
        chip_pin = diag.get('chipPin', '?')
        arduino_pin = diag.get('arduinoPin', '?')

        if tested == 0:
            continue
        pct = (correct / tested * 100) if tested > 0 else 0

        if stuck == 'HIGH':
            icon, status, level = '🔴', f'STUCK HIGH ({correct}/{tested} correct)', 'error'
        elif stuck == 'LOW':
            icon, status, level = '🔵', f'STUCK LOW ({correct}/{tested} correct)', 'error'
        elif stuck == 'NO_RESPONSE':
            icon, status, level = '⚫', f'NO RESPONSE ({errors} errors)', 'error'
        elif stuck == 'INTERMITTENT':
            icon, status, level = '🟡', f'INTERMITTENT ({correct}/{tested} correct)', 'warning'
        elif wrong > 0 or errors > 0:
            icon, status, level = '🟠', f'{correct}/{tested} correct ({pct:.0f}%)', 'warning'
        else:
            icon, status, level = '🟢', f'{correct}/{tested} correct', 'info'

        _send('log', {'message': f'  {icon} {pin_name} (pin {chip_pin} → Ard.{arduino_pin}): {status}', 'level': level})

        if wrong > 0:
            wrongs = diag.get('wrongReadings', [])
            for w in wrongs[:3]:
                _send('log', {'message': f"       Test {w['testId']}: expected {w['expected']}, got {w['actual']}", 'level': 'warning'})
            if len(wrongs) > 3:
                _send('log', {'message': f'       ...and {len(wrongs) - 3} more failures', 'level': 'warning'})

    _send('log', {'message': '═' * 50, 'level': 'info'})


def _serialize_diagnostic_report(report) -> dict:
    """Convert DiagnosticReport to a JSON-safe dict for the dashboard."""
    pin_diag = {}
    for pn, entry in report.pin_diagnostics.items():
        pin_diag[pn] = {
            'chip_pin': entry.chip_pin,
            'arduino_pin': entry.arduino_pin,
            'pass_rate': entry.pass_rate,
            'severity': entry.severity,
            'detail': entry.detail,
            'stability_score': entry.stability_score,
        }
    return {
        'chip_id': report.chip_id,
        'overall_result': report.overall_result,
        'overall_confidence': report.overall_confidence,
        'tests_run': report.tests_run,
        'tests_passed': report.tests_passed,
        'pin_diagnostics': pin_diag,
        'fault_summary': report.fault_summary,
        'recommendations': report.recommendations,
        'avg_propagation_us': report.avg_propagation_us,
        'signal_stability': report.signal_stability,
    }


def run_web_ui(host='127.0.0.1', port=5050, debug=False):
    """Run the web UI server."""
    app = create_app()
    logger.info(f"Starting Web UI on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_web_ui(debug=True)
