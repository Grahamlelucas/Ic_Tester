# ic_tester_app/gui/manual_tester.py
# Purpose: Separate-window manual tester with game mode for known chips and sandbox mode for manual setups

"""
Manual tester add-on window.

This module provides a separate Toplevel workflow that complements the existing
automated tester instead of replacing it:

- Known Chip Game Mode: turn-based prediction game driven by generated truth tables
- Unknown/Manual Lab Mode: turn-based manual input driving with real output reads
"""

import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .theme import Theme, get_fonts
from .widgets import ModernButton
from ..logger import get_logger
from ..arduino.commands import ArduinoCommands
from ..chips.test_generator import TestGenerator, GATE_LOGIC
from ..intelligence.knowledge_base import ChipKnowledge

logger = get_logger("gui.manual_tester")


@dataclass
class KnownChipRound:
    """Single game round generated from a chip truth table."""
    round_number: int
    prompt: str
    explanation: str
    inputs: Dict[str, str]
    expected_outputs: Dict[str, str]
    observed_outputs: Dict[str, str] = field(default_factory=dict)
    predicted_outputs: Dict[str, str] = field(default_factory=dict)
    player_correct: bool = False
    hardware_match: bool = False


@dataclass
class KnownChipGameSession:
    """In-memory state for the known-chip game mode."""
    chip_id: str
    chip_name: str
    board: str
    chip_data: Dict[str, Any]
    pin_mapping: Dict[str, int]
    rounds: List[KnownChipRound]
    output_order: List[str]
    current_round_index: int = 0
    score: int = 0
    streak: int = 0
    lives: int = 3
    history: List[KnownChipRound] = field(default_factory=list)
    completed: bool = False
    status_text: str = "Ready"


@dataclass
class ManualSignalDefinition:
    """Named signal in manual-lab mode."""
    name: str
    arduino_pin: int


@dataclass
class ManualLabTurn:
    """Recorded turn in the manual lab."""
    turn_number: int
    driven_inputs: Dict[str, str]
    observed_outputs: Dict[str, str]
    explanation: str


@dataclass
class ManualLabSession:
    """In-memory state for the manual-lab mode."""
    board: str
    inputs: List[ManualSignalDefinition]
    outputs: List[ManualSignalDefinition]
    current_driven_state: Dict[str, str] = field(default_factory=dict)
    turn_history: List[ManualLabTurn] = field(default_factory=list)


class ManualTesterController:
    """Board-aware controller for manual tester interactions."""

    DEFAULT_LIVES = 3

    def __init__(self, arduino, chip_db, test_generator: TestGenerator, knowledge: ChipKnowledge):
        self.arduino = arduino
        self.chip_db = chip_db
        self.test_generator = test_generator
        self.knowledge = knowledge

    def normalize_board(self, board: str) -> str:
        value = str(board or "MEGA2560").upper()
        if value in ("MEGA", "MEGA2560"):
            return "MEGA2560"
        if value in ("UNO", "UNO_R3"):
            return "UNO_R3"
        return value

    def get_board_type(self, fallback: str = "MEGA2560") -> str:
        if getattr(self.arduino, "commands", None):
            return self.normalize_board(self.arduino.commands.get_board_type())
        return self.normalize_board(fallback)

    def get_pin_ranges(self, board: str) -> Dict[str, Tuple[int, int]]:
        config = ArduinoCommands.BOARD_CONFIGS.get(
            self.normalize_board(board),
            ArduinoCommands.BOARD_CONFIGS["MEGA2560"],
        )
        return {
            "digital": config["digital_pins"],
            "analog": config["analog_pins"],
        }

    def parse_pin_value(self, value: str, board: str) -> Optional[int]:
        text = str(value or "").strip().upper()
        if not text:
            return None
        if text.startswith("A") and text[1:].isdigit():
            analog_index = int(text[1:])
            config = self.get_pin_ranges(board)
            analog_start, analog_end = config["analog"]
            parsed_pin = analog_start + analog_index
            if parsed_pin <= analog_end:
                return parsed_pin
            return None
        if text.isdigit():
            return int(text)
        return None

    def is_valid_pin(self, pin: int, board: str) -> bool:
        config = self.get_pin_ranges(board)
        d_start, d_end = config["digital"]
        a_start, a_end = config["analog"]
        return d_start <= pin <= d_end or a_start <= pin <= a_end

    def evaluate_known_chip_support(
        self, chip_data: Optional[Dict[str, Any]], mapping: Optional[Dict[str, int]]
    ) -> Tuple[bool, str]:
        if chip_data is None:
            return False, "Select a chip in the main window first."
        if not mapping:
            return False, "Validate a pin mapping in the main window before starting game mode."

        suite = self.test_generator.generate_suite_from_chip(chip_data)
        groups = self.test_generator.infer_gate_groups(chip_data)
        if suite is None or not suite.vectors or not groups:
            return False, "Game mode supports standard combinational gates and inverter-style chips only."

        missing_names = []
        pinout = chip_data.get("pinout", {})
        name_to_pin = {
            entry["name"]: entry["pin"]
            for entry in pinout.get("inputs", []) + pinout.get("outputs", [])
        }
        for signal_name, chip_pin in name_to_pin.items():
            if str(chip_pin) not in mapping:
                missing_names.append(signal_name)
        if missing_names:
            return False, f"Missing mapped signals for game mode: {', '.join(missing_names[:4])}"

        return True, f"{suite.gate_function} game supported with {len(suite.vectors)} generated rounds."

    def create_known_game_session(
        self, chip_data: Dict[str, Any], mapping: Dict[str, int], board: str
    ) -> Tuple[Optional[KnownChipGameSession], str]:
        supported, reason = self.evaluate_known_chip_support(chip_data, mapping)
        if not supported:
            return None, reason

        suite = self.test_generator.generate_suite_from_chip(chip_data)
        gate_groups = self.test_generator.infer_gate_groups(chip_data) or []
        logic_function = suite.gate_function
        pinout = chip_data.get("pinout", {})
        all_inputs = [entry["name"] for entry in pinout.get("inputs", [])]
        output_order = [entry["name"] for entry in pinout.get("outputs", [])]
        groups_by_output = {group["output"]: group for group in gate_groups}
        rounds: List[KnownChipRound] = []

        for index, vector in enumerate(suite.vectors, 1):
            active_group = groups_by_output.get(next(iter(vector.expected_outputs.keys())))
            required_inputs = {name: "LOW" for name in all_inputs}
            for name, numeric_value in vector.inputs.items():
                required_inputs[name] = "HIGH" if numeric_value else "LOW"

            expected_outputs: Dict[str, str] = {}
            for group in gate_groups:
                bit_values = [
                    1 if required_inputs[input_name] == "HIGH" else 0
                    for input_name in group["inputs"]
                ]
                logic = GATE_LOGIC[logic_function]
                if len(bit_values) == 1:
                    output_value = logic(bit_values[0])
                else:
                    output_value = logic(bit_values[0], bit_values[1])
                expected_outputs[group["output"]] = "HIGH" if output_value else "LOW"

            prompt_inputs = ", ".join(
                f"{name}={required_inputs[name]}" for name in (active_group["inputs"] if active_group else required_inputs)
            )
            chip_text = self.knowledge.get_plain_english(chip_data.get("chipId", ""))
            explanation = (
                f"{chip_text} For this round, {prompt_inputs}. "
                f"The source-of-truth outputs should be "
                + ", ".join(f"{name}={expected_outputs[name]}" for name in output_order)
                + "."
            )
            rounds.append(KnownChipRound(
                round_number=index,
                prompt=f"Predict the outputs when {prompt_inputs}.",
                explanation=explanation,
                inputs=required_inputs,
                expected_outputs=expected_outputs,
            ))

        session = KnownChipGameSession(
            chip_id=chip_data.get("chipId", "UNKNOWN"),
            chip_name=chip_data.get("name", chip_data.get("chipId", "Unknown Chip")),
            board=self.normalize_board(board),
            chip_data=chip_data,
            pin_mapping={str(key): int(value) for key, value in mapping.items()},
            rounds=rounds,
            output_order=output_order,
            lives=self.DEFAULT_LIVES,
            status_text="Game in progress",
        )
        return session, f"Generated {len(rounds)} rounds for {session.chip_name}."

    def evaluate_known_round(
        self, session: KnownChipGameSession, predictions: Dict[str, str]
    ) -> KnownChipRound:
        round_data = session.rounds[session.current_round_index]
        round_data.predicted_outputs = predictions.copy()

        self._apply_named_states(session.chip_data, session.pin_mapping, round_data.inputs)
        observed_outputs = self._read_named_outputs(
            session.chip_data, session.pin_mapping, session.output_order
        )
        round_data.observed_outputs = observed_outputs
        round_data.player_correct = all(
            predictions.get(name) == round_data.expected_outputs.get(name)
            for name in session.output_order
        )
        round_data.hardware_match = all(
            observed_outputs.get(name) == round_data.expected_outputs.get(name)
            for name in session.output_order
        )

        if round_data.player_correct:
            session.score += 100 + (session.streak * 25)
            session.streak += 1
            session.status_text = "Correct"
        else:
            session.lives -= 1
            session.streak = 0
            session.status_text = "Incorrect"

        session.history.append(round_data)
        if session.lives <= 0:
            session.completed = True
            session.status_text = "Game Over"
        elif session.current_round_index >= len(session.rounds) - 1:
            session.completed = True
            session.status_text = "Victory"

        return round_data

    def advance_known_round(self, session: KnownChipGameSession):
        if session.completed:
            return
        session.current_round_index += 1
        if session.current_round_index >= len(session.rounds):
            session.completed = True
            session.status_text = "Victory"

    def create_manual_lab_session(
        self,
        board: str,
        input_rows: List[Tuple[str, str]],
        output_rows: List[Tuple[str, str]],
    ) -> Tuple[Optional[ManualLabSession], str]:
        normalized_board = self.normalize_board(board)
        parsed_inputs: List[ManualSignalDefinition] = []
        parsed_outputs: List[ManualSignalDefinition] = []
        used_pins: Dict[int, str] = {}
        used_names: set[str] = set()

        def _consume_rows(rows: List[Tuple[str, str]], target: List[ManualSignalDefinition], signal_type: str):
            for name, raw_pin in rows:
                signal_name = str(name or "").strip()
                if not signal_name:
                    return f"Every {signal_type} needs a name."
                if signal_name.lower() in used_names:
                    return f"Duplicate signal name: {signal_name}"
                parsed_pin = self.parse_pin_value(raw_pin, normalized_board)
                if parsed_pin is None or not self.is_valid_pin(parsed_pin, normalized_board):
                    return f"Invalid {signal_type} pin '{raw_pin}' for {normalized_board}"
                if parsed_pin in used_pins:
                    return f"Arduino pin {parsed_pin} is already used by {used_pins[parsed_pin]}"
                used_names.add(signal_name.lower())
                used_pins[parsed_pin] = signal_name
                target.append(ManualSignalDefinition(signal_name, parsed_pin))
            return None

        input_error = _consume_rows(input_rows, parsed_inputs, "input")
        if input_error:
            return None, input_error
        output_error = _consume_rows(output_rows, parsed_outputs, "output")
        if output_error:
            return None, output_error

        if not parsed_inputs or not parsed_outputs:
            return None, "Manual lab mode needs at least one input and one output."

        return ManualLabSession(
            board=normalized_board,
            inputs=parsed_inputs,
            outputs=parsed_outputs,
        ), f"Manual lab ready with {len(parsed_inputs)} inputs and {len(parsed_outputs)} outputs."

    def run_manual_turn(
        self, session: ManualLabSession, driven_inputs: Dict[str, str]
    ) -> ManualLabTurn:
        for signal in session.inputs:
            desired_state = driven_inputs.get(signal.name, "LOW")
            self._set_pin(signal.arduino_pin, desired_state)

        # Allow the driven lines to settle before the reveal phase samples the
        # connected outputs.
        time.sleep(0.03)
        observed_outputs = {
            signal.name: self._read_pin(signal.arduino_pin)
            for signal in session.outputs
        }
        session.current_driven_state = driven_inputs.copy()
        turn_number = len(session.turn_history) + 1
        explanation = (
            "The app drove "
            + ", ".join(f"{name}={state}" for name, state in driven_inputs.items())
            + " and observed "
            + ", ".join(f"{name}={observed_outputs[name]}" for name in observed_outputs)
            + ". Compare the observed outputs with your datasheet or expected behavior."
        )
        turn = ManualLabTurn(
            turn_number=turn_number,
            driven_inputs=driven_inputs.copy(),
            observed_outputs=observed_outputs,
            explanation=explanation,
        )
        session.turn_history.append(turn)
        return turn

    def _apply_named_states(
        self, chip_data: Dict[str, Any], pin_mapping: Dict[str, int], inputs: Dict[str, str]
    ):
        pinout_inputs = {
            entry["name"]: entry["pin"]
            for entry in chip_data.get("pinout", {}).get("inputs", [])
        }
        for signal_name, state in inputs.items():
            chip_pin = pinout_inputs.get(signal_name)
            if chip_pin is None:
                continue
            arduino_pin = pin_mapping.get(str(chip_pin))
            if arduino_pin is None:
                continue
            self._set_pin(arduino_pin, state)
        time.sleep(0.03)

    def _read_named_outputs(
        self, chip_data: Dict[str, Any], pin_mapping: Dict[str, int], outputs: List[str]
    ) -> Dict[str, str]:
        pinout_outputs = {
            entry["name"]: entry["pin"]
            for entry in chip_data.get("pinout", {}).get("outputs", [])
        }
        result: Dict[str, str] = {}
        for signal_name in outputs:
            chip_pin = pinout_outputs.get(signal_name)
            if chip_pin is None:
                continue
            arduino_pin = pin_mapping.get(str(chip_pin))
            if arduino_pin is None:
                continue
            result[signal_name] = self._read_pin(arduino_pin)
        return result

    def _get_commands(self) -> ArduinoCommands:
        commands = getattr(self.arduino, "commands", None)
        if commands is None:
            raise RuntimeError("Arduino command helper is unavailable. Reconnect the board and try again.")
        return commands

    def _set_pin(self, arduino_pin: int, state: str) -> bool:
        desired_state = "HIGH" if str(state).upper() == "HIGH" else "LOW"
        commands = self._get_commands()
        return commands.set_pin_output(arduino_pin) and commands.write_pin(arduino_pin, desired_state)

    def _read_pin(self, arduino_pin: int) -> str:
        commands = self._get_commands()
        reads: List[str] = []
        for _ in range(3):
            if not commands.set_pin_input(arduino_pin):
                reads.append("ERROR")
                continue
            response = commands.read_pin(arduino_pin)
            reads.append(response if response in ("HIGH", "LOW") else "ERROR")

        if reads.count("HIGH") > reads.count("LOW"):
            return "HIGH"
        if reads.count("LOW") > 0:
            return "LOW"
        return "ERROR"


class ManualTesterWindow:
    """Separate-window manual tester add-on."""

    def __init__(
        self,
        parent,
        controller: ManualTesterController,
        get_current_context: Callable[[], Dict[str, Any]],
        is_main_app_busy: Callable[[], bool],
        on_close: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.controller = controller
        self.get_current_context = get_current_context
        self.is_main_app_busy = is_main_app_busy
        self.on_close = on_close
        self.fonts = get_fonts()
        self.known_session: Optional[KnownChipGameSession] = None
        self.lab_session: Optional[ManualLabSession] = None
        self.known_guess_vars: Dict[str, tk.StringVar] = {}
        self.lab_input_rows: List[Dict[str, Any]] = []
        self.lab_output_rows: List[Dict[str, Any]] = []
        self.lab_state_vars: Dict[str, tk.StringVar] = {}
        self._known_round_revealed = False

        self.window = tk.Toplevel(parent)
        self.window.title("IC Tester Pro - Manual Tester")
        self.window.geometry("1180x860")
        self.window.minsize(980, 760)
        self.window.configure(bg=Theme.BG_DARK)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.mode_var = tk.StringVar(value="known")
        self._build_ui()
        self._refresh_connection_summary()
        self._switch_mode()

    def focus(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self):
        try:
            if self.on_close:
                self.on_close()
        finally:
            self.window.destroy()

    def _build_ui(self):
        root = tk.Frame(self.window, bg=Theme.BG_DARK)
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        header = tk.Frame(root, bg=Theme.BG_DARK)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            header,
            text="Manual Tester",
            font=self.fonts["heading"],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text="Add-on mode for turn-based exploration and gameplay",
            font=self.fonts["body"],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_SECONDARY,
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))

        mode_card = tk.Frame(root, bg=Theme.BG_CARD, padx=14, pady=12)
        mode_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            mode_card, text="Mode", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY
        ).pack(anchor=tk.W)

        mode_row = tk.Frame(mode_card, bg=Theme.BG_CARD)
        mode_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Radiobutton(
            mode_row, text="Known Chip Game", variable=self.mode_var,
            value="known", command=self._switch_mode
        ).pack(side=tk.LEFT, padx=(0, 18))
        ttk.Radiobutton(
            mode_row, text="Unknown / Manual Lab", variable=self.mode_var,
            value="lab", command=self._switch_mode
        ).pack(side=tk.LEFT)

        self.summary_card = tk.Frame(root, bg=Theme.BG_CARD, padx=14, pady=12)
        self.summary_card.pack(fill=tk.X, pady=(0, 10))
        self.connection_summary_label = tk.Label(
            self.summary_card,
            text="",
            font=self.fonts["body"],
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY,
            justify=tk.LEFT,
        )
        self.connection_summary_label.pack(anchor=tk.W)

        self.content_frame = tk.Frame(root, bg=Theme.BG_DARK)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(1, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)

        self.known_frame = tk.Frame(self.content_frame, bg=Theme.BG_DARK)
        self.lab_frame = tk.Frame(self.content_frame, bg=Theme.BG_DARK)

        self._build_known_mode()
        self._build_lab_mode()

        bottom = tk.Frame(root, bg=Theme.BG_DARK)
        bottom.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        explanation_card = tk.Frame(bottom, bg=Theme.BG_CARD, padx=12, pady=12)
        explanation_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tk.Label(
            explanation_card, text="Explanation", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY
        ).pack(anchor=tk.W)
        self.explanation_label = tk.Label(
            explanation_card,
            text="Start a game or lab session to see turn-by-turn explanations.",
            font=self.fonts["body"],
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY,
            justify=tk.LEFT,
            wraplength=480,
        )
        self.explanation_label.pack(anchor=tk.W, pady=(8, 0))

        history_card = tk.Frame(bottom, bg=Theme.BG_CARD, padx=12, pady=12)
        history_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        tk.Label(
            history_card, text="Session History", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY
        ).pack(anchor=tk.W)
        self.history_text = scrolledtext.ScrolledText(
            history_card,
            font=self.fonts["small"],
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_PRIMARY,
            relief=tk.FLAT,
            height=10,
            wrap=tk.WORD,
        )
        self.history_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.history_text.configure(state=tk.DISABLED)

    def _build_known_mode(self):
        card = tk.Frame(self.known_frame, bg=Theme.BG_CARD, padx=14, pady=14)
        card.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(card, bg=Theme.BG_CARD)
        top.pack(fill=tk.X)
        tk.Label(
            top, text="Known Chip Game", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY
        ).pack(side=tk.LEFT)
        ModernButton(
            top, "Use Current Selection", self._load_current_known_context,
            width=170, height=32, bg_color=Theme.ACCENT_INFO
        ).pack(side=tk.RIGHT, padx=(10, 0))
        ModernButton(
            top, "Start / Restart", self._start_known_game,
            width=140, height=32, bg_color=Theme.ACCENT_SUCCESS
        ).pack(side=tk.RIGHT)

        self.known_context_label = tk.Label(
            card, text="", font=self.fonts["body"], bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY, justify=tk.LEFT, wraplength=520
        )
        self.known_context_label.pack(anchor=tk.W, pady=(10, 6))

        self.known_status_label = tk.Label(
            card, text="", font=self.fonts["body_bold"], bg=Theme.BG_CARD,
            fg=Theme.ACCENT_WARNING, justify=tk.LEFT, wraplength=520
        )
        self.known_status_label.pack(anchor=tk.W, pady=(0, 10))

        score_row = tk.Frame(card, bg=Theme.BG_CARD)
        score_row.pack(fill=tk.X, pady=(0, 10))
        self.score_label = tk.Label(score_row, text="Score: 0", font=self.fonts["body_bold"],
                                    bg=Theme.BG_CARD, fg=Theme.ACCENT_SUCCESS)
        self.score_label.pack(side=tk.LEFT, padx=(0, 18))
        self.streak_label = tk.Label(score_row, text="Streak: 0", font=self.fonts["body_bold"],
                                     bg=Theme.BG_CARD, fg=Theme.ACCENT_INFO)
        self.streak_label.pack(side=tk.LEFT, padx=(0, 18))
        self.lives_label = tk.Label(score_row, text="Lives: 3", font=self.fonts["body_bold"],
                                    bg=Theme.BG_CARD, fg=Theme.ACCENT_ERROR)
        self.lives_label.pack(side=tk.LEFT, padx=(0, 18))
        self.round_label = tk.Label(score_row, text="Round: -", font=self.fonts["body_bold"],
                                    bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY)
        self.round_label.pack(side=tk.LEFT)

        turn_card = tk.Frame(card, bg=Theme.BG_DARK, padx=12, pady=12)
        turn_card.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            turn_card, text="Current Turn", font=self.fonts["subheading"],
            bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY
        ).pack(anchor=tk.W)
        self.known_prompt_label = tk.Label(
            turn_card, text="Load a supported chip and start the game.",
            font=self.fonts["body"], bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY,
            justify=tk.LEFT, wraplength=520
        )
        self.known_prompt_label.pack(anchor=tk.W, pady=(8, 6))
        self.known_inputs_label = tk.Label(
            turn_card, text="", font=self.fonts["mono"], bg=Theme.BG_DARK,
            fg=Theme.ACCENT_WARNING, justify=tk.LEFT, wraplength=520
        )
        self.known_inputs_label.pack(anchor=tk.W, pady=(0, 10))

        self.known_prediction_frame = tk.Frame(turn_card, bg=Theme.BG_DARK)
        self.known_prediction_frame.pack(fill=tk.X, pady=(0, 10))

        action_row = tk.Frame(turn_card, bg=Theme.BG_DARK)
        action_row.pack(fill=tk.X)
        self.submit_guess_button = ModernButton(
            action_row, "Submit Guess", self._submit_known_guess,
            width=130, height=34, bg_color=Theme.ACCENT_PRIMARY
        )
        self.submit_guess_button.pack(side=tk.LEFT, padx=(0, 10))
        self.next_round_button = ModernButton(
            action_row, "Next Turn", self._next_known_round,
            width=120, height=34, bg_color=Theme.ACCENT_INFO
        )
        self.next_round_button.pack(side=tk.LEFT)

    def _build_lab_mode(self):
        card = tk.Frame(self.lab_frame, bg=Theme.BG_CARD, padx=14, pady=14)
        card.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(card, bg=Theme.BG_CARD)
        top.pack(fill=tk.X)
        tk.Label(
            top, text="Unknown / Manual Lab", font=self.fonts["subheading"],
            bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY
        ).pack(side=tk.LEFT)
        ModernButton(
            top, "Start Lab", self._start_lab_session,
            width=120, height=32, bg_color=Theme.ACCENT_SUCCESS
        ).pack(side=tk.RIGHT)

        self.lab_status_label = tk.Label(
            card,
            text="Define named inputs and outputs, then start a session.",
            font=self.fonts["body"],
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY,
            justify=tk.LEFT,
            wraplength=520,
        )
        self.lab_status_label.pack(anchor=tk.W, pady=(10, 10))

        setup_row = tk.Frame(card, bg=Theme.BG_CARD)
        setup_row.pack(fill=tk.BOTH, expand=True)
        setup_row.grid_columnconfigure(0, weight=1)
        setup_row.grid_columnconfigure(1, weight=1)

        input_card = tk.Frame(setup_row, bg=Theme.BG_DARK, padx=12, pady=12)
        input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(input_card, text="Inputs", font=self.fonts["subheading"],
                 bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY).pack(anchor=tk.W)
        ModernButton(
            input_card, "Add Input", lambda: self._add_lab_row("input"),
            width=100, height=28, bg_color=Theme.ACCENT_INFO
        ).pack(anchor=tk.W, pady=(8, 8))
        self.lab_inputs_rows_frame = tk.Frame(input_card, bg=Theme.BG_DARK)
        self.lab_inputs_rows_frame.pack(fill=tk.BOTH, expand=True)

        output_card = tk.Frame(setup_row, bg=Theme.BG_DARK, padx=12, pady=12)
        output_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(output_card, text="Outputs", font=self.fonts["subheading"],
                 bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY).pack(anchor=tk.W)
        ModernButton(
            output_card, "Add Output", lambda: self._add_lab_row("output"),
            width=110, height=28, bg_color=Theme.ACCENT_INFO
        ).pack(anchor=tk.W, pady=(8, 8))
        self.lab_outputs_rows_frame = tk.Frame(output_card, bg=Theme.BG_DARK)
        self.lab_outputs_rows_frame.pack(fill=tk.BOTH, expand=True)

        controls_card = tk.Frame(card, bg=Theme.BG_DARK, padx=12, pady=12)
        controls_card.pack(fill=tk.X, pady=(10, 0))
        tk.Label(
            controls_card, text="Turn Controls", font=self.fonts["subheading"],
            bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY
        ).pack(anchor=tk.W)
        self.lab_turn_controls_frame = tk.Frame(controls_card, bg=Theme.BG_DARK)
        self.lab_turn_controls_frame.pack(fill=tk.X, pady=(8, 6))
        self.lab_run_button = ModernButton(
            controls_card, "Drive & Reveal", self._run_lab_turn,
            width=130, height=34, bg_color=Theme.ACCENT_PRIMARY
        )
        self.lab_run_button.pack(anchor=tk.W)
        self.lab_snapshot_label = tk.Label(
            controls_card, text="No lab turn run yet.", font=self.fonts["body"],
            bg=Theme.BG_DARK, fg=Theme.TEXT_SECONDARY, justify=tk.LEFT, wraplength=520
        )
        self.lab_snapshot_label.pack(anchor=tk.W, pady=(10, 0))

        self._add_lab_row("input", name="IN1", pin="2")
        self._add_lab_row("output", name="OUT1", pin="3")

    def _switch_mode(self):
        self.known_frame.grid_forget()
        self.lab_frame.grid_forget()
        if self.mode_var.get() == "known":
            self.known_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self._load_current_known_context()
        else:
            self.lab_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self._refresh_connection_summary()

    def _refresh_connection_summary(self):
        context = self.get_current_context()
        board = self.controller.get_board_type(context.get("board", "MEGA"))
        ranges = self.controller.get_pin_ranges(board)
        connected = "Connected" if context.get("connected") else "Not connected"
        self.connection_summary_label.config(
            text=(
                f"Arduino: {connected}\n"
                f"Board: {board.replace('_', ' ')} | "
                f"Digital pins {ranges['digital'][0]}-{ranges['digital'][1]}, "
                f"Analog pins {ranges['analog'][0]}-{ranges['analog'][1]}"
            )
        )

    def _load_current_known_context(self):
        context = self.get_current_context()
        self._refresh_connection_summary()
        chip_id = context.get("chip_id") or "No chip selected"
        chip_data = context.get("chip_data")
        mapping = context.get("mapping")
        board = self.controller.get_board_type(context.get("board", "MEGA"))
        reason = self.controller.evaluate_known_chip_support(chip_data, mapping)[1]
        self.known_context_label.config(
            text=(
                f"Current chip: {chip_id}\n"
                f"Board profile: {board.replace('_', ' ')}\n"
                f"Mapping status: {'Validated' if mapping else 'Not ready'}"
            )
        )
        self.known_status_label.config(text=reason)

    def _require_hardware_ready(self) -> bool:
        context = self.get_current_context()
        if not context.get("connected"):
            messagebox.showerror("Arduino Not Connected", "Connect to Arduino before starting a manual tester session.")
            return False
        if self.is_main_app_busy():
            messagebox.showwarning("Main App Busy", "Wait for the current automated test or diagnostic task to finish first.")
            return False
        return True

    def _start_known_game(self):
        if not self._require_hardware_ready():
            return

        context = self.get_current_context()
        chip_data = context.get("chip_data")
        mapping = context.get("mapping")
        board = context.get("board", "MEGA")
        session, reason = self.controller.create_known_game_session(chip_data, mapping, board)
        if session is None:
            self.known_status_label.config(text=reason, fg=Theme.ACCENT_ERROR)
            messagebox.showwarning("Game Mode Unavailable", reason)
            return

        self.known_session = session
        self._known_round_revealed = False
        self.known_status_label.config(text=reason, fg=Theme.ACCENT_SUCCESS)
        self._render_known_round()
        self._set_explanation("Game started. Predict the outputs from the generated truth-table round, then reveal the real hardware result.")
        self._append_history(f"Started game for {session.chip_name} with {len(session.rounds)} rounds.")

    def _render_known_round(self):
        session = self.known_session
        if session is None:
            return

        self.score_label.config(text=f"Score: {session.score}")
        self.streak_label.config(text=f"Streak: {session.streak}")
        self.lives_label.config(text=f"Lives: {session.lives}")
        self.round_label.config(text=f"Round: {session.current_round_index + 1}/{len(session.rounds)}")

        round_data = session.rounds[session.current_round_index]
        self.known_prompt_label.config(text=round_data.prompt)
        self.known_inputs_label.config(
            text="Drive: " + ", ".join(f"{name}={state}" for name, state in round_data.inputs.items())
        )

        for widget in self.known_prediction_frame.winfo_children():
            widget.destroy()
        self.known_guess_vars.clear()
        for index, output_name in enumerate(session.output_order):
            row = tk.Frame(self.known_prediction_frame, bg=Theme.BG_DARK)
            row.grid(row=index, column=0, sticky="w", pady=3)
            tk.Label(
                row, text=output_name, font=self.fonts["body"],
                bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY, width=8, anchor="w"
            ).pack(side=tk.LEFT)
            var = tk.StringVar(value="LOW")
            combo = ttk.Combobox(row, textvariable=var, state="readonly", width=8)
            combo["values"] = ("LOW", "HIGH")
            combo.pack(side=tk.LEFT)
            self.known_guess_vars[output_name] = var

        if session.completed:
            self.known_prompt_label.config(text=f"{session.status_text}: restart the game to play again.")
        self.next_round_button.draw_button(Theme.ACCENT_INFO if self._known_round_revealed and not session.completed else Theme.TEXT_MUTED)

    def _submit_known_guess(self):
        session = self.known_session
        if session is None:
            messagebox.showinfo("Start Game", "Start a known-chip game first.")
            return
        if session.completed:
            messagebox.showinfo("Game Complete", "Restart the game to play again.")
            return
        if self._known_round_revealed:
            messagebox.showinfo("Round Complete", "Click Next Turn to continue.")
            return
        if not self._require_hardware_ready():
            return

        predictions = {
            name: variable.get()
            for name, variable in self.known_guess_vars.items()
        }
        try:
            round_data = self.controller.evaluate_known_round(session, predictions)
        except Exception as exc:
            logger.error(f"Known-chip round failed: {exc}")
            messagebox.showerror("Manual Tester Error", str(exc))
            return
        self._known_round_revealed = True

        correctness_text = "Correct" if round_data.player_correct else "Incorrect"
        hardware_text = "matched" if round_data.hardware_match else "did not match"
        self.known_status_label.config(
            text=f"{correctness_text}. Hardware {hardware_text} the truth table for this turn.",
            fg=Theme.ACCENT_SUCCESS if round_data.player_correct else Theme.ACCENT_ERROR,
        )
        self._set_explanation(
            round_data.explanation
            + "\nExpected: "
            + ", ".join(f"{name}={round_data.expected_outputs[name]}" for name in session.output_order)
            + "\nObserved: "
            + ", ".join(f"{name}={round_data.observed_outputs.get(name, 'ERROR')}" for name in session.output_order)
        )
        self._append_history(
            f"Round {round_data.round_number}: predicted "
            + ", ".join(f"{name}={predictions[name]}" for name in session.output_order)
            + " | expected "
            + ", ".join(f"{name}={round_data.expected_outputs[name]}" for name in session.output_order)
            + " | observed "
            + ", ".join(f"{name}={round_data.observed_outputs.get(name, 'ERROR')}" for name in session.output_order)
        )

        self.score_label.config(text=f"Score: {session.score}")
        self.streak_label.config(text=f"Streak: {session.streak}")
        self.lives_label.config(text=f"Lives: {session.lives}")
        if session.completed:
            self.known_prompt_label.config(text=f"{session.status_text}. Restart to play again.")
        self.next_round_button.draw_button(Theme.ACCENT_INFO if not session.completed else Theme.TEXT_MUTED)

    def _next_known_round(self):
        session = self.known_session
        if session is None or not self._known_round_revealed or session.completed:
            return
        self.controller.advance_known_round(session)
        self._known_round_revealed = False
        self._render_known_round()
        if not session.completed:
            self._set_explanation("New round loaded. Predict the outputs, then reveal the result.")

    def _add_lab_row(self, row_type: str, name: str = "", pin: str = ""):
        container = self.lab_inputs_rows_frame if row_type == "input" else self.lab_outputs_rows_frame
        row = tk.Frame(container, bg=Theme.BG_DARK)
        row.pack(fill=tk.X, pady=3)
        name_entry = tk.Entry(row, width=14, bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY, insertbackground=Theme.TEXT_PRIMARY)
        name_entry.pack(side=tk.LEFT, padx=(0, 8))
        name_entry.insert(0, name)
        pin_entry = tk.Entry(row, width=10, bg=Theme.BG_CARD, fg=Theme.TEXT_PRIMARY, insertbackground=Theme.TEXT_PRIMARY)
        pin_entry.pack(side=tk.LEFT, padx=(0, 8))
        pin_entry.insert(0, pin)
        tk.Label(row, text="Example: 2 or A0", font=self.fonts["small"], bg=Theme.BG_DARK, fg=Theme.TEXT_MUTED).pack(side=tk.LEFT)
        remove_button = ModernButton(
            row, "Remove", lambda row_type=row_type, row_dict=None: self._remove_lab_row(row_type, row_dict),
            width=72, height=24, bg_color=Theme.ACCENT_ERROR
        )
        remove_button.pack(side=tk.RIGHT)

        row_dict = {
            "frame": row,
            "name_entry": name_entry,
            "pin_entry": pin_entry,
            "button": remove_button,
        }
        remove_button.command = lambda row_type=row_type, row_dict=row_dict: self._remove_lab_row(row_type, row_dict)
        row_type_list = self.lab_input_rows if row_type == "input" else self.lab_output_rows
        row_type_list.append(row_dict)

    def _remove_lab_row(self, row_type: str, row_dict: Dict[str, Any]):
        row_dict["frame"].destroy()
        row_type_list = self.lab_input_rows if row_type == "input" else self.lab_output_rows
        if row_dict in row_type_list:
            row_type_list.remove(row_dict)

    def _collect_lab_rows(self, rows: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        return [
            (row["name_entry"].get().strip(), row["pin_entry"].get().strip())
            for row in rows
            if row["name_entry"].winfo_exists()
        ]

    def _start_lab_session(self):
        if not self._require_hardware_ready():
            return

        board = self.controller.get_board_type(self.get_current_context().get("board", "MEGA"))
        session, reason = self.controller.create_manual_lab_session(
            board=board,
            input_rows=self._collect_lab_rows(self.lab_input_rows),
            output_rows=self._collect_lab_rows(self.lab_output_rows),
        )
        if session is None:
            self.lab_status_label.config(text=reason, fg=Theme.ACCENT_ERROR)
            messagebox.showwarning("Invalid Lab Setup", reason)
            return

        self.lab_session = session
        self.lab_status_label.config(text=reason, fg=Theme.ACCENT_SUCCESS)
        self._render_lab_turn_controls()
        self._set_explanation("Manual lab started. Choose input states, then drive the hardware and inspect the observed outputs.")
        self._append_history(f"Started manual lab with {len(session.inputs)} inputs and {len(session.outputs)} outputs.")

    def _render_lab_turn_controls(self):
        for widget in self.lab_turn_controls_frame.winfo_children():
            widget.destroy()
        self.lab_state_vars.clear()

        session = self.lab_session
        if session is None:
            return

        for index, signal in enumerate(session.inputs):
            row = tk.Frame(self.lab_turn_controls_frame, bg=Theme.BG_DARK)
            row.grid(row=index, column=0, sticky="w", pady=2)
            tk.Label(
                row, text=f"{signal.name} (Pin {signal.arduino_pin})",
                font=self.fonts["body"], bg=Theme.BG_DARK, fg=Theme.TEXT_PRIMARY, width=20, anchor="w"
            ).pack(side=tk.LEFT)
            var = tk.StringVar(value="LOW")
            combo = ttk.Combobox(row, textvariable=var, state="readonly", width=8)
            combo["values"] = ("LOW", "HIGH")
            combo.pack(side=tk.LEFT)
            self.lab_state_vars[signal.name] = var

        outputs_text = ", ".join(f"{signal.name}@{signal.arduino_pin}" for signal in session.outputs)
        self.lab_snapshot_label.config(text=f"Outputs to observe: {outputs_text}")

    def _run_lab_turn(self):
        if self.lab_session is None:
            messagebox.showinfo("Start Lab", "Start a manual lab session first.")
            return
        if not self._require_hardware_ready():
            return

        input_states = {
            name: variable.get()
            for name, variable in self.lab_state_vars.items()
        }
        try:
            turn = self.controller.run_manual_turn(self.lab_session, input_states)
        except Exception as exc:
            logger.error(f"Manual lab turn failed: {exc}")
            messagebox.showerror("Manual Tester Error", str(exc))
            return
        self._set_explanation(turn.explanation)
        self.lab_snapshot_label.config(
            text="Observed outputs: " + ", ".join(
                f"{name}={state}" for name, state in turn.observed_outputs.items()
            )
        )
        self._append_history(
            f"Turn {turn.turn_number}: drove "
            + ", ".join(f"{name}={state}" for name, state in turn.driven_inputs.items())
            + " | observed "
            + ", ".join(f"{name}={state}" for name, state in turn.observed_outputs.items())
        )

    def _set_explanation(self, text: str):
        self.explanation_label.config(text=text)

    def _append_history(self, line: str):
        self.history_text.configure(state=tk.NORMAL)
        self.history_text.insert(tk.END, line + "\n")
        self.history_text.see(tk.END)
        self.history_text.configure(state=tk.DISABLED)
